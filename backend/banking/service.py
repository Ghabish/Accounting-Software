"""Cash and bank: receipts / payments vouchers, transfers (direct or via transit), daily cash position."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.accounting import engine
from backend.accounting.engine import LineInput
from backend.accounting.models import Account, ControlType, DocStatus, JournalLine, JournalType, SourceModule
from backend.accounting.numbering import next_number
from backend.ap.service import wf_reset
from backend.audit.service import record
from backend.banking.models import BankAccount, BankAccountKind, BankTransfer, CashBankVoucher, CashBankVoucherLine
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.money import ZERO, money
from backend.masters.models import CostCentre
from backend.tax import engine as tax
from backend.workflow import engine as wf

D = Decimal
CASH_IN_TRANSIT = "01-02-07-0005"
FUNDS_IN_TRANSIT = "01-02-07-0010"
BANK_CHARGES = "08-01-01-0003"


def validate_bank_account(db: Session, actor: Actor, ba: BankAccount, data: dict) -> None:
    gl_id = data.get("gl_account_id") or ba.gl_account_id
    acc = db.get(Account, gl_id) if gl_id else None
    if acc is None or not acc.is_postable or acc.cash_flow_line != "CASH" or acc.control_type not in (ControlType.BANK, ControlType.CASH):
        raise ValidationFailed("Bank / cash accounts must use a cash or bank ledger (01-02-07-xxxx)")
    kind = data.get("kind") or ba.kind
    if str(getattr(kind, "value", kind)) in ("CASH", "PETTY_CASH") and not (data.get("site_id") or ba.site_id):
        raise ValidationFailed("Cash and petty cash accounts need a site")
    if data.get("is_default_payment"):
        for other in db.scalars(select(BankAccount).where(BankAccount.is_default_payment.is_(True), BankAccount.id != (ba.id or 0))):
            other.is_default_payment = False


def gl_balance(db: Session, ba: BankAccount, as_of: date) -> Decimal:
    q = select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
        JournalLine.is_posted.is_(True), JournalLine.account_id == ba.gl_account_id, JournalLine.posting_date <= as_of)
    if ba.site_id:
        q = q.where(JournalLine.site_id == ba.site_id)
    return money(db.scalar(q) or 0)


# ------------------------------------------------------------------ vouchers
def save_voucher(db: Session, actor: Actor, company_id: int, data: dict, v: CashBankVoucher | None = None) -> CashBankVoucher:
    actor.require("cash_voucher.create")
    ba = db.get(BankAccount, data["bank_account_id"])
    if ba is None or ba.company_id != company_id or not ba.is_active:
        raise ValidationFailed("Bank / cash account not found")
    actor.require_site(ba.site_id)
    direction = data.get("direction", "PAYMENT")
    if direction not in ("PAYMENT", "RECEIPT"):
        raise ValidationFailed("direction must be PAYMENT or RECEIPT")
    is_bank = ba.kind == BankAccountKind.BANK
    vtype = ("BPV" if is_bank else "CPV") if direction == "PAYMENT" else ("BRV" if is_bank else "CRV")
    lines = data.get("lines") or []
    if not lines:
        raise ValidationFailed("At least one line is required")
    if v is None:
        v = CashBankVoucher(company_id=company_id, voucher_type=vtype, number=next_number(db, company_id, f"CB-{vtype}", f"{vtype}-", 6),
                            created_by_id=actor.id, status=DocStatus.DRAFT)
        db.add(v)
    elif v.status != DocStatus.DRAFT:
        wf_reset(db, actor, "CASH_VOUCHER", v)
    v.voucher_type, v.bank_account_id = vtype, ba.id
    v.voucher_date = data["voucher_date"]
    v.counterparty, v.cheque_no, v.reference = data.get("counterparty"), data.get("cheque_no"), data.get("reference")
    v.description = data.get("description") or f"{vtype} {data.get('counterparty') or ''}".strip()
    v.lines.clear()
    gross = taxes = ZERO
    for n, l in enumerate(lines, start=1):
        acc = db.get(Account, l["account_id"])
        if acc is None:
            raise ValidationFailed(f"Line {n}: account not found")
        if acc.control_type in (ControlType.AP_CONTROL, ControlType.AR_CONTROL):
            raise ValidationFailed(f"Line {n}: use the AP / AR modules for supplier and customer control accounts")
        if acc.cash_flow_line == "CASH":
            raise ValidationFailed(f"Line {n}: use a transfer to move funds between cash and bank accounts")
        amt = money(l["amount"])
        t_amt, t_rate = ZERO, None
        if l.get("tax_code_id"):
            if l.get("tax_amount") is not None:
                t_amt = money(l["tax_amount"])
            else:
                calc = tax.compute(db, l["tax_code_id"], amt, v.voucher_date)
                t_amt, t_rate = calc.amount, calc.rate
        v.lines.append(CashBankVoucherLine(line_no=n, account_id=acc.id, site_id=l.get("site_id"), cost_centre_id=l.get("cost_centre_id"),
                                           supplier_id=l.get("supplier_id"), customer_id=l.get("customer_id"),
                                           employee_id=l.get("employee_id"), description=l.get("description"), amount=amt,
                                           tax_code_id=l.get("tax_code_id"), tax_rate=t_rate, tax_amount=t_amt,
                                           dimensions={str(k): int(x) for k, x in (l.get("dimensions") or {}).items() if x} or None))
        gross += amt
        taxes += t_amt
    v.gross_total, v.tax_total, v.net_total = money(gross), money(taxes), money(gross - taxes)
    if v.net_total <= 0:
        raise ValidationFailed("Voucher net amount must be positive")
    db.flush()
    _voucher_lines(db, v, ba, validate=True, actor=actor)
    record(db, actor, "cash_voucher.save", "cash_voucher", v.id, None, {"number": v.number, "net": str(v.net_total)})
    return v


def _voucher_lines(db: Session, v: CashBankVoucher, ba: BankAccount, *, validate: bool, actor) -> list[LineInput]:
    payment = v.voucher_type in ("BPV", "CPV")
    out: list[LineInput] = []
    tax_group: dict[int, list] = defaultdict(lambda: [ZERO, ZERO])
    for l in v.lines:
        li = LineInput(account_id=l.account_id, site_id=l.site_id, cost_centre_id=l.cost_centre_id, supplier_id=l.supplier_id,
                       customer_id=l.customer_id, employee_id=l.employee_id, description=l.description or v.description,
                       reference=v.cheque_no or v.number, dimensions={int(k): int(x) for k, x in (l.dimensions or {}).items()})
        if payment:
            li.debit = l.amount
        else:
            li.credit = l.amount
        out.append(li)
        if l.tax_code_id and l.tax_amount:
            tax_group[l.tax_code_id][0] += l.tax_amount
            tax_group[l.tax_code_id][1] += l.amount
    for tcid, (amt, base) in tax_group.items():
        tc = tax.get_code(db, tcid)
        li = LineInput(account_id=tc.account_id, tax_code_id=tc.id, tax_base=money(base), description=f"{tc.name} - {v.number}")
        if payment:
            li.credit = amt   # tax withheld from the payee
        else:
            li.debit = amt    # tax deducted by the payer (refundable)
        out.append(li)
    bank = LineInput(account_id=ba.gl_account_id, site_id=ba.site_id, description=v.description, reference=v.cheque_no or v.number)
    if payment:
        bank.credit = v.net_total
    else:
        bank.debit = v.net_total
    out.append(bank)
    if validate:
        engine.validate_lines(db, v.company_id, out, manual=False, actor=actor, txn_date=v.voucher_date)
    return out


def _post_voucher(db: Session, v: CashBankVoucher, actor: Actor) -> None:
    v = db.scalar(select(CashBankVoucher).where(CashBankVoucher.id == v.id).with_for_update())
    ba = db.get(BankAccount, v.bank_account_id)
    je = engine.create_and_post(db, actor, company_id=v.company_id, journal_type=JournalType(v.voucher_type),
                                transaction_date=v.voucher_date, description=f"{v.number} {v.description}",
                                lines=_voucher_lines(db, v, ba, validate=False, actor=actor),
                                reference=v.cheque_no or v.number, source_module=SourceModule.BANK,
                                source_type="cash_voucher", source_id=v.id, source_key=f"CB-{v.id}")
    for l in v.lines:
        if l.tax_code_id and l.tax_amount:
            tc = tax.get_code(db, l.tax_code_id)
            tax.record(db, company_id=v.company_id, calc=tax.TaxCalc(tc, l.tax_rate or ZERO, l.amount, l.tax_amount, None),
                       journal=je, journal_line=tax.line_for(je, tc.account_id, tc.id), source_type="cash_voucher",
                       source_id=v.id, transaction_date=v.voucher_date, site_id=l.site_id, document_ref=v.number)
    v.journal_id = je.id
    v.status = DocStatus.POSTED
    db.flush()


def voucher_spec(db: Session, v: CashBankVoucher) -> wf.WorkflowSpec:
    ba = db.get(BankAccount, v.bank_account_id)
    return wf.WorkflowSpec(doc_type="CASH_VOUCHER", perm_prefix="cash_voucher", amount=v.gross_total,
                           site_id=ba.site_id, poster=_post_voucher)


def reverse_voucher(db: Session, actor: Actor, v: CashBankVoucher, reversal_date: date, reason: str) -> CashBankVoucher:
    actor.require("cash_voucher.reverse")
    if v.status != DocStatus.POSTED:
        raise Conflict("Only posted vouchers can be reversed")
    rev = engine.create_reversal(db, v.journal_id, actor, reversal_date, reason, post=True)
    tax.reverse_for_journal(db, v.journal_id, rev)
    v.status = DocStatus.REVERSED
    return v


# ------------------------------------------------------------------ transfers
def save_transfer(db: Session, actor: Actor, company_id: int, data: dict, t: BankTransfer | None = None) -> BankTransfer:
    actor.require("bank_transfer.create")
    src, dst = db.get(BankAccount, data["from_account_id"]), db.get(BankAccount, data["to_account_id"])
    if src is None or dst is None or src.id == dst.id:
        raise ValidationFailed("Select two different accounts")
    actor.require_site(src.site_id)
    if t is None:
        t = BankTransfer(company_id=company_id, number=next_number(db, company_id, "CB-TRF", "TRF-", 6),
                         created_by_id=actor.id, status=DocStatus.DRAFT)
        db.add(t)
    elif t.status != DocStatus.DRAFT:
        wf_reset(db, actor, "BANK_TRANSFER", t)
    t.from_account_id, t.to_account_id = src.id, dst.id
    t.transfer_date = data["transfer_date"]
    t.amount = money(data["amount"])
    t.charges = money(data.get("charges") or 0)
    t.via_transit = bool(data.get("via_transit"))
    t.reference = data.get("reference")
    t.description = data.get("description") or f"Transfer {src.code} to {dst.code}"
    if t.amount <= 0:
        raise ValidationFailed("Amount must be positive")
    db.flush()
    _transfer_lines(db, t, validate=True, actor=actor)
    return t


def _transit_account(db: Session, src: BankAccount) -> tuple[int, int | None]:
    code = CASH_IN_TRANSIT if src.kind != BankAccountKind.BANK else FUNDS_IN_TRANSIT
    acc = db.scalar(select(Account).where(Account.code == code))
    return acc.id, src.site_id if code == CASH_IN_TRANSIT else None


def _transfer_lines(db: Session, t: BankTransfer, *, validate: bool, actor) -> list[LineInput]:
    src, dst = db.get(BankAccount, t.from_account_id), db.get(BankAccount, t.to_account_id)
    if t.via_transit:
        tid, tsite = _transit_account(db, src)
        out = [LineInput(account_id=tid, debit=t.amount, site_id=tsite, description=t.description, reference=t.reference or t.number)]
    else:
        out = [LineInput(account_id=dst.gl_account_id, debit=t.amount, site_id=dst.site_id, description=t.description,
                         reference=t.reference or t.number)]
    out.append(LineInput(account_id=src.gl_account_id, credit=t.amount + t.charges, site_id=src.site_id,
                         description=t.description, reference=t.reference or t.number))
    if t.charges:
        corp = db.scalar(select(CostCentre.id).where(CostCentre.company_id == t.company_id, CostCentre.code == "090101"))
        out.append(LineInput(account_id=db.scalar(select(Account.id).where(Account.code == BANK_CHARGES)), debit=t.charges,
                             cost_centre_id=corp, description=f"Bank charges {t.number}"))
    if validate:
        engine.validate_lines(db, t.company_id, out, manual=False, actor=actor, txn_date=t.transfer_date)
    return out


def _post_transfer(db: Session, t: BankTransfer, actor: Actor) -> None:
    t = db.scalar(select(BankTransfer).where(BankTransfer.id == t.id).with_for_update())
    je = engine.create_and_post(db, actor, company_id=t.company_id, journal_type=JournalType.TRF, transaction_date=t.transfer_date,
                                description=f"{t.number} {t.description}", lines=_transfer_lines(db, t, validate=False, actor=actor),
                                reference=t.reference or t.number, source_module=SourceModule.BANK, source_type="bank_transfer",
                                source_id=t.id, source_key=f"TRF-{t.id}")
    t.journal_id = je.id
    t.status = DocStatus.POSTED
    db.flush()


def transfer_spec(db: Session, t: BankTransfer) -> wf.WorkflowSpec:
    src = db.get(BankAccount, t.from_account_id)
    return wf.WorkflowSpec(doc_type="BANK_TRANSFER", perm_prefix="bank_transfer", amount=t.amount, site_id=src.site_id,
                           poster=_post_transfer)


def receive_transfer(db: Session, actor: Actor, t: BankTransfer, received_date: date) -> BankTransfer:
    """Second leg of a transfer via transit (e.g. cash deposit credited by the bank)."""
    actor.require("bank_transfer.post")
    t = db.scalar(select(BankTransfer).where(BankTransfer.id == t.id).with_for_update())
    if not t.via_transit or t.status != DocStatus.POSTED or t.receive_journal_id:
        raise Conflict("Transfer is not awaiting receipt")
    src, dst = db.get(BankAccount, t.from_account_id), db.get(BankAccount, t.to_account_id)
    tid, tsite = _transit_account(db, src)
    je = engine.create_and_post(db, actor, company_id=t.company_id, journal_type=JournalType.TRF, transaction_date=received_date,
                                description=f"{t.number} received in {dst.code}",
                                lines=[LineInput(account_id=dst.gl_account_id, debit=t.amount, site_id=dst.site_id, reference=t.reference or t.number),
                                       LineInput(account_id=tid, credit=t.amount, site_id=tsite, reference=t.reference or t.number)],
                                reference=t.reference or t.number, source_module=SourceModule.BANK, source_type="bank_transfer_receipt",
                                source_id=t.id, source_key=f"TRF-RCV-{t.id}")
    t.receive_journal_id = je.id
    t.received_date = received_date
    db.flush()
    record(db, actor, "bank_transfer.receive", "bank_transfer", t.id, None, {"journal": je.number})
    return t


# ------------------------------------------------------------------ daily cash position
def daily_cash_position(db: Session, company_id: int, actor: Actor, on_date: date) -> dict:
    rows_out = []
    tot = [ZERO] * 4
    for ba in db.scalars(select(BankAccount).where(BankAccount.company_id == company_id, BankAccount.is_active.is_(True))
                         .order_by(BankAccount.kind, BankAccount.code)).all():
        if not actor.can_site(ba.site_id):
            continue
        q = select(func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0)).where(
            JournalLine.is_posted.is_(True), JournalLine.company_id == company_id, JournalLine.account_id == ba.gl_account_id)
        if ba.site_id:
            q = q.where(JournalLine.site_id == ba.site_id)
        o_dr, o_cr = db.execute(q.where(JournalLine.posting_date < on_date)).one()
        d_dr, d_cr = db.execute(q.where(JournalLine.posting_date == on_date)).one()
        opening = D(o_dr) - D(o_cr)
        vals = [money(opening), money(d_dr), money(d_cr), money(opening + D(d_dr) - D(d_cr))]
        tot = [a + b for a, b in zip(tot, vals)]
        rows_out.append({"label": f"{ba.code} - {ba.name}", "kind": ba.kind.value, "level": 1, "style": "line",
                         "bank_account_id": ba.id, **{f"c{i}": v for i, v in enumerate(vals)},
                         "drill": {"account_id": ba.gl_account_id, "site_id": ba.site_id}})
    rows_out.append({"label": "TOTAL CASH AND BANK", "level": 0, "style": "grand", **{f"c{i}": money(v) for i, v in enumerate(tot)}})
    return {"title": "Daily Cash Position", "subtitle": on_date.strftime("%A %d %B %Y"),
            "columns": [{"key": "label", "label": "Account", "type": "text"}, {"key": "c0", "label": "Opening", "type": "money"},
                        {"key": "c1", "label": "Receipts", "type": "money"}, {"key": "c2", "label": "Payments", "type": "money"},
                        {"key": "c3", "label": "Closing", "type": "money"}],
            "rows": rows_out, "meta": {"total_closing": money(tot[3])}}
