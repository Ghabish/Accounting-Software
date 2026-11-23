"""Double-entry accounting engine.

Every module (manual journals, AP, AR, banking, assets, cinema, opening balances,
year-end) creates journals through ``create_journal`` and posts them through
``post_journal``.  Nothing else writes posted ledger lines.

Rules enforced here (see documentation/03_ACCOUNTING_WORKFLOWS.md):
  * total debit = total credit > 0; every line one-sided and positive
  * level-4, active, in-date accounts only
  * site, cost-centre, party, intercompany and extra-dimension rules per account
  * manual-journal permission per account (ALLOWED / RESTRICTED / NOT_ALLOWED)
  * posting date inside an OPEN period (soft-closed needs special authority)
  * abnormal-balance BLOCK accounts cannot be driven to the wrong side
  * posted journals are immutable; corrections by reversal only
  * gapless numbers assigned at posting; duplicate system postings rejected
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.accounting.models import (
    AbnormalBalance, Account, ControlType, CostCentreRule, DocStatus, FiscalYear, JournalEntry, JournalLine,
    JournalLineDimension, JournalType, ManualJournal, PartyType, Rule, SourceModule,
)
from backend.accounting.numbering import next_number
from backend.accounting.periods import assert_postable, period_for_date
from backend.audit.service import record
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.money import ZERO, money
from backend.database.base import utcnow
from backend.masters.models import (
    AccountDimensionRule, CostCentre, CostCentreFunction, DimensionRule, DimensionValue, Employee, Site,
)


@dataclass
class LineInput:
    account_id: int
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    site_id: int | None = None
    cost_centre_id: int | None = None
    supplier_id: int | None = None
    customer_id: int | None = None
    employee_id: int | None = None
    partner_company_id: int | None = None
    description: str | None = None
    reference: str | None = None
    tax_code_id: int | None = None
    tax_base: Decimal | None = None
    tax_rate: Decimal | None = None
    dimensions: dict[int, int] = field(default_factory=dict)  # dimension_type_id -> dimension_value_id


class _Cache:
    """Per-call lookups so validating 1,000 lines does not issue 1,000 queries per entity."""

    def __init__(self, db: Session):
        self.db = db
        self.accounts: dict[int, Account] = {}
        self.sites: dict[int, Site] = {}
        self.ccs: dict[int, CostCentre] = {}
        self.dim_rules: dict[int, dict[int, DimensionRule]] = {}

    def account(self, aid: int) -> Account | None:
        if aid not in self.accounts:
            self.accounts[aid] = self.db.get(Account, aid)
        return self.accounts[aid]

    def site(self, sid: int) -> Site | None:
        if sid not in self.sites:
            self.sites[sid] = self.db.get(Site, sid)
        return self.sites[sid]

    def cc(self, cid: int) -> CostCentre | None:
        if cid not in self.ccs:
            self.ccs[cid] = self.db.get(CostCentre, cid)
        return self.ccs[cid]

    def rules(self, aid: int) -> dict[int, DimensionRule]:
        if aid not in self.dim_rules:
            rows = self.db.scalars(select(AccountDimensionRule).where(AccountDimensionRule.account_id == aid)).all()
            self.dim_rules[aid] = {r.dimension_type_id: r.rule for r in rows}
        return self.dim_rules[aid]


# ---------------------------------------------------------------- validation
def validate_lines(db: Session, company_id: int, lines: list[LineInput], *, manual: bool,
                   actor: Actor | None, txn_date: date) -> list[str]:
    """Raise ValidationFailed listing every problem; return non-blocking warnings."""
    errors: list[str] = []
    warnings: list[str] = []
    if len(lines) < 2:
        errors.append("A journal needs at least two lines")
    cache = _Cache(db)
    total_dr = total_cr = ZERO
    for i, ln in enumerate(lines, start=1):
        p = f"Line {i}: "
        dr, cr = money(ln.debit or 0), money(ln.credit or 0)
        ln.debit, ln.credit = dr, cr
        if dr < 0 or cr < 0:
            errors.append(p + "negative amounts are not allowed")
        if dr > 0 and cr > 0:
            errors.append(p + "a line cannot have both a debit and a credit")
        if dr == 0 and cr == 0:
            errors.append(p + "amount is zero")
        total_dr += dr
        total_cr += cr
        acc = cache.account(ln.account_id) if ln.account_id else None
        if acc is None:
            errors.append(p + "account not found")
            continue
        an = f"{acc.code} {acc.name}"
        if not acc.is_postable or acc.level != 4:
            errors.append(p + f"{an} is a group account and cannot be posted to")
        if not acc.is_active:
            errors.append(p + f"{an} is inactive")
        if (acc.effective_from and txn_date < acc.effective_from) or (acc.effective_to and txn_date > acc.effective_to):
            errors.append(p + f"{an} is not effective on {txn_date.isoformat()}")
        # ---- site
        if ln.site_id is not None:
            site = cache.site(ln.site_id)
            if site is None or site.company_id != company_id:
                errors.append(p + "site not found for this company")
            elif not site.is_active:
                errors.append(p + f"site {site.code} is inactive")
            elif actor is not None and not actor.can_site(site.id):
                errors.append(p + f"you are not authorised for site {site.code}")
        if acc.site_rule == Rule.REQ and ln.site_id is None:
            errors.append(p + f"site is mandatory for {an}")
        if acc.site_rule == Rule.NONE and ln.site_id is not None:
            errors.append(p + f"site is not allowed on {an}")
        # ---- cost centre
        cc = cache.cc(ln.cost_centre_id) if ln.cost_centre_id else None
        if ln.cost_centre_id and (cc is None or cc.company_id != company_id):
            errors.append(p + "cost centre not found for this company")
            cc = None
        if cc is not None and cc.function == CostCentreFunction.NOT_PL:
            ln.cost_centre_id, cc = None, None  # 000000 means "no cost centre"
        if cc is not None and (not cc.is_active or not cc.is_postable):
            errors.append(p + f"cost centre {cc.code} is inactive or not postable")
        rule = acc.cost_centre_rule
        if rule == CostCentreRule.BS and cc is not None:
            errors.append(p + f"{an} is a balance sheet account: cost centre must be blank / 000000")
        elif rule == CostCentreRule.LOC and cc is not None and cc.function == CostCentreFunction.COMPANY_LEVEL:
            errors.append(p + f"company-level cost centre {cc.code} is not allowed on {an}")
        elif rule == CostCentreRule.REQ:
            if cc is None:
                errors.append(p + f"cost centre is mandatory for {an}")
            elif cc.function == CostCentreFunction.COMPANY_LEVEL:
                errors.append(p + f"{an} needs a department / operating cost centre, not company level {cc.code}")
        elif rule == CostCentreRule.CORP and (cc is None or cc.function != CostCentreFunction.COMPANY_LEVEL):
            errors.append(p + f"{an} must use the company-level cost centre (090101)")
        # ---- party
        parties = {PartyType.SUPPLIER: ln.supplier_id, PartyType.CUSTOMER: ln.customer_id,
                   PartyType.EMPLOYEE: ln.employee_id}
        given = [t for t, v in parties.items() if v]
        if len(given) > 1:
            errors.append(p + "only one party (supplier, customer or employee) per line")
        if acc.party_rule == Rule.REQ and parties.get(acc.party_type) is None:
            errors.append(p + f"{acc.party_type.value.lower()} code is mandatory on {an}")
        if acc.party_rule == Rule.NONE and given:
            errors.append(p + f"a party code is not allowed on {an}")
        if given and acc.party_type != PartyType.NONE and given[0] != acc.party_type:
            errors.append(p + f"{an} takes a {acc.party_type.value.lower()} code, not {given[0].value.lower()}")
        if ln.supplier_id:
            from backend.ap.models import Supplier
            sup = db.get(Supplier, ln.supplier_id)
            if sup is None:
                errors.append(p + "supplier not found")
            elif not sup.is_active:
                errors.append(p + f"supplier {sup.code} is inactive")
        if ln.customer_id:
            from backend.ar.models import Customer
            cus = db.get(Customer, ln.customer_id)
            if cus is None:
                errors.append(p + "customer not found")
            elif not cus.is_active:
                errors.append(p + f"customer {cus.code} is inactive")
        if ln.employee_id:
            emp = db.get(Employee, ln.employee_id)
            if emp is None or not emp.is_active:
                errors.append(p + "employee not found or inactive")
        # ---- intercompany
        if acc.is_intercompany:
            if not ln.partner_company_id:
                errors.append(p + f"partner company is mandatory on intercompany account {an}")
            elif ln.partner_company_id == company_id:
                errors.append(p + "partner company cannot be the posting company")
        # ---- extra dimensions
        rules = cache.rules(acc.id)
        for type_id, value_id in (ln.dimensions or {}).items():
            dv = db.get(DimensionValue, value_id)
            if dv is None or dv.dimension_type_id != int(type_id):
                errors.append(p + "dimension value does not belong to its dimension type")
            elif not dv.is_active:
                errors.append(p + f"dimension value {dv.code} is inactive")
            if rules.get(int(type_id)) == DimensionRule.NONE:
                errors.append(p + f"dimension {type_id} is not allowed on {an}")
        for type_id, r in rules.items():
            if r == DimensionRule.REQ and type_id not in {int(k) for k in (ln.dimensions or {})}:
                errors.append(p + f"dimension {type_id} is mandatory on {an}")
        # ---- manual journal control
        if manual:
            if acc.manual_journal == ManualJournal.NOT_ALLOWED:
                errors.append(p + f"{an} does not accept manual journals")
            restricted = acc.manual_journal == ManualJournal.RESTRICTED or acc.control_type in (
                ControlType.AP_CONTROL, ControlType.AR_CONTROL)
            if restricted and (actor is None or not actor.has("journal.restricted")):
                errors.append(p + f"{an} is restricted: manual journals need Finance Controller authority")
    total_dr, total_cr = money(total_dr), money(total_cr)
    if total_dr != total_cr:
        errors.append(f"Journal is not balanced: debits {total_dr:,.2f} vs credits {total_cr:,.2f}")
    if total_dr == 0:
        errors.append("Journal total is zero")
    if errors:
        raise ValidationFailed("Journal validation failed", code="journal_invalid", details=errors)
    return warnings


# ---------------------------------------------------------------- creation
def create_journal(db: Session, *, company_id: int, journal_type: JournalType, transaction_date: date,
                   description: str, lines: list[LineInput], actor: Actor | None,
                   posting_date: date | None = None, reference: str | None = None,
                   source_module: SourceModule = SourceModule.MANUAL, source_type: str | None = None,
                   source_id: int | None = None, source_key: str | None = None, is_system: bool = False,
                   is_accrual: bool = False, auto_reverse_date: date | None = None,
                   reversal_of_id: int | None = None) -> JournalEntry:
    if not description or not description.strip():
        raise ValidationFailed("Journal description (narration) is required")
    manual = source_module == SourceModule.MANUAL and not is_system
    posting_date = posting_date or transaction_date
    validate_lines(db, company_id, lines, manual=manual, actor=actor, txn_date=posting_date)
    if source_key and db.scalar(select(JournalEntry.id).where(JournalEntry.source_key == source_key)):
        raise Conflict(f"A journal already exists for source {source_key} (duplicate posting prevented)",
                       code="duplicate_posting")
    je = JournalEntry(company_id=company_id, journal_type=journal_type, transaction_date=transaction_date,
                      posting_date=posting_date, description=description.strip(), reference=reference,
                      source_module=source_module, source_type=source_type, source_id=source_id,
                      source_key=source_key, status=DocStatus.DRAFT, is_system=is_system, is_accrual=is_accrual,
                      auto_reverse_date=auto_reverse_date, reversal_of_id=reversal_of_id,
                      created_by_id=actor.id if actor else None)
    _set_lines(je, lines)
    db.add(je)
    db.flush()
    record(db, actor, "journal.create", "journal", je.id, None,
           {"type": journal_type.value, "total": str(je.total_debit), "description": je.description})
    return je


def _set_lines(je: JournalEntry, lines: Iterable[LineInput]) -> None:
    je.lines.clear()
    tdr = tcr = ZERO
    for n, ln in enumerate(lines, start=1):
        jl = JournalLine(line_no=n, account_id=ln.account_id, site_id=ln.site_id, cost_centre_id=ln.cost_centre_id,
                         supplier_id=ln.supplier_id, customer_id=ln.customer_id, employee_id=ln.employee_id,
                         partner_company_id=ln.partner_company_id, description=ln.description,
                         reference=ln.reference, debit=money(ln.debit), credit=money(ln.credit),
                         tax_code_id=ln.tax_code_id, tax_base=ln.tax_base, tax_rate=ln.tax_rate)
        jl.dimensions = [JournalLineDimension(dimension_type_id=int(t), dimension_value_id=int(v))
                         for t, v in (ln.dimensions or {}).items()]
        je.lines.append(jl)
        tdr += jl.debit
        tcr += jl.credit
    je.total_debit, je.total_credit = money(tdr), money(tcr)


def replace_lines(db: Session, je: JournalEntry, lines: list[LineInput], actor: Actor | None) -> None:
    """Edit a non-posted journal (returns it to DRAFT and clears approvals)."""
    if je.status not in (DocStatus.DRAFT, DocStatus.SUBMITTED, DocStatus.CHECKED, DocStatus.APPROVED):
        raise Conflict("Only unposted journals can be edited")
    validate_lines(db, je.company_id, lines, manual=je.source_module == SourceModule.MANUAL and not je.is_system,
                   actor=actor, txn_date=je.posting_date)
    _set_lines(je, lines)
    je.status = DocStatus.DRAFT
    je.submitted_by_id = je.checked_by_id = je.approved_by_id = None
    db.flush()


def lines_from_journal(je: JournalEntry) -> list[LineInput]:
    return [LineInput(account_id=l.account_id, debit=l.debit, credit=l.credit, site_id=l.site_id,
                      cost_centre_id=l.cost_centre_id, supplier_id=l.supplier_id, customer_id=l.customer_id,
                      employee_id=l.employee_id, partner_company_id=l.partner_company_id,
                      description=l.description, reference=l.reference, tax_code_id=l.tax_code_id,
                      tax_base=l.tax_base, tax_rate=l.tax_rate,
                      dimensions={d.dimension_type_id: d.dimension_value_id for d in l.dimensions})
            for l in je.lines]


# ---------------------------------------------------------------- posting
def _check_abnormal(db: Session, je: JournalEntry) -> None:
    """BLOCK accounts may not end on their abnormal side (checked per account and site)."""
    nets: dict[tuple[int, int | None], Decimal] = {}
    for l in je.lines:
        nets[(l.account_id, l.site_id)] = nets.get((l.account_id, l.site_id), ZERO) + l.debit - l.credit
    for (aid, sid), net in nets.items():
        acc = db.get(Account, aid)
        if acc.abnormal_balance != AbnormalBalance.BLOCK:
            continue
        q = select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
            JournalLine.account_id == aid, JournalLine.is_posted.is_(True))
        if sid is not None:
            q = q.where(JournalLine.site_id == sid)
        bal = Decimal(db.scalar(q) or 0) + net
        if acc.sign * bal < 0:
            raise ValidationFailed(
                f"Posting would leave {acc.code} {acc.name} with an abnormal balance ({bal:,.2f})",
                code="abnormal_balance")


def post_journal(db: Session, journal_id: int, actor: Actor | None, *, require_approved: bool = True) -> JournalEntry:
    """Post inside the caller's transaction. Locks the journal and its period row."""
    je = db.scalar(select(JournalEntry).where(JournalEntry.id == journal_id).with_for_update())
    if je is None:
        raise NotFound("Journal not found")
    if je.status == DocStatus.POSTED:
        raise Conflict(f"Journal {je.number} is already posted", code="already_posted")
    allowed = (DocStatus.APPROVED,) if require_approved else (DocStatus.DRAFT, DocStatus.SUBMITTED,
                                                               DocStatus.CHECKED, DocStatus.APPROVED)
    if je.status not in allowed:
        raise Conflict(f"Journal must be {'APPROVED' if require_approved else 'unposted'} to post "
                       f"(current status {je.status.value})", code="not_approved")
    period = period_for_date(db, je.company_id, je.posting_date, lock=True)
    assert_postable(period, actor)
    db.refresh(je)  # make sure lines are current after the lock
    validate_lines(db, je.company_id, lines_from_journal(je),
                   manual=je.source_module == SourceModule.MANUAL and not je.is_system,
                   actor=actor, txn_date=je.posting_date)
    _check_abnormal(db, je)
    fy = db.get(FiscalYear, period.fiscal_year_id)
    fy_tag = f"{str(fy.start_date.year)[2:]}{str(fy.end_date.year)[2:]}"
    je.number = next_number(db, je.company_id, f"{je.journal_type.value}-{fy.code}",
                            f"{je.journal_type.value}-{fy_tag}-")
    je.period_id = period.id
    je.status = DocStatus.POSTED
    je.posted_by_id = actor.id if actor else None
    je.posted_at = utcnow()
    for l in je.lines:
        l.company_id = je.company_id
        l.posting_date = je.posting_date
        l.period_id = period.id
        l.source_module = je.source_module.value
        l.is_posted = True
    db.flush()
    if je.reversal_of_id:
        orig = db.get(JournalEntry, je.reversal_of_id)
        orig.status = DocStatus.REVERSED
        orig.reversed_by_id = actor.id if actor else None
        orig.reversed_at = utcnow()
        db.flush()
    record(db, actor, "journal.post", "journal", je.id, None,
           {"number": je.number, "total": str(je.total_debit), "posting_date": je.posting_date.isoformat()})
    return je


