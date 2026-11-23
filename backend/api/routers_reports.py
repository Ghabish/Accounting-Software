"""Financial reports. Every endpoint accepts ``format=json|xlsx|csv|pdf``."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import select

from backend.accounting.models import Account, JournalEntry
from backend.api.deps import DB, CompanyId, CurrentActor
from backend.core.exceptions import ValidationFailed
from backend.reporting import financial as fin
from backend.reporting.common import LineFilter
from backend.reporting.exports import respond

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _flt(company_id, actor, site_ids=None, cost_centre_ids=None, account_ids=None, dimension_value_ids=None,
         supplier_id=None, customer_id=None, account_prefix=None, db=None):
    if account_prefix and db is not None:
        ids = db.scalars(select(Account.id).where(Account.code.like(f"{account_prefix}%"), Account.is_postable.is_(True))).all()
        account_ids = ",".join(str(i) for i in ids) or "0"
    return LineFilter.build(company_id, actor, site_ids=site_ids, cost_centre_ids=cost_centre_ids,
                            account_ids=account_ids, dimension_value_ids=dimension_value_ids,
                            supplier_id=supplier_id, customer_id=customer_id)


@router.get("/trial-balance")
def trial_balance(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
                  site_ids: str | None = None, cost_centre_ids: str | None = None, include_zero: bool = False,
                  exclude_closing: bool = False, format: str = "json"):
    actor.require("report.view")
    rep = fin.trial_balance(db, company_id, actor, date_from, date_to,
                            flt=_flt(company_id, actor, site_ids, cost_centre_ids), include_zero=include_zero,
                            exclude_closing=exclude_closing)
    return respond(rep, format)


@router.get("/gl")
def general_ledger(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
                   account_ids: str | None = None, account_prefix: str | None = None, site_ids: str | None = None,
                   cost_centre_ids: str | None = None, dimension_value_ids: str | None = None,
                   supplier_id: int | None = None, customer_id: int | None = None,
                   page_no: int = Query(1, alias="page"), page_size: int = 200, format: str = "json"):
    actor.require("report.view")
    flt = _flt(company_id, actor, site_ids, cost_centre_ids, account_ids, dimension_value_ids, supplier_id,
               customer_id, account_prefix, db)
    if format != "json":
        return respond(fin.gl_detail_report(db, company_id, actor, date_from, date_to, flt=flt), format)
    return respond(fin.gl_detail(db, company_id, actor, date_from, date_to, flt=flt, page_no=page_no,
                                 page_size=page_size), "json")


@router.get("/account-statement")
def account_statement(db: DB, actor: CurrentActor, company_id: CompanyId, account_id: int, date_from: date,
                      date_to: date, site_ids: str | None = None, cost_centre_ids: str | None = None,
                      supplier_id: int | None = None, customer_id: int | None = None, format: str = "json",
                      page_no: int = Query(1, alias="page"), page_size: int = 500):
    actor.require("report.view")
    acc = db.get(Account, account_id)
    if acc is None:
        raise ValidationFailed("Account not found")
    flt = _flt(company_id, actor, site_ids, cost_centre_ids, str(account_id), None, supplier_id, customer_id)
    if format != "json":
        return respond(fin.gl_detail_report(db, company_id, actor, date_from, date_to, flt=flt,
                                            title=f"Account Statement - {acc.code} {acc.name}"), format)
    data = fin.gl_detail(db, company_id, actor, date_from, date_to, flt=flt, page_no=page_no, page_size=page_size)
    data["account"] = {"id": acc.id, "code": acc.code, "name": acc.name, "normal_balance": acc.normal_balance}
    return respond(data, "json")


@router.get("/gl-monthly")
def gl_monthly(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
               site_ids: str | None = None, cost_centre_ids: str | None = None, account_prefix: str | None = None,
               compare_prior_year: bool = False, format: str = "json"):
    actor.require("report.view")
    flt = _flt(company_id, actor, site_ids, cost_centre_ids, account_prefix=account_prefix, db=db)
    return respond(fin.monthly_movements(db, company_id, actor, date_from, date_to, flt=flt,
                                         compare_prior_year=compare_prior_year), format)


@router.get("/profit-loss")
def profit_loss(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
                preset: str = "period", detail: str = "account", site_ids: str | None = None,
                cost_centre_ids: str | None = None, dimension_value_ids: str | None = None,
                budget_version_id: int | None = None, format: str = "json"):
    actor.require("report.view")
    if preset not in ("period", "monthly", "ytd", "comparative", "budget", "site", "cost_centre"):
        raise ValidationFailed("Unknown preset")
    flt = _flt(company_id, actor, site_ids, cost_centre_ids, dimension_value_ids=dimension_value_ids)
    return respond(fin.pl_preset(db, company_id, actor, preset, date_from, date_to, flt=flt, detail=detail,
                                 budget_version_id=budget_version_id), format)


@router.get("/balance-sheet")
def balance_sheet(db: DB, actor: CurrentActor, company_id: CompanyId, as_of: date, compare: str | None = None,
                  site_ids: str | None = None, detail: str = "account", format: str = "json"):
    actor.require("report.view")
    dates = [as_of]
    if compare == "prior_month":
        dates.append(fin.prior_month_end(as_of))
    elif compare == "prior_year":
        dates.append(fin._shift_year(as_of, -1))
    elif compare == "fy_start":
        dates.append(fin.fiscal_year_for(db, company_id, as_of).start_date - timedelta(days=1))
    flt = _flt(company_id, actor, site_ids)
    return respond(fin.balance_sheet(db, company_id, actor, dates, flt=flt, detail=detail), format)


@router.get("/cash-flow")
def cash_flow(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
              method: str = "indirect", site_ids: str | None = None, format: str = "json"):
    actor.require("report.view")
    flt = _flt(company_id, actor, site_ids)
    if method == "direct":
        return respond(fin.cash_flow_direct(db, company_id, actor, date_from, date_to, flt=flt), format)
    return respond(fin.cash_flow(db, company_id, actor, date_from, date_to, flt=flt), format)


@router.get("/cash-flow-monthly")
def cash_flow_monthly(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
                      format: str = "json"):
    actor.require("report.view")
    months = fin.month_ranges(date_from, date_to)
    reps = [fin.cash_flow(db, company_id, actor, a, b) for _l, a, b in months]
    ytd = fin.cash_flow(db, company_id, actor, date_from, date_to)
    rows_out = []
    for i, r in enumerate(ytd["rows"]):
        out = {k: v for k, v in r.items() if k != "c0"}
        for m, rep in enumerate(reps):
            match = next((x for x in rep["rows"] if x["label"] == r["label"]), None)
            out[f"c{m}"] = match.get("c0") if match else None
        out[f"c{len(reps)}"] = r.get("c0")
        rows_out.append(out)
    cols = [{"key": "label", "label": "", "type": "text"}] + [
        {"key": f"c{i}", "label": lbl, "type": "money"} for i, (lbl, _a, _b) in enumerate(months)] + [
        {"key": f"c{len(months)}", "label": "Year to date", "type": "money"}]
    return respond({**ytd, "title": "Monthly Cash Flow Statement", "columns": cols, "rows": rows_out}, format)


@router.get("/cash-position")
def cash_position(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
                  format: str = "json"):
    actor.require("bank.view")
    return respond(fin.cash_by_account(db, company_id, actor, date_from, date_to), format)


@router.get("/journal-listing")
def journal_listing(db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
                    journal_type: str | None = None, status: str | None = None, format: str = "json"):
    actor.require("journal.view")
    stmt = select(JournalEntry).where(JournalEntry.company_id == company_id,
                                      JournalEntry.posting_date.between(date_from, date_to))
    if journal_type:
        stmt = stmt.where(JournalEntry.journal_type == journal_type)
    if status:
        stmt = stmt.where(JournalEntry.status == status)
    rows_out = []
    for j in db.scalars(stmt.order_by(JournalEntry.posting_date, JournalEntry.id).limit(20000)).all():
        rows_out.append({"label": j.posting_date.isoformat(), "number": j.number or f"DRAFT-{j.id}",
                         "type": j.journal_type.value, "description": j.description, "status": j.status.value,
                         "source": j.source_module.value, "total": j.total_debit, "journal_id": j.id})
    cols = [{"key": "label", "label": "Date", "type": "text"}, {"key": "number", "label": "Number", "type": "text"},
            {"key": "type", "label": "Type", "type": "text"}, {"key": "description", "label": "Description", "type": "text"},
            {"key": "status", "label": "Status", "type": "text"}, {"key": "source", "label": "Source", "type": "text"},
            {"key": "total", "label": "Amount", "type": "money"}]
    return respond({"title": "Journal Listing", "company": "", "subtitle": f"{date_from} to {date_to}",
                    "columns": cols, "rows": rows_out, "meta": {}}, format)
