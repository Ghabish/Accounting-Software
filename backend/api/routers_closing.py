"""Month-end close, year-end close, CFO dashboard, ratios and reporting pack."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.accounting.models import AccountingPeriod
from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import jsonable, row, rows
from backend.closing import service as svc
from backend.core.exceptions import NotFound
from backend.reporting.common import _ids
from backend.reporting.dashboard import cfo_dashboard, ratios
from backend.reporting.exports import respond
from backend.reporting.pack import monthly_pack

router = APIRouter(prefix="/api/closing", tags=["closing"])
export_router = APIRouter(prefix="/api/cfo", tags=["cfo"])


@router.get("/{period_id}/checklist")
def checklist(period_id: int, db: DB, actor: CurrentActor):
    items = svc.checklist(db, actor, period_id)
    db.commit()
    return rows(items)


class SignOffIn(BaseModel):
    status: str
    comment: str | None = None


@router.post("/{period_id}/checklist/{code}")
def sign_off(period_id: int, code: str, body: SignOffIn, db: DB, actor: CurrentActor):
    item = svc.sign_off(db, actor, period_id, code, body.status, body.comment)
    db.commit()
    return row(item)


@router.post("/{period_id}/close")
def close(period_id: int, db: DB, actor: CurrentActor):
    p = svc.close_period(db, actor, period_id)
    db.commit()
    return row(p)


class ReopenIn(BaseModel):
    reason: str = Field(min_length=5)


@router.post("/{period_id}/reopen")
def reopen(period_id: int, body: ReopenIn, db: DB, actor: CurrentActor):
    p = svc.reopen_period(db, actor, period_id, body.reason)
    db.commit()
    return row(p)


class YearEndIn(BaseModel):
    fiscal_year_id: int


@router.post("/year-end")
def year_end(body: YearEndIn, db: DB, actor: CurrentActor):
    je = svc.year_end_close(db, actor, body.fiscal_year_id)
    db.commit()
    return {"journal_id": je.id, "number": je.number}


@export_router.get("/dashboard")
def dashboard(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date, site_ids: str | None = None,
              cost_centre_ids: str | None = None, revenue_stream: str | None = None):
    actor.require("report.view")
    return jsonable(cfo_dashboard(db, company_id, actor, date_from, date_to, site_ids=_ids(site_ids),
                                  cost_centre_ids=_ids(cost_centre_ids), revenue_stream=revenue_stream))


@export_router.get("/ratios")
def get_ratios(db: DB, actor: CurrentActor, company_id: CompanyId, as_of: date):
    actor.require("report.view")
    return jsonable(ratios(db, company_id, actor, as_of))


@export_router.get("/pack")
def pack(db: DB, actor: CurrentActor, company_id: CompanyId, period_id: int, format: str = "pdf"):
    actor.require("report.cfo")
    p = db.get(AccountingPeriod, period_id)
    if p is None or p.company_id != company_id:
        raise NotFound("Period not found")
    return respond(monthly_pack(db, company_id, actor, p.start_date, p.end_date), format)
