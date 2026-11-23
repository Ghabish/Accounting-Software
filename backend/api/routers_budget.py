"""Budgeting API."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.accounting.models import Account, AccountingPeriod
from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import row, rows
from backend.budgeting import service as svc
from backend.budgeting.models import Budget, BudgetLine, BudgetVersion
from backend.core.exceptions import NotFound
from backend.core.money import ZERO, money
from backend.reporting import financial as fin
from backend.reporting.common import LineFilter, balances_by_account
from backend.reporting.exports import respond

router = APIRouter(prefix="/api/budgets", tags=["budgeting"])


class BudgetIn(BaseModel):
    fiscal_year_id: int
    name: str = Field(min_length=2)
    description: str | None = None


@router.get("")
def list_budgets(db: DB, actor: CurrentActor, company_id: CompanyId):
    actor.require("budget.view")
    out = []
    for b in db.scalars(select(Budget).where(Budget.company_id == company_id).order_by(Budget.id.desc())).all():
        versions = db.scalars(select(BudgetVersion).where(BudgetVersion.budget_id == b.id).order_by(BudgetVersion.version_no)).all()
        out.append(row(b, extra={"versions": rows(versions)}))
    return out


@router.post("", status_code=201)
def create_budget(body: BudgetIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    b = svc.create_budget(db, actor, company_id, body.fiscal_year_id, body.name, body.description)
    db.commit()
    return row(b)


class LineIn(BaseModel):
    account_id: int
    site_id: int | None = None
    cost_centre_id: int | None = None
    dimension_value_id: int | None = None
    period_id: int
    amount: Decimal


@router.get("/versions/{version_id}/lines")
def get_lines(version_id: int, db: DB, actor: CurrentActor):
    actor.require("budget.view")
    return rows(svc.version_lines(db, version_id))


@router.put("/versions/{version_id}/lines")
def put_lines(version_id: int, body: list[LineIn], db: DB, actor: CurrentActor):
    n = svc.upsert_lines(db, actor, version_id, [l.model_dump() for l in body])
    db.commit()
    return {"saved": n}


@router.post("/versions/{version_id}/approve")
def approve(version_id: int, db: DB, actor: CurrentActor):
    v = svc.approve_version(db, actor, version_id)
    db.commit()
    return row(v)


class ReviseIn(BaseModel):
    reason: str = Field(min_length=3)


@router.post("/{budget_id}/revise")
def revise(budget_id: int, body: ReviseIn, db: DB, actor: CurrentActor):
    v = svc.revise(db, actor, budget_id, body.reason)
    db.commit()
    return row(v)


@router.get("/reports/variance")
def variance(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
             version_id: int | None = None, site_ids: str | None = None, cost_centre_ids: str | None = None,
             format: str = "json"):
    """Budget vs actual by account: period and YTD actual, budget, variance, variance %."""
    actor.require("budget.view")
    fy = fin.fiscal_year_for(db, company_id, date_to)
    vid = version_id or svc.active_version_id(db, company_id, fy.id)
    flt = LineFilter.build(company_id, actor, site_ids=site_ids, cost_centre_ids=cost_centre_ids, exclude_sources=("CLOSING",))
    site_list = flt.site_ids
    cc_list = flt.cost_centre_ids
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.pl_section.is_not(None))).all()}

    def actual(d1, d2):
        out = {}
        for aid, (dr, cr) in balances_by_account(db, flt, date_from=d1, date_to=d2).items():
            a = accounts.get(aid)
            if a:
                out[aid] = (cr - dr) if a.pl_section in ("REVENUE", "OTHER_INCOME") else (dr - cr)
        return out
    act_p, act_y = actual(date_from, date_to), actual(fy.start_date, date_to)
    bud_p = svc.budget_by_account(db, company_id, vid, date_from, date_to, site_ids=site_list, cost_centre_ids=cc_list)
    bud_y = svc.budget_by_account(db, company_id, vid, fy.start_date, date_to, site_ids=site_list, cost_centre_ids=cc_list)
    rows_out = []
    for aid in sorted(set(act_p) | set(act_y) | set(bud_p) | set(bud_y), key=lambda i: accounts[i].code):
        a = accounts[aid]
        ap, bp, ay, by = (money(x.get(aid, ZERO)) for x in (act_p, bud_p, act_y, bud_y))
        income = a.pl_section in ("REVENUE", "OTHER_INCOME")
        vp, vy = ap - bp, ay - by
        rows_out.append({"label": f"{a.code} {a.name}", "section": a.pl_section, "c0": ap, "c1": bp, "c2": vp,
                         "c3": (vp / abs(bp) * 100).quantize(Decimal("0.1")) if bp else None, "c4": ay, "c5": by, "c6": vy,
                         "c7": (vy / abs(by) * 100).quantize(Decimal("0.1")) if by else None,
                         "favourable": (vy >= 0) if income else (vy <= 0), "level": 1, "style": "line",
                         "drill": {"account_id": aid}})
    cols = [{"key": "label", "label": "Account", "type": "text"}] + [
        {"key": f"c{i}", "label": l, "type": "pct" if "%" in l else "money"} for i, l in enumerate(
            ["Actual", "Budget", "Variance", "Var %", "YTD actual", "YTD budget", "YTD variance", "YTD var %"])]
    return respond({"title": "Budget vs Actual", "subtitle": f"{date_from} to {date_to} (YTD from {fy.start_date})",
                    "columns": cols, "rows": rows_out, "meta": {"version_id": vid}}, format)
