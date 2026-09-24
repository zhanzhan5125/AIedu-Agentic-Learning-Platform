from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from math import exp

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Answer,
    Assignment,
    AssignmentQuestion,
    ChatMessage,
    ClassMasterySnapshot,
    Conversation,
    CourseMapEdge,
    CourseMapNode,
    CourseMapVersion,
    CourseOffering,
    Enrollment,
    KnowledgePoint,
    LearningEvidence,
    MessageRole,
    PracticeSession,
    Question,
    Submission,
    StudentMasteryProfile,
)

SOURCE_WEIGHTS = {"assignment": 70, "practice": 30}


def course_knowledge_catalog(db: Session, offering_id: int) -> list[dict]:
    """Return current leaf knowledge points in course-map order with display numbering."""
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        return []
    all_points = db.scalars(select(KnowledgePoint).where(
        KnowledgePoint.course_id == offering.course_id
    ).order_by(KnowledgePoint.code, KnowledgePoint.id)).all()
    point_by_id = {point.id: point for point in all_points}
    published_map = db.scalar(select(CourseMapVersion).where(
        CourseMapVersion.offering_id == offering_id,
        CourseMapVersion.status == "published",
    ).order_by(CourseMapVersion.version.desc()))
    catalog: list[dict] = []
    if published_map:
        map_nodes = db.scalars(select(CourseMapNode).where(
            CourseMapNode.version_id == published_map.id
        ).order_by(CourseMapNode.position, CourseMapNode.id)).all()
        node_by_id = {node.id: node for node in map_nodes}
        contains_edges = db.scalars(select(CourseMapEdge).where(
            CourseMapEdge.version_id == published_map.id,
            CourseMapEdge.relation_type == "contains",
        )).all()
        parent_node_ids = {edge.source_node_id for edge in contains_edges}
        parent_by_child = {edge.target_node_id: edge.source_node_id for edge in contains_edges}
        chapter_nodes = [node for node in map_nodes if node.id in parent_node_ids]
        chapter_number = {node.id: index for index, node in enumerate(chapter_nodes, 1)}
        point_number_by_chapter: dict[int, int] = defaultdict(int)
        seen_point_ids: set[int] = set()
        for node in map_nodes:
            if node.id in parent_node_ids or not node.knowledge_point_id:
                continue
            point = point_by_id.get(node.knowledge_point_id)
            if point is None or point.id in seen_point_ids:
                continue
            parent_node = node_by_id.get(parent_by_child.get(node.id))
            parent_number = chapter_number.get(parent_node.id) if parent_node else None
            if parent_number is not None:
                point_number_by_chapter[parent_node.id] += 1
                display_code = f"{parent_number}-{point_number_by_chapter[parent_node.id]}"
            else:
                display_code = point.code
            catalog.append({
                "point": point,
                "display_code": display_code,
                "chapter_id": parent_node.knowledge_point_id if parent_node else point.parent_id,
                "chapter_name": parent_node.name if parent_node else (
                    point_by_id[point.parent_id].name if point.parent_id in point_by_id else None
                ),
            })
            seen_point_ids.add(point.id)
        return catalog

    chapter_ids = {point.parent_id for point in all_points if point.parent_id is not None}
    chapter_points = [point for point in all_points if point.id in chapter_ids]
    chapter_number = {point.id: index for index, point in enumerate(chapter_points, 1)}
    point_number_by_chapter: dict[int, int] = defaultdict(int)
    for point in all_points:
        if point.id in chapter_ids:
            continue
        parent = point_by_id.get(point.parent_id)
        parent_number = chapter_number.get(point.parent_id)
        if parent_number is not None:
            point_number_by_chapter[point.parent_id] += 1
            display_code = f"{parent_number}-{point_number_by_chapter[point.parent_id]}"
        else:
            display_code = point.code
        catalog.append({
            "point": point,
            "display_code": display_code,
            "chapter_id": parent.id if parent else None,
            "chapter_name": parent.name if parent else None,
        })
    return catalog


def _mastery_values(evidence_rows: list[LearningEvidence], now: datetime | None = None) -> tuple[int, int]:
    now = now or datetime.now()
    source_scores: dict[str, float] = {}
    for source_type in SOURCE_WEIGHTS:
        source_rows = [item for item in evidence_rows if item.source_type == source_type]
        weighted_sum = 0.0
        total_weight = 0.0
        for item in source_rows:
            age_days = max(0.0, (now - item.observed_at).total_seconds() / 86400)
            time_decay = exp(-age_days / 120.0)
            effective_weight = (item.confidence / 100.0) * time_decay
            weighted_sum += item.score * effective_weight
            total_weight += effective_weight
        if total_weight:
            source_scores[source_type] = weighted_sum / total_weight
    available_weight = sum(SOURCE_WEIGHTS[source] for source in source_scores)
    score = round(sum(source_scores[source] * SOURCE_WEIGHTS[source]
                      for source in source_scores) / available_weight) if available_weight else 0
    confidence = min(100, round(sum(item.confidence for item in evidence_rows) / len(evidence_rows))) \
        if evidence_rows else 0
    return score, confidence


