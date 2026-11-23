"""Tax engine: effective-dated rate selection, calculation, slabs and tax transaction records.

Rates are data (tax_rates table) - never hard-coded.  Selection (as in the reference
workbook): tax code + payee type (or ALL) + ATL status (or ALL) + effective date
(+ optional site-specific rate), most specific match wins.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.accounting.models import JournalEntry, JournalLine
from backend.core.exceptions import ValidationFailed
from backend.core.money import ZERO, money
from backend.tax.models import TaxCode, TaxRate, TaxSlab, TaxTransaction, TaxType

ROUND_TO_RUPEE = {TaxType.WHT_DEDUCTED, TaxType.ST_WITHHELD}

DIRECTION = {
    TaxType.SALES_TAX_OUTPUT: "OUTPUT", TaxType.PST_OUTPUT: "OUTPUT", TaxType.ENTERTAINMENT_DUTY: "OUTPUT",
    TaxType.SALES_TAX_INPUT: "INPUT", TaxType.PST_INPUT: "INPUT",
    TaxType.WHT_DEDUCTED: "WITHHELD", TaxType.ST_WITHHELD: "WITHHELD",
    TaxType.WHT_SUFFERED: "SUFFERED", TaxType.ADVANCE_TAX: "SUFFERED",
}


@dataclass
class TaxCalc:
    tax_code: TaxCode
    rate: Decimal
    base: Decimal
    amount: Decimal
    tax_rate_id: int | None
    overridden: bool = False
    reason: str | None = None


def get_code(db: Session, tax_code_id: int | None) -> TaxCode | None:
    if not tax_code_id:
        return None
    tc = db.get(TaxCode, tax_code_id)
    if tc is None:
        raise ValidationFailed("Invalid tax code")
    if not tc.is_active:
        raise ValidationFailed(f"Tax code {tc.code} is inactive")
    return tc


def find_rate(db: Session, tax_code_id: int, on_date: date, payee_type: str = "ALL", atl_status: str = "ALL",
              site_id: int | None = None, transaction_type: str | None = None) -> TaxRate | None:
    q = select(TaxRate).where(TaxRate.tax_code_id == tax_code_id, TaxRate.is_active.is_(True),
                              TaxRate.effective_from <= on_date,
                              or_(TaxRate.effective_to.is_(None), TaxRate.effective_to >= on_date))
    best, best_score = None, -1
    for r in db.scalars(q).all():
        if r.payee_type not in ("ALL", payee_type) or r.atl_status not in ("ALL", atl_status):
            continue
        if r.site_id is not None and r.site_id != site_id:
            continue
        if r.transaction_type and r.transaction_type != transaction_type:
            continue
        score = (8 if r.site_id else 0) + (4 if r.payee_type != "ALL" else 0) + (2 if r.atl_status != "ALL" else 0) \
            + (1 if r.transaction_type else 0)
        if score > best_score or (score == best_score and best is not None and r.effective_from > best.effective_from):
            best, best_score = r, score
    return best


def round_tax(tc: TaxCode, amount: Decimal) -> Decimal:
    if tc.tax_type in ROUND_TO_RUPEE:
        return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(Decimal("0.01"))
    return money(amount)


def compute(db: Session, tax_code_id: int | None, base: Decimal, on_date: date, *, payee_type: str = "ALL",
            atl_status: str = "ALL", site_id: int | None = None, override_rate: Decimal | None = None,
            reason: str | None = None, inclusive: bool = False) -> TaxCalc | None:
    """Tax on ``base``.  ``inclusive=True`` means base already contains the tax (POS prices)."""
    tc = get_code(db, tax_code_id)
    if tc is None:
        return None
    if override_rate is not None:
        if not reason or not reason.strip():
            raise ValidationFailed(f"A reason is required to override the {tc.code} rate")
        rate, rid, over = Decimal(str(override_rate)), None, True
    else:
        r = find_rate(db, tc.id, on_date, payee_type, atl_status, site_id)
        if r is None:
            raise ValidationFailed(f"No {tc.code} rate effective on {on_date.isoformat()} for payee {payee_type}/{atl_status}",
                                   code="no_tax_rate")
        rate, rid, over = r.rate, r.id, False
    base = money(base)
    if inclusive:
        net = money(base / (1 + rate)) if rate else base
        amount = base - net
        return TaxCalc(tc, rate, net, amount, rid, over, reason)
    return TaxCalc(tc, rate, base, round_tax(tc, base * rate), rid, over, reason)


def split_inclusive(db: Session, gross: Decimal, tax_code_ids: list[int], on_date: date,
                    site_id: int | None = None) -> tuple[Decimal, list[TaxCalc]]:
    """Split a tax-inclusive amount into net + one or more taxes levied on the same net base."""
    calcs = []
    total_rate = ZERO
    rates = []
    for tid in tax_code_ids:
        tc = get_code(db, tid)
        r = find_rate(db, tc.id, on_date, site_id=site_id)
        if r is None:
            raise ValidationFailed(f"No {tc.code} rate effective on {on_date.isoformat()}", code="no_tax_rate")
        rates.append((tc, r))
        total_rate += r.rate
    gross = money(gross)
    net = money(gross / (1 + total_rate)) if total_rate else gross
    allocated = ZERO
    for i, (tc, r) in enumerate(rates):
        amt = money(net * r.rate) if i < len(rates) - 1 else gross - net - allocated
        allocated += amt
        calcs.append(TaxCalc(tc, r.rate, net, amt, r.id))
    return net, calcs


def slab_tax(db: Session, tax_code_id: int, annual_amount: Decimal, on_date: date) -> tuple[Decimal, Decimal]:
    """(annual tax, effective rate) from the slab table - used for rent to individuals (s.155) and salary (s.149)."""
    slabs = db.scalars(select(TaxSlab).where(TaxSlab.tax_code_id == tax_code_id, TaxSlab.effective_from <= on_date,
                                             or_(TaxSlab.effective_to.is_(None), TaxSlab.effective_to >= on_date))
                       .order_by(TaxSlab.amount_from)).all()
    if not slabs:
        raise ValidationFailed("No slab table for this tax code and date")
    amt = money(annual_amount)
    for s in slabs:
        if amt >= s.amount_from and (s.amount_to is None or amt <= s.amount_to):
            threshold = s.amount_from - 1 if s.amount_from > 0 else ZERO
            tax = money(s.fixed_tax + max(amt - threshold, ZERO) * s.rate)
            return tax, (tax / amt).quantize(Decimal("0.000001")) if amt else ZERO
    return ZERO, ZERO


def record(db: Session, *, company_id: int, calc: TaxCalc, journal: JournalEntry, journal_line: JournalLine | None,
           source_type: str, source_id: int | None, transaction_date: date, supplier=None, customer=None,
           site_id: int | None = None, document_ref: str | None = None, sign: int = 1) -> TaxTransaction:
    party = supplier or customer
    tt = TaxTransaction(company_id=company_id, tax_code_id=calc.tax_code.id, tax_rate_id=calc.tax_rate_id,
                        journal_id=journal.id, journal_line_id=journal_line.id if journal_line else None,
                        source_type=source_type, source_id=source_id, transaction_date=transaction_date,
                        period_id=journal.period_id, direction=DIRECTION[calc.tax_code.tax_type],
                        supplier_id=supplier.id if supplier else None, customer_id=customer.id if customer else None,
                        site_id=site_id, party_ntn=getattr(party, "ntn", None) or getattr(party, "cnic", None),
                        party_name=getattr(party, "name", None), document_ref=document_ref,
                        base_amount=money(calc.base) * sign, rate=calc.rate, tax_amount=money(calc.amount) * sign,
                        rate_overridden=calc.overridden, override_reason=calc.reason, is_reversal=sign < 0)
    db.add(tt)
    return tt


def reverse_for_journal(db: Session, original_journal_id: int, reversal: JournalEntry) -> int:
    """Create negative tax transactions mirroring those of a reversed journal."""
    n = 0
    for t in db.scalars(select(TaxTransaction).where(TaxTransaction.journal_id == original_journal_id)).all():
        db.add(TaxTransaction(company_id=t.company_id, tax_code_id=t.tax_code_id, tax_rate_id=t.tax_rate_id,
                              journal_id=reversal.id, source_type=t.source_type, source_id=t.source_id,
                              transaction_date=reversal.posting_date, period_id=reversal.period_id,
                              direction=t.direction, supplier_id=t.supplier_id, customer_id=t.customer_id,
                              site_id=t.site_id, party_ntn=t.party_ntn, party_name=t.party_name,
                              document_ref=t.document_ref, base_amount=-t.base_amount, rate=t.rate,
                              tax_amount=-t.tax_amount, rate_overridden=t.rate_overridden,
                              override_reason=t.override_reason, is_reversal=True))
        n += 1
    return n


def line_for(journal: JournalEntry, account_id: int, tax_code_id: int | None = None) -> JournalLine | None:
    for l in journal.lines:
        if l.account_id == account_id and (tax_code_id is None or l.tax_code_id == tax_code_id):
            return l
    return None
