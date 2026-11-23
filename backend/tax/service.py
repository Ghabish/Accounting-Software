"""Tax administration (rates, deposits) and tax reports derived from tax transactions + GL."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.accounting import engine
from backend.accounting.engine import LineInput
from backend.accounting.models import Account, JournalEntry, JournalLine, JournalType, SourceModule
from backend.audit.service import record
from backend.banking.models import BankAccount
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.money import ZERO, money
from backend.tax.models import TaxCode, TaxRate, TaxTransaction, TaxType

D = Decimal
LIABILITY_TYPES = {TaxType.SALES_TAX_OUTPUT, TaxType.PST_OUTPUT, TaxType.ENTERTAINMENT_DUTY, TaxType.WHT_DEDUCTED,
                   TaxType.ST_WITHHELD}


def add_rate(db: Session, actor: Actor, data: dict) -> TaxRate:
    """Add an effective-dated rate; the previous open-ended rate for the same key is closed the day before."""
    actor.require("tax.manage")
    tc = db.get(TaxCode, data["tax_code_id"])
    if tc is None:
        raise NotFound("Tax code not found")
    if D(str(data["rate"])) < 0 or D(str(data["rate"])) > 1:
        raise ValidationFailed("Rate must be a fraction between 0 and 1 (e.g. 0.16 for 16%)")
    prev = db.scalars(select(TaxRate).where(TaxRate.tax_code_id == tc.id, TaxRate.payee_type == data.get("payee_type", "ALL"),
                                            TaxRate.atl_status == data.get("atl_status", "ALL"),
                                            TaxRate.site_id.is_(data.get("site_id")) if data.get("site_id") is None else TaxRate.site_id == data["site_id"],
                                            TaxRate.effective_to.is_(None), TaxRate.is_active.is_(True))).all()
    for p in prev:
        if p.effective_from >= data["effective_from"]:
            raise Conflict(f"A rate already starts on or after {data['effective_from']}")
        p.effective_to = data["effective_from"] - timedelta(days=1)
    r = TaxRate(created_by_id=actor.id, **data)
    db.add(r)
    db.flush()
    record(db, actor, "tax_rate.add", "tax_rate", r.id, None, {"code": tc.code, "rate": str(r.rate),
                                                                "from": r.effective_from.isoformat()})
    return r


def _txn_query(company_id: int, date_from: date, date_to: date):
    return select(TaxTransaction).where(TaxTransaction.company_id == company_id,
                                        TaxTransaction.transaction_date.between(date_from, date_to))


def summary(db: Session, company_id: int, date_from: date, date_to: date) -> dict:
    """Sales tax (output / input / net) and withholding summary by tax code."""
    q = select(TaxTransaction.tax_code_id, TaxTransaction.direction, func.sum(TaxTransaction.base_amount),
               func.sum(TaxTransaction.tax_amount), func.count()).where(
        TaxTransaction.company_id == company_id, TaxTransaction.transaction_date.between(date_from, date_to)
    ).group_by(TaxTransaction.tax_code_id, TaxTransaction.direction)
    codes = {c.id: c for c in db.scalars(select(TaxCode)).all()}
    groups: dict[str, list] = defaultdict(list)
    for tcid, direction, base, amt, n in db.execute(q).all():
        groups[direction].append((codes[tcid], D(base), D(amt), n))
    rows_out = []
    totals = {}
    labels = {"OUTPUT": "OUTPUT TAX (charged on sales)", "INPUT": "INPUT TAX (charged by suppliers, adjustable)",
              "WITHHELD": "TAX WITHHELD FROM SUPPLIERS / EMPLOYEES (payable)",
              "SUFFERED": "TAX DEDUCTED FROM US (refundable / adjustable)"}
    for direction in ("OUTPUT", "INPUT", "WITHHELD", "SUFFERED"):
        rows_out.append({"label": labels[direction], "level": 0, "style": "header"})
        tb = tt = ZERO
        for tc, base, amt, n in sorted(groups.get(direction, []), key=lambda x: x[0].code):
            rows_out.append({"label": f"{tc.code} - {tc.name}", "authority": tc.authority, "section": tc.law_section,
                             "count": n, "base": money(base), "tax": money(amt), "level": 1, "style": "line",
                             "drill": {"tax_code_id": tc.id}})
            tb += base
            tt += amt
        totals[direction] = money(tt)
        rows_out.append({"label": f"Total {direction.lower()}", "base": money(tb), "tax": money(tt), "level": 0, "style": "total"})
    net_st = totals["OUTPUT"] - totals["INPUT"]
    rows_out.append({"label": "NET SALES TAX POSITION (output - input): payable / (refundable)", "tax": net_st,
                     "level": 0, "style": "grand"})
    rows_out.append({"label": "WITHHOLDING TAX PAYABLE FOR THE PERIOD", "tax": totals["WITHHELD"], "level": 0, "style": "grand"})
    return {"title": "Tax Summary", "subtitle": f"{date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}",
            "columns": [{"key": "label", "label": "Tax code", "type": "text"}, {"key": "authority", "label": "Authority", "type": "text"},
                        {"key": "count", "label": "Transactions", "type": "int"}, {"key": "base", "label": "Taxable value", "type": "money"},
                        {"key": "tax", "label": "Tax", "type": "money"}],
            "rows": rows_out, "meta": {"totals": totals, "net_sales_tax": net_st}}


def listing(db: Session, company_id: int, date_from: date, date_to: date, *, direction: str | None = None,
            tax_code_id: int | None = None, supplier_id: int | None = None, customer_id: int | None = None,
            deposited: bool | None = None, title: str = "Tax Transaction Listing") -> dict:
    q = _txn_query(company_id, date_from, date_to)
    if direction:
        q = q.where(TaxTransaction.direction == direction)
    if tax_code_id:
        q = q.where(TaxTransaction.tax_code_id == tax_code_id)
    if supplier_id:
        q = q.where(TaxTransaction.supplier_id == supplier_id)
    if customer_id:
        q = q.where(TaxTransaction.customer_id == customer_id)
    if deposited is not None:
        q = q.where(TaxTransaction.deposited.is_(deposited))
    codes = {c.id: c for c in db.scalars(select(TaxCode)).all()}
    rows_out = []
    tb = tt = ZERO
    for t in db.scalars(q.order_by(TaxTransaction.transaction_date, TaxTransaction.id).limit(50000)).all():
        tc = codes[t.tax_code_id]
        num = db.scalar(select(JournalEntry.number).where(JournalEntry.id == t.journal_id))
        rows_out.append({"label": t.transaction_date.isoformat(), "code": tc.code, "section": tc.law_section,
                         "direction": t.direction, "party": t.party_name, "ntn": t.party_ntn, "document": t.document_ref,
                         "journal": num, "journal_id": t.journal_id, "base": t.base_amount, "rate": t.rate * 100,
                         "tax": t.tax_amount, "override": "Yes" if t.rate_overridden else "",
                         "deposit": t.deposit_reference or "", "level": 1, "style": "line", "id": t.id})
        tb += t.base_amount
        tt += t.tax_amount
    rows_out.append({"label": "TOTAL", "base": money(tb), "tax": money(tt), "level": 0, "style": "grand"})
    return {"title": title, "subtitle": f"{date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}",
            "columns": [{"key": "label", "label": "Date", "type": "text"}, {"key": "code", "label": "Tax code", "type": "text"},
                        {"key": "section", "label": "Section", "type": "text"}, {"key": "party", "label": "Party", "type": "text"},
                        {"key": "ntn", "label": "NTN / CNIC", "type": "text"}, {"key": "document", "label": "Document", "type": "text"},
                        {"key": "journal", "label": "Journal", "type": "text"}, {"key": "base", "label": "Base", "type": "money"},
                        {"key": "rate", "label": "Rate %", "type": "pct"}, {"key": "tax", "label": "Tax", "type": "money"},
                        {"key": "override", "label": "Rate override", "type": "text"}, {"key": "deposit", "label": "CPR / PSID", "type": "text"}],
            "rows": rows_out, "meta": {"total_tax": money(tt)}}


def account_reconciliation(db: Session, company_id: int, date_from: date, date_to: date) -> dict:
    """Tax sub-ledger (tax transactions) vs GL movement on each tax account, excluding tax deposits."""
    codes = db.scalars(select(TaxCode)).all()
    by_account: dict[int, list[TaxCode]] = defaultdict(list)
    for c in codes:
        by_account[c.account_id].append(c)
    rows_out = []
    ok = True
    for acc_id, tcs in sorted(by_account.items(), key=lambda kv: db.get(Account, kv[0]).code):
        acc = db.get(Account, acc_id)
        liability = acc.normal_balance == "C"
        recoverable_ids = [c.id for c in tcs if c.is_recoverable]
        sub = D(db.scalar(select(func.coalesce(func.sum(TaxTransaction.tax_amount), 0)).where(
            TaxTransaction.company_id == company_id, TaxTransaction.tax_code_id.in_(recoverable_ids or [0]),
            TaxTransaction.transaction_date.between(date_from, date_to))) or 0)
        gl_q = select(func.coalesce(func.sum(JournalLine.credit - JournalLine.debit if liability else JournalLine.debit - JournalLine.credit), 0)) \
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_id).where(
            JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.account_id == acc_id,
            JournalLine.posting_date.between(date_from, date_to),
            JournalLine.source_module.not_in(["OPENING", "CLOSING"]),
            func.coalesce(JournalEntry.source_type, "") != "tax_deposit")
        gl = D(db.scalar(gl_q) or 0)
        diff = money(sub - gl)
        if not sub and not gl:
            continue
        ok = ok and diff == 0
        rows_out.append({"label": f"{acc.code} {acc.name}", "codes": ", ".join(c.code for c in tcs), "c0": money(sub),
                         "c1": money(gl), "c2": diff, "level": 1, "style": "line", "drill": {"account_id": acc.id}})
    return {"title": "Tax Accounts Reconciliation (sub-ledger vs GL)", "subtitle": f"{date_from} to {date_to}",
            "columns": [{"key": "label", "label": "Tax account", "type": "text"}, {"key": "codes", "label": "Tax codes", "type": "text"},
                        {"key": "c0", "label": "Tax transactions", "type": "money"}, {"key": "c1", "label": "GL movement", "type": "money"},
                        {"key": "c2", "label": "Difference", "type": "money"}],
            "rows": rows_out, "meta": {"reconciled": ok}}


def record_deposit(db: Session, actor: Actor, company_id: int, *, tax_code_ids: list[int], date_from: date, date_to: date,
                   bank_account_id: int, deposit_date: date, cpr_number: str) -> JournalEntry:
    """Pay withheld / output tax to the authority (V24): posts the payment and stamps the CPR on the covered lines."""
    actor.require("tax.manage")
    if not cpr_number or not cpr_number.strip():
        raise ValidationFailed("CPR / PSID number is required")
    ba = db.get(BankAccount, bank_account_id)
    if ba is None:
        raise NotFound("Bank account not found")
    txns = db.scalars(select(TaxTransaction).where(TaxTransaction.company_id == company_id,
                                                   TaxTransaction.tax_code_id.in_(tax_code_ids),
                                                   TaxTransaction.transaction_date.between(date_from, date_to),
                                                   TaxTransaction.deposited.is_(False),
                                                   TaxTransaction.direction.in_(["WITHHELD", "OUTPUT"]))
                      .with_for_update()).all()
    if not txns:
        raise ValidationFailed("No undeposited tax found for the selection")
    per_acc: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for t in txns:
        per_acc[db.get(TaxCode, t.tax_code_id).account_id] += t.tax_amount
    total = money(sum(per_acc.values(), ZERO))
    if total <= 0:
        raise ValidationFailed("Nothing to deposit")
    lines = [LineInput(account_id=a, debit=money(v), description=f"Tax deposit CPR {cpr_number}", reference=cpr_number)
             for a, v in per_acc.items() if v]
    lines.append(LineInput(account_id=ba.gl_account_id, credit=total, site_id=ba.site_id,
                           description=f"Tax deposit CPR {cpr_number}", reference=cpr_number))
    je = engine.create_and_post(db, actor, company_id=company_id, journal_type=JournalType.BPV, transaction_date=deposit_date,
                                description=f"Tax deposited to authority - CPR {cpr_number}", lines=lines, reference=cpr_number,
                                source_module=SourceModule.TAX, source_type="tax_deposit", source_key=f"TAXDEP-{cpr_number}")
    for t in txns:
        t.deposited, t.deposit_reference, t.deposit_date = True, cpr_number, deposit_date
    record(db, actor, "tax.deposit", "journal", je.id, None, {"cpr": cpr_number, "amount": str(total), "lines": len(txns)})
    return je


def working_papers(db: Session, company_id: int, date_from: date, date_to: date) -> list[dict]:
    return [summary(db, company_id, date_from, date_to),
            {**listing(db, company_id, date_from, date_to, direction="OUTPUT", title="Output tax register"), "sheet": "Output tax"},
            {**listing(db, company_id, date_from, date_to, direction="INPUT", title="Input tax register"), "sheet": "Input tax"},
            {**listing(db, company_id, date_from, date_to, direction="WITHHELD", title="Withholding statement - tax deducted from suppliers"), "sheet": "WHT deducted"},
            {**listing(db, company_id, date_from, date_to, direction="SUFFERED", title="Tax deducted from us (certificates)"), "sheet": "WHT suffered"},
            account_reconciliation(db, company_id, date_from, date_to)]
