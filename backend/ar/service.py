"""Accounts receivable services."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from backend.accounting import engine
from backend.accounting.engine import LineInput
from backend.accounting.models import Account, DocStatus, JournalEntry, JournalLine, JournalType, SourceModule
from backend.accounting.numbering import next_number
from backend.ap.models import PaymentStatus
from backend.ap.service import BUCKETS, wf_reset
from backend.ar.models import (
    ARAllocation, ARDocType, ARDocument, ARDocumentLine, ARReceipt, ARReceiptLine, Customer, CustomerCategory,
)
from backend.audit.service import record
from backend.banking.models import BankAccount
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.money import ZERO, money
from backend.tax import engine as tax
from backend.workflow import engine as wf

D = Decimal


def validate_customer(db: Session, actor: Actor, cus: Customer, data: dict) -> None:
    if data.get("ntn"):
        dup = db.scalar(select(Customer).where(Customer.ntn == data["ntn"], Customer.id != (cus.id or 0)))
        if dup:
            raise Conflict(f"NTN {data['ntn']} already used by customer {dup.code} (V26)")
    if not cus.id and not data.get("code"):
        last = db.scalar(select(func.max(Customer.code)).where(Customer.code.like("C0%"), Customer.code < "C009"))
        n = int(last[1:]) + 1 if last and last[1:].isdigit() else 1
        data["code"] = f"C{n:05d}"
    if data.get("category_id") and db.get(CustomerCategory, data["category_id"]) is None:
        raise ValidationFailed("Customer category not found")


def control_account(db: Session, cus: Customer) -> int:
    return db.get(CustomerCategory, cus.category_id).ar_control_account_id


def advance_account(db: Session, cus: Customer) -> int:
    cat = db.get(CustomerCategory, cus.category_id)
    if not cat.advance_account_id:
        raise ValidationFailed("Customer category has no advance account")
    return cat.advance_account_id


def save_document(db: Session, actor: Actor, company_id: int, data: dict, doc: ARDocument | None = None) -> ARDocument:
    actor.require("ar_invoice.create")
    lines = data.pop("lines")
    if not lines:
        raise ValidationFailed("At least one line is required")
    cus = db.get(Customer, data["customer_id"])
    if cus is None or not cus.is_active:
        raise ValidationFailed("Customer not found or inactive")
    doc_type = ARDocType(data.get("doc_type", "INVOICE"))
    if doc is None:
        prefix = {"INVOICE": "SI", "DEBIT_NOTE": "SDN", "CREDIT_NOTE": "SCN"}[doc_type.value]
        doc = ARDocument(company_id=company_id, doc_type=doc_type, number=next_number(db, company_id, f"AR-{prefix}", f"{prefix}-", 6),
                         created_by_id=actor.id, status=DocStatus.DRAFT)
        db.add(doc)
    elif doc.status not in (DocStatus.DRAFT, DocStatus.SUBMITTED, DocStatus.CHECKED, DocStatus.APPROVED):
        raise Conflict("Only unposted documents can be edited")
    elif doc.status != DocStatus.DRAFT:
        wf_reset(db, actor, "AR_INVOICE", doc)
    cat = db.get(CustomerCategory, cus.category_id)
    doc.customer_id, doc.doc_type = cus.id, doc_type
    doc.customer_reference = data.get("customer_reference")
    doc.invoice_date = data["invoice_date"]
    doc.posting_date = data.get("posting_date") or doc.invoice_date
    doc.due_date = data.get("due_date") or doc.invoice_date + timedelta(days=cus.payment_terms_days or 0)
    doc.site_id = data.get("site_id")
    doc.description = data.get("description") or f"{doc_type.value.title()} to {cus.name}"
    doc.related_document_id = data.get("related_document_id")
    actor.require_site(doc.site_id)
    doc.lines.clear()
    subtotal = tax_total = ZERO
    for n, l in enumerate(lines, start=1):
        amount = money(l.get("amount") if l.get("amount") is not None else D(str(l.get("quantity", 1))) * D(str(l.get("unit_price", 0))))
        if amount <= 0:
            raise ValidationFailed(f"Line {n}: amount must be positive")
        account_id = l.get("account_id") or cat.default_revenue_account_id
        if not account_id:
            raise ValidationFailed(f"Line {n}: revenue account is required")
        tcode = l["tax_code_id"] if "tax_code_id" in l else cat.default_output_tax_code_id
        t_amt, t_rate = ZERO, None
        if tcode:
            calc = tax.compute(db, tcode, amount, doc.invoice_date, site_id=l.get("site_id") or doc.site_id)
            t_amt, t_rate = calc.amount, calc.rate
        doc.lines.append(ARDocumentLine(line_no=n, account_id=account_id, site_id=l.get("site_id") or doc.site_id,
                                        cost_centre_id=l.get("cost_centre_id"), description=l.get("description"),
                                        quantity=D(str(l.get("quantity", 1))), unit_price=money(l.get("unit_price") or amount),
                                        amount=amount, tax_code_id=tcode, tax_rate=t_rate, tax_amount=t_amt,
                                        dimensions={str(k): int(v) for k, v in (l.get("dimensions") or {}).items() if v} or None))
        subtotal += amount
        tax_total += t_amt
    doc.subtotal, doc.tax_total, doc.total = money(subtotal), money(tax_total), money(subtotal + tax_total)
    db.flush()
    _journal_lines(db, doc, cus, validate=True, actor=actor)
    record(db, actor, "ar_document.save", "ar_document", doc.id, None, {"number": doc.number, "total": str(doc.total)})
    return doc


def _journal_lines(db: Session, doc: ARDocument, cus: Customer, *, validate: bool, actor) -> list[LineInput]:
    reduce = doc.doc_type == ARDocType.CREDIT_NOTE
    out = []
    ctrl = LineInput(account_id=control_account(db, cus), customer_id=cus.id, description=doc.description, reference=doc.number)
    if reduce:
        ctrl.credit = doc.total
    else:
        ctrl.debit = doc.total
    out.append(ctrl)
    taxes: dict[int, list] = defaultdict(lambda: [ZERO, ZERO])
    for l in doc.lines:
        li = LineInput(account_id=l.account_id, site_id=l.site_id, cost_centre_id=l.cost_centre_id,
                       description=l.description or doc.description, reference=doc.number,
                       dimensions={int(k): int(v) for k, v in (l.dimensions or {}).items()})
        if reduce:
            li.debit = l.amount
        else:
            li.credit = l.amount
        out.append(li)
        if l.tax_code_id and l.tax_amount:
            taxes[l.tax_code_id][0] += l.tax_amount
            taxes[l.tax_code_id][1] += l.amount
    for tcid, (amt, base) in taxes.items():
        tc = tax.get_code(db, tcid)
        li = LineInput(account_id=tc.account_id, tax_code_id=tc.id, tax_base=money(base), description=f"{tc.name} - {doc.number}")
        if reduce:
            li.debit = amt
        else:
            li.credit = amt
        out.append(li)
    if validate:
        engine.validate_lines(db, doc.company_id, out, manual=False, actor=actor, txn_date=doc.posting_date)
    return out


def _post_document(db: Session, doc: ARDocument, actor: Actor) -> None:
    doc = db.scalar(select(ARDocument).where(ARDocument.id == doc.id).with_for_update())
    cus = db.get(Customer, doc.customer_id)
    jt = JournalType.ARC if doc.doc_type == ARDocType.CREDIT_NOTE else JournalType.ARI
    je = engine.create_and_post(db, actor, company_id=doc.company_id, journal_type=jt, transaction_date=doc.invoice_date,
                                posting_date=doc.posting_date, description=f"{doc.number} {doc.description}",
                                lines=_journal_lines(db, doc, cus, validate=False, actor=actor), reference=doc.number,
                                source_module=SourceModule.OPENING if doc.is_opening else SourceModule.AR,
                                source_type="ar_document", source_id=doc.id,
                                source_key=f"AR-DOC-{doc.id}")
    sign = -1 if doc.doc_type == ARDocType.CREDIT_NOTE else 1
    for l in doc.lines:
        if l.tax_code_id and l.tax_amount:
            tc = tax.get_code(db, l.tax_code_id)
            tax.record(db, company_id=doc.company_id, calc=tax.TaxCalc(tc, l.tax_rate or ZERO, l.amount, l.tax_amount, None),
                       journal=je, journal_line=tax.line_for(je, tc.account_id, tc.id), source_type="ar_document",
                       source_id=doc.id, transaction_date=doc.posting_date, customer=cus, site_id=l.site_id,
                       document_ref=doc.number, sign=sign)
    doc.journal_id = je.id
    doc.status = DocStatus.POSTED
    db.flush()
    if doc.doc_type == ARDocType.CREDIT_NOTE and doc.related_document_id:
        inv = db.get(ARDocument, doc.related_document_id)
        if inv and inv.status == DocStatus.POSTED and inv.customer_id == doc.customer_id and inv.outstanding > 0:
            allocate_credit(db, actor, doc.id, inv.id, min(inv.outstanding, doc.outstanding), _skip_perm=True)


def doc_spec(db: Session, doc: ARDocument) -> wf.WorkflowSpec:
    return wf.WorkflowSpec(doc_type="AR_INVOICE", perm_prefix="ar_invoice", amount=doc.total, site_id=doc.site_id,
                           poster=_post_document)


def reverse_document(db: Session, actor: Actor, doc: ARDocument, reversal_date: date, reason: str) -> ARDocument:
    actor.require("ar_invoice.reverse")
    if doc.status != DocStatus.POSTED:
        raise Conflict("Only posted documents can be reversed")
    active = db.scalar(select(func.count()).select_from(ARAllocation).where(
        ARAllocation.is_active.is_(True), or_(ARAllocation.invoice_id == doc.id, ARAllocation.credit_document_id == doc.id)))
    if active:
        raise Conflict("Document has receipts or allocations; reverse them first")
    rev = engine.create_reversal(db, doc.journal_id, actor, reversal_date, reason, post=True)
    tax.reverse_for_journal(db, doc.journal_id, rev)
    doc.status = DocStatus.REVERSED
    record(db, actor, "ar_document.reverse", "ar_document", doc.id, None, {"reversal": rev.number, "reason": reason})
    return doc


def _apply(inv: ARDocument, amount: Decimal) -> None:
    inv.amount_settled = money(inv.amount_settled + amount)
    if inv.amount_settled > inv.total:
        raise ValidationFailed(f"Allocation exceeds the outstanding amount of {inv.number}")
    inv.payment_status = PaymentStatus.PAID if inv.amount_settled == inv.total else (
        PaymentStatus.PARTIAL if inv.amount_settled > 0 else PaymentStatus.UNPAID)


def allocate_credit(db: Session, actor: Actor, credit_doc_id: int, invoice_id: int, amount: Decimal, *,
                    _skip_perm: bool = False) -> ARAllocation:
    if not _skip_perm:
        actor.require("ar_invoice.post")
    cn = db.scalar(select(ARDocument).where(ARDocument.id == credit_doc_id).with_for_update())
    inv = db.scalar(select(ARDocument).where(ARDocument.id == invoice_id).with_for_update())
    amount = money(amount)
    if cn is None or inv is None or cn.doc_type != ARDocType.CREDIT_NOTE or inv.doc_type == ARDocType.CREDIT_NOTE:
        raise ValidationFailed("Allocate a credit note against an invoice or debit note")
    if cn.customer_id != inv.customer_id or cn.status != DocStatus.POSTED or inv.status != DocStatus.POSTED:
        raise ValidationFailed("Both documents must be posted and belong to the same customer")
    if amount <= 0 or amount > cn.outstanding or amount > inv.outstanding:
        raise ValidationFailed("Allocation amount exceeds what is open")
    _apply(inv, amount)
    _apply(cn, amount)
    a = ARAllocation(company_id=inv.company_id, invoice_id=inv.id, source_type="CREDIT_NOTE", credit_document_id=cn.id,
                     amount=amount, allocation_date=max(cn.posting_date, inv.posting_date), created_by_id=actor.id)
    db.add(a)
    db.flush()
    return a


# ------------------------------------------------------------------ receipts
def save_receipt(db: Session, actor: Actor, company_id: int, data: dict, rec: ARReceipt | None = None) -> ARReceipt:
    actor.require("ar_receipt.create")
    cus = db.get(Customer, data["customer_id"])
    if cus is None or not cus.is_active:
        raise ValidationFailed("Customer not found or inactive")
    ba = db.get(BankAccount, data["bank_account_id"])
    if ba is None or not ba.is_active or ba.company_id != company_id:
        raise ValidationFailed("Bank / cash account not found")
    actor.require_site(ba.site_id)
    if rec is None:
        rec = ARReceipt(company_id=company_id, number=next_number(db, company_id, "AR-RCT", "RCT-", 6),
                        created_by_id=actor.id, status=DocStatus.DRAFT)
        db.add(rec)
    elif rec.status != DocStatus.DRAFT:
        wf_reset(db, actor, "AR_RECEIPT", rec)
    rec.customer_id, rec.bank_account_id = cus.id, ba.id
    rec.receipt_date = data["receipt_date"]
    rec.receipt_method = data.get("receipt_method", "TRANSFER")
    rec.reference = data.get("reference")
    rec.description = data.get("description") or f"Receipt from {cus.name}"
    rec.site_id = data.get("site_id") or ba.site_id
    rec.amount_received = money(data.get("amount_received") or 0)
    rec.tax_deducted = money(data.get("tax_deducted") or 0)
    rec.wht_tax_code_id = data.get("wht_tax_code_id") or cus.wht_tax_code_id
    if rec.tax_deducted and not rec.wht_tax_code_id:
        from backend.tax.models import TaxCode
        rec.wht_tax_code_id = db.scalar(select(TaxCode.id).where(TaxCode.code == "WHT-SUFF-CUS"))
    rec.gross_amount = rec.amount_received + rec.tax_deducted
    rec.lines.clear()
    allocated = ZERO
    for l in data.get("lines") or []:
        inv = db.get(ARDocument, l["document_id"])
        if inv is None or inv.customer_id != cus.id or inv.status != DocStatus.POSTED or inv.doc_type == ARDocType.CREDIT_NOTE:
            raise ValidationFailed("Receipts settle posted invoices / debit notes of the same customer")
        amt = money(l["amount"])
        if amt > inv.outstanding:
            raise ValidationFailed(f"Amount exceeds the outstanding balance of {inv.number}")
        rec.lines.append(ARReceiptLine(document_id=inv.id, amount=amt))
        allocated += amt
    if rec.gross_amount <= 0:
        raise ValidationFailed("Receipt amount must be positive")
    if allocated > rec.gross_amount:
        raise ValidationFailed("Allocated amount exceeds the receipt (received + tax deducted)")
    rec.is_advance = bool(data.get("is_advance")) or allocated < rec.gross_amount
    rec.unapplied_amount = rec.gross_amount - allocated
    db.flush()
    _receipt_lines(db, rec, cus, ba, validate=True, actor=actor)
    record(db, actor, "ar_receipt.save", "ar_receipt", rec.id, None, {"number": rec.number, "gross": str(rec.gross_amount)})
    return rec


def _receipt_lines(db: Session, rec: ARReceipt, cus: Customer, ba: BankAccount, *, validate: bool, actor) -> list[LineInput]:
    out = [LineInput(account_id=ba.gl_account_id, debit=rec.amount_received, site_id=ba.site_id,
                     description=rec.description, reference=rec.reference or rec.number)] if rec.amount_received else []
    if rec.tax_deducted:
        tc = tax.get_code(db, rec.wht_tax_code_id)
        acc = db.get(Account, tc.account_id)
        out.append(LineInput(account_id=tc.account_id, debit=rec.tax_deducted, tax_code_id=tc.id,
                             customer_id=cus.id if acc.party_type.value == "CUSTOMER" else None,
                             tax_base=rec.gross_amount, description=f"Tax deducted by {cus.name}", reference=rec.number))
    allocated = sum((l.amount for l in rec.lines), ZERO)
    if allocated:
        out.append(LineInput(account_id=control_account(db, cus), credit=allocated, customer_id=cus.id,
                             description=rec.description, reference=rec.number))
    if rec.unapplied_amount:
        out.append(LineInput(account_id=advance_account(db, cus), credit=rec.unapplied_amount, customer_id=cus.id,
                             description=f"Advance / unapplied - {rec.description}", reference=rec.number))
    if validate:
        engine.validate_lines(db, rec.company_id, out, manual=False, actor=actor, txn_date=rec.receipt_date)
    return out


def _post_receipt(db: Session, rec: ARReceipt, actor: Actor) -> None:
    rec = db.scalar(select(ARReceipt).where(ARReceipt.id == rec.id).with_for_update())
    cus = db.get(Customer, rec.customer_id)
    ba = db.get(BankAccount, rec.bank_account_id)
    for l in rec.lines:
        inv = db.scalar(select(ARDocument).where(ARDocument.id == l.document_id).with_for_update())
        if l.amount > inv.outstanding:
            raise Conflict(f"{inv.number} outstanding changed; recalculate the receipt")
    je = engine.create_and_post(db, actor, company_id=rec.company_id, journal_type=JournalType.ARR,
                                transaction_date=rec.receipt_date, description=f"{rec.number} {rec.description}",
                                lines=_receipt_lines(db, rec, cus, ba, validate=False, actor=actor),
                                reference=rec.reference or rec.number, source_module=SourceModule.AR,
                                source_type="ar_receipt", source_id=rec.id, source_key=f"AR-RCT-{rec.id}")
    if rec.tax_deducted:
        tc = tax.get_code(db, rec.wht_tax_code_id)
        rate = (rec.tax_deducted / rec.gross_amount).quantize(D("0.000001"))
        tax.record(db, company_id=rec.company_id, calc=tax.TaxCalc(tc, rate, rec.gross_amount, rec.tax_deducted, None),
                   journal=je, journal_line=tax.line_for(je, tc.account_id), source_type="ar_receipt", source_id=rec.id,
                   transaction_date=rec.receipt_date, customer=cus, site_id=rec.site_id, document_ref=rec.reference or rec.number)
    for l in rec.lines:
        inv = db.get(ARDocument, l.document_id)
        _apply(inv, l.amount)
        db.add(ARAllocation(company_id=rec.company_id, invoice_id=inv.id, source_type="RECEIPT", receipt_id=rec.id,
                            amount=l.amount, allocation_date=rec.receipt_date, journal_id=je.id, created_by_id=actor.id))
    rec.journal_id = je.id
    rec.status = DocStatus.POSTED
    db.flush()


def receipt_spec(db: Session, rec: ARReceipt) -> wf.WorkflowSpec:
    return wf.WorkflowSpec(doc_type="AR_RECEIPT", perm_prefix="ar_receipt", amount=rec.gross_amount, site_id=rec.site_id,
                           poster=_post_receipt)


def apply_advance(db: Session, actor: Actor, receipt_id: int, invoice_id: int, amount: Decimal, on_date: date) -> ARAllocation:
    actor.require("ar_receipt.post")
    rec = db.scalar(select(ARReceipt).where(ARReceipt.id == receipt_id).with_for_update())
    inv = db.scalar(select(ARDocument).where(ARDocument.id == invoice_id).with_for_update())
    amount = money(amount)
    if rec is None or rec.status != DocStatus.POSTED or amount <= 0 or amount > rec.unapplied_amount:
        raise ValidationFailed("Amount exceeds the unapplied receipt")
    if inv is None or inv.customer_id != rec.customer_id or inv.status != DocStatus.POSTED or amount > inv.outstanding:
        raise ValidationFailed("Select a posted invoice of the same customer with enough outstanding")
    cus = db.get(Customer, rec.customer_id)
    je = engine.create_and_post(db, actor, company_id=rec.company_id, journal_type=JournalType.ARA, transaction_date=on_date,
                                description=f"Advance {rec.number} applied to {inv.number}",
                                lines=[LineInput(account_id=advance_account(db, cus), debit=amount, customer_id=cus.id, reference=rec.number),
                                       LineInput(account_id=control_account(db, cus), credit=amount, customer_id=cus.id, reference=inv.number)],
                                source_module=SourceModule.AR, source_type="ar_advance_application", source_id=rec.id)
    rec.unapplied_amount = money(rec.unapplied_amount - amount)
    _apply(inv, amount)
    a = ARAllocation(company_id=rec.company_id, invoice_id=inv.id, source_type="ADVANCE", receipt_id=rec.id, amount=amount,
                     allocation_date=on_date, journal_id=je.id, created_by_id=actor.id)
    db.add(a)
    db.flush()
    return a


def reverse_receipt(db: Session, actor: Actor, rec: ARReceipt, reversal_date: date, reason: str) -> ARReceipt:
    actor.require("ar_receipt.reverse")
    if rec.status != DocStatus.POSTED:
        raise Conflict("Only posted receipts can be reversed")
    applied_adv = db.scalar(select(func.count()).select_from(ARAllocation).where(
        ARAllocation.receipt_id == rec.id, ARAllocation.source_type == "ADVANCE", ARAllocation.is_active.is_(True)))
    if applied_adv:
        raise Conflict("Part of this receipt was applied as an advance; reverse the applications first")
    rev = engine.create_reversal(db, rec.journal_id, actor, reversal_date, reason, post=True)
    tax.reverse_for_journal(db, rec.journal_id, rev)
    for a in db.scalars(select(ARAllocation).where(ARAllocation.receipt_id == rec.id, ARAllocation.is_active.is_(True))).all():
        inv = db.scalar(select(ARDocument).where(ARDocument.id == a.invoice_id).with_for_update())
        _apply(inv, -a.amount)
        a.is_active = False
    rec.unapplied_amount = ZERO
    rec.status = DocStatus.REVERSED
    record(db, actor, "ar_receipt.reverse", "ar_receipt", rec.id, None, {"reversal": rev.number, "reason": reason})
    return rec


# ------------------------------------------------------------------ reports
def open_items(db: Session, company_id: int, as_of: date, customer_id: int | None = None) -> list[dict]:
    q = select(ARDocument).where(ARDocument.company_id == company_id, ARDocument.posting_date <= as_of,
                                 or_(ARDocument.status == DocStatus.POSTED,
                                     and_(ARDocument.status == DocStatus.REVERSED,
                                          ARDocument.journal_id.in_(select(JournalEntry.reversal_of_id).where(
                                              JournalEntry.posting_date > as_of, JournalEntry.reversal_of_id.is_not(None))))))
    if customer_id:
        q = q.where(ARDocument.customer_id == customer_id)
    docs = db.scalars(q).all()
    ids = [d.id for d in docs]

    def settled(field):
        if not ids:
            return {}
        col = getattr(ARAllocation, field)
        return {k: D(v) for k, v in db.execute(select(col, func.sum(ARAllocation.amount)).where(
            col.in_(ids), ARAllocation.allocation_date <= as_of, ARAllocation.is_active.is_(True)).group_by(col)).all()}
    by_inv, by_note = settled("invoice_id"), settled("credit_document_id")
    out = []
    for d in docs:
        open_amt = d.total - by_inv.get(d.id, ZERO) - by_note.get(d.id, ZERO)
        if open_amt == 0:
            continue
        sign = -1 if d.doc_type == ARDocType.CREDIT_NOTE else 1
        out.append({"document_id": d.id, "number": d.number, "doc_type": d.doc_type.value, "customer_id": d.customer_id,
                    "invoice_date": d.invoice_date, "due_date": d.due_date, "total": d.total, "open": open_amt * sign,
                    "days_overdue": (as_of - d.due_date).days, "site_id": d.site_id})
    rq = select(ARReceipt).where(ARReceipt.company_id == company_id, ARReceipt.status == DocStatus.POSTED,
                                 ARReceipt.receipt_date <= as_of)
    if customer_id:
        rq = rq.where(ARReceipt.customer_id == customer_id)
    for r in db.scalars(rq).all():
        alloc = sum((l.amount for l in r.lines), ZERO)
        applied = D(db.scalar(select(func.coalesce(func.sum(ARAllocation.amount), 0)).where(
            ARAllocation.receipt_id == r.id, ARAllocation.source_type == "ADVANCE", ARAllocation.is_active.is_(True),
            ARAllocation.allocation_date <= as_of)) or 0)
        unapplied = r.gross_amount - alloc - applied
        if unapplied:
            out.append({"document_id": None, "receipt_id": r.id, "number": r.number, "doc_type": "ADVANCE",
                        "customer_id": r.customer_id, "invoice_date": r.receipt_date, "due_date": r.receipt_date,
                        "total": r.gross_amount, "open": -unapplied, "days_overdue": 0, "site_id": r.site_id, "is_advance": True})
    return out


def aging(db: Session, company_id: int, as_of: date, customer_id: int | None = None) -> dict:
    items = open_items(db, company_id, as_of, customer_id)
    cus = {c.id: c for c in db.scalars(select(Customer)).all()}
    per: dict[int, dict] = {}
    for it in items:
        c = cus[it["customer_id"]]
        row = per.setdefault(c.id, {"customer_id": c.id, "code": c.code, "label": c.name, "level": 1, "style": "line",
                                    **{k: ZERO for k, *_ in BUCKETS}, "unapplied": ZERO, "total": ZERO,
                                    "drill": {"customer_id": c.id}})
        amt = it["open"]
        if it["doc_type"] in ("ADVANCE", "CREDIT_NOTE"):
            row["unapplied"] += amt
        else:
            days = it["days_overdue"]
            for key, _l, lo, hi in BUCKETS:
                if (lo is None and days <= 0) or (lo is not None and days >= lo and (hi is None or days <= hi)):
                    row[key] += amt
                    break
        row["total"] += amt
    rows_out = sorted(per.values(), key=lambda r: r["code"])
    tot = {"label": "TOTAL", "level": 0, "style": "grand"}
    for k in [b[0] for b in BUCKETS] + ["unapplied", "total"]:
        tot[k] = money(sum((r[k] for r in rows_out), ZERO))
    rows_out.append(tot)
    cols = [{"key": "code", "label": "Code", "type": "text"}, {"key": "label", "label": "Customer", "type": "text"}] + [
        {"key": k, "label": lbl, "type": "money"} for k, lbl, *_ in BUCKETS] + [
        {"key": "unapplied", "label": "Unapplied / advances", "type": "money"}, {"key": "total", "label": "Net receivable", "type": "money"}]
    return {"title": "Accounts Receivable Aging", "subtitle": f"As at {as_of.strftime('%d %b %Y')} (days past due date)",
            "columns": cols, "rows": rows_out, "meta": {"items": items}}


def reconciliation(db: Session, company_id: int, as_of: date) -> dict:
    items = open_items(db, company_id, as_of)
    cats = db.scalars(select(CustomerCategory)).all()
    ctrl_ids = sorted({c.ar_control_account_id for c in cats})
    adv_ids = sorted({c.advance_account_id for c in cats if c.advance_account_id})

    def gl(ids):
        return D(db.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
            JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.posting_date <= as_of,
            JournalLine.account_id.in_(ids))) or 0) if ids else ZERO
    # Customer-party lines on control accounts that come from other modules (cinema day close / collections)
    sub_recv = money(sum((i["open"] for i in items if i["doc_type"] != "ADVANCE"), ZERO))
    sub_adv = money(-sum((i["open"] for i in items if i["doc_type"] == "ADVANCE"), ZERO))
    cinema = D(db.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
        JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.posting_date <= as_of,
        JournalLine.account_id.in_(ctrl_ids), JournalLine.source_module == "CINEMA")) or 0)
    gl_recv = money(gl(ctrl_ids))
    gl_adv = money(-gl(adv_ids))
    rows_out = [
        {"label": "Trade receivables - AR documents", "c0": sub_recv, "level": 1, "style": "line"},
        {"label": "Collections clearing from cinema day close (gateway / wallet / platform / corporate)", "c0": money(cinema),
         "level": 1, "style": "line"},
        {"label": "Receivables per sub-ledger", "c0": money(sub_recv + cinema), "c1": gl_recv,
         "c2": money(sub_recv + cinema - gl_recv), "level": 0, "style": "total"},
        {"label": "Customer advances", "c0": sub_adv, "c1": gl_adv, "c2": money(sub_adv - gl_adv), "level": 0, "style": "total"},
    ]
    ok = money(sub_recv + cinema - gl_recv) == 0 and money(sub_adv - gl_adv) == 0
    non_module = db.execute(select(JournalLine.journal_id, JournalEntry.number, JournalLine.debit, JournalLine.credit)
                            .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
                            .where(JournalLine.company_id == company_id, JournalLine.is_posted.is_(True),
                                   JournalLine.posting_date <= as_of, JournalLine.account_id.in_(ctrl_ids + adv_ids),
                                   JournalLine.source_module.not_in(["AR", "CINEMA", "OPENING"]))).all()
    return {"title": "AR Sub-ledger to GL Reconciliation", "subtitle": f"As at {as_of.strftime('%d %b %Y')}",
            "columns": [{"key": "label", "label": "", "type": "text"}, {"key": "c0", "label": "Sub-ledger", "type": "money"},
                        {"key": "c1", "label": "General ledger", "type": "money"}, {"key": "c2", "label": "Difference", "type": "money"}],
            "rows": rows_out, "meta": {"reconciled": ok, "non_module_lines": [
                {"journal_id": j, "number": n, "debit": d, "credit": c} for j, n, d, c in non_module]}}


def customer_statement(db: Session, company_id: int, customer_id: int, date_from: date, date_to: date) -> dict:
    cus = db.get(Customer, customer_id)
    if cus is None:
        raise NotFound("Customer not found")
    cats = db.scalars(select(CustomerCategory)).all()
    acc_ids = list({c.ar_control_account_id for c in cats} | {c.advance_account_id for c in cats if c.advance_account_id})
    base = select(JournalLine, JournalEntry).join(JournalEntry, JournalEntry.id == JournalLine.journal_id).where(
        JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.customer_id == customer_id,
        JournalLine.account_id.in_(acc_ids))
    opening = D(db.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
        JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.customer_id == customer_id,
        JournalLine.account_id.in_(acc_ids), JournalLine.posting_date < date_from)) or 0)
    bal = opening
    rows_out = [{"label": "Opening balance", "style": "subtotal", "level": 0, "balance": money(opening)}]
    for l, j in db.execute(base.where(JournalLine.posting_date.between(date_from, date_to))
                           .order_by(JournalLine.posting_date, JournalLine.id)).all():
        bal += l.debit - l.credit
        rows_out.append({"label": l.posting_date.isoformat(), "number": j.number, "journal_id": j.id,
                         "description": l.description or j.description, "reference": l.reference, "debit": l.debit,
                         "credit": l.credit, "balance": money(bal), "level": 1, "style": "line"})
    rows_out.append({"label": "Closing balance (receivable)", "style": "grand", "level": 0, "balance": money(bal)})
    return {"title": f"Customer Statement - {cus.code} {cus.name}", "subtitle": f"{date_from} to {date_to}",
            "columns": [{"key": "label", "label": "Date", "type": "text"}, {"key": "number", "label": "Journal", "type": "text"},
                        {"key": "description", "label": "Description", "type": "text"}, {"key": "reference", "label": "Reference", "type": "text"},
                        {"key": "debit", "label": "Debit (invoiced)", "type": "money"}, {"key": "credit", "label": "Credit (received)", "type": "money"},
                        {"key": "balance", "label": "Balance", "type": "money"}],
            "rows": rows_out, "meta": {"opening": money(opening), "closing": money(bal)}}
