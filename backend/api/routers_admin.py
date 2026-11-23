"""Administration: users, roles, approval limits, workflow configuration, audit trail, attachments."""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.accounting.models import DocStatus, JournalEntry
from backend.api.deps import DB, CurrentActor
from backend.api.serialize import page, row, rows
from backend.audit.models import Attachment, AuditLog
from backend.audit.service import record
from backend.authentication import service as auth_svc
from backend.authentication.models import Permission, Role, User
from backend.config import get_settings
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.pagination import paginate
from backend.workflow.models import ApprovalLimit, WorkflowDefinition, WorkflowHistory

router = APIRouter(prefix="/api/admin", tags=["admin"])
files_router = APIRouter(prefix="/api/attachments", tags=["attachments"])


def _user_out(u: User) -> dict:
    return row(u, extra={"roles": [r.code for r in u.roles], "site_ids": [s.site_id for s in u.site_access]})


class UserIn(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,60}$")
    full_name: str = Field(min_length=2, max_length=120)
    email: str | None = None
    password: str | None = None
    is_active: bool = True
    all_sites: bool = False
    role_codes: list[str] = []
    site_ids: list[int] = []
    default_company_id: int | None = None
    must_change_password: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    password: str | None = None
    is_active: bool | None = None
    all_sites: bool | None = None
    role_codes: list[str] | None = None
    site_ids: list[int] | None = None
    default_company_id: int | None = None
    must_change_password: bool | None = None


@router.get("/users")
def users(db: DB, actor: CurrentActor):
    actor.require("admin.users")
    return [_user_out(u) for u in db.scalars(select(User).order_by(User.username)).all()]


@router.post("/users", status_code=201)
def user_create(body: UserIn, db: DB, actor: CurrentActor):
    u = auth_svc.save_user(db, actor, body.model_dump())
    db.commit()
    return _user_out(u)


@router.patch("/users/{user_id}")
def user_update(user_id: int, body: UserUpdate, db: DB, actor: CurrentActor):
    u = auth_svc.save_user(db, actor, body.model_dump(exclude_unset=True), user_id)
    db.commit()
    return _user_out(u)


@router.get("/roles")
def roles(db: DB, actor: CurrentActor):
    actor.require("admin.roles")
    return [row(r, extra={"permissions": [p.code for p in r.permissions]}) for r in
            db.scalars(select(Role).order_by(Role.code)).all()]


@router.get("/permissions")
def permissions(db: DB, actor: CurrentActor):
    actor.require("admin.roles")
    return rows(db.scalars(select(Permission).order_by(Permission.code)).all())


class RoleIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_]{2,40}$")
    name: str
    description: str | None = None
    permissions: list[str]


@router.post("/roles", status_code=201)
def role_create(body: RoleIn, db: DB, actor: CurrentActor):
    actor.require("admin.roles")
    if db.scalar(select(Role.id).where(Role.code == body.code)):
        raise Conflict("Role code exists")
    perms = db.scalars(select(Permission).where(Permission.code.in_(body.permissions))).all()
    r = Role(code=body.code, name=body.name, description=body.description, permissions=list(perms))
    db.add(r)
    db.flush()
    record(db, actor, "role.create", "role", r.id, None, {"code": r.code, "permissions": body.permissions})
    db.commit()
    return row(r, extra={"permissions": [p.code for p in r.permissions]})


class RolePermsIn(BaseModel):
    permissions: list[str]


@router.put("/roles/{role_id}/permissions")
def role_perms(role_id: int, body: RolePermsIn, db: DB, actor: CurrentActor):
    actor.require("admin.roles")
    r = db.get(Role, role_id)
    if r is None:
        raise NotFound("Role not found")
    old = [p.code for p in r.permissions]
    r.permissions = list(db.scalars(select(Permission).where(Permission.code.in_(body.permissions))).all())
    record(db, actor, "role.permissions", "role", r.id, {"permissions": old}, {"permissions": body.permissions})
    db.commit()
    return row(r, extra={"permissions": [p.code for p in r.permissions]})


# ------------------------------------------------------------------ workflow configuration
@router.get("/workflows")
def workflows(db: DB, actor: CurrentActor):
    actor.require("admin.settings")
    return rows(db.scalars(select(WorkflowDefinition).order_by(WorkflowDefinition.doc_type)).all())


class WorkflowUpdate(BaseModel):
    require_check: bool | None = None
    segregation_of_duties: bool | None = None
    auto_post_on_approval: bool | None = None
    require_attachment: bool | None = None


@router.patch("/workflows/{wf_id}")
def workflow_update(wf_id: int, body: WorkflowUpdate, db: DB, actor: CurrentActor):
    actor.require("admin.settings")
    wf = db.get(WorkflowDefinition, wf_id)
    if wf is None:
        raise NotFound("Workflow not found")
    data = body.model_dump(exclude_unset=True)
    old = {k: getattr(wf, k) for k in data}
    for k, v in data.items():
        setattr(wf, k, v)
    record(db, actor, "workflow.update", "workflow_definition", wf.id, old, data)
    db.commit()
    return row(wf)


@router.get("/approval-limits")
def approval_limits(db: DB, actor: CurrentActor):
    actor.require("admin.roles")
    return rows(db.scalars(select(ApprovalLimit).order_by(ApprovalLimit.doc_type, ApprovalLimit.id)).all())


