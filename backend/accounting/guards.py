"""ORM-level immutability guards for posted ledger data (PostgreSQL triggers add a second layer)."""
from __future__ import annotations

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from backend.accounting.models import DocStatus, JournalEntry, JournalLine, JournalLineDimension
from backend.audit.models import AuditLog
from backend.core.exceptions import Conflict

_LOCKED = {DocStatus.POSTED, DocStatus.REVERSED}
_HEADER_ALLOWED = {"status", "reversed_by_id", "reversed_at", "version", "updated_at"}


def _was_posted(obj: JournalLine) -> bool:
    hist = inspect(obj).attrs.is_posted.history
    if hist.deleted:
        return bool(hist.deleted[0])
    return bool(obj.is_posted) and not hist.added


@event.listens_for(Session, "before_flush")
def _protect_posted(session: Session, flush_context, instances) -> None:  # pragma: no cover - exercised via tests
    for obj in list(session.dirty):
        if isinstance(obj, JournalLine) and session.is_modified(obj, include_collections=False):
            if _was_posted(obj):
                raise Conflict("Posted journal lines cannot be modified; use a reversal", code="immutable")
        elif isinstance(obj, JournalEntry):
            state = inspect(obj)
            status_hist = state.attrs.status.history
            old_status = status_hist.deleted[0] if status_hist.deleted else obj.status
            if old_status in _LOCKED:
                changed = {a.key for a in state.mapper.column_attrs if state.attrs[a.key].history.has_changes()}
                illegal = changed - _HEADER_ALLOWED
                if illegal or (obj.status not in _LOCKED):
                    raise Conflict("Posted journals cannot be modified; use a reversal", code="immutable")
        elif isinstance(obj, AuditLog) and session.is_modified(obj):
            raise Conflict("Audit log entries are immutable", code="immutable")
    for obj in list(session.deleted):
        if isinstance(obj, JournalEntry) and obj.status in _LOCKED:
            raise Conflict("Posted journals cannot be deleted", code="immutable")
        if isinstance(obj, JournalLine) and obj.is_posted:
            raise Conflict("Posted journal lines cannot be deleted", code="immutable")
        if isinstance(obj, JournalLineDimension):
            line = obj.journal_line_id and session.get(JournalLine, obj.journal_line_id)
            if line is not None and line.is_posted:
                raise Conflict("Dimensions of posted lines cannot be changed", code="immutable")
        if isinstance(obj, AuditLog):
            raise Conflict("Audit log entries cannot be deleted", code="immutable")
