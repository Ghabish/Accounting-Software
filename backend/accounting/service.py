"""Manual journals (JV), accruals with auto-reversal, recurring journals."""
from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.accounting import engine
from backend.accounting.engine import LineInput
from backend.accounting.models import (
    AccountingPeriod, DocStatus, JournalEntry, JournalType, RecurringJournal, RecurringJournalLine, SourceModule,
)
from backend.accounting.periods import period_for_date
from backend.audit.models import Attachment
from backend.audit.service import record
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.database.base import utcnow
from backend.workflow import engine as wf

DOC_TYPE = "JOURNAL"


def _has_attachment(db: Session, je: JournalEntry):
    return lambda: db.scalar(select(Attachment.id).where(Attachment.entity_type == "journal",
                                                         Attachment.entity_id == je.id)) is not None


def _poster(db: Session, je: JournalEntry, actor: Actor) -> None:
    engine.post_journal(db, je.id, actor, require_approved=True)
    if je.is_accrual:
        rev_date = je.auto_reverse_date or _first_day_next_period(db, je)
        engine.create_reversal(db, je.id, actor, rev_date, "Automatic accrual reversal", post=True)


def _first_day_next_period(db: Session, je: JournalEntry) -> date:
    p = db.get(AccountingPeriod, je.period_id)
    return p.end_date + timedelta(days=1)


def spec(db: Session, je: JournalEntry) -> wf.WorkflowSpec:
    return wf.WorkflowSpec(doc_type=DOC_TYPE, perm_prefix="journal", amount=je.total_debit, site_id=None,
                           poster=_poster, has_attachment=_has_attachment(db, je))


def get_manual(db: Session, journal_id: int) -> JournalEntry:
    je = db.get(JournalEntry, journal_id)
    if je is None:
        raise NotFound("Journal not found")
    return je


def create_manual(db: Session, actor: Actor, company_id: int, *, transaction_date: date, description: str,
                  lines: list[LineInput], posting_date: date | None = None, reference: str | None = None,
                  is_accrual: bool = False, auto_reverse_date: date | None = None) -> tuple[JournalEntry, list[str]]:
    actor.require("journal.create")
    period_for_date(db, company_id, posting_date or transaction_date)  # must exist
    je = engine.create_journal(db, company_id=company_id, journal_type=JournalType.JV,
                               transaction_date=transaction_date, posting_date=posting_date, description=description,
                               lines=lines, actor=actor, reference=reference, source_module=SourceModule.MANUAL,
                               is_accrual=is_accrual, auto_reverse_date=auto_reverse_date)
    dups = engine.find_possible_duplicates(db, company_id, je.posting_date, je.total_debit, reference, exclude_id=je.id)
    warnings = [f"Possible duplicate of journal {d.number or d.id} ({d.description[:60]})" for d in dups]
    return je, warnings


def update_manual(db: Session, actor: Actor, je: JournalEntry, *, description: str | None, lines: list[LineInput],
                  transaction_date: date | None = None, posting_date: date | None = None,
                  reference: str | None = None, is_accrual: bool | None = None,
                  auto_reverse_date: date | None = None) -> JournalEntry:
    actor.require("journal.create")
    _ensure_manual(je)
    if je.status in (DocStatus.POSTED, DocStatus.REVERSED, DocStatus.CANCELLED):
        raise Conflict("Posted or cancelled journals cannot be edited; reverse instead", code="immutable")
    was = je.status
    if transaction_date:
        je.transaction_date = transaction_date
    if posting_date or transaction_date:
        je.posting_date = posting_date or transaction_date
        period_for_date(db, je.company_id, je.posting_date)
    if description:
        je.description = description
    if reference is not None:
        je.reference = reference
    if is_accrual is not None:
        je.is_accrual = is_accrual
        je.auto_reverse_date = auto_reverse_date
    engine.replace_lines(db, je, lines, actor)
    if was != DocStatus.DRAFT:
        from backend.workflow.models import WorkflowHistory
        db.add(WorkflowHistory(doc_type=DOC_TYPE, doc_id=je.id, action="edit", from_status=was.value,
                               to_status=DocStatus.DRAFT.value, user_id=actor.id,
                               comment="Edited after submission: approvals cleared"))
    record(db, actor, "journal.update", "journal", je.id, {"status": was.value}, {"total": str(je.total_debit)})
    return je


def _ensure_manual(je: JournalEntry) -> None:
    if je.source_module not in (SourceModule.MANUAL, SourceModule.RECURRING) or je.is_system:
        raise Conflict("System-generated journals are managed by their source module", code="system_journal")


def act(db: Session, actor: Actor, je: JournalEntry, action: str, comment: str | None = None) -> JournalEntry:
    _ensure_manual(je)
    wf.transition(db, je, spec(db, je), action, actor, comment)
    return je