def upsert_evidence(
    db: Session,
    *,
    student_id: int,
    offering_id: int,
    knowledge_point_id: int,
    source_type: str,
    source_id: int,
    score: int,
    confidence: int,
    agent_run_id: int | None = None,
    observed_at: datetime | None = None,
) -> LearningEvidence:
    evidence = db.scalar(select(LearningEvidence).where(
        LearningEvidence.student_id == student_id,
        LearningEvidence.knowledge_point_id == knowledge_point_id,
        LearningEvidence.source_type == source_type,
        LearningEvidence.source_id == source_id,
    ))
    values = {
        "offering_id": offering_id,
        "score": max(0, min(100, score)),
        "weight": SOURCE_WEIGHTS.get(source_type, 0),
        "confidence": max(0, min(100, confidence)),
        "observed_at": observed_at or datetime.now(),
        "agent_run_id": agent_run_id,
    }
    if evidence is None:
        evidence = LearningEvidence(
            student_id=student_id,
            knowledge_point_id=knowledge_point_id,
            source_type=source_type,
            source_id=source_id,
            **values,
        )
        db.add(evidence)
    else:
        for key, value in values.items():
            setattr(evidence, key, value)
    return evidence


def refresh_student_mastery(db: Session, student_id: int, offering_id: int) -> list[StudentMasteryProfile]:
    db.flush()
    now = datetime.now()
    rows = db.scalars(select(LearningEvidence).where(
        LearningEvidence.student_id == student_id,
        LearningEvidence.offering_id == offering_id,
        LearningEvidence.source_type.in_(tuple(SOURCE_WEIGHTS)),
        LearningEvidence.confidence > 0,
    )).all()
    grouped: dict[int, list[LearningEvidence]] = defaultdict(list)
    for row in rows:
        grouped[row.knowledge_point_id].append(row)

    profiles: list[StudentMasteryProfile] = []
    for knowledge_id, evidence_rows in grouped.items():
        score, confidence = _mastery_values(evidence_rows, now)
        existing = db.scalar(select(StudentMasteryProfile).where(
            StudentMasteryProfile.student_id == student_id,
            StudentMasteryProfile.offering_id == offering_id,
            StudentMasteryProfile.knowledge_point_id == knowledge_id,
        ))
        previous = existing.mastery_score if existing else score
        trend = "up" if score >= previous + 5 else "down" if score <= previous - 5 else "stable"
        values = {
            "mastery_score": score,
            "confidence": confidence,
            "observation_count": len(evidence_rows),
            "trend": trend,
            "last_observed_at": max(item.observed_at for item in evidence_rows),
        }
        if existing is None:
            existing = StudentMasteryProfile(
                student_id=student_id,
                offering_id=offering_id,
                knowledge_point_id=knowledge_id,
                **values,
            )
            db.add(existing)
        else:
            for key, value in values.items():
                setattr(existing, key, value)
            existing.version += 1
        profiles.append(existing)
    stale_profiles = delete(StudentMasteryProfile).where(
        StudentMasteryProfile.student_id == student_id,
        StudentMasteryProfile.offering_id == offering_id,
    )
    if grouped:
        stale_profiles = stale_profiles.where(
            StudentMasteryProfile.knowledge_point_id.notin_(set(grouped))
        )
    db.execute(stale_profiles)
    db.flush()
    return profiles


def refresh_class_mastery(db: Session, offering_id: int) -> list[ClassMasterySnapshot]:
    db.flush()
    rows = db.execute(
        select(StudentMasteryProfile, KnowledgePoint)
        .join(KnowledgePoint, KnowledgePoint.id == StudentMasteryProfile.knowledge_point_id)
        .where(StudentMasteryProfile.offering_id == offering_id)
    ).all()
    grouped: dict[int, list[StudentMasteryProfile]] = defaultdict(list)
    for profile, _ in rows:
        grouped[profile.knowledge_point_id].append(profile)
    snapshots = []
    now = datetime.now()
    for knowledge_id, profiles in grouped.items():
        eligible = [p for p in profiles if p.confidence > 0 and p.observation_count > 0]
        snapshot = ClassMasterySnapshot(
            offering_id=offering_id,
            knowledge_point_id=knowledge_id,
            weak_student_count=sum(1 for p in eligible if p.mastery_score < 60),
            student_count=len(eligible),
            average_mastery=round(sum(p.mastery_score for p in eligible) / len(eligible)) if eligible else 0,
            snapshot_at=now,
        )
        db.add(snapshot)
        snapshots.append(snapshot)
    return snapshots


