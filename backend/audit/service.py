"""Audit trail helper. Every important action calls ``record``."""
from __future__ import annotations

import contextvars
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.audit.models import AuditLog

request_context: contextvars.ContextVar[dict] = contextvars.ContextVar("request_context", default={})


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def snapshot(obj: Any, fields: list[str] | None = None) -> dict:
    """Column values of an ORM object as a JSON-safe dict."""
    mapper = inspect(obj).mapper
    cols = fields or [c.key for c in mapper.column_attrs]
    return {c: _jsonable(getattr(obj, c, None)) for c in cols if c not in ("password_hash",)}


def changes(obj: Any) -> tuple[dict, dict]:
    """(old, new) for attributes modified in the current unit of work."""
    old, new = {}, {}
    state = inspect(obj)
    for attr in state.mapper.column_attrs:
        hist = state.attrs[attr.key].history
        if hist.has_changes() and attr.key not in ("updated_at", "password_hash"):
            old[attr.key] = _jsonable(hist.deleted[0] if hist.deleted else None)
            new[attr.key] = _jsonable(hist.added[0] if hist.added else None)
    return old, new


def record(db: Session, user: Any, action: str, entity_type: str, entity_id: Any = None,
           old: dict | None = None, new: dict | None = None, notes: str | None = None) -> AuditLog:
    ctx = request_context.get()
    entry = AuditLog(
        user_id=getattr(user, "id", None), username=getattr(user, "username", None),
        action=action, entity_type=entity_type, entity_id=None if entity_id is None else str(entity_id),
        old_values=_jsonable(old) if old else None, new_values=_jsonable(new) if new else None,
        ip_address=ctx.get("ip"), user_agent=(ctx.get("ua") or "")[:255] or None, notes=notes,
    )
    db.add(entry)
    return entry
