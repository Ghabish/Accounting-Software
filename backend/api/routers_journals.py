"""Journal vouchers: create / edit / workflow / reverse / list / drill-down; recurring journals."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, or_, select

from backend.accounting import service as jsvc
from backend.accounting.models import (
    Account, DocStatus, JournalEntry, JournalLine, JournalLineDimension, RecurringJournal,
)
from backend.ap.models import Supplier
from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import jsonable, page, row, rows
from backend.ar.models import Customer
from backend.authentication.models import User
from backend.core.exceptions import NotFound
from backend.core.pagination import paginate
from backend.masters.models import CostCentre, DimensionValue, Employee, Site
from backend.workflow.engine import history

router = APIRouter(prefix="/api/journals", tags=["journals"])


class LineIn(BaseModel):
    account_id: int
    debit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    credit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    site_id: int | None = None
    cost_centre_id: int | None = None
    supplier_id: int | None = None
    customer_id: int | None = None
    employee_id: int | None = None
    partner_company_id: int | None = None
    description: str | None = None
    reference: str | None = None
    tax_code_id: int | None = None
    dimensions: dict[str, int | None] = {}


class JournalIn(BaseModel):
    transaction_date: date
    posting_date: date | None = None
    description: str = Field(min_length=3, max_length=2000)
    reference: str | None = Field(default=None, max_length=120)
    is_accrual: bool = False
    auto_reverse_date: date | None = None
    lines: list[LineIn] = Field(min_length=2, max_length=2000)


class ActionIn(BaseModel):
    comment: str | None = None


class ReverseIn(BaseModel):
    reversal_date: date
    reason: str = Field(min_length=3)


def journal_detail(db, je: JournalEntry) -> dict:
    users = {u.id: u.username for u in db.scalars(select(User).where(User.id.in_(
        [x for x in (je.created_by_id, je.submitted_by_id, je.checked_by_id, je.approved_by_id, je.posted_by_id) if x])))}
    lines = []
    for l in je.lines:
        acc = db.get(Account, l.account_id)
        site = db.get(Site, l.site_id) if l.site_id else None
        cc = db.get(CostCentre, l.cost_centre_id) if l.cost_centre_id else None
        party = None
        if l.supplier_id:
            s = db.get(Supplier, l.supplier_id)
            party = {"type": "SUPPLIER", "id": s.id, "code": s.code, "name": s.name}
        elif l.customer_id:
            c = db.get(Customer, l.customer_id)
            party = {"type": "CUSTOMER", "id": c.id, "code": c.code, "name": c.name}
        elif l.employee_id:
            e = db.get(Employee, l.employee_id)
            party = {"type": "EMPLOYEE", "id": e.id, "code": e.code, "name": e.name}
        dims = []
        for d in l.dimensions:
            dv = db.get(DimensionValue, d.dimension_value_id)
            dims.append({"dimension_type_id": d.dimension_type_id, "value_id": dv.id, "code": dv.code, "name": dv.name})
        lines.append(row(l, extra={"account_code": acc.code, "account_name": acc.name,
                                   "site_code": site.code if site else None, "site_name": site.name if site else None,
                                   "cost_centre_code": cc.code if cc else None, "party": party,
                                   "dimension_values": dims}))
    reversal = db.scalar(select(JournalEntry).where(JournalEntry.reversal_of_id == je.id,
                                                     JournalEntry.status != DocStatus.CANCELLED))
    return row(je, extra={"lines": lines, "users": {str(k): v for k, v in users.items()},
                          "reversed_by_journal": {"id": reversal.id, "number": reversal.number, "status": reversal.status.value} if reversal else None,
                          "history": rows(history(db, "JOURNAL", je.id))})


@router.get("")
def list_journals(db: DB, actor: CurrentActor, company_id: CompanyId,
                  date_from: date | None = None, date_to: date | None = None, journal_type: str | None = None,
                  status: str | None = None, q: str | None = None, number: str | None = None,
                  account_id: int | None = None, site_id: int | None = None, cost_centre_id: int | None = None,
                  supplier_id: int | None = None, customer_id: int | None = None, created_by_id: int | None = None,
                  amount_min: Decimal | None = None, amount_max: Decimal | None = None,
                  source_module: str | None = None, page_no: int = Query(1, alias="page"), page_size: int = 50):
    actor.require("journal.view")
    stmt = select(JournalEntry).where(JournalEntry.company_id == company_id)
    if date_from:
        stmt = stmt.where(JournalEntry.posting_date >= date_from)
    if date_to:
        stmt = stmt.where(JournalEntry.posting_date <= date_to)
    if journal_type:
        stmt = stmt.where(JournalEntry.journal_type == journal_type)
    if status:
        stmt = stmt.where(JournalEntry.status.in_(status.split(",")))
    if source_module:
        stmt = stmt.where(JournalEntry.source_module == source_module)
    if number:
        stmt = stmt.where(JournalEntry.number.ilike(f"%{number}%"))
    if q:
        stmt = stmt.where(or_(JournalEntry.description.ilike(f"%{q}%"), JournalEntry.reference.ilike(f"%{q}%"),
                              JournalEntry.number.ilike(f"%{q}%")))
    if created_by_id:
        stmt = stmt.where(JournalEntry.created_by_id == created_by_id)
    if amount_min is not None:
        stmt = stmt.where(JournalEntry.total_debit >= amount_min)
    if amount_max is not None:
        stmt = stmt.where(JournalEntry.total_debit <= amount_max)
    line_conds = []
    for col, val in ((JournalLine.account_id, account_id), (JournalLine.site_id, site_id),
                     (JournalLine.cost_centre_id, cost_centre_id), (JournalLine.supplier_id, supplier_id),
                     (JournalLine.customer_id, customer_id)):
        if val:
            line_conds.append(col == val)
    if actor.site_ids is not None:  # site-restricted users only see journals touching their sites
        line_conds.append(JournalLine.site_id.in_(actor.site_ids))
    if line_conds:
        stmt = stmt.where(exists().where(and_(JournalLine.journal_id == JournalEntry.id, *line_conds)))
    stmt = stmt.order_by(JournalEntry.posting_date.desc(), JournalEntry.id.desc())
    items, total = paginate(db, stmt, page_no, page_size)
    return page(rows(items), total, page_no, page_size)


@router.get("/{journal_id}")
def get_journal(journal_id: int, db: DB, actor: CurrentActor):
    actor.require("journal.view")
    je = jsvc.get_manual(db, journal_id)
    if actor.site_ids is not None and not any(l.site_id in actor.site_ids for l in je.lines):
        raise NotFound("Journal not found")
    return journal_detail(db, je)


@router.post("", status_code=201)
def create(body: JournalIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    je, warnings = jsvc.create_manual(db, actor, company_id, transaction_date=body.transaction_date,
                                      posting_date=body.posting_date, description=body.description,
                                      reference=body.reference, is_accrual=body.is_accrual,
                                      auto_reverse_date=body.auto_reverse_date,
                                      lines=jsvc.to_line_inputs([l.model_dump() for l in body.lines]))
    db.commit()
    out = journal_detail(db, je)
    out["warnings"] = warnings
    return out


@router.put("/{journal_id}")
def update(journal_id: int, body: JournalIn, db: DB, actor: CurrentActor):
    je = jsvc.get_manual(db, journal_id)
    jsvc.update_manual(db, actor, je, description=body.description, transaction_date=body.transaction_date,
                       posting_date=body.posting_date, reference=body.reference, is_accrual=body.is_accrual,
                       auto_reverse_date=body.auto_reverse_date,
                       lines=jsvc.to_line_inputs([l.model_dump() for l in body.lines]))
    db.commit()
    return journal_detail(db, je)


@router.post("/{journal_id}/{action}")
def workflow_action(journal_id: int, action: str, body: ActionIn, db: DB, actor: CurrentActor):
    if action not in ("submit", "check", "approve", "reject", "cancel", "post"):
        raise NotFound("Unknown action")
    je = jsvc.get_manual(db, journal_id)
    jsvc.act(db, actor, je, action, body.comment)
    db.commit()
    return journal_detail(db, je)


@router.post("/{journal_id}/reverse/request")
def reverse(journal_id: int, body: ReverseIn, db: DB, actor: CurrentActor):
    je = jsvc.get_manual(db, journal_id)
    rev = jsvc.reverse(db, actor, je, body.reversal_date, body.reason)
    db.commit()
    return journal_detail(db, rev)


# ------------------------------------------------------------------ recurring
class RecurringIn(BaseModel):
    name: str
    description: str
    frequency: str = "MONTHLY"
    next_run_date: date
    end_date: date | None = None
    auto_submit: bool = False
    is_active: bool = True
    lines: list[LineIn] = Field(min_length=2)


rec_router = APIRouter(prefix="/api/recurring-journals", tags=["journals"])


@rec_router.get("")
def rec_list(db: DB, actor: CurrentActor, company_id: CompanyId):
    actor.require("journal.view")
    return [row(r, extra={"lines": rows(r.lines)}) for r in
            db.scalars(select(RecurringJournal).where(RecurringJournal.company_id == company_id)).all()]


@rec_router.post("", status_code=201)
def rec_create(body: RecurringIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    rj = jsvc.save_recurring(db, actor, company_id, body.model_dump())
    db.commit()
    return row(rj, extra={"lines": rows(rj.lines)})


@rec_router.put("/{rj_id}")
def rec_update(rj_id: int, body: RecurringIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    rj = db.get(RecurringJournal, rj_id)
    if rj is None:
        raise NotFound("Recurring journal not found")
    rj = jsvc.save_recurring(db, actor, company_id, body.model_dump(), rj)
    db.commit()
    return row(rj, extra={"lines": rows(rj.lines)})


class RunIn(BaseModel):
    as_of: date


@rec_router.post("/run")
def rec_run(body: RunIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    created = jsvc.run_recurring(db, actor, company_id, body.as_of)
    db.commit()
    return {"created": [{"id": j.id, "description": j.description, "status": j.status.value} for j in created]}


# expose both routers
export_router = rec_router