class LimitIn(BaseModel):
    doc_type: str
    role_id: int | None = None
    user_id: int | None = None
    site_id: int | None = None
    max_amount: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True


@router.post("/approval-limits", status_code=201)
def limit_create(body: LimitIn, db: DB, actor: CurrentActor):
    actor.require("admin.roles")
    if not (body.role_id or body.user_id):
        raise ValidationFailed("Approval limit needs a role or a user")
    lim = ApprovalLimit(**body.model_dump())
    db.add(lim)
    db.flush()
    record(db, actor, "approval_limit.create", "approval_limit", lim.id, None, row(lim))
    db.commit()
    return row(lim)


@router.patch("/approval-limits/{limit_id}")
def limit_update(limit_id: int, body: LimitIn, db: DB, actor: CurrentActor):
    actor.require("admin.roles")
    lim = db.get(ApprovalLimit, limit_id)
    if lim is None:
        raise NotFound("Limit not found")
    old = row(lim)
    for k, v in body.model_dump().items():
        setattr(lim, k, v)
    record(db, actor, "approval_limit.update", "approval_limit", lim.id, old, row(lim))
    db.commit()
    return row(lim)


# ------------------------------------------------------------------ audit trail
@router.get("/audit")
def audit(db: DB, actor: CurrentActor, entity_type: str | None = None, entity_id: str | None = None,
          user_id: int | None = None, action: str | None = None, date_from: date | None = None,
          date_to: date | None = None, page_no: int = Query(1, alias="page"), page_size: int = 100):
    actor.require("audit.view")
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if date_from:
        stmt = stmt.where(AuditLog.ts >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(AuditLog.ts <= datetime.combine(date_to, time.max))
    items, total = paginate(db, stmt, page_no, page_size)
    return page(rows(items), total, page_no, page_size)


@router.get("/workflow-history/{doc_type}/{doc_id}")
def wf_history(doc_type: str, doc_id: int, db: DB, actor: CurrentActor):
    return rows(db.scalars(select(WorkflowHistory).where(WorkflowHistory.doc_type == doc_type.upper(),
                                                         WorkflowHistory.doc_id == doc_id)
                           .order_by(WorkflowHistory.id)).all())


# ------------------------------------------------------------------ attachments
ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", "text/csv", "text/plain",
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel",
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
_POSTED_ENTITY_STATUS = {"journal": JournalEntry}


@files_router.post("", status_code=201)
async def upload(db: DB, actor: CurrentActor, entity_type: str = Form(...), entity_id: int = Form(...),
                 description: str | None = Form(None), file: UploadFile = File(...)):
    s = get_settings()
    content = await file.read()
    if len(content) > s.max_upload_mb * 1024 * 1024:
        raise ValidationFailed(f"File larger than {s.max_upload_mb} MB")
    if file.content_type not in ALLOWED_TYPES:
        raise ValidationFailed(f"File type {file.content_type} is not allowed")
    digest = hashlib.sha256(content).hexdigest()
    folder = Path(s.attachment_dir) / entity_type
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in (file.filename or "file") if c.isalnum() or c in "._- ")[:120] or "file"
    path = folder / f"{uuid.uuid4().hex}_{safe}"
    path.write_bytes(content)
    att = Attachment(entity_type=entity_type, entity_id=entity_id, filename=safe, content_type=file.content_type,
                     size_bytes=len(content), sha256=digest, storage_path=str(path), description=description,
                     uploaded_by_id=actor.id)
    db.add(att)
    db.flush()
    record(db, actor, "attachment.upload", entity_type, entity_id, None, {"file": safe, "sha256": digest})
    db.commit()
    return row(att, exclude=("storage_path",))


@files_router.get("")
def list_attachments(entity_type: str, entity_id: int, db: DB, actor: CurrentActor):
    return rows(db.scalars(select(Attachment).where(Attachment.entity_type == entity_type,
                                                    Attachment.entity_id == entity_id)).all(), exclude=("storage_path",))


@files_router.get("/{att_id}/download")
def download(att_id: int, db: DB, actor: CurrentActor):
    att = db.get(Attachment, att_id)
    if att is None or not os.path.exists(att.storage_path):
        raise NotFound("Attachment not found")
    record(db, actor, "attachment.download", att.entity_type, att.entity_id, None, {"attachment": att.id})
    db.commit()
    return FileResponse(att.storage_path, filename=att.filename, media_type=att.content_type)


@files_router.delete("/{att_id}")
def delete_attachment(att_id: int, db: DB, actor: CurrentActor):
    att = db.get(Attachment, att_id)
    if att is None:
        raise NotFound("Attachment not found")
    model = _POSTED_ENTITY_STATUS.get(att.entity_type)
    if model is not None:
        doc = db.get(model, att.entity_id)
        if doc is not None and doc.status in (DocStatus.POSTED, DocStatus.REVERSED):
            raise Conflict("Attachments of posted documents cannot be removed")
    if att.uploaded_by_id != actor.id and not actor.has("admin.settings"):
        raise Conflict("Only the uploader can remove an attachment")
    record(db, actor, "attachment.delete", att.entity_type, att.entity_id, {"file": att.filename}, None)
    db.delete(att)
    db.commit()
    return {"ok": True}
