"""Generic list / get / create / update endpoints for master data.

Masters are never hard-deleted (referential integrity and audit): they are
deactivated with ``is_active = false``.  Every create and update is audited.
"""

from typing import Any, Callable

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import page, row
from backend.audit.service import changes, record, snapshot
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound
from backend.core.pagination import paginate


def register_crud(router: APIRouter, path: str, model: Any, create_schema: type[BaseModel],
                  update_schema: type[BaseModel], *, view_perm: str, manage_perm: str,
                  search_fields: tuple[str, ...] = ("code", "name"), order_by: str = "code",
                  company_scoped: bool = False, filters: tuple[str, ...] = (),
                  site_scoped_field: str | None = None,
                  validate: Callable[[Session, Actor, Any, dict], None] | None = None,
                  serializer: Callable[[Session, Any], dict] | None = None, entity: str | None = None) -> None:
    entity = entity or model.__tablename__
    ser = serializer or (lambda db, o: row(o))

    @router.get(path, name=f"list_{entity}")
    def _list(db: DB, actor: CurrentActor, company_id: CompanyId, q: str | None = None,
              active: bool | None = None, page_no: int = Query(1, alias="page"), page_size: int = 100,
              filter_field: str | None = Query(None, alias="field"), filter_value: str | None = Query(None, alias="value")):
        actor.require(view_perm)
        stmt = select(model)
        if company_scoped:
            stmt = stmt.where(model.company_id == company_id)
        if q:
            stmt = stmt.where(or_(*[getattr(model, f).ilike(f"%{q}%") for f in search_fields]))
        if active is not None and hasattr(model, "is_active"):
            stmt = stmt.where(model.is_active.is_(active))
        if filter_field and filter_field in filters and filter_value is not None:
            stmt = stmt.where(getattr(model, filter_field) == filter_value)
        if site_scoped_field and actor.site_ids is not None:
            col = getattr(model, site_scoped_field)
            stmt = stmt.where(or_(col.is_(None), col.in_(actor.site_ids)))
        stmt = stmt.order_by(getattr(model, order_by))
        items, total = paginate(db, stmt, page_no, page_size)
        return page([ser(db, i) for i in items], total, page_no, page_size)

    @router.get(path + "/{item_id}", name=f"get_{entity}")
    def _get(item_id: int, db: DB, actor: CurrentActor):
        actor.require(view_perm)
        obj = db.get(model, item_id)
        if obj is None:
            raise NotFound(f"{entity} not found")
        return ser(db, obj)

    @router.post(path, status_code=201, name=f"create_{entity}")
    def _create(body: create_schema, db: DB, actor: CurrentActor, company_id: CompanyId):  # type: ignore[valid-type]
        actor.require(manage_perm)
        data = body.model_dump(exclude_unset=False)
        if company_scoped:
            data["company_id"] = company_id
        obj = model()
        if validate:
            validate(db, actor, obj, data)
        for k, v in data.items():
            if hasattr(model, k):
                setattr(obj, k, v)
        if hasattr(obj, "created_by_id"):
            obj.created_by_id = actor.id
        db.add(obj)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise Conflict(f"{entity}: duplicate code or invalid reference") from exc
        record(db, actor, f"{entity}.create", entity, obj.id, None, snapshot(obj))
        db.commit()
        return ser(db, obj)

    @router.patch(path + "/{item_id}", name=f"update_{entity}")
    def _update(item_id: int, body: update_schema, db: DB, actor: CurrentActor):  # type: ignore[valid-type]
        actor.require(manage_perm)
        obj = db.get(model, item_id)
        if obj is None:
            raise NotFound(f"{entity} not found")
        data = body.model_dump(exclude_unset=True)
        if validate:
            validate(db, actor, obj, data)
        for k, v in data.items():
            if hasattr(model, k):
                setattr(obj, k, v)
        old, new = changes(obj)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise Conflict(f"{entity}: duplicate code or invalid reference") from exc
        if old:
            record(db, actor, f"{entity}.update", entity, obj.id, old, new)
        db.commit()
        return ser(db, obj)
