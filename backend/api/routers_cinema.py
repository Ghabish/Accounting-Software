"""Cinema operations API: masters, POS imports, day close, collections, distributor settlements, management reports."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api.crud import register_crud
from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import jsonable, page, row, rows
from backend.cinema import reports as crep
from backend.cinema import service as svc
from backend.cinema.models import (
    CollectionBatch, CollectionSettlement, DayClose, DistributorSettlement, Film, PaymentMethod, RevenueType, Screen, Show,
)
from backend.core.exceptions import NotFound
from backend.core.pagination import paginate
from backend.imports.parsers import as_date, read_rows
from backend.reporting.common import _ids
from backend.reporting.exports import respond

router = APIRouter(prefix="/api/cinema", tags=["cinema"])


class ScreenIn(BaseModel):
    site_id: int
    code: str = Field(min_length=1, max_length=10)
    name: str
    seats: int = Field(default=0, ge=0)
    screen_type: str = "STANDARD"
    is_active: bool = True


class ScreenUpdate(BaseModel):
    name: str | None = None
    seats: int | None = Field(default=None, ge=0)
    screen_type: str | None = None
    is_active: bool | None = None


class FilmIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    title: str
    distributor_id: int
    language: str | None = None
    rating: str | None = None
    release_date: date
    runtime_minutes: int | None = None
    is_active: bool = True


class FilmUpdate(BaseModel):
    title: str | None = None
    distributor_id: int | None = None
    language: str | None = None
    rating: str | None = None
    release_date: date | None = None
    runtime_minutes: int | None = None
    is_active: bool | None = None


class PaymentMethodIn(BaseModel):
    code: str
    name: str
    method_type: str = Field(pattern="^(CASH|CARD|GATEWAY|WALLET|CORPORATE|VOUCHER|PLATFORM)$")
    clearing_account_id: int
    customer_id: int | None = None
    fee_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    fee_account_id: int | None = None
    settlement_bank_account_id: int | None = None
    settlement_days: int = 1
    is_active: bool = True


class PaymentMethodUpdate(BaseModel):
    name: str | None = None
    clearing_account_id: int | None = None
    customer_id: int | None = None
    fee_pct: Decimal | None = None
    fee_account_id: int | None = None
    settlement_bank_account_id: int | None = None
    settlement_days: int | None = None
    is_active: bool | None = None


class RevenueTypeIn(BaseModel):
    code: str
    name: str
    stream: str = Field(pattern="^(TICKETING|FNB|ADVERTISING|OTHER)$")
    revenue_account_id: int
    discount_account_id: int | None = None
    refund_account_id: int | None = None
    cost_centre_id: int
    tax_code_ids: str | None = None
    applies_film_rental: bool = False
    is_active: bool = True


class RevenueTypeUpdate(BaseModel):
    name: str | None = None
    revenue_account_id: int | None = None
    discount_account_id: int | None = None
    refund_account_id: int | None = None
    cost_centre_id: int | None = None
    tax_code_ids: str | None = None
    applies_film_rental: bool | None = None
    is_active: bool | None = None


register_crud(router, "/screens", Screen, ScreenIn, ScreenUpdate, view_perm="cinema.view", manage_perm="cinema.manage",
              filters=("site_id",), site_scoped_field="site_id", validate=svc.validate_screen)
register_crud(router, "/films", Film, FilmIn, FilmUpdate, view_perm="cinema.view", manage_perm="cinema.manage",
              search_fields=("code", "title"), order_by="release_date", filters=("distributor_id",), validate=svc.validate_film,
              serializer=lambda db, f: row(f, extra={"terms": rows(f.terms)}))
register_crud(router, "/payment-methods", PaymentMethod, PaymentMethodIn, PaymentMethodUpdate, view_perm="cinema.view",
              manage_perm="cinema.manage")
register_crud(router, "/revenue-types", RevenueType, RevenueTypeIn, RevenueTypeUpdate, view_perm="cinema.view",
              manage_perm="cinema.manage", filters=("stream",))


class TermIn(BaseModel):
    site_id: int | None = None
    week_from: int = Field(ge=1)
    week_to: int = Field(ge=1)
    share_pct: Decimal = Field(ge=0, le=1)
    minimum_guarantee: Decimal | None = None


@router.put("/films/{film_id}/terms")
def film_terms(film_id: int, body: list[TermIn], db: DB, actor: CurrentActor):
    f = svc.set_film_terms(db, actor, film_id, [t.model_dump() for t in body])
    db.commit()
    return row(f, extra={"terms": rows(f.terms)})


@router.get("/shows")
def shows(db: DB, actor: CurrentActor, site_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
          page_no: int = Query(1, alias="page"), page_size: int = 200):
    actor.require("cinema.view")
    stmt = select(Show)
    if site_id:
        stmt = stmt.where(Show.site_id == site_id)
    if date_from:
        stmt = stmt.where(Show.business_date >= date_from)
    if date_to:
        stmt = stmt.where(Show.business_date <= date_to)
    if actor.site_ids is not None:
        stmt = stmt.where(Show.site_id.in_(actor.site_ids))
    items, total = paginate(db, stmt.order_by(Show.show_time), page_no, page_size)
    return page(rows(items), total, page_no, page_size)


# ------------------------------------------------------------------ imports
class BoxOfficeRow(BaseModel):
    site_code: str
    business_date: date
    screen_code: str
    film_code: str
    show_date: date | None = None
    show_time: str | None = None
    revenue_type_code: str
    payment_method_code: str
    tickets_sold: int = Field(default=0, ge=0)
    complimentary_tickets: int = Field(default=0, ge=0)
    complimentary_value: Decimal = Field(default=Decimal("0"), ge=0)
    refund_tickets: int = Field(default=0, ge=0)
    gross_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    refund_amount: Decimal = Field(default=Decimal("0"), ge=0)
    source_ref: str | None = None


class FnBRow(BaseModel):
    site_code: str
    business_date: date
    revenue_type_code: str
    payment_method_code: str
    quantity: int = Field(default=0, ge=0)
    gross_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    refund_amount: Decimal = Field(default=Decimal("0"), ge=0)
    source_ref: str | None = None


@router.post("/imports/box-office", status_code=201)
def import_bo(body: list[BoxOfficeRow], db: DB, actor: CurrentActor, company_id: CompanyId):
    b = svc.import_box_office(db, actor, company_id, [r.model_dump() for r in body])
    db.commit()
    return row(b)


@router.post("/imports/fnb", status_code=201)
def import_fnb(body: list[FnBRow], db: DB, actor: CurrentActor, company_id: CompanyId):
    b = svc.import_fnb(db, actor, company_id, [r.model_dump() for r in body])
    db.commit()
    return row(b)


@router.post("/imports/{kind}/file", status_code=201)
async def import_file(kind: str, db: DB, actor: CurrentActor, company_id: CompanyId, file: UploadFile = File(...)):
    raw = read_rows(await file.read(), file.filename or "")
    for r in raw:
        if r.get("business_date"):
            r["business_date"] = as_date(r["business_date"])
        if r.get("show_date"):
            r["show_date"] = as_date(r["show_date"])
    if kind == "box-office":
        b = svc.import_box_office(db, actor, company_id, [BoxOfficeRow(**r).model_dump() for r in raw], file.filename)
    elif kind == "fnb":
        b = svc.import_fnb(db, actor, company_id, [FnBRow(**r).model_dump() for r in raw], file.filename)
    else:
        raise NotFound("Unknown import kind")
    db.commit()
    return row(b)


# ------------------------------------------------------------------ day close
class DayCloseIn(BaseModel):
    site_id: int
    business_date: date
    cash_declared: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


@router.get("/day-close/preview")
def dc_preview(db: DB, actor: CurrentActor, company_id: CompanyId, site_id: int, business_date: date):
    actor.require("cinema.view")
    actor.require_site(site_id)
    return jsonable(svc.preview_day_close(db, company_id, site_id, business_date))


@router.post("/day-close", status_code=201)
def dc_post(body: DayCloseIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    dc = svc.day_close(db, actor, company_id, body.site_id, body.business_date, cash_declared=body.cash_declared, notes=body.notes)
    db.commit()
    return row(dc)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3)


@router.post("/day-close/{dc_id}/reverse")
def dc_reverse(dc_id: int, body: ReasonIn, db: DB, actor: CurrentActor):
    dc = svc.reverse_day_close(db, actor, dc_id, body.reason)
    db.commit()
    return row(dc)


@router.get("/day-close")
def dc_list(db: DB, actor: CurrentActor, company_id: CompanyId, site_id: int | None = None, date_from: date | None = None,
            date_to: date | None = None, page_no: int = Query(1, alias="page"), page_size: int = 100):
    actor.require("cinema.view")
    stmt = select(DayClose).where(DayClose.company_id == company_id)
    if site_id:
        stmt = stmt.where(DayClose.site_id == site_id)
    if date_from:
        stmt = stmt.where(DayClose.business_date >= date_from)
    if date_to:
        stmt = stmt.where(DayClose.business_date <= date_to)
    if actor.site_ids is not None:
        stmt = stmt.where(DayClose.site_id.in_(actor.site_ids))
    items, total = paginate(db, stmt.order_by(DayClose.business_date.desc(), DayClose.id.desc()), page_no, page_size)
    return page(rows(items), total, page_no, page_size)


# ------------------------------------------------------------------ collections
@router.get("/collections")
def collections(db: DB, actor: CurrentActor, company_id: CompanyId, status: str | None = None, payment_method_id: int | None = None):
    actor.require("cinema.view")
    stmt = select(CollectionBatch).where(CollectionBatch.company_id == company_id)
    if status:
        stmt = stmt.where(CollectionBatch.status.in_(status.split(",")))
    if payment_method_id:
        stmt = stmt.where(CollectionBatch.payment_method_id == payment_method_id)
    if actor.site_ids is not None:
        stmt = stmt.where(CollectionBatch.site_id.in_(actor.site_ids))
    return [row(b, extra={"difference": b.difference}) for b in
            db.scalars(stmt.order_by(CollectionBatch.business_date, CollectionBatch.id).limit(2000)).all()]


class SettleIn(BaseModel):
    payment_method_id: int
    bank_account_id: int
    settlement_date: date
    gross_amount: Decimal = Field(gt=0)
    fee_amount: Decimal = Field(default=Decimal("0"), ge=0)
    tax_deducted: Decimal = Field(default=Decimal("0"), ge=0)
    reference: str | None = None
    batch_ids: list[int] | None = None


@router.post("/settlements", status_code=201)
def settle(body: SettleIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    s = svc.settle(db, actor, company_id, **body.model_dump())
    db.commit()
    return row(s, extra={"allocations": rows(s.allocations)})


@router.get("/settlements")
def settlements(db: DB, actor: CurrentActor, company_id: CompanyId):
    actor.require("cinema.view")
    return rows(db.scalars(select(CollectionSettlement).where(CollectionSettlement.company_id == company_id)
                           .order_by(CollectionSettlement.id.desc()).limit(500)).all())


# ------------------------------------------------------------------ distributor settlements
class DistSettleIn(BaseModel):
    distributor_id: int
    period_from: date
    period_to: date
    reference: str | None = None
    adjustment: Decimal = Decimal("0")
    notes: str | None = None


@router.post("/distributor-settlements", status_code=201)
def dist_prepare(body: DistSettleIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    s = svc.prepare_distributor_settlement(db, actor, company_id, **body.model_dump())
    db.commit()
    return row(s, extra={"lines": rows(s.lines)})


class DistInvoiceIn(BaseModel):
    invoice_no: str = Field(min_length=1)
    invoice_date: date


@router.post("/distributor-settlements/{sid}/invoice")
def dist_invoice(sid: int, body: DistInvoiceIn, db: DB, actor: CurrentActor):
    doc = svc.invoice_distributor_settlement(db, actor, sid, body.invoice_no, body.invoice_date)
    db.commit()
    return {"ap_document_id": doc.id, "number": doc.number, "total": jsonable(doc.total), "status": doc.status.value}


@router.get("/distributor-settlements")
def dist_list(db: DB, actor: CurrentActor, company_id: CompanyId):
    actor.require("cinema.view")
    return [row(s, extra={"lines": rows(s.lines)}) for s in db.scalars(
        select(DistributorSettlement).where(DistributorSettlement.company_id == company_id).order_by(DistributorSettlement.id.desc())).all()]


# ------------------------------------------------------------------ reports
@router.get("/reports/revenue")
def report_revenue(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date, group_by: str = "site",
                   site_ids: str | None = None, format: str = "json"):
    actor.require("cinema.view")
    return respond(crep.revenue_analysis(db, company_id, date_from, date_to, group_by, site_ids=_ids(site_ids), actor=actor), format)


@router.get("/reports/kpis")
def report_kpis(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date, site_ids: str | None = None):
    actor.require("cinema.view")
    return jsonable(crep.kpis(db, company_id, date_from, date_to, site_ids=_ids(site_ids), actor=actor))


@router.get("/reports/collections-reconciliation")
def report_collections(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date, format: str = "json"):
    actor.require("cinema.view")
    return respond(svc.revenue_reconciliation(db, company_id, date_from, date_to, actor), format)


@router.get("/reports/gl-reconciliation")
def report_gl_recon(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date, format: str = "json"):
    actor.require("report.view")
    return respond(crep.gl_reconciliation(db, company_id, date_from, date_to), format)
