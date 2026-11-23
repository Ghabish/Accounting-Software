"""Fiscal years and accounting periods (July-June by default)."""
from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.accounting.models import AccountingPeriod, FiscalYear, PeriodStatus, PeriodStatusLog
from backend.audit.service import record
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, PeriodClosed, ValidationFailed
from backend.database.base import utcnow


def fiscal_year_bounds(any_date: date, start_month: int = 7) -> tuple[date, date]:
    start_year = any_date.year if any_date.month >= start_month else any_date.year - 1
    start = date(start_year, start_month, 1)
    end_year = start_year + 1 if start_month > 1 else start_year
    end_month = start_month - 1 if start_month > 1 else 12
    return start, date(end_year, end_month, calendar.monthrange(end_year, end_month)[1])


def create_fiscal_year(db: Session, company_id: int, start: date, start_month: int = 7) -> FiscalYear:
    fy_start, fy_end = fiscal_year_bounds(start, start_month)
    code = f"FY{fy_start.year}-{str(fy_end.year)[2:]}"
    existing = db.scalar(select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.code == code))
    if existing:
        return existing
    fy = FiscalYear(company_id=company_id, code=code, start_date=fy_start, end_date=fy_end)
    db.add(fy)
    db.flush()
    y, m = fy_start.year, fy_start.month
    for n in range(1, 13):
        last = calendar.monthrange(y, m)[1]
        db.add(AccountingPeriod(company_id=company_id, fiscal_year_id=fy.id, period_no=n,
                                name=date(y, m, 1).strftime("%b-%Y"), start_date=date(y, m, 1),
                                end_date=date(y, m, last), status=PeriodStatus.OPEN))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    db.flush()
    return fy


def period_for_date(db: Session, company_id: int, d: date, *, lock: bool = False) -> AccountingPeriod:
    stmt = select(AccountingPeriod).where(AccountingPeriod.company_id == company_id,
                                          AccountingPeriod.start_date <= d, AccountingPeriod.end_date >= d)
    if lock:
        stmt = stmt.with_for_update()
    p = db.scalar(stmt)
    if p is None:
        raise PeriodClosed(f"No accounting period exists for {d.isoformat()}", code="no_period")
    return p


def assert_postable(period: AccountingPeriod, actor: Actor | None) -> None:
    if period.status == PeriodStatus.OPEN:
        return
    if period.status == PeriodStatus.SOFT_CLOSED:
        if actor is not None and actor.has("period.post_soft_closed"):
            return
        raise PeriodClosed(f"Period {period.name} is soft-closed; posting needs special authority")
    raise PeriodClosed(f"Period {period.name} is {period.status.value}; posting is not allowed")


ALLOWED_TRANSITIONS = {
    (PeriodStatus.OPEN, PeriodStatus.SOFT_CLOSED): "period.manage",
    (PeriodStatus.SOFT_CLOSED, PeriodStatus.OPEN): "period.manage",
    (PeriodStatus.OPEN, PeriodStatus.CLOSED): "period.close",
    (PeriodStatus.SOFT_CLOSED, PeriodStatus.CLOSED): "period.close",
    (PeriodStatus.CLOSED, PeriodStatus.OPEN): "period.reopen",
    (PeriodStatus.CLOSED, PeriodStatus.SOFT_CLOSED): "period.reopen",
    (PeriodStatus.CLOSED, PeriodStatus.LOCKED): "period.lock",
}


def change_status(db: Session, period_id: int, new_status: PeriodStatus, actor: Actor, reason: str | None,
                  *, _skip_checks: bool = False) -> AccountingPeriod:
    period = db.scalar(select(AccountingPeriod).where(AccountingPeriod.id == period_id).with_for_update())
    if period is None:
        raise NotFound("Period not found")
    old = period.status
    if old == new_status:
        return period
    perm = ALLOWED_TRANSITIONS.get((old, new_status))
    if perm is None:
        raise Conflict(f"Cannot change period {period.name} from {old.value} to {new_status.value}")
    actor.require(perm)
    if perm in ("period.reopen", "period.lock") and not (reason and reason.strip()):
        raise ValidationFailed("A reason is required to reopen or lock a period")
    period.status = new_status
    period.status_changed_by_id = actor.id
    period.status_changed_at = utcnow()
    db.add(PeriodStatusLog(period_id=period.id, from_status=old.value, to_status=new_status.value,
                           user_id=actor.id, reason=reason))
    record(db, actor, f"period.{new_status.value.lower()}", "accounting_period", period.id,
           {"status": old.value}, {"status": new_status.value}, notes=reason)
    return period
