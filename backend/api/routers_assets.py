"""Fixed assets API."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import page, row, rows
from backend.assets import service as svc
from backend.assets.models import AssetCategory, AssetTransaction, DepreciationMethod, DepreciationRun, FixedAsset
from backend.core.exceptions import NotFound
from backend.core.pagination import paginate
from backend.reporting.exports import respond

router = APIRouter(prefix="/api/assets", tags=["fixed assets"])


class AssetIn(BaseModel):
    code: str | None = None
    name: str = Field(min_length=2)
    description: str | None = None
    category_id: int
    site_id: int
    cost_centre_id: int
    supplier_id: int | None = None
    purchase_date: date
    capitalisation_date: date | None = None
    depreciation_start_date: date | None = None
    cost: Decimal = Field(gt=0)
    residual_value: Decimal = Field(default=Decimal("0"), ge=0)
    useful_life_months: int | None = Field(default=None, gt=0)
    method: DepreciationMethod | None = None
    reducing_rate: Decimal | None = None
    serial_no: str | None = None
    tag_no: str | None = None


class CapitaliseIn(BaseModel):
    source: str = Field(pattern="^(AP_INVOICE|JOURNAL|OPENING)$")
    ap_document_line_id: int | None = None
    offset_account_id: int | None = None
    opening_accumulated: Decimal | None = None


def _out(db, a: FixedAsset) -> dict:
    return row(a, extra={"net_book_value": a.net_book_value,
                         "transactions": rows(db.scalars(select(AssetTransaction).where(AssetTransaction.asset_id == a.id)
                                                         .order_by(AssetTransaction.id)).all())})


def _get(db, aid) -> FixedAsset:
    a = db.get(FixedAsset, aid)
    if a is None:
        raise NotFound("Asset not found")
    return a


@router.get("/categories")
def categories(db: DB, actor: CurrentActor):
    actor.require("asset.view")
    return rows(db.scalars(select(AssetCategory).order_by(AssetCategory.code)).all())


@router.get("")
def list_assets(db: DB, actor: CurrentActor, company_id: CompanyId, q: str | None = None, status: str | None = None,
                site_id: int | None = None, category_id: int | None = None, page_no: int = Query(1, alias="page"),
                page_size: int = 100):
    actor.require("asset.view")
    stmt = select(FixedAsset).where(FixedAsset.company_id == company_id)
    if q:
        stmt = stmt.where(or_(FixedAsset.code.ilike(f"%{q}%"), FixedAsset.name.ilike(f"%{q}%"), FixedAsset.tag_no.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(FixedAsset.status.in_(status.split(",")))
    if site_id:
        stmt = stmt.where(FixedAsset.site_id == site_id)
    if category_id:
        stmt = stmt.where(FixedAsset.category_id == category_id)
    if actor.site_ids is not None:
        stmt = stmt.where(FixedAsset.site_id.in_(actor.site_ids))
    items, total = paginate(db, stmt.order_by(FixedAsset.code), page_no, page_size)
    return page([row(i, extra={"net_book_value": i.net_book_value}) for i in items], total, page_no, page_size)


@router.get("/runs/list")
def runs(db: DB, actor: CurrentActor, company_id: CompanyId):
    actor.require("asset.view")
    return [row(r, extra={"line_count": len(r.lines)}) for r in
            db.scalars(select(DepreciationRun).where(DepreciationRun.company_id == company_id).order_by(DepreciationRun.id.desc())).all()]


@router.get("/runs/{run_id}")
def run_get(run_id: int, db: DB, actor: CurrentActor):
    actor.require("asset.view")
    r = db.get(DepreciationRun, run_id)
    if r is None:
        raise NotFound("Run not found")
    return row(r, extra={"lines": [row(l, extra={"asset_code": db.get(FixedAsset, l.asset_id).code}) for l in r.lines]})


class RunIn(BaseModel):
    period_id: int


@router.post("/runs", status_code=201)
def run_compute(body: RunIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    r = svc.compute_run(db, actor, company_id, body.period_id)
    db.commit()
    return row(r, extra={"lines": rows(r.lines)})


@router.post("/runs/{run_id}/post")
def run_post(run_id: int, db: DB, actor: CurrentActor):
    r = svc.post_run(db, actor, run_id)
    db.commit()
    return row(r)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3)


@router.post("/runs/{run_id}/reverse")
def run_reverse(run_id: int, body: ReasonIn, db: DB, actor: CurrentActor):
    r = svc.reverse_run(db, actor, run_id, body.reason)
    db.commit()
    return row(r)


@router.get("/reports/register")
def report_register(db: DB, actor: CurrentActor, company_id: CompanyId, as_of: date, site_id: int | None = None,
                    format: str = "json"):
    actor.require("asset.view")
    return respond(svc.register(db, company_id, as_of, site_id), format)


@router.get("/reports/reconciliation")
def report_recon(db: DB, actor: CurrentActor, company_id: CompanyId, as_of: date, format: str = "json"):
    actor.require("asset.view")
    return respond(svc.reconciliation(db, company_id, as_of), format)


@router.get("/{asset_id}")
def get_asset(asset_id: int, db: DB, actor: CurrentActor):
    actor.require("asset.view")
    return _out(db, _get(db, asset_id))


@router.post("", status_code=201)
def create(body: AssetIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    a = svc.create_asset(db, actor, company_id, body.model_dump())
    db.commit()
    return _out(db, a)


@router.post("/{asset_id}/capitalise")
def capitalise(asset_id: int, body: CapitaliseIn, db: DB, actor: CurrentActor):
    a = svc.capitalise(db, actor, _get(db, asset_id), **body.model_dump())
    db.commit()
    return _out(db, a)


class TransferIn(BaseModel):
    date: date
    to_site_id: int
    to_cost_centre_id: int
    notes: str | None = None


@router.post("/{asset_id}/transfer")
def transfer(asset_id: int, body: TransferIn, db: DB, actor: CurrentActor):
    a = _get(db, asset_id)
    svc.transfer(db, actor, a, body.date, body.to_site_id, body.to_cost_centre_id, body.notes)
    db.commit()
    return _out(db, a)


class DisposeIn(BaseModel):
    date: date
    proceeds: Decimal = Field(ge=0)
    bank_account_id: int | None = None
    notes: str | None = None


@router.post("/{asset_id}/dispose")
def dispose(asset_id: int, body: DisposeIn, db: DB, actor: CurrentActor):
    a = _get(db, asset_id)
    svc.dispose(db, actor, a, body.date, body.proceeds, body.bank_account_id, body.notes)
    db.commit()
    return _out(db, a)


class ImpairIn(BaseModel):
    date: date
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=3)


@router.post("/{asset_id}/impair")
def impair(asset_id: int, body: ImpairIn, db: DB, actor: CurrentActor):
    a = _get(db, asset_id)
    svc.impair(db, actor, a, body.date, body.amount, body.reason)
    db.commit()
    return _out(db, a)
