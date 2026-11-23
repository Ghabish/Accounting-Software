"""Budgets: versions, lines, approval, revision (history kept), budget vs actual, budget checks."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.accounting.models import Account, AccountingPeriod, BudgetControl, FiscalYear, JournalLine
from backend.audit.service import record
from backend.budgeting.models import Budget, BudgetLine, BudgetVersion
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.money import ZERO, money
from backend.database.base import utcnow


def create_budget(db: Session, actor: Actor, company_id: int, fiscal_year_id: int, name: str,
                  description: str | None = None) -> Budget:
    actor.require("budget.manage")
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None or fy.company_id != company_id:
        raise NotFound("Fiscal year not found")
    b = Budget(company_id=company_id, fiscal_year_id=fiscal_year_id, name=name, description=description,
               created_by_id=actor.id)
    db.add(b)
    db.flush()
    v = BudgetVersion(budget_id=b.id, version_no=1, label="Original", status="DRAFT", created_by_id=actor.id)
    db.add(v)
    db.flush()
    record(db, actor, "budget.create", "budget", b.id, None, {"name": name, "fiscal_year": fy.code})
    return b


def _version(db: Session, version_id: int) -> BudgetVersion:
    v = db.get(BudgetVersion, version_id)
    if v is None:
        raise NotFound("Budget version not found")
    return v


def upsert_lines(db: Session, actor: Actor, version_id: int, lines: list[dict]) -> int:
    """lines: {account_id, site_id, cost_centre_id, dimension_value_id, period_id, amount}. Replaces matching keys."""
    actor.require("budget.manage")
    v = _version(db, version_id)
    if v.status != "DRAFT":
        raise Conflict("Only draft budget versions can be edited; create a revision")
    budget = db.get(Budget, v.budget_id)
    periods = {p.id for p in db.scalars(select(AccountingPeriod).where(AccountingPeriod.fiscal_year_id == budget.fiscal_year_id))}
    n = 0
    for l in lines:
        if l["period_id"] not in periods:
            raise ValidationFailed("Budget period outside the budget's fiscal year")
        acc = db.get(Account, l["account_id"])
        if acc is None or not acc.is_postable:
            raise ValidationFailed("Budget lines must use posting accounts")
        actor.require_site(l.get("site_id"))
        key = dict(version_id=v.id, account_id=l["account_id"], site_id=l.get("site_id"),
                   cost_centre_id=l.get("cost_centre_id"), dimension_value_id=l.get("dimension_value_id"),
                   period_id=l["period_id"])
        stmt = select(BudgetLine).filter_by(**key)
        existing = db.scalar(stmt)
        amount = money(l["amount"])
        if existing:
            existing.amount = amount
        else:
            db.add(BudgetLine(**key, amount=amount))
        n += 1
    db.flush()
    record(db, actor, "budget.lines", "budget_version", v.id, None, {"lines": n})
    return n


def approve_version(db: Session, actor: Actor, version_id: int) -> BudgetVersion:
    actor.require("budget.approve")
    v = _version(db, version_id)
    if v.status != "DRAFT":
        raise Conflict("Only draft versions can be approved")
    if v.created_by_id == actor.id:
        raise Conflict("Segregation of duties: the preparer cannot approve the budget")
    b = db.get(Budget, v.budget_id)
    if b.active_version_id:
        old = db.get(BudgetVersion, b.active_version_id)
        old.status = "SUPERSEDED"
    v.status = "APPROVED"
    v.approved_by_id = actor.id
    v.approved_at = utcnow()
    b.active_version_id = v.id
    record(db, actor, "budget.approve", "budget_version", v.id, None, {"budget": b.name, "version": v.label})
    return v


def revise(db: Session, actor: Actor, budget_id: int, reason: str) -> BudgetVersion:
    """New draft version copied from the latest version; earlier versions remain for audit."""
    actor.require("budget.manage")
    if not reason or not reason.strip():
        raise ValidationFailed("A reason is required for a budget revision")
    b = db.get(Budget, budget_id)
    if b is None:
        raise NotFound("Budget not found")
    last = db.scalar(select(BudgetVersion).where(BudgetVersion.budget_id == b.id).order_by(BudgetVersion.version_no.desc()))
    if last.status == "DRAFT":
        raise Conflict("Approve or discard the existing draft before revising")
    nv = BudgetVersion(budget_id=b.id, version_no=last.version_no + 1, label=f"Revision {last.version_no}",
                       status="DRAFT", reason=reason, created_by_id=actor.id)
    db.add(nv)
    db.flush()
    for l in db.scalars(select(BudgetLine).where(BudgetLine.version_id == last.id)).all():
        db.add(BudgetLine(version_id=nv.id, account_id=l.account_id, site_id=l.site_id, cost_centre_id=l.cost_centre_id,
                          dimension_value_id=l.dimension_value_id, period_id=l.period_id, amount=l.amount))
    db.flush()
    record(db, actor, "budget.revise", "budget", b.id, {"version": last.version_no}, {"version": nv.version_no, "reason": reason})
    return nv


def active_version_id(db: Session, company_id: int, fiscal_year_id: int) -> int | None:
    return db.scalar(select(Budget.active_version_id).where(Budget.company_id == company_id,
                                                            Budget.fiscal_year_id == fiscal_year_id,
                                                            Budget.active_version_id.is_not(None)).order_by(Budget.id))


def budget_by_account(db: Session, company_id: int, version_id: int | None, date_from: date | None, date_to: date | None,
                      *, site_ids=None, cost_centre_ids=None) -> dict[int, Decimal]:
    if not version_id:
        return {}
    q = select(BudgetLine.account_id, func.sum(BudgetLine.amount)).join(
        AccountingPeriod, AccountingPeriod.id == BudgetLine.period_id).where(BudgetLine.version_id == version_id)
    if date_from:
        q = q.where(AccountingPeriod.end_date >= date_from)
    if date_to:
        q = q.where(AccountingPeriod.start_date <= date_to)
    if site_ids:
        q = q.where(BudgetLine.site_id.in_(site_ids))
    if cost_centre_ids:
        q = q.where(BudgetLine.cost_centre_id.in_(cost_centre_ids))
    return {aid: Decimal(v) for aid, v in db.execute(q.group_by(BudgetLine.account_id)).all()}


def check_budget(db: Session, company_id: int, posting_date: date, lines: list[tuple[int, int | None, int | None, Decimal]]) -> list[str]:
    """lines: (account_id, site_id, cost_centre_id, debit_amount). Advisory -> warnings, Absolute -> error."""
    period = db.scalar(select(AccountingPeriod).where(AccountingPeriod.company_id == company_id,
                                                      AccountingPeriod.start_date <= posting_date,
                                                      AccountingPeriod.end_date >= posting_date))
    if period is None:
        return []
    vid = active_version_id(db, company_id, period.fiscal_year_id)
    if not vid:
        return []
    fy = db.get(FiscalYear, period.fiscal_year_id)
    warnings, errors = [], []
    grouped: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
    for aid, sid, cid, amt in lines:
        grouped[(aid, sid, cid)] += amt
    for (aid, sid, cid), amt in grouped.items():
        acc = db.get(Account, aid)
        if acc.budget_control == BudgetControl.NONE or amt <= 0:
            continue
        bq = select(func.coalesce(func.sum(BudgetLine.amount), 0)).join(
            AccountingPeriod, AccountingPeriod.id == BudgetLine.period_id).where(
            BudgetLine.version_id == vid, BudgetLine.account_id == aid, AccountingPeriod.end_date <= period.end_date)
        aq = select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
            JournalLine.is_posted.is_(True), JournalLine.company_id == company_id, JournalLine.account_id == aid,
            JournalLine.posting_date.between(fy.start_date, period.end_date))
        if sid:
            bq, aq = bq.where(BudgetLine.site_id == sid), aq.where(JournalLine.site_id == sid)
        if cid:
            bq, aq = bq.where(BudgetLine.cost_centre_id == cid), aq.where(JournalLine.cost_centre_id == cid)
        budget = Decimal(db.scalar(bq) or 0)
        actual = Decimal(db.scalar(aq) or 0)
        if actual + amt > budget:
            msg = (f"{acc.code} {acc.name}: YTD actual {actual:,.2f} + this document {amt:,.2f} exceeds "
                   f"budget {budget:,.2f}")
            (errors if acc.budget_control == BudgetControl.ABSOLUTE else warnings).append(msg)
    if errors:
        raise ValidationFailed("Budget exceeded (absolute budget control)", code="budget_exceeded", details=errors)
    return warnings


def version_lines(db: Session, version_id: int) -> list[BudgetLine]:
    return list(db.scalars(select(BudgetLine).where(BudgetLine.version_id == version_id)).all())


def delete_draft_lines(db: Session, actor: Actor, version_id: int) -> None:
    actor.require("budget.manage")
    v = _version(db, version_id)
    if v.status != "DRAFT":
        raise Conflict("Only draft versions can be cleared")
    db.execute(delete(BudgetLine).where(BudgetLine.version_id == v.id))
