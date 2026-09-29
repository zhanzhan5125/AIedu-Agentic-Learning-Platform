from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Assignment, AssignmentStatus, Submission, SubmissionStatus


def auto_submit_assignment_drafts(
    db: Session, assignment_id: int, now: datetime | None = None,
) -> int:
    """Atomically submit only explicitly saved drafts for one expired assignment.

    ``not_started`` rows deliberately remain unsubmitted: the deadline worker must
    never invent an answer for a student who did not save one.
    """
    deadline = now or datetime.now()
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or assignment.end_at is None or assignment.end_at > deadline:
        return 0
    changed = db.execute(
        update(Submission)
        .where(
            Submission.assignment_id == assignment_id,
            Submission.status == SubmissionStatus.draft,
        )
        .values(
            status=SubmissionStatus.submitted,
            submitted_at=assignment.end_at,
            version=Submission.version + 1,
        )
        .execution_options(synchronize_session=False)
    ).rowcount or 0
    if assignment.status in (AssignmentStatus.open, AssignmentStatus.scheduled):
        assignment.status = AssignmentStatus.closed
    return int(changed)


def auto_submit_expired_drafts(db: Session, now: datetime | None = None) -> int:
    """Compatibility helper; production dispatches one MQ event per assignment."""
    deadline = now or datetime.now()
    assignment_ids = db.scalars(
        select(Assignment.id)
        .join(Submission, Submission.assignment_id == Assignment.id)
        .where(
            Submission.status == SubmissionStatus.draft,
            Assignment.end_at.is_not(None),
            Assignment.end_at <= deadline,
        )
        .distinct()
    ).all()
    changed = sum(auto_submit_assignment_drafts(db, assignment_id, deadline)
                  for assignment_id in assignment_ids)
    db.commit()
    return changed