def reverse(db: Session, actor: Actor, je: JournalEntry, reversal_date: date, reason: str) -> JournalEntry:
    actor.require("journal.reverse")
    _ensure_manual(je)
    rev = engine.create_reversal(db, je.id, actor, reversal_date, reason, post=False)
    rev.source_module = SourceModule.MANUAL
    rev.is_system = False
    return rev


# ------------------------------------------------------------------ recurring journals
def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


STEP = {"MONTHLY": 1, "QUARTERLY": 3, "YEARLY": 12}


def save_recurring(db: Session, actor: Actor, company_id: int, data: dict, rj: RecurringJournal | None = None) -> RecurringJournal:
    actor.require("journal.create")
    lines = data.pop("lines")
    if data.get("frequency", "MONTHLY") not in STEP:
        raise ValidationFailed("Frequency must be MONTHLY, QUARTERLY or YEARLY")
    li = [LineInput(**{k: v for k, v in l.items() if k != "dimensions"},
                    dimensions={int(k): int(v) for k, v in (l.get("dimensions") or {}).items()}) for l in lines]
    engine.validate_lines(db, company_id, li, manual=True, actor=actor, txn_date=data["next_run_date"])
    if rj is None:
        rj = RecurringJournal(company_id=company_id, created_by_id=actor.id)
        db.add(rj)
    for k, v in data.items():
        setattr(rj, k, v)
    rj.lines = [RecurringJournalLine(line_no=i, account_id=l.account_id, site_id=l.site_id,
                                     cost_centre_id=l.cost_centre_id, supplier_id=l.supplier_id,
                                     customer_id=l.customer_id, employee_id=l.employee_id,
                                     description=l.description, debit=l.debit, credit=l.credit,
                                     dimensions=json.dumps(l.dimensions) if l.dimensions else None)
                for i, l in enumerate(li, start=1)]
    db.flush()
    record(db, actor, "recurring_journal.save", "recurring_journal", rj.id, None, {"name": rj.name})
    return rj


def run_recurring(db: Session, actor: Actor, company_id: int, as_of: date) -> list[JournalEntry]:
    """Generate DRAFT journals for every due occurrence up to ``as_of``; they then follow the normal workflow."""
    actor.require("journal.create")
    created: list[JournalEntry] = []
    due = db.scalars(select(RecurringJournal).where(RecurringJournal.company_id == company_id,
                                                    RecurringJournal.is_active.is_(True),
                                                    RecurringJournal.next_run_date <= as_of)
                     .with_for_update()).all()
    for rj in due:
        while rj.next_run_date <= as_of and (rj.end_date is None or rj.next_run_date <= rj.end_date):
            lines = [LineInput(account_id=l.account_id, debit=l.debit, credit=l.credit, site_id=l.site_id,
                               cost_centre_id=l.cost_centre_id, supplier_id=l.supplier_id, customer_id=l.customer_id,
                               employee_id=l.employee_id, description=l.description,
                               dimensions={int(k): int(v) for k, v in json.loads(l.dimensions or "{}").items()})
                     for l in rj.lines]
            je = engine.create_journal(db, company_id=company_id, journal_type=JournalType.REC,
                                       transaction_date=rj.next_run_date,
                                       description=f"{rj.description} ({rj.next_run_date.strftime('%b-%Y')})",
                                       lines=lines, actor=actor, source_module=SourceModule.RECURRING,
                                       source_type="recurring_journal", source_id=rj.id,
                                       source_key=f"REC-{rj.id}-{rj.next_run_date.isoformat()}")
            je.recurring_journal_id = rj.id
            if rj.auto_submit:
                wf.transition(db, je, spec(db, je), "submit", actor, "Recurring journal auto-submitted")
            created.append(je)
            rj.next_run_date = _add_months(rj.next_run_date, STEP[rj.frequency])
        rj.last_run_at = utcnow()
        if rj.end_date and rj.next_run_date > rj.end_date:
            rj.is_active = False
    db.flush()
    return created


def to_line_inputs(payload: list[dict]) -> list[LineInput]:
    out = []
    for l in payload:
        dims = {int(k): int(v) for k, v in (l.get("dimensions") or {}).items() if v}
        out.append(LineInput(account_id=l["account_id"], debit=Decimal(str(l.get("debit") or 0)),
                             credit=Decimal(str(l.get("credit") or 0)), site_id=l.get("site_id"),
                             cost_centre_id=l.get("cost_centre_id"), supplier_id=l.get("supplier_id"),
                             customer_id=l.get("customer_id"), employee_id=l.get("employee_id"),
                             partner_company_id=l.get("partner_company_id"), description=l.get("description"),
                             reference=l.get("reference"), tax_code_id=l.get("tax_code_id"), dimensions=dims))
    return out
