from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assignment, AssignmentStatus, Submission, SubmissionStatus


def auto_submit_expired_drafts(db: Session, now: datetime | None = None) -> int:
    """Submit the last explicitly saved snapshot when its assignment reaches the deadline."""
    deadline = now or datetime.now()
    rows = db.execute(
        select(Submission, Assignment)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .where(
            Submission.status == SubmissionStatus.draft,
            Assignment.end_at.is_not(None),
            Assignment.end_at <= deadline,
        )
    ).all()
    assignment_ids: set[int] = set()
    for submission, assignment in rows:
        submission.status = SubmissionStatus.submitted
        submission.submitted_at = assignment.end_at
        assignment_ids.add(assignment.id)

    if assignment_ids:
        assignments = db.scalars(select(Assignment).where(Assignment.id.in_(assignment_ids))).all()
        for assignment in assignments:
            if assignment.status in (AssignmentStatus.open, AssignmentStatus.scheduled):
                assignment.status = AssignmentStatus.closed
    db.commit()
    return len(rows)
