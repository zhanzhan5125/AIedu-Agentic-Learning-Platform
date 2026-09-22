from __future__ import annotations

from datetime import datetime, timedelta

from app.db import SessionLocal
from app.models import (AgentRun, Answer, Assignment, AssignmentQuestion, AssignmentStatus, Course,
                        CourseOffering, CourseResource, Enrollment, KnowledgePoint, Notification,
                        OfferingStatus, ProcessingStatus, Question, ResourceChunk, Role,
                        ScheduledNotification, Submission, SubmissionStatus, User)
from app.services.learning import profile_view, refresh_student_mastery, upsert_evidence
from app.services.submissions import auto_submit_expired_drafts
from app.worker import deliver_scheduled_notifications, run_local_once


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_and_response_contract(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert set(response.json()) == {"code", "msg", "data", "request_id"}


def test_legacy_md5_is_upgraded_on_login(client, auth):
    token = auth(client, "teacher", "teacher")
    assert token
    with SessionLocal() as db:
        teacher = db.query(User).filter_by(role=Role.teacher, account="teacher").one()
        assert teacher.password_migrated is True
        assert teacher.password_hash.startswith("$argon2")


def test_rbac_and_database_pagination(client, auth):
    teacher = auth(client, "teacher", "teacher")
    denied = client.post("/api/v1/admin/courses", headers=headers(teacher),
                         json={"number": "CS101", "name": "程序设计"})
    assert denied.status_code == 403
    manager = auth(client, "manager", "admin")
    created = client.post("/api/v1/admin/courses", headers=headers(manager),
                          json={"number": "CS101", "name": "程序设计"})
    assert created.status_code == 201
    page = client.get("/api/v1/admin/courses?page=1&page_size=10", headers=headers(manager)).json()["data"]
    assert page["total"] == 1
    assert len(page["records"]) == 1


def test_teacher_can_open_multiple_teaching_sections(client, auth):
    manager_token = auth(client, "manager", "admin")
    teacher_token = auth(client, "teacher", "teacher")
    course_id = client.post(
        "/api/v1/admin/courses",
        headers=headers(manager_token),
        json={"number": "CS110", "name": "教学班测试课程"},
    ).json()["data"]["id"]

    first = client.post(
        "/api/v1/teacher/offerings",
        headers=headers(teacher_token),
        json={"course_id": course_id, "year": 2026, "term": 1,
              "section_code": "01", "section_name": "程序设计一班"},
    )
    second = client.post(
        "/api/v1/teacher/offerings",
        headers=headers(teacher_token),
        json={"course_id": course_id, "year": 2026, "term": 1,
              "section_code": "02", "section_name": "程序设计二班"},
    )
    duplicate = client.post(
        "/api/v1/teacher/offerings",
        headers=headers(teacher_token),
        json={"course_id": course_id, "year": 2026, "term": 1,
              "section_code": "01"},
    )

    assert first.status_code == second.status_code == 201
    assert duplicate.status_code == 409
    records = client.get(
        "/api/v1/teacher/offerings", headers=headers(teacher_token)
    ).json()["data"]["records"]
    assert {(row["section_code"], row["section_name"]) for row in records} == {
        ("01", "程序设计一班"), ("02", "程序设计二班")
    }


def test_student_conversation_history(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS111", name="会话测试课程")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, section_code="01", section_name="教学班01",
                                  status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        db.add(Enrollment(offering_id=offering.id, student_id=student.id))
        offering_id = offering.id

    token = auth(client, "student", "student")
    created = client.post("/api/v1/conversations", headers=headers(token),
                          json={"offering_id": offering_id, "title": "新对话"})
    assert created.status_code == 201
    conversation_id = created.json()["data"]["id"]
    first = client.post(f"/api/v1/conversations/{conversation_id}/messages",
                        headers=headers(token),
                        json={"role": "user", "content": "什么是进程？"})
    second = client.post(f"/api/v1/conversations/{conversation_id}/messages",
                         headers=headers(token),
                         json={"role": "assistant", "content": "进程是运行中的程序。"})
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["title"] == "什么是进程？"
    messages = client.get(f"/api/v1/conversations/{conversation_id}/messages",
                          headers=headers(token)).json()["data"]["records"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    listed = client.get(f"/api/v1/conversations?offering_id={offering_id}",
                        headers=headers(token)).json()["data"]["records"]
    assert listed[0]["id"] == conversation_id


def test_publish_submit_and_ai_job_are_idempotent(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS102", name="数据结构")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        db.add(Enrollment(offering_id=offering.id, student_id=student.id))
        assignment = Assignment(offering_id=offering.id, title="第一次作业")
        question = Question(prompt="1+1=?", reference_answer="2", score=10)
        db.add_all([assignment, question])
        db.flush()
        db.add(AssignmentQuestion(assignment_id=assignment.id, question_id=question.id, position=1))
        assignment_id = assignment.id
    teacher_token = auth(client, "teacher", "teacher")
    start = datetime.now() - timedelta(minutes=1)
    end = datetime.now() + timedelta(days=1)
    payload = {"start_at": start.isoformat(), "end_at": end.isoformat(), "idempotency_key": "publish-key-001"}
    first = client.post(f"/api/v1/assignments/{assignment_id}/publish",
                        headers=headers(teacher_token), json=payload)
    second = client.post(f"/api/v1/assignments/{assignment_id}/publish",
                         headers=headers(teacher_token), json=payload)
    assert first.status_code == second.status_code == 200
    with SessionLocal() as db:
        assert db.query(Submission).filter_by(assignment_id=assignment_id).count() == 1
        notice = db.query(Notification).filter_by(kind="assignment_published").one()
        assert notice.offering_id == assignment.offering_id
        assert db.query(ScheduledNotification).filter_by(
            assignment_id=assignment_id, kind="assignment_deadline"
        ).count() >= 1

    job_payload = {"resource_id": assignment_id, "idempotency_key": "summary-key-001"}
    first_job = client.post("/api/v1/ai/summary-jobs", headers=headers(teacher_token), json=job_payload).json()
    second_job = client.post("/api/v1/ai/summary-jobs", headers=headers(teacher_token), json=job_payload).json()
    assert first_job["data"]["job_id"] == second_job["data"]["job_id"]
    assert run_local_once() == 1
    status = client.get(f"/api/v1/jobs/{first_job['data']['job_id']}", headers=headers(teacher_token)).json()
    assert status["data"]["status"] == "succeeded"
    assert status["data"]["progress"] == 100


def test_saved_snapshot_can_be_edited_and_submit_uses_current_answers(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS103", name="操作系统")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        db.add(Enrollment(offering_id=offering.id, student_id=student.id))
        assignment = Assignment(offering_id=offering.id, title="快照作业")
        question = Question(prompt="进程是什么？", score=10)
        db.add_all([assignment, question])
        db.flush()
        db.add(AssignmentQuestion(assignment_id=assignment.id, question_id=question.id, position=1))
        assignment_id, question_id = assignment.id, question.id

    teacher_token = auth(client, "teacher", "teacher")
    student_token = auth(client, "student", "student")
    client.post(f"/api/v1/assignments/{assignment_id}/publish", headers=headers(teacher_token), json={
        "start_at": (datetime.now() - timedelta(minutes=1)).isoformat(),
        "end_at": (datetime.now() + timedelta(days=1)).isoformat(),
        "idempotency_key": "snapshot-publish-key",
    })
    save_url = f"/api/v1/student/assignments/{assignment_id}/submission"
    first = client.put(save_url, headers=headers(student_token), json={
        "answers": [{"question_id": question_id, "content": "保存版本"}]
    })
    second = client.put(save_url, headers=headers(student_token), json={
        "answers": [{"question_id": question_id, "content": "再次保存版本"}]
    })
    assert first.status_code == second.status_code == 200

    submitted = client.post(f"/api/v1/student/assignments/{assignment_id}/submit",
                            headers=headers(student_token), json={
        "answers": [{"question_id": question_id, "content": "页面当前版本"}]
    })
    assert submitted.status_code == 200
    with SessionLocal() as db:
        submission = db.query(Submission).filter_by(assignment_id=assignment_id).one()
        answer = db.query(Answer).filter_by(submission_id=submission.id).one()
        assert submission.status == SubmissionStatus.submitted
        assert answer.content == "页面当前版本"
        first_submitted_at = submission.submitted_at

    # 截止前提交后仍可保存新快照；再次提交时覆盖答案并记录最后一次提交时间。
    reopened = client.put(save_url, headers=headers(student_token), json={
        "answers": [{"question_id": question_id, "content": "提交后再次保存"}]
    })
    assert reopened.status_code == 200
    assert reopened.json()["data"]["status"] == "draft"
    resubmitted = client.post(f"/api/v1/student/assignments/{assignment_id}/submit",
                              headers=headers(student_token), json={
        "answers": [{"question_id": question_id, "content": "最后提交版本"}]
    })
    assert resubmitted.status_code == 200
    with SessionLocal() as db:
        submission = db.query(Submission).filter_by(assignment_id=assignment_id).one()
        answer = db.query(Answer).filter_by(submission_id=submission.id).one()
        assert submission.status == SubmissionStatus.submitted
        assert submission.submitted_at >= first_submitted_at
        assert answer.content == "最后提交版本"


def test_student_assignment_detail_hides_answers_until_grade_confirmed(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS104", name="作业详情契约")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        db.add(Enrollment(offering_id=offering.id, student_id=student.id))
        assignment = Assignment(offering_id=offering.id, title="详情作业",
                                status=AssignmentStatus.open,
                                start_at=datetime.now() - timedelta(minutes=1),
                                end_at=datetime.now() + timedelta(days=1), total_score=10)
        question = Question(prompt="2+2=?", reference_answer="4", score=10)
        db.add_all([assignment, question])
        db.flush()
        db.add(AssignmentQuestion(assignment_id=assignment.id, question_id=question.id, position=1))
        submission = Submission(assignment_id=assignment.id, student_id=student.id,
                                status=SubmissionStatus.submitted)
        db.add(submission)
        db.flush()
        answer = Answer(submission_id=submission.id, question_id=question.id, content="4")
        db.add(answer)
        assignment_id = assignment.id

    token = auth(client, "student", "student")
    before = client.get(f"/api/v1/student/assignments/{assignment_id}",
                        headers=headers(token))
    assert before.status_code == 200
    assert before.json()["data"]["questions"][0]["reference_answer"] is None
    assert before.json()["data"]["submission"]["total_score"] is None

    with SessionLocal.begin() as db:
        submission = db.query(Submission).filter_by(assignment_id=assignment_id).one()
        submission.status = SubmissionStatus.graded
        submission.total_score = 10
        submission.graded_at = datetime.now()
        answer = db.query(Answer).filter_by(submission_id=submission.id).one()
        answer.score = 10
        answer.ai_comment = "计算正确"
        answer.teacher_comment = "很好"

    after = client.get(f"/api/v1/student/assignments/{assignment_id}",
                       headers=headers(token)).json()["data"]
    assert after["result_visible"] is True
    assert after["submission"]["total_score"] == 10
    assert after["questions"][0]["reference_answer"] == "4"
    assert after["questions"][0]["teacher_comment"] == "很好"


def test_expired_saved_snapshot_is_auto_submitted(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS104", name="计算机网络")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        assignment = Assignment(
            offering_id=offering.id,
            title="自动提交作业",
            start_at=datetime.now() - timedelta(days=1),
            end_at=datetime.now() - timedelta(seconds=1),
        )
        db.add(assignment)
        db.flush()
        submission = Submission(assignment_id=assignment.id, student_id=student.id,
                                status=SubmissionStatus.draft)
        db.add(submission)
        db.flush()
        submission_id = submission.id

    with SessionLocal() as db:
        assert auto_submit_expired_drafts(db) == 1
        submission = db.get(Submission, submission_id)
        assert submission.status == SubmissionStatus.submitted
        assert submission.submitted_at is not None


def test_teacher_submission_counts_and_manual_grading_time(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        second_student = User(
            role=Role.student, account="student2", display_name="学生二",
            password_hash=student.password_hash,
        )
        course = Course(number="CS105", name="操作系统")
        db.add_all([second_student, course])
        db.flush()
        offering = CourseOffering(
            course_id=course.id, teacher_id=teacher.id, year=2026, term=1,
            status=OfferingStatus.active,
        )
        db.add(offering)
        db.flush()
        db.add_all([
            Enrollment(offering_id=offering.id, student_id=student.id),
            Enrollment(offering_id=offering.id, student_id=second_student.id),
        ])
        assignment = Assignment(
            offering_id=offering.id, title="状态统计作业",
            start_at=datetime.now() - timedelta(hours=1),
            end_at=datetime.now() + timedelta(hours=1),
        )
        question = Question(prompt="什么是进程？", score=10)
        db.add_all([assignment, question])
        db.flush()
        db.add(AssignmentQuestion(
            assignment_id=assignment.id, question_id=question.id, position=1,
        ))
        submission = Submission(
            assignment_id=assignment.id, student_id=student.id,
            status=SubmissionStatus.submitted, submitted_at=datetime.now(),
        )
        db.add(submission)
        db.flush()
        answer = Answer(
            submission_id=submission.id, question_id=question.id, content="运行中的程序",
        )
        db.add(answer)
        db.flush()
        offering_id, assignment_id = offering.id, assignment.id
        submission_id, answer_id = submission.id, answer.id

    teacher_token = auth(client, "teacher", "teacher")
    assignment_page = client.get(
        f"/api/v1/teacher/assignments?offering_id={offering_id}",
        headers=headers(teacher_token),
    )
    record = assignment_page.json()["data"]["records"][0]
    assert record["assigned_count"] == 2
    assert record["submitted_count"] == 1
    assert record["not_submitted_count"] == 1
    assert record["pending_grading_count"] == 1

    ai_job = client.post(
        "/api/v1/ai/grading-jobs",
        headers=headers(teacher_token),
        json={"resource_id": submission_id, "idempotency_key": "grade-status-key-001"},
    )
    assert ai_job.status_code == 202
    with SessionLocal() as db:
        assert db.get(Submission, submission_id).status == SubmissionStatus.ai_grading
    assert run_local_once() == 1
    with SessionLocal() as db:
        ai_submission = db.get(Submission, submission_id)
        assert ai_submission.status == SubmissionStatus.needs_review
        assert ai_submission.ai_graded_at is not None

    graded = client.post(
        f"/api/v1/teacher/submissions/{submission_id}/grade",
        headers=headers(teacher_token),
        json={"items": [{"answer_id": answer_id, "score": 8, "comment": "基本正确"}]},
    )
    assert graded.status_code == 200

    submissions = client.get(
        f"/api/v1/teacher/assignments/{assignment_id}/submissions",
        headers=headers(teacher_token),
    ).json()["data"]
    assert submissions["graded_count"] == 1
    assert submissions["pending_grading_count"] == 0
    assert submissions["records"][0]["grading_source"] == "ai_assisted"
    assert submissions["records"][0]["graded_at"] is not None


def test_mastery_requires_three_confident_observations(client):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS201", name="掌握度测试")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        point = KnowledgePoint(course_id=course.id, code="KP-1", name="递归")
        db.add(point)
        db.flush()
        for source_id, score in enumerate((30, 50, 40), 1):
            upsert_evidence(db, student_id=student.id, offering_id=offering.id,
                            knowledge_point_id=point.id, source_type="assignment",
                            source_id=source_id, score=score, confidence=90)
        refresh_student_mastery(db, student.id, offering.id)
        view = profile_view(db, student.id, offering.id)
        assert view["knowledge_points"][0]["state"] == "weak"
        assert view["knowledge_points"][0]["observation_count"] == 3


def test_tutor_blocks_direct_answer_for_open_assignment(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS202", name="防抄测试")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        db.add(Enrollment(offering_id=offering.id, student_id=student.id))
        assignment = Assignment(offering_id=offering.id, title="开放作业",
                                status=AssignmentStatus.open,
                                start_at=datetime.now() - timedelta(hours=1),
                                end_at=datetime.now() + timedelta(hours=1), total_score=10)
        question = Question(prompt="请解释快速排序的分区过程", reference_answer="使用枢轴分区", score=10)
        db.add_all([assignment, question])
        db.flush()
        db.add(AssignmentQuestion(assignment_id=assignment.id, question_id=question.id, position=1))
        offering_id = offering.id
    token = auth(client, "student", "student")
    conversation_id = client.post("/api/v1/conversations", headers=headers(token),
                                  json={"offering_id": offering_id, "title": "作业辅导"}).json()["data"]["id"]
    response = client.post(f"/api/v1/conversations/{conversation_id}/ask", headers=headers(token),
                           json={"content": "请解释快速排序的分区过程",
                                 "idempotency_key": "tutor-guard-001", "hint_level": 0})
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["policy_mode"] == "guided"
    assert "不能直接给出答案" in data["answer"]
    assert data["matched_assignment_id"] is not None


def test_agent_draft_is_traceable_and_idempotent(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        course = Course(number="CS203", name="出题测试")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        offering_id = offering.id
    token = auth(client, "teacher", "teacher")
    payload = {"keywords": ["二叉树"], "question_count": 3, "difficulty": 2,
               "question_kinds": ["short_answer"], "idempotency_key": "draft-agent-001"}
    first = client.post(f"/api/v1/teacher/offerings/{offering_id}/assignment-drafts",
                        headers=headers(token), json=payload)
    second = client.post(f"/api/v1/teacher/offerings/{offering_id}/assignment-drafts",
                         headers=headers(token), json=payload)
    assert first.status_code == second.status_code == 202
    assert first.json()["data"]["job_id"] == second.json()["data"]["job_id"]
    assert run_local_once() == 1
    run_id = first.json()["data"]["agent_run_id"]
    run = client.get(f"/api/v1/agent-runs/{run_id}", headers=headers(token)).json()["data"]
    steps = client.get(f"/api/v1/agent-runs/{run_id}/steps", headers=headers(token)).json()["data"]
    assert run["status"] == "succeeded"
    assert len(run["result"]["questions"]) == 3
    with SessionLocal() as db:
        draft = db.get(Assignment, run["result"]["assignment_id"])
        assert draft.status == AssignmentStatus.draft
        assert draft.origin == "agent"
    assert [step["node_name"] for step in steps] == [
        "prepare_context", "make_plan", "execute_tools", "compose_result",
        "validate_result", "reflect_once", "finalize",
    ]
    assert run["agent_name"] == "teacher_assessment_agent"
    assert len(run["plan"]["steps"]) <= 4
    assert run["reflection_count"] <= 1
    with SessionLocal() as db:
        child = db.query(AgentRun).filter_by(parent_run_id=run_id).one()
        assert child.agent_name == "teacher_course_assistant"
        assert child.task_type == "course_context_brief"


def test_personalized_tutor_delegates_only_to_learning_agent(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS208", name="个性化问答测试")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        db.add(Enrollment(offering_id=offering.id, student_id=student.id))
        db.add(KnowledgePoint(course_id=course.id, code="KP-P", name="动态规划"))
        offering_id = offering.id
    token = auth(client, "student", "student")
    conversation_id = client.post("/api/v1/conversations", headers=headers(token),
                                  json={"offering_id": offering_id, "title": "个性化"}).json()["data"]["id"]
    response = client.post(f"/api/v1/conversations/{conversation_id}/ask", headers=headers(token),
                           json={"content": "结合我的情况，我应该如何复习？",
                                 "idempotency_key": "personal-tutor-001", "hint_level": 0})
    assert response.status_code == 201
    data = response.json()["data"]
    with SessionLocal() as db:
        parent = db.get(AgentRun, data["agent_run_id"])
        child = db.query(AgentRun).filter_by(parent_run_id=parent.id).one()
        assert parent.agent_name == "student_qa_agent"
        assert child.agent_name == "student_learning_assistant"
        assert child.result["insufficient_points"] == ["动态规划"]


def test_course_map_draft_has_evidence_and_requires_publish(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        course = Course(number="CS209", name="课程路线测试")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        resource = CourseResource(
            offering_id=offering.id, uploader_id=teacher.id, title="算法课件",
            original_name="algorithms.pdf", object_key="tests/course-map/algorithms.pdf",
            mime_type="application/pdf", size=100, sha256="a" * 64,
            processing_status=ProcessingStatus.ready, chunk_count=2,
        )
        db.add(resource)
        db.flush()
        db.add_all([
            ResourceChunk(resource_id=resource.id, offering_id=offering.id, position=0,
                          block_type="heading", heading_path="第一章 > 排序",
                          page_number=1, text="排序算法概述", token_count=8, content_hash="b" * 64),
            ResourceChunk(resource_id=resource.id, offering_id=offering.id, position=1,
                          block_type="paragraph", heading_path="第二章 > 查找",
                          page_number=2, text="二分查找的前提与过程", token_count=12, content_hash="c" * 64),
        ])
        offering_id, resource_id = offering.id, resource.id
    token = auth(client, "teacher", "teacher")
    created = client.post(f"/api/v1/teacher/offerings/{offering_id}/course-map-drafts",
                          headers=headers(token), json={"resource_ids": [resource_id],
                                                       "idempotency_key": "course-map-test-001"})
    assert created.status_code == 202
    assert run_local_once() == 1
    course_map = client.get(f"/api/v1/offerings/{offering_id}/course-map",
                            headers=headers(token)).json()["data"]
    assert course_map["status"] == "draft"
    assert len(course_map["nodes"]) == 2
    assert course_map["nodes"][0]["evidence"][0]["page_number"] == 1
    published = client.post(f"/api/v1/teacher/course-map-versions/{course_map['id']}/publish",
                            headers=headers(token))
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "published"


def test_student_cannot_broadcast_but_can_contact_course_teacher(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS204", name="消息测试")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        db.add(Enrollment(offering_id=offering.id, student_id=student.id))
        offering_id, teacher_id = offering.id, teacher.id
    student_token = auth(client, "student", "student")
    teacher_token = auth(client, "teacher", "teacher")
    contacts = client.get(f"/api/v1/messages/offerings/{offering_id}/contacts",
                          headers=headers(student_token)).json()["data"]
    assert contacts == [{"id": teacher_id, "name": "教师", "account": "teacher",
                         "role": "teacher"}]
    denied = client.post(f"/api/v1/messages/offerings/{offering_id}/announcements",
                         headers=headers(student_token), json={"title": "全体", "body": "消息"})
    assert denied.status_code == 403
    direct = client.post("/api/v1/messages/direct-threads", headers=headers(student_token),
                         json={"offering_id": offering_id, "recipient_id": teacher_id})
    assert direct.status_code == 201
    thread_id = direct.json()["data"]["id"]
    sent = client.post(f"/api/v1/messages/threads/{thread_id}", headers=headers(student_token),
                       json={"body": "老师您好"})
    assert sent.status_code == 201
    teacher_unread = client.get(
        f"/api/v1/messages/unread-summary?offering_id={offering_id}",
        headers=headers(teacher_token),
    ).json()["data"]
    assert teacher_unread == {"message_unread": 1, "notification_unread": 0, "total": 1}
    listed = client.get(f"/api/v1/messages/threads?offering_id={offering_id}",
                        headers=headers(student_token)).json()["data"]["records"]
    assert listed[0]["title"] == "教师"
    teacher_threads = client.get(f"/api/v1/messages/threads?offering_id={offering_id}",
                                 headers=headers(teacher_token)).json()["data"]["records"]
    assert teacher_threads[0]["title"] == "学生"
    reply = client.post(f"/api/v1/messages/threads/{thread_id}", headers=headers(teacher_token),
                        json={"body": "你好，有什么问题？"})
    assert reply.status_code == 201
    student_unread = client.get(
        "/api/v1/messages/unread-summary", headers=headers(student_token)
    ).json()["data"]
    assert student_unread["message_unread"] == 1
    assert student_unread["total"] == 1
    messages = client.get(f"/api/v1/messages/threads/{thread_id}",
                          headers=headers(student_token)).json()["data"]["records"]
    assert [item["body"] for item in messages] == ["老师您好", "你好，有什么问题？"]
    client.put(f"/api/v1/messages/threads/{thread_id}/read", headers=headers(student_token))
    after_read = client.get(
        "/api/v1/messages/unread-summary", headers=headers(student_token)
    ).json()["data"]
    assert after_read["total"] == 0


def test_course_notifications_are_scoped_but_home_notifications_are_aggregated(client, auth):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        first_course = Course(number="CS205", name="消息课程一")
        second_course = Course(number="CS206", name="消息课程二")
        db.add_all([first_course, second_course])
        db.flush()
        first = CourseOffering(course_id=first_course.id, teacher_id=teacher.id, year=2026,
                               term=1, status=OfferingStatus.active)
        second = CourseOffering(course_id=second_course.id, teacher_id=teacher.id, year=2026,
                                term=1, status=OfferingStatus.active)
        db.add_all([first, second])
        db.flush()
        db.add_all([
            Enrollment(offering_id=first.id, student_id=student.id),
            Enrollment(offering_id=second.id, student_id=student.id),
            Notification(user_id=student.id, offering_id=first.id, kind="system",
                         title="课程一通知", body="第一门课程"),
            Notification(user_id=student.id, offering_id=second.id, kind="system",
                         title="课程二通知", body="第二门课程"),
        ])
        first_id = first.id

    token = auth(client, "student", "student")
    scoped = client.get(f"/api/v1/notifications?offering_id={first_id}&page_size=100",
                        headers=headers(token)).json()["data"]
    aggregate = client.get("/api/v1/notifications?page_size=100",
                           headers=headers(token)).json()["data"]
    assert [item["title"] for item in scoped["records"]] == ["课程一通知"]
    assert {item["title"] for item in aggregate["records"]} == {"课程一通知", "课程二通知"}


def test_due_assignment_reminder_is_delivered_once_to_unsubmitted_students(client):
    with SessionLocal.begin() as db:
        teacher = db.query(User).filter_by(role=Role.teacher).one()
        student = db.query(User).filter_by(role=Role.student).one()
        course = Course(number="CS207", name="截止提醒测试")
        db.add(course)
        db.flush()
        offering = CourseOffering(course_id=course.id, teacher_id=teacher.id, year=2026,
                                  term=1, status=OfferingStatus.active)
        db.add(offering)
        db.flush()
        db.add(Enrollment(offering_id=offering.id, student_id=student.id))
        assignment = Assignment(offering_id=offering.id, title="定时作业",
                                status=AssignmentStatus.open,
                                start_at=datetime.now() - timedelta(hours=1),
                                end_at=datetime.now() + timedelta(hours=2))
        db.add(assignment)
        db.flush()
        db.add(Submission(assignment_id=assignment.id, student_id=student.id,
                          status=SubmissionStatus.not_started))
        db.add(ScheduledNotification(
            offering_id=offering.id, assignment_id=assignment.id,
            kind="assignment_deadline", scheduled_at=datetime.now() - timedelta(seconds=1),
            dedup_key=f"assignment:{assignment.id}:deadline:test",
            payload={"hours": 2, "title": assignment.title},
        ))
        offering_id = offering.id

    assert deliver_scheduled_notifications() == 1
    assert deliver_scheduled_notifications() == 0
    with SessionLocal() as db:
        notices = db.query(Notification).all()
        assert len(notices) == 1
        assert notices[0].offering_id == offering_id
        assert notices[0].title == "作业截止提醒"
