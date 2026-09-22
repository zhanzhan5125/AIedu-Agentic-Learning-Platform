from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AgentRun, AgentRunStep, JobStatus


def _add_steps(db: Session, run_id: int, steps: list[dict[str, Any]]) -> None:
    for position, step in enumerate(steps, 1):
        digest = step.get("input_digest")
        if not digest:
            public_input = step.get("input_summary") or {
                "node_name": step["node_name"], "tool_name": step.get("tool_name")
            }
            digest = hashlib.sha256(json.dumps(
                public_input, ensure_ascii=False, sort_keys=True, default=str
            ).encode()).hexdigest()
        db.add(AgentRunStep(
            run_id=run_id,
            position=position,
            node_name=step["node_name"],
            agent_name=step.get("agent_name"),
            step_type=step.get("step_type", "node"),
            tool_name=step.get("tool_name"),
            input_digest=digest,
            output_summary=step.get("output_summary"),
            status=step.get("status", "completed"),
            duration_ms=step.get("duration_ms"),
        ))


def persist_execution_trace(
    db: Session, run: AgentRun, output: dict[str, Any], *, latency_ms: int,
) -> None:
    """Persist public decision summaries and delegated child runs, never model chain-of-thought."""
    run.agent_name = output.get("agent_name")
    run.task_type = output.get("task_type")
    run.plan = output.get("plan")
    run.reflection_count = int(output.get("reflection_count", 0))
    run.token_usage = output.get("token_usage")
    public_result = output.get("result") or {}
    run.result = {
        **public_result,
        "_validation": output.get("validation"),
        "_agent": {
            "name": output.get("agent_name"),
            "task_type": output.get("task_type"),
            "reflection_count": output.get("reflection_count", 0),
        },
    } if isinstance(public_result, dict) else public_result
    run.latency_ms = latency_ms

    db.query(AgentRunStep).filter(AgentRunStep.run_id == run.id).delete()
    _add_steps(db, run.id, output.get("steps", []))

    child_ids: list[int] = []
    for delegation in output.get("delegations", []):
        child = AgentRun(
            kind=f"delegation.{delegation['task_type']}",
            agent_name=delegation["agent_name"],
            task_type=delegation["task_type"],
            parent_run_id=run.id,
            owner_id=run.owner_id,
            resource_type=run.resource_type,
            resource_id=run.resource_id,
            status=JobStatus.succeeded,
            graph_version="four-agent-v1",
            prompt_version="four-agent-prompts-v1",
            model=get_settings().llm_model,
            plan=delegation.get("plan"),
            reflection_count=0,
            result=delegation.get("result"),
            latency_ms=sum(int(step.get("duration_ms") or 0) for step in delegation.get("steps", [])),
        )
        db.add(child)
        db.flush()
        child_ids.append(child.id)
        _add_steps(db, child.id, delegation.get("steps", []))
    if child_ids and isinstance(run.result, dict):
        run.result = {**run.result, "delegated_run_ids": child_ids}
