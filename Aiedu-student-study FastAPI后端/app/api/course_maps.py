from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.responses import ok
from app.db import get_db
from app.dependencies import current_user, require_roles
from app.models import (
    CourseMapEdge, CourseMapEvidence, CourseMapNode, CourseMapVersion,
    CourseOffering, CourseResource, Enrollment, KnowledgePoint, ResourceChunk,
    Role, User,
)
from app.services.access import offering_for_user


router = APIRouter(tags=["课程知识路线"])


class MapNodeInput(BaseModel):
    node_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    position: int = Field(default=0, ge=0)
    evidence_chunk_ids: list[int] = Field(default_factory=list, max_length=20)


class MapEdgeInput(BaseModel):
    source_key: str
    target_key: str
    relation_type: Literal["contains", "next", "related"]
    evidence_chunk_ids: list[int] = Field(default_factory=list, max_length=20)


class CourseMapUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)
    nodes: list[MapNodeInput] = Field(min_length=1, max_length=100)
    edges: list[MapEdgeInput] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def valid_graph(self):
        keys = {node.node_key for node in self.nodes}
        if len(keys) != len(self.nodes):
            raise ValueError("节点 key 不能重复")
        if any(edge.source_key not in keys or edge.target_key not in keys or
               edge.source_key == edge.target_key for edge in self.edges):
            raise ValueError("课程路线包含无效边")
        return self


def _version_for_user(db: Session, version_id: int, user: User, draft_required: bool = False) -> CourseMapVersion:
    version = db.get(CourseMapVersion, version_id)
    if version is None:
        raise NotFound("课程路线版本不存在")
    offering = db.get(CourseOffering, version.offering_id)
    if user.role == Role.teacher and offering and offering.teacher_id == user.id:
        pass
    elif user.role == Role.manager:
        pass
    else:
        raise Forbidden("无权操作该课程路线")
    if draft_required and version.status != "draft":
        raise Conflict("只有草稿版本可以修改或发布")
    return version


