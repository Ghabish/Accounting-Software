"""Generic document workflow: Draft -> Submitted -> (Checked) -> Approved -> Posted.

Works on any ORM document with ``status`` and ``created_by_id``.  The calling
module supplies the document type, permission prefix, amount and site, and a
``poster`` callback that performs the accounting when the document is posted.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.accounting.models import DocStatus
from backend.audit.service import record
from backend.core.actor import Actor
from backend.core.exceptions import PermissionDenied, ValidationFailed, WorkflowError
from backend.database.base import utcnow
from backend.workflow.models import ApprovalLimit, WorkflowDefinition, WorkflowHistory


@dataclass
class WorkflowSpec:
    doc_type: str          # e.g. "JOURNAL", "AP_INVOICE"
    perm_prefix: str       # e.g. "journal", "ap_invoice"
    amount: Decimal
    site_id: int | None
    poster: Callable[[Session, Any, Actor], Any] | None = None
    has_attachment: Callable[[], bool] | None = None


def definition(db: Session, doc_type: str) -> WorkflowDefinition:
    wf = db.scalar(select(WorkflowDefinition).where(WorkflowDefinition.doc_type == doc_type))
    if wf is None:  # safe default
        wf = WorkflowDefinition(doc_type=doc_type, name=doc_type, require_check=False,
                                segregation_of_duties=True, auto_post_on_approval=False)
    return wf


def _cycle_actors(db: Session, doc_type: str, doc_id: int) -> dict[str, int | None]:
    """Who submitted / checked / approved in the current cycle (since the last rejection)."""
    rows = db.scalars(select(WorkflowHistory).where(WorkflowHistory.doc_type == doc_type,
                                                    WorkflowHistory.doc_id == doc_id)
                      .order_by(WorkflowHistory.id)).all()
    actors: dict[str, int | None] = {}
    for r in rows:
        if r.action in ("reject", "edit"):
            actors = {}
        else:
            actors[r.action] = r.user_id
    return actors


def approval_authority(db: Session, doc_type: str, actor: Actor, site_id: int | None) -> Decimal | None | bool:
    """Highest limit the actor holds: Decimal, None (unlimited) or False (no authority)."""
    conds = [ApprovalLimit.user_id == actor.id]
    if actor.role_ids:
        conds.append(ApprovalLimit.role_id.in_(actor.role_ids))
    q = select(ApprovalLimit).where(ApprovalLimit.doc_type == doc_type, ApprovalLimit.is_active.is_(True), or_(*conds))
    limits = [l for l in db.scalars(q).all() if l.site_id is None or l.site_id == site_id]
    if not limits:
        return False
    if any(l.max_amount is None for l in limits):
        return None
    return max(l.max_amount for l in limits)


def _log(db: Session, spec: WorkflowSpec, doc: Any, action: str, old: DocStatus, actor: Actor, comment: str | None):
    db.add(WorkflowHistory(doc_type=spec.doc_type, doc_id=doc.id, action=action, from_status=old.value,
                           to_status=doc.status.value, user_id=actor.id, comment=comment))
    record(db, actor, f"{spec.perm_prefix}.{action}", spec.doc_type.lower(), doc.id,
           {"status": old.value}, {"status": doc.status.value}, notes=comment)


def _stamp(doc: Any, field: str, actor: Actor) -> None:
    if hasattr(doc, f"{field}_by_id"):
        setattr(doc, f"{field}_by_id", actor.id)
        setattr(doc, f"{field}_at", utcnow())


def transition(db: Session, doc: Any, spec: WorkflowSpec, action: str, actor: Actor,
               comment: str | None = None) -> Any:
    wf = definition(db, spec.doc_type)
    actor.require_site(spec.site_id)
    status: DocStatus = doc.status
    actors = _cycle_actors(db, spec.doc_type, doc.id)
    preparer = actors.get("submit") or getattr(doc, "created_by_id", None)

    if action == "submit":
        if status != DocStatus.DRAFT:
            raise WorkflowError(f"Only drafts can be submitted (status {status.value})")
        actor.require(f"{spec.perm_prefix}.create")
        if wf.require_attachment and spec.has_attachment and not spec.has_attachment():
            raise ValidationFailed("A supporting document must be attached before submission", code="attachment_required")
        doc.status = DocStatus.SUBMITTED
        _stamp(doc, "submitted", actor)
    elif action == "check":
        if not wf.require_check:
            raise WorkflowError("This document type has no check stage")
        if status != DocStatus.SUBMITTED:
            raise WorkflowError(f"Only submitted documents can be checked (status {status.value})")
        actor.require(f"{spec.perm_prefix}.check")
        if wf.segregation_of_duties and actor.id == preparer:
            raise PermissionDenied("Segregation of duties: the preparer cannot check their own document", code="sod")
        doc.status = DocStatus.CHECKED
        _stamp(doc, "checked", actor)
    elif action == "approve":
        expected = DocStatus.CHECKED if wf.require_check else DocStatus.SUBMITTED
        if status != expected:
            raise WorkflowError(f"Document must be {expected.value} before approval (status {status.value})")
        actor.require(f"{spec.perm_prefix}.approve")
        if wf.segregation_of_duties and actor.id in {preparer, actors.get("check")}:
            raise PermissionDenied("Segregation of duties: the preparer or checker cannot approve", code="sod")
        limit = approval_authority(db, spec.doc_type, actor, spec.site_id)
        if limit is False:
            raise PermissionDenied("You have no approval authority for this document type", code="no_authority")
        if limit is not None and spec.amount > limit:
            raise PermissionDenied(f"Amount {spec.amount:,.2f} exceeds your approval limit {limit:,.2f}",
                                   code="limit_exceeded")
        doc.status = DocStatus.APPROVED
        _stamp(doc, "approved", actor)
    elif action == "reject":
        if status not in (DocStatus.SUBMITTED, DocStatus.CHECKED, DocStatus.APPROVED):
            raise WorkflowError("Only submitted, checked or approved documents can be rejected")
        if not (actor.has(f"{spec.perm_prefix}.check") or actor.has(f"{spec.perm_prefix}.approve")):
            raise PermissionDenied("You cannot reject this document")
        if not comment or not comment.strip():
            raise ValidationFailed("A reason is required to reject")
        doc.status = DocStatus.DRAFT
        if hasattr(doc, "rejection_reason"):
            doc.rejection_reason = comment
        for f in ("submitted", "checked", "approved"):
            if hasattr(doc, f"{f}_by_id"):
                setattr(doc, f"{f}_by_id", None)
    elif action == "cancel":
        if status != DocStatus.DRAFT:
            raise WorkflowError("Only drafts can be cancelled; posted documents must be reversed")
        actor.require(f"{spec.perm_prefix}.create")
        doc.status = DocStatus.CANCELLED
    elif action == "post":
        if status != DocStatus.APPROVED:
            raise WorkflowError(f"Only approved documents can be posted (status {status.value})")
        actor.require(f"{spec.perm_prefix}.post")
        if wf.segregation_of_duties and actor.id == preparer:
            raise PermissionDenied("Segregation of duties: the preparer cannot post their own document", code="sod")
    else:
        raise WorkflowError(f"Unknown workflow action '{action}'")

    if action == "post":
        if spec.poster is None:
            raise WorkflowError("This document cannot be posted directly")
        spec.poster(db, doc, actor)
        db.add(WorkflowHistory(doc_type=spec.doc_type, doc_id=doc.id, action="post", from_status=status.value,
                               to_status=DocStatus.POSTED.value, user_id=actor.id, comment=comment))
        return doc

    _log(db, spec, doc, action, status, actor, comment)
    db.flush()
    if action == "approve" and wf.auto_post_on_approval and spec.poster is not None:
        if actor.has(f"{spec.perm_prefix}.post"):
            spec.poster(db, doc, actor)
            db.add(WorkflowHistory(doc_type=spec.doc_type, doc_id=doc.id, action="post",
                                   from_status=DocStatus.APPROVED.value, to_status=DocStatus.POSTED.value,
                                   user_id=actor.id, comment="auto-post on approval"))
    return doc


def history(db: Session, doc_type: str, doc_id: int) -> list[WorkflowHistory]:
    return list(db.scalars(select(WorkflowHistory).where(WorkflowHistory.doc_type == doc_type,
                                                         WorkflowHistory.doc_id == doc_id)
                           .order_by(WorkflowHistory.id)).all())
