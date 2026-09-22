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
    average = round(
        sum(row.total_score / assignment.total_score * 100 for row in graded_rows) / len(graded_rows), 1
    ) if graded_rows and assignment.total_score else None

    question_rows = db.execute(
        select(Question, AssignmentQuestion.position)
        .join(AssignmentQuestion, AssignmentQuestion.question_id == Question.id)
        .where(AssignmentQuestion.assignment_id == assignment.id)
        .order_by(AssignmentQuestion.position)
    ).all()
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
        rate = round(sum(a.score for a, _ in answers) / (len(answers) * question.score) * 100, 1) if answers and question.score else None
        bindings = db.execute(
            select(QuestionKnowledgePoint, KnowledgePoint)
            .join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id)
            .where(QuestionKnowledgePoint.question_id == question.id)
        ).all()
        errors: dict[str, int] = defaultdict(int)
        for _, analysis in answers:
            if analysis and analysis.error_type:
                errors[analysis.error_type] += 1
        question_stats.append({
            "question_id": question.id,
            "position": position,
            "prompt": question.prompt,
            "submission_count": len(answers),
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
        "average_score": average,
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
    points = db.execute(
        select(KnowledgePoint, StudentMasteryProfile)
        .join(StudentMasteryProfile, StudentMasteryProfile.knowledge_point_id == KnowledgePoint.id)
        .where(StudentMasteryProfile.offering_id == offering_id)
    ).all()
    grouped: dict[int, dict] = defaultdict(lambda: {"profiles": []})
    for point, profile in points:
        grouped[point.id]["point"] = point
        grouped[point.id]["profiles"].append(profile)
    knowledge = []
    for point_id, values in grouped.items():
        profiles = values["profiles"]
        eligible = [p for p in profiles if p.confidence >= 40 and p.observation_count >= 3]
        weak_count = sum(1 for p in eligible if p.mastery_score < 60)
        knowledge.append({
            "id": point_id,
            "code": values["point"].code,
            "name": values["point"].name,
            "evidence_student_count": len(eligible),
            "average_mastery": round(sum(p.mastery_score for p in eligible) / len(eligible), 1) if eligible else None,
            "weak_student_count": weak_count,
            "weak_ratio": round(weak_count / len(eligible), 2) if eligible else 0,
            "is_class_weak": len(eligible) >= 5 and weak_count / len(eligible) >= 0.3,
        })
    knowledge.sort(key=lambda item: (item["average_mastery"] is None, item["average_mastery"] or 0))
    return {"offering_id": offering_id, "student_count": enrollment_count, "knowledge_points": knowledge}
