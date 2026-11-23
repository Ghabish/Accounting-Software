"""Month-end and year-end closing."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.accounting import engine
from backend.accounting.engine import LineInput
from backend.accounting.models import (
    AbnormalBalance, Account, AccountingPeriod, DocStatus, FiscalYear, JournalEntry, JournalLine, JournalType, PeriodStatus,
    SourceModule,
)
from backend.accounting.periods import change_status
from backend.audit.service import record
from backend.closing.models import PeriodChecklistItem
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.money import ZERO, money
from backend.database.base import utcnow
from backend.masters.models import CostCentre

UNPOSTED = (DocStatus.DRAFT, DocStatus.SUBMITTED, DocStatus.CHECKED, DocStatus.APPROVED)
MANUAL_ITEMS = [
    ("ACCRUALS", "Accruals reviewed and posted (utilities, rent, film rental, payroll)", True),
    ("PREPAYMENTS", "Prepayments amortised (rent, insurance, licences)", True),
    ("INVENTORY", "F&B stock count reconciled to the ledger", False),
    ("REVENUE_REVIEW", "Revenue and collections reconciliation reviewed", True),
    ("CASH_COUNT", "Cash counts and petty cash reconciled", True),
    ("INTERCOMPANY", "Intercompany balances agreed with group companies", False),
    ("TB_REVIEW", "Trial balance and management accounts reviewed by CFO", True),
]


def _period(db: Session, period_id: int) -> AccountingPeriod:
    p = db.get(AccountingPeriod, period_id)
    if p is None:
        raise NotFound("Period not found")
    return p


def _auto_checks(db: Session, p: AccountingPeriod) -> list[tuple[str, str, bool, bool, str]]:
    """(code, title, passed, blocking, detail)"""
    from backend.ap.models import APDocument, APPayment
    from backend.ar.models import ARDocument, ARReceipt
    from backend.assets.models import AssetCategory, AssetStatus, DepreciationRun, FixedAsset
    from backend.banking.models import BankTransfer, CashBankVoucher
    from backend.banking.reconciliation import status_for_period
    from backend.cinema.models import BoxOfficeSale, CollectionBatch, FnBSale
    from backend.reporting import financial as fin
    from backend.ap import service as ap
    from backend.ar import service as ar
    from backend.assets import service as fa
    from backend.tax import service as tax

    cid, d1, d2 = p.company_id, p.start_date, p.end_date
    out = []
    counts = {
        "journals": db.scalar(select(func.count()).select_from(JournalEntry).where(
            JournalEntry.company_id == cid, JournalEntry.posting_date.between(d1, d2), JournalEntry.status.in_(UNPOSTED))),
        "AP documents": db.scalar(select(func.count()).select_from(APDocument).where(
            APDocument.company_id == cid, APDocument.posting_date.between(d1, d2), APDocument.status.in_(UNPOSTED))),
        "AP payments": db.scalar(select(func.count()).select_from(APPayment).where(
            APPayment.company_id == cid, APPayment.payment_date.between(d1, d2), APPayment.status.in_(UNPOSTED))),
        "AR documents": db.scalar(select(func.count()).select_from(ARDocument).where(
            ARDocument.company_id == cid, ARDocument.posting_date.between(d1, d2), ARDocument.status.in_(UNPOSTED))),
        "AR receipts": db.scalar(select(func.count()).select_from(ARReceipt).where(
            ARReceipt.company_id == cid, ARReceipt.receipt_date.between(d1, d2), ARReceipt.status.in_(UNPOSTED))),
        "cash vouchers": db.scalar(select(func.count()).select_from(CashBankVoucher).where(
            CashBankVoucher.company_id == cid, CashBankVoucher.voucher_date.between(d1, d2), CashBankVoucher.status.in_(UNPOSTED))),
        "transfers": db.scalar(select(func.count()).select_from(BankTransfer).where(
            BankTransfer.company_id == cid, BankTransfer.transfer_date.between(d1, d2), BankTransfer.status.in_(UNPOSTED))),
    }
    pending = {k: v for k, v in counts.items() if v}
    out.append(("UNPOSTED", "No unposted transactions in the period", not pending, True,
                ", ".join(f"{v} {k}" for k, v in pending.items()) or "None"))
    tb = fin.trial_balance(db, cid, None, d1, d2)
    out.append(("TB_BALANCED", "Trial balance balances", tb["meta"]["balanced"], True,
                f"Debits {tb['meta']['totals'][4]} / credits {tb['meta']['totals'][5]}"))
    banks = status_for_period(db, cid, d2)
    bad = [b["code"] for b in banks if not b["ok"]]
    out.append(("BANK_REC", "All bank accounts reconciled to the period end", not bad, True, ", ".join(bad) or "All reconciled"))
    for code, title, rep in (("AP_REC", "AP sub-ledger agrees to GL", ap.reconciliation(db, cid, d2)),
                             ("AR_REC", "AR sub-ledger agrees to GL", ar.reconciliation(db, cid, d2)),
                             ("FA_REC", "Fixed asset register agrees to GL", fa.reconciliation(db, cid, d2)),
                             ("TAX_REC", "Tax sub-ledger agrees to GL", tax.account_reconciliation(db, cid, d1, d2))):
        diffs = [f"{r['label']}: {r.get('c2')}" for r in rep["rows"] if r.get("c2") not in (None, ZERO, Decimal("0.00"))]
        out.append((code, title, rep["meta"]["reconciled"], True, "; ".join(diffs) or "Agreed"))
    dep_needed = db.scalar(select(func.count()).select_from(FixedAsset).join(AssetCategory).where(
        FixedAsset.company_id == cid, FixedAsset.status == AssetStatus.ACTIVE, AssetCategory.is_depreciable.is_(True),
        FixedAsset.depreciation_start_date <= d2))
    dep_done = db.scalar(select(func.count()).select_from(DepreciationRun).where(
        DepreciationRun.period_id == p.id, DepreciationRun.status == "POSTED"))
    out.append(("DEPRECIATION", "Depreciation posted for the period", (not dep_needed) or bool(dep_done), True,
                "Posted" if dep_done else ("No depreciable assets" if not dep_needed else "Depreciation run not posted")))
    zero_accts = db.scalars(select(Account).where(Account.zero_at_period_end.is_(True))).all()
    nonzero = []
    for a in zero_accts:
        b = money(db.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
            JournalLine.company_id == cid, JournalLine.is_posted.is_(True), JournalLine.account_id == a.id,
            JournalLine.posting_date <= d2)) or 0)
        if b:
            nonzero.append(f"{a.code} {a.name}: {b:,.2f}")
    out.append(("ZERO_ACCOUNTS", "Suspense, in-transit and migration clearing accounts are nil", not nonzero, True,
                "; ".join(nonzero) or "All nil"))
    open_bo = db.scalar(select(func.count()).select_from(BoxOfficeSale).where(
        BoxOfficeSale.company_id == cid, BoxOfficeSale.business_date.between(d1, d2), BoxOfficeSale.day_close_id.is_(None)))
    open_fnb = db.scalar(select(func.count()).select_from(FnBSale).where(
        FnBSale.company_id == cid, FnBSale.business_date.between(d1, d2), FnBSale.day_close_id.is_(None)))
    out.append(("DAY_CLOSE", "All imported cinema sales are day-closed", not (open_bo or open_fnb), True,
                f"{open_bo} box office and {open_fnb} F&B rows not day-closed" if (open_bo or open_fnb) else "All closed"))
    stale = db.scalar(select(func.count()).select_from(CollectionBatch).where(
        CollectionBatch.company_id == cid, CollectionBatch.business_date <= d2 - timedelta(days=7),
        CollectionBatch.status.in_(["OPEN", "PARTIAL"])))
    out.append(("COLLECTIONS", "Card / gateway collections settled within 7 days", not stale, False,
                f"{stale} collection batches unsettled for more than 7 days" if stale else "Up to date"))
    abnormal = [r["code"] for r in tb["rows"] if r.get("abnormal")]
    out.append(("ABNORMAL", "No accounts with abnormal balances", not abnormal, False, ", ".join(abnormal[:20]) or "None"))
    return out


def checklist(db: Session, actor: Actor, period_id: int) -> list[PeriodChecklistItem]:
    actor.require("period.view")
    p = _period(db, period_id)
    existing = {i.code: i for i in db.scalars(select(PeriodChecklistItem).where(PeriodChecklistItem.period_id == p.id))}
    for code, title, passed, blocking, detail in _auto_checks(db, p):
        item = existing.get(code) or PeriodChecklistItem(period_id=p.id, code=code, title=title, is_auto=True)
        if item.status != "WAIVED":
            item.status = "PASS" if passed else "FAIL"
        item.title, item.is_blocking, item.detail = title, blocking, detail
        db.add(item)
        existing[code] = item
    for code, title, blocking in MANUAL_ITEMS:
        if code not in existing:
            item = PeriodChecklistItem(period_id=p.id, code=code, title=title, is_auto=False, is_blocking=blocking, status="PENDING")
            db.add(item)
            existing[code] = item
    db.flush()
    return sorted(existing.values(), key=lambda i: (not i.is_auto, i.id or 0))


def sign_off(db: Session, actor: Actor, period_id: int, code: str, status: str, comment: str | None) -> PeriodChecklistItem:
    actor.require("period.close")
    item = db.scalar(select(PeriodChecklistItem).where(PeriodChecklistItem.period_id == period_id, PeriodChecklistItem.code == code))
    if item is None:
        raise NotFound("Checklist item not found (run the checklist first)")
    if status not in ("DONE", "WAIVED", "PENDING"):
        raise ValidationFailed("Status must be DONE, WAIVED or PENDING")
    if item.is_auto and status == "DONE":
        raise ValidationFailed("Automatic checks pass by themselves; they can only be waived")
    if status == "WAIVED":
        actor.require("period.reopen")  # CFO-level authority to waive
        if not comment or not comment.strip():
            raise ValidationFailed("A reason is required to waive a check")
    item.status, item.comment = status, comment
    item.signed_off_by_id, item.signed_off_at = actor.id, utcnow()
    record(db, actor, "closing.sign_off", "period_checklist", item.id, None, {"code": code, "status": status, "comment": comment})
    return item


def close_period(db: Session, actor: Actor, period_id: int) -> AccountingPeriod:
    actor.require("period.close")
    p = _period(db, period_id)
    earlier = db.scalar(select(func.count()).select_from(AccountingPeriod).where(
        AccountingPeriod.company_id == p.company_id, AccountingPeriod.start_date < p.start_date,
        AccountingPeriod.status.in_([PeriodStatus.OPEN, PeriodStatus.SOFT_CLOSED])))
    if earlier:
        raise Conflict("Close earlier periods first (periods are closed in sequence)")
    items = checklist(db, actor, period_id)
    blocking = [i for i in items if i.is_blocking and i.status not in ("PASS", "DONE", "WAIVED")]
    if blocking:
        raise ValidationFailed("Month-end checklist incomplete", code="checklist_incomplete",
                               details=[f"{i.title}: {i.detail or i.status}" for i in blocking])
    return change_status(db, period_id, PeriodStatus.CLOSED, actor, "Month-end close: checklist complete")


def reopen_period(db: Session, actor: Actor, period_id: int, reason: str) -> AccountingPeriod:
    p = _period(db, period_id)
    later = db.scalar(select(func.count()).select_from(AccountingPeriod).where(
        AccountingPeriod.company_id == p.company_id, AccountingPeriod.start_date > p.start_date,
        AccountingPeriod.status.in_([PeriodStatus.CLOSED, PeriodStatus.LOCKED])))
    if later:
        raise Conflict("Reopen later closed periods first")
    return change_status(db, period_id, PeriodStatus.OPEN, actor, reason)


def year_end_close(db: Session, actor: Actor, fiscal_year_id: int) -> JournalEntry:
    """Close income and expense accounts (and dividends) to unappropriated profit at the fiscal year end."""
    actor.require("period.close")
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise NotFound("Fiscal year not found")
    if fy.closing_journal_id:
        raise Conflict("Year-end close already posted")
    open_before_last = db.scalar(select(func.count()).select_from(AccountingPeriod).where(
        AccountingPeriod.fiscal_year_id == fy.id, AccountingPeriod.period_no < 12,
        AccountingPeriod.status.in_([PeriodStatus.OPEN, PeriodStatus.SOFT_CLOSED])))
    if open_before_last:
        raise Conflict("Close periods 1 to 11 before the year-end close")
    re_acc = db.scalar(select(Account).where(Account.code == "03-01-02-0001"))
    div_acc = db.scalar(select(Account).where(Account.code == "03-01-02-0002"))
    q = select(JournalLine.account_id, JournalLine.site_id, JournalLine.cost_centre_id,
               func.sum(JournalLine.debit - JournalLine.credit)).join(Account, Account.id == JournalLine.account_id).where(
        JournalLine.company_id == fy.company_id, JournalLine.is_posted.is_(True),
        JournalLine.posting_date.between(fy.start_date, fy.end_date),
        (Account.pl_section.is_not(None)) | (Account.id == div_acc.id)
    ).group_by(JournalLine.account_id, JournalLine.site_id, JournalLine.cost_centre_id)
    lines, net = [], ZERO
    for aid, sid, cid, bal in db.execute(q).all():
        bal = money(bal)
        if not bal:
            continue
        lines.append(LineInput(account_id=aid, site_id=sid, cost_centre_id=cid, debit=-bal if bal < 0 else ZERO,
                               credit=bal if bal > 0 else ZERO, description=f"Year-end close {fy.code}"))
        net += bal
    if not lines:
        raise ValidationFailed("Nothing to close")
    lines.append(LineInput(account_id=re_acc.id, debit=net if net > 0 else ZERO, credit=-net if net < 0 else ZERO,
                           description=f"Result for {fy.code} transferred to unappropriated profit"))
    je = engine.create_and_post(db, actor, company_id=fy.company_id, journal_type=JournalType.YEC, transaction_date=fy.end_date,
                                description=f"Year-end close {fy.code}", lines=lines, source_module=SourceModule.CLOSING,
                                source_type="fiscal_year", source_id=fy.id, source_key=f"YEC-{fy.id}")
    fy.closing_journal_id = je.id
    fy.status = "CLOSED"
    record(db, actor, "closing.year_end", "fiscal_year", fy.id, None, {"journal": je.number, "result": str(-net)})
    return je