def create_and_post(db: Session, actor: Actor | None, **kwargs) -> JournalEntry:
    """System journals (already authorised by their source document's workflow)."""
    kwargs.setdefault("is_system", True)
    je = create_journal(db, actor=actor, **kwargs)
    return post_journal(db, je.id, actor, require_approved=False)


def create_reversal(db: Session, journal_id: int, actor: Actor | None, reversal_date: date, reason: str,
                    *, post: bool = False) -> JournalEntry:
    orig = db.get(JournalEntry, journal_id)
    if orig is None:
        raise NotFound("Journal not found")
    if orig.status != DocStatus.POSTED:
        raise Conflict("Only posted journals can be reversed", code="not_posted")
    if not reason or not reason.strip():
        raise ValidationFailed("A reason is required for a reversal")
    pending = db.scalar(select(JournalEntry.id).where(JournalEntry.reversal_of_id == orig.id,
                                                      JournalEntry.status.not_in([DocStatus.CANCELLED])))
    if pending:
        raise Conflict("A reversal for this journal already exists", code="already_reversed")
    lines = lines_from_journal(orig)
    for ln in lines:
        ln.debit, ln.credit = ln.credit, ln.debit
    rev = create_journal(db, company_id=orig.company_id, journal_type=orig.journal_type,
                         transaction_date=reversal_date, posting_date=reversal_date,
                         description=f"Reversal of {orig.number}: {reason.strip()}", lines=lines, actor=actor,
                         reference=orig.number, source_module=orig.source_module, source_type=orig.source_type,
                         source_id=orig.source_id, is_system=orig.is_system or post,
                         reversal_of_id=orig.id)
    rev.reversal_reason = reason.strip()
    record(db, actor, "journal.reverse_request", "journal", orig.id, None, {"reversal_id": rev.id, "reason": reason})
    if post:
        post_journal(db, rev.id, actor, require_approved=False)
    return rev


def account_balance(db: Session, account_id: int, as_of: date, *, site_id: int | None = None,
                    company_id: int | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
        JournalLine.account_id == account_id, JournalLine.is_posted.is_(True), JournalLine.posting_date <= as_of)
    if site_id is not None:
        q = q.where(JournalLine.site_id == site_id)
    if company_id is not None:
        q = q.where(JournalLine.company_id == company_id)
    return money(db.scalar(q) or 0)


def find_possible_duplicates(db: Session, company_id: int, posting_date: date, total: Decimal,
                             reference: str | None, exclude_id: int | None = None) -> list[JournalEntry]:
    q = select(JournalEntry).where(JournalEntry.company_id == company_id, JournalEntry.total_debit == money(total),
                                   JournalEntry.posting_date == posting_date,
                                   JournalEntry.status.not_in([DocStatus.CANCELLED]))
    if reference:
        q = select(JournalEntry).where(JournalEntry.company_id == company_id,
                                       JournalEntry.total_debit == money(total),
                                       JournalEntry.reference == reference,
                                       JournalEntry.status.not_in([DocStatus.CANCELLED]))
    if exclude_id:
        q = q.where(JournalEntry.id != exclude_id)
    return list(db.scalars(q.limit(10)).all())