def _evidence_excerpt(db: Session, chunk: ResourceChunk, limit: int = 600) -> str:
    """Show readable evidence: remove stored overlap and stop at a sentence boundary."""
    text = (chunk.text or "").strip()
    previous = db.scalar(select(ResourceChunk).where(
        ResourceChunk.resource_id == chunk.resource_id,
        ResourceChunk.position == chunk.position - 1,
    )) if chunk.position > 0 else None
    if previous and text:
        previous_text = (previous.text or "").rstrip()
        maximum = min(1000, len(previous_text), len(text))
        for size in range(maximum, 15, -1):
            if previous_text[-size:] == text[:size]:
                text = text[size:].lstrip()
                break

    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= limit:
        return text
    lower = max(1, limit // 2)
    boundaries = [text.rfind(mark, lower, limit) for mark in ("。", "！", "？", ". ", "! ", "? ", "\n")]
    end = max(boundaries)
    if end < lower:
        forward = [position for mark in ("。", "！", "？", ". ", "! ", "? ", "\n")
                   if 0 <= (position := text.find(mark, limit, min(len(text), limit + 180)))]
        end = min(forward) if forward else limit - 1
    return text[:end + 1].rstrip() + "……"


def _evidence_view(db: Session, *, node_id: int | None = None, edge_id: int | None = None) -> list[dict]:
    query = (select(CourseMapEvidence, ResourceChunk, CourseResource)
             .join(ResourceChunk, ResourceChunk.id == CourseMapEvidence.chunk_id)
             .join(CourseResource, CourseResource.id == ResourceChunk.resource_id))
    query = query.where(CourseMapEvidence.node_id == node_id) if node_id else query.where(
        CourseMapEvidence.edge_id == edge_id)
    return [{
        "chunk_id": chunk.id, "resource_id": resource.id, "title": resource.title,
        "resource_type": resource.resource_type,
        "position": chunk.position, "heading_path": chunk.heading_path,
        "page_number": chunk.page_number, "slide_number": chunk.slide_number,
        "excerpt": _evidence_excerpt(db, chunk),
    } for _, chunk, resource in db.execute(query).all()]


def _view(db: Session, version: CourseMapVersion) -> dict:
    nodes = db.scalars(select(CourseMapNode).where(
        CourseMapNode.version_id == version.id).order_by(CourseMapNode.position, CourseMapNode.id)).all()
    edges = db.scalars(select(CourseMapEdge).where(CourseMapEdge.version_id == version.id)).all()
    by_id = {node.id: node for node in nodes}
    chapter_ids = {edge.source_node_id for edge in edges if edge.relation_type == "contains"}
    knowledge_point_ids = {edge.target_node_id for edge in edges if edge.relation_type == "contains"}
    return {
        "id": version.id, "course_id": version.course_id, "offering_id": version.offering_id,
        "version": version.version, "status": version.status, "title": version.title,
        "summary": version.summary, "agent_run_id": version.agent_run_id,
        "published_at": version.published_at,
        "nodes": [{
            "id": node.id, "node_key": node.node_key, "name": node.name,
            "description": node.description, "position": node.position,
            "node_type": ("chapter" if node.id in chapter_ids else
                          "knowledge_point" if node.id in knowledge_point_ids else "topic"),
            "confidence": node.confidence, "knowledge_point_id": node.knowledge_point_id,
            "evidence": _evidence_view(db, node_id=node.id),
        } for node in nodes],
        "edges": [{
            "id": edge.id,
            "source_key": by_id[edge.source_node_id].node_key,
            "target_key": by_id[edge.target_node_id].node_key,
            "relation_type": edge.relation_type, "confidence": edge.confidence,
            "evidence": _evidence_view(db, edge_id=edge.id),
        } for edge in edges if edge.source_node_id in by_id and edge.target_node_id in by_id],
    }


@router.get("/offerings/{offering_id}/course-map")
def get_course_map(offering_id: int, request: Request, user: User = Depends(current_user),
                   map_status: Literal["latest", "published"] = Query(default="latest", alias="status"),
                   db: Session = Depends(get_db)):
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise NotFound("教学班不存在")
    if user.role == Role.teacher:
        offering_for_user(db, offering_id, user)
        statuses = ["draft", "published"]
    elif user.role == Role.student:
        if not db.scalar(select(Enrollment.id).where(
            Enrollment.offering_id == offering_id, Enrollment.student_id == user.id)):
            raise Forbidden("未加入该教学班")
        statuses = ["published"]
    elif user.role == Role.manager:
        statuses = ["draft", "published"]
    else:
        raise Forbidden("无权查看课程路线")
    if map_status == "published":
        statuses = ["published"]
    version = db.scalar(select(CourseMapVersion).where(
        CourseMapVersion.offering_id == offering_id,
        CourseMapVersion.status.in_(statuses),
    ).order_by(CourseMapVersion.version.desc()))
    return ok(_view(db, version) if version else None, request.state.request_id)


@router.put("/teacher/course-map-versions/{version_id}")
def update_course_map(version_id: int, payload: CourseMapUpdate, request: Request,
                      user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    version = _version_for_user(db, version_id, user, draft_required=True)
    chunk_ids = {chunk_id for node in payload.nodes for chunk_id in node.evidence_chunk_ids}
    chunk_ids.update(chunk_id for edge in payload.edges for chunk_id in edge.evidence_chunk_ids)
    if chunk_ids:
        valid = set(db.scalars(select(ResourceChunk.id).where(
            ResourceChunk.offering_id == version.offering_id, ResourceChunk.id.in_(chunk_ids))).all())
        if valid != chunk_ids:
            raise Conflict("课程路线包含无效资料证据")
    old_node_ids = set(db.scalars(select(CourseMapNode.id).where(
        CourseMapNode.version_id == version.id)).all())
    old_edge_ids = set(db.scalars(select(CourseMapEdge.id).where(
        CourseMapEdge.version_id == version.id)).all())
    if old_node_ids or old_edge_ids:
        db.execute(delete(CourseMapEvidence).where(
            (CourseMapEvidence.node_id.in_(old_node_ids)) |
            (CourseMapEvidence.edge_id.in_(old_edge_ids))))
    db.execute(delete(CourseMapEdge).where(CourseMapEdge.version_id == version.id))
    db.execute(delete(CourseMapNode).where(CourseMapNode.version_id == version.id))
    version.title = payload.title
    version.summary = payload.summary
    nodes: dict[str, CourseMapNode] = {}
    for item in payload.nodes:
        node = CourseMapNode(version_id=version.id, node_key=item.node_key, name=item.name,
                             description=item.description, position=item.position, confidence=100)
        db.add(node)
        db.flush()
        nodes[item.node_key] = node
        db.add_all([CourseMapEvidence(node_id=node.id, chunk_id=chunk_id)
                    for chunk_id in set(item.evidence_chunk_ids)])
    for item in payload.edges:
        edge = CourseMapEdge(version_id=version.id, source_node_id=nodes[item.source_key].id,
                             target_node_id=nodes[item.target_key].id,
                             relation_type=item.relation_type, confidence=100)
        db.add(edge)
        db.flush()
        db.add_all([CourseMapEvidence(edge_id=edge.id, chunk_id=chunk_id)
                    for chunk_id in set(item.evidence_chunk_ids)])
    db.commit()
    return ok(_view(db, version), request.state.request_id)


@router.post("/teacher/course-map-versions/{version_id}/publish")
def publish_course_map(version_id: int, request: Request,
                       user: User = Depends(require_roles(Role.teacher)), db: Session = Depends(get_db)):
    version = _version_for_user(db, version_id, user, draft_required=True)
    nodes = db.scalars(select(CourseMapNode).where(CourseMapNode.version_id == version.id)
                       .order_by(CourseMapNode.position)).all()
    if not nodes:
        raise Conflict("空课程路线不能发布")
    db.query(CourseMapVersion).filter(
        CourseMapVersion.course_id == version.course_id,
        CourseMapVersion.status == "published",
    ).update({CourseMapVersion.status: "archived"})
    points: dict[int, KnowledgePoint] = {}
    for node in nodes:
        code = f"MAP-{node.node_key}"[:64]
        point = db.scalar(select(KnowledgePoint).where(
            KnowledgePoint.course_id == version.course_id, KnowledgePoint.code == code))
        if point is None:
            point = KnowledgePoint(course_id=version.course_id, code=code, name=node.name,
                                   description=node.description)
            db.add(point)
            db.flush()
        else:
            point.name = node.name
            point.description = node.description
        node.knowledge_point_id = point.id
        points[node.id] = point
    for edge in db.scalars(select(CourseMapEdge).where(
        CourseMapEdge.version_id == version.id, CourseMapEdge.relation_type == "contains")).all():
        if edge.source_node_id in points and edge.target_node_id in points:
            points[edge.target_node_id].parent_id = points[edge.source_node_id].id
    version.status = "published"
    version.published_at = datetime.now()
    db.commit()
    return ok(_view(db, version), request.state.request_id)
