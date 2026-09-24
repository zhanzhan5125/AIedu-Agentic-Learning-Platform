from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Answer,
    AnswerAnalysis,
    Assignment,
    AssignmentQuestion,
    Enrollment,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    StudentMasteryProfile,
    Submission,
    SubmissionStatus,
)
from app.services.learning import course_knowledge_catalog

FINAL_STATUSES = (SubmissionStatus.graded, SubmissionStatus.returned)


def assignment_insights(db: Session, assignment: Assignment) -> dict:
    assigned = db.scalar(select(func.count(Enrollment.id)).where(
        Enrollment.offering_id == assignment.offering_id)) or 0
    submitted = db.scalar(select(func.count(Submission.id)).where(
        Submission.assignment_id == assignment.id,
        Submission.status.notin_([SubmissionStatus.not_started, SubmissionStatus.draft]),
    )) or 0
    graded_rows = db.scalars(select(Submission).where(
        Submission.assignment_id == assignment.id,
        Submission.status.in_(FINAL_STATUSES),
    )).all()
    question_rows = db.execute(
        select(Question, AssignmentQuestion.position)
        .join(AssignmentQuestion, AssignmentQuestion.question_id == Question.id)
        .where(AssignmentQuestion.assignment_id == assignment.id)
        .order_by(AssignmentQuestion.position)
    ).all()
    total_score = assignment.total_score or sum(question.score for question, _ in question_rows)
    final_scores = [row.total_score for row in graded_rows if row.total_score is not None]
    average = round(sum(final_scores) / len(final_scores), 1) if final_scores else None
    average_rate = round(average / total_score * 100, 1) if (
        average is not None and total_score
    ) else None
    question_stats = []
    point_losses: dict[int, dict] = defaultdict(lambda: {"loss": 0.0, "weight": 0.0, "errors": defaultdict(int)})
    for question, position in question_rows:
        answers = db.execute(
            select(Answer, AnswerAnalysis)
            .join(Submission, Submission.id == Answer.submission_id)
            .outerjoin(AnswerAnalysis, AnswerAnalysis.answer_id == Answer.id)
            .where(
                Submission.assignment_id == assignment.id,
                Submission.status.in_(FINAL_STATUSES),
                Answer.question_id == question.id,
            )
        ).all()
        scores = [answer.score for answer, _ in answers if answer.score is not None]
        question_average = round(sum(scores) / len(scores), 1) if scores else None
        rate = round(question_average / question.score * 100, 1) if (
            question_average is not None and question.score
        ) else None
        bindings = db.execute(
            select(QuestionKnowledgePoint, KnowledgePoint)
            .join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id)
            .where(QuestionKnowledgePoint.question_id == question.id)
        ).all()
        errors: dict[str, int] = defaultdict(int)
        for answer, analysis in answers:
            error_type = (analysis.error_type if analysis and analysis.error_type else
                          (answer.ai_raw or {}).get("error_type"))
            if error_type:
                errors[str(error_type)] += 1
        question_stats.append({
            "question_id": question.id,
            "position": position,
            "prompt": question.prompt,
            "submission_count": len(answers),
            "max_score": question.score,
            "average_score": question_average,
            "highest_score": max(scores) if scores else None,
            "lowest_score": min(scores) if scores else None,
            "score_rate": rate,
            "is_error_prone": len(answers) >= 5 and rate is not None and rate < 60,
            "knowledge_points": [{"id": kp.id, "name": kp.name, "weight": link.weight} for link, kp in bindings],
            "error_types": dict(errors),
        })
        if rate is not None:
            for link, kp in bindings:
                point_losses[kp.id]["name"] = kp.name
                point_losses[kp.id]["loss"] += (100 - rate) * link.weight
                point_losses[kp.id]["weight"] += link.weight
                for name, count in errors.items():
                    point_losses[kp.id]["errors"][name] += count
    weak_points = [{
        "knowledge_point_id": point_id,
        "name": values.get("name"),
        "loss_rate": round(values["loss"] / values["weight"], 1) if values["weight"] else 0,
        "error_types": dict(values["errors"]),
    } for point_id, values in point_losses.items()]
    weak_points.sort(key=lambda item: item["loss_rate"], reverse=True)
    return {
        "assignment_id": assignment.id,
        "total_score": total_score,
        "average_score": average,
        "average_rate": average_rate,
        "highest_score": max(final_scores) if final_scores else None,
        "lowest_score": min(final_scores) if final_scores else None,
        "assigned_count": assigned,
        "submitted_count": submitted,
        "submission_rate": round(submitted / assigned * 100, 1) if assigned else 0,
        "graded_count": len(graded_rows),
        "questions": question_stats,
        "weak_knowledge_points": weak_points,
    }


def class_insights(db: Session, offering_id: int) -> dict:
    enrollment_count = db.scalar(select(func.count(Enrollment.id)).where(
        Enrollment.offering_id == offering_id)) or 0
    profiles = db.scalars(select(StudentMasteryProfile).where(
        StudentMasteryProfile.offering_id == offering_id
    )).all()
    grouped: dict[int, list[StudentMasteryProfile]] = defaultdict(list)
    for profile in profiles:
        grouped[profile.knowledge_point_id].append(profile)
    knowledge = []
    for catalog_item in course_knowledge_catalog(db, offering_id):
        point = catalog_item["point"]
        eligible = [p for p in grouped.get(point.id, [])
                    if p.confidence > 0 and p.observation_count > 0]
        weak_count = sum(1 for p in eligible if p.mastery_score < 60)
        knowledge.append({
            "id": point.id,
            "code": catalog_item["display_code"],
            "storage_code": point.code,
            "name": point.name,
            "chapter_id": catalog_item["chapter_id"],
            "chapter_name": catalog_item["chapter_name"],
            "evidence_student_count": len(eligible),
            "average_mastery": round(sum(p.mastery_score for p in eligible) / len(eligible), 1) if eligible else None,
            "weak_student_count": weak_count,
            "weak_ratio": round(weak_count / len(eligible), 2) if eligible else 0,
            "is_class_weak": len(eligible) >= 5 and weak_count / len(eligible) >= 0.3,
            "sample_status": "none" if not eligible else "limited" if len(eligible) < 5 else "sufficient",
        })
    return {"offering_id": offering_id, "student_count": enrollment_count, "knowledge_points": knowledge}
