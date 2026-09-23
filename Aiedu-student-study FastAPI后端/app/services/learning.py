from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from math import exp

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
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
    StudentMasteryProfile,
)

SOURCE_WEIGHTS = {"assignment": 70, "practice": 30}


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
        eligible = [p for p in profiles if p.confidence >= 40 and p.observation_count >= 3]
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
    offering = db.get(CourseOffering, offering_id)
    all_points = db.scalars(select(KnowledgePoint).where(
        KnowledgePoint.course_id == offering.course_id
    ).order_by(KnowledgePoint.code)).all() if offering else []
    point_by_id = {point.id: point for point in all_points}
    chapter_by_point_id: dict[int, KnowledgePoint] = {}
    published_map = db.scalar(select(CourseMapVersion).where(
        CourseMapVersion.offering_id == offering_id,
        CourseMapVersion.status == "published",
    ).order_by(CourseMapVersion.version.desc())) if offering else None
    if published_map:
        map_nodes = db.scalars(select(CourseMapNode).where(
            CourseMapNode.version_id == published_map.id
        ).order_by(CourseMapNode.position)).all()
        node_by_id = {node.id: node for node in map_nodes}
        contains_edges = db.scalars(select(CourseMapEdge).where(
            CourseMapEdge.version_id == published_map.id,
            CourseMapEdge.relation_type == "contains",
        )).all()
        parent_node_ids = {edge.source_node_id for edge in contains_edges}
        leaf_nodes = [node for node in map_nodes
                      if node.id not in parent_node_ids and node.knowledge_point_id]
        points = [point_by_id[node.knowledge_point_id] for node in leaf_nodes
                  if node.knowledge_point_id in point_by_id]
        for edge in contains_edges:
            child_node = node_by_id.get(edge.target_node_id)
            parent_node = node_by_id.get(edge.source_node_id)
            if child_node and child_node.knowledge_point_id and parent_node:
                parent_point = point_by_id.get(parent_node.knowledge_point_id)
                if parent_point:
                    chapter_by_point_id[child_node.knowledge_point_id] = parent_point
    else:
        chapter_ids = {point.parent_id for point in all_points if point.parent_id is not None}
        points = [point for point in all_points if point.id not in chapter_ids]
        chapter_by_point_id = {
            point.id: point_by_id[point.parent_id]
            for point in points if point.parent_id in point_by_id
        }
    knowledge = []
    for point in points:
        evidence = db.scalars(select(LearningEvidence).where(
            LearningEvidence.student_id == student_id,
            LearningEvidence.offering_id == offering_id,
            LearningEvidence.knowledge_point_id == point.id,
            LearningEvidence.source_type.in_(tuple(SOURCE_WEIGHTS)),
        ).order_by(LearningEvidence.observed_at.desc()).limit(20)).all()
        mastery_score, confidence = _mastery_values(evidence)
        observation_count = len(evidence)
        state = "insufficient_data"
        if confidence >= 40 and observation_count >= 3:
            state = "weak" if mastery_score < 60 else "mastered"
        chapter = chapter_by_point_id.get(point.id)
        knowledge.append({
            "id": point.id,
            "code": point.code,
            "name": point.name,
            "chapter_id": chapter.id if chapter else None,
            "chapter_name": chapter.name if chapter else None,
            "mastery_score": mastery_score,
            "confidence": confidence / 100,
            "observation_count": observation_count,
            "evidence_needed": max(0, 3 - observation_count),
            "state": state,
            "last_observed_at": max((item.observed_at for item in evidence), default=None),
            "evidence": [{
                "id": item.id, "source_type": item.source_type, "source_id": item.source_id,
                "score": item.score, "confidence": item.confidence / 100,
                "observed_at": item.observed_at,
            } for item in evidence],
        })
    sufficient_count = sum(1 for item in knowledge if item["state"] != "insufficient_data")
    return {
        "student_id": student_id, "offering_id": offering_id,
        "activity": student_activity(db, student_id, offering_id),
        "mastery_weights": SOURCE_WEIGHTS,
        "profile_coverage": {"sufficient": sufficient_count, "total": len(knowledge)},
        "knowledge_points": knowledge,
    }