def student_activity(db: Session, student_id: int, offering_id: int) -> dict:
    since = datetime.now() - timedelta(days=30)
    messages = db.scalars(
        select(ChatMessage)
        .join(Conversation, Conversation.id == ChatMessage.conversation_id)
        .where(
            Conversation.user_id == student_id,
            Conversation.offering_id == offering_id,
            ChatMessage.role == MessageRole.user,
            ChatMessage.created_at >= since,
        )
    ).all()
    active_days = len({row.created_at.date() for row in messages})
    meaningful = sum(1 for row in messages if row.content and len(row.content.strip()) >= 8)
    followups = max(0, meaningful - 1)
    resource_actions = 0
    score = round(
        min(active_days / 10, 1) * 40
        + min(meaningful / 10, 1) * 30
        + min(followups / 5, 1) * 20
        + min(resource_actions / 5, 1) * 10
    )
    return {
        "score": score,
        "active_days": active_days,
        "meaningful_questions": meaningful,
        "followups": followups,
        "resource_actions": resource_actions,
    }


def profile_view(db: Session, student_id: int, offering_id: int) -> dict:
    knowledge = []
    for catalog_item in course_knowledge_catalog(db, offering_id):
        point = catalog_item["point"]
        evidence = db.scalars(select(LearningEvidence).where(
            LearningEvidence.student_id == student_id,
            LearningEvidence.offering_id == offering_id,
            LearningEvidence.knowledge_point_id == point.id,
            LearningEvidence.source_type.in_(tuple(SOURCE_WEIGHTS)),
        ).order_by(LearningEvidence.observed_at.desc(), LearningEvidence.id.desc()).limit(20)).all()
        mastery_score, confidence = _mastery_values(evidence)
        observation_count = len(evidence)
        state = "unobserved" if observation_count == 0 else (
            "weak" if mastery_score < 60 else "mastered"
        )
        knowledge.append({
            "id": point.id,
            "code": catalog_item["display_code"],
            "storage_code": point.code,
            "name": point.name,
            "chapter_id": catalog_item["chapter_id"],
            "chapter_name": catalog_item["chapter_name"],
            "mastery_score": mastery_score,
            "confidence": confidence / 100,
            "observation_count": observation_count,
            "state": state,
            "last_observed_at": max((item.observed_at for item in evidence), default=None),
            "evidence": [{
                "id": item.id, "source_type": item.source_type, "source_id": item.source_id,
                "score": item.score, "confidence": item.confidence / 100,
                "observed_at": item.observed_at,
            } for item in evidence],
        })

    # 为证据补齐可导航的业务来源。作业证据的 source_id 是答案 ID，
    # 因而可以无歧义地定位到“哪份作业的第几题”。
    assignment_evidence_ids = {
        int(item["source_id"])
        for point in knowledge for item in point["evidence"]
        if item["source_type"] == "assignment"
    }
    assignment_sources: dict[int, dict] = {}
    if assignment_evidence_ids:
        rows = db.execute(
            select(
                Answer.id,
                Assignment.id,
                Assignment.title,
                Question.id,
                Question.prompt,
                AssignmentQuestion.position,
            )
            .join(Submission, Submission.id == Answer.submission_id)
            .join(Assignment, Assignment.id == Submission.assignment_id)
            .join(Question, Question.id == Answer.question_id)
            .join(AssignmentQuestion, and_(
                AssignmentQuestion.assignment_id == Assignment.id,
                AssignmentQuestion.question_id == Question.id,
            ))
            .where(Answer.id.in_(assignment_evidence_ids))
        ).all()
        assignment_sources = {
            int(answer_id): {
                "assignment_id": assignment_id,
                "assignment_title": assignment_title,
                "question_id": question_id,
                "question_position": position,
                "question_prompt": question_prompt,
            }
            for answer_id, assignment_id, assignment_title, question_id, question_prompt, position in rows
        }

    practice_session_ids = {
        int(item["source_id"])
        for point in knowledge for item in point["evidence"]
        if item["source_type"] == "practice"
    }
    practice_sources = {
        row.id: {
            "practice_session_id": row.id,
            "practice_title": f"个性化练习 · {row.created_at:%m-%d %H:%M}",
        }
        for row in db.scalars(select(PracticeSession).where(
            PracticeSession.id.in_(practice_session_ids),
            PracticeSession.student_id == student_id,
        )).all()
    } if practice_session_ids else {}

    for point in knowledge:
        for item in point["evidence"]:
            if item["source_type"] == "assignment":
                item.update(assignment_sources.get(int(item["source_id"]), {}))
            elif item["source_type"] == "practice":
                item.update(practice_sources.get(int(item["source_id"]), {}))
    return {
        "student_id": student_id, "offering_id": offering_id,
        "activity": student_activity(db, student_id, offering_id),
        "mastery_weights": SOURCE_WEIGHTS,
        "knowledge_points": knowledge,
    }
