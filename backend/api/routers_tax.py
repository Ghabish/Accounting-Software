"""Tax API: codes, effective-dated rates, slab calculator, deposits, reports."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api.crud import register_crud
from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import jsonable, row, rows
from backend.core.exceptions import NotFound
from backend.reporting.exports import respond
from backend.tax import engine as tax_engine
from backend.tax import service as svc
from backend.tax.models import TaxBase, TaxCode, TaxRate, TaxType

router = APIRouter(prefix="/api/tax", tags=["tax"])


class TaxCodeIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9-]{2,30}$")
    name: str
    tax_type: TaxType
    authority: str
    law_section: str | None = None
    base: TaxBase = TaxBase.NET_AMOUNT
    account_id: int
    is_recoverable: bool = True
    is_active: bool = True
    needs_confirmation: bool = False
    notes: str | None = None


class TaxCodeUpdate(BaseModel):
    name: str | None = None
    law_section: str | None = None
    account_id: int | None = None
    is_recoverable: bool | None = None
    is_active: bool | None = None
    needs_confirmation: bool | None = None
    notes: str | None = None


def _tc_out(db, tc: TaxCode) -> dict:
    rates = db.scalars(select(TaxRate).where(TaxRate.tax_code_id == tc.id).order_by(TaxRate.effective_from.desc())).all()
    return row(tc, extra={"rates": rows(rates)})


register_crud(router, "/codes", TaxCode, TaxCodeIn, TaxCodeUpdate, view_perm="tax.view", manage_perm="tax.manage",
              filters=("tax_type", "authority"), serializer=_tc_out)


class RateIn(BaseModel):
    tax_code_id: int
    name: str
    payee_type: str = Field(default="ALL", pattern="^(ALL|COMPANY|INDIVIDUAL|AOP|NON_RESIDENT)$")
    atl_status: str = Field(default="ALL", pattern="^(ALL|ATL|NON_ATL)$")
    rate: Decimal = Field(ge=0, le=1)
    effective_from: date
    site_id: int | None = None
    transaction_type: str | None = None
    source_ref: str | None = None


@router.post("/rates", status_code=201)
def add_rate(body: RateIn, db: DB, actor: CurrentActor):
    r = svc.add_rate(db, actor, body.model_dump())
    db.commit()
    return row(r)


@router.get("/rate-lookup")
def rate_lookup(db: DB, actor: CurrentActor, tax_code_id: int, on_date: date, payee_type: str = "ALL",
                atl_status: str = "ALL", site_id: int | None = None):
    actor.require("tax.view")
    r = tax_engine.find_rate(db, tax_code_id, on_date, payee_type, atl_status, site_id)
    if r is None:
        raise NotFound("No effective rate")
    return row(r)


@router.get("/slab-calc")
def slab_calc(db: DB, actor: CurrentActor, tax_code_id: int, annual_amount: Decimal, on_date: date):
    actor.require("tax.view")
    tax, rate = tax_engine.slab_tax(db, tax_code_id, annual_amount, on_date)
    return jsonable({"annual_tax": tax, "effective_rate": rate})


class DepositIn(BaseModel):
    tax_code_ids: list[int] = Field(min_length=1)
    date_from: date
    date_to: date
    bank_account_id: int
    deposit_date: date
    cpr_number: str = Field(min_length=3, max_length=60)


@router.post("/deposits", status_code=201)
def deposit(body: DepositIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    je = svc.record_deposit(db, actor, company_id, **body.model_dump())
    db.commit()
    return {"journal_id": je.id, "number": je.number, "amount": jsonable(je.total_debit)}


@router.get("/reports/summary")
def report_summary(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date, format: str = "json"):
    actor.require("tax.view")
    return respond(svc.summary(db, company_id, date_from, date_to), format)


@router.get("/reports/transactions")
def report_listing(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
                   direction: str | None = None, tax_code_id: int | None = None, supplier_id: int | None = None,
                   customer_id: int | None = None, deposited: bool | None = None, format: str = "json"):
    actor.require("tax.view")
    return respond(svc.listing(db, company_id, date_from, date_to, direction=direction, tax_code_id=tax_code_id,
                               supplier_id=supplier_id, customer_id=customer_id, deposited=deposited), format)


@router.get("/reports/reconciliation")
def report_recon(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date, format: str = "json"):
    actor.require("tax.view")
    return respond(svc.account_reconciliation(db, company_id, date_from, date_to), format)


@router.get("/reports/working-papers")
def report_working_papers(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
                          format: str = "xlsx"):
    actor.require("tax.view")
    return respond(svc.working_papers(db, company_id, date_from, date_to), format)
