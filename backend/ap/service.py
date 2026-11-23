"""Accounts payable services."""
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
from backend.ap.models import (
    APAllocation, APDocType, APDocument, APDocumentLine, APPayment, APPaymentLine, PaymentStatus, Supplier,
    SupplierCategory,
)
from backend.audit.service import record
from backend.banking.models import BankAccount
from backend.config import get_settings
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.money import ZERO, money
from backend.tax import engine as tax
from backend.tax.models import TaxType
from backend.workflow import engine as wf

D = Decimal


# ------------------------------------------------------------------ suppliers
def validate_supplier(db: Session, actor: Actor, sup: Supplier, data: dict) -> None:
    for field in ("ntn", "cnic"):
        val = data.get(field)
        if val:
            dup = db.scalar(select(Supplier).where(getattr(Supplier, field) == val, Supplier.id != (sup.id or 0)))
            if dup:
                raise Conflict(f"{field.upper()} {val} already used by supplier {dup.code} (V26)")
    cat_id = data.get("category_id") or sup.category_id
    if cat_id:
        cat = db.get(SupplierCategory, cat_id)
        if cat is None:
            raise ValidationFailed("Supplier category not found")
        for f, default in (("wht_tax_code_id", cat.default_wht_tax_code_id), ("st_tax_code_id", cat.default_st_tax_code_id),
                           ("stw_tax_code_id", cat.default_stw_tax_code_id)):
            if not data.get(f) and not getattr(sup, f, None):
                data[f] = default
    if not sup.id and not data.get("code"):
        last = db.scalar(select(func.max(Supplier.code)).where(Supplier.code.like("V%")))
        n = int(last[1:]) + 1 if last and last[1:].isdigit() else 1
        data["code"] = f"V{n:05d}"
    if not data.get("beneficiary_name") and not sup.beneficiary_name:
        data["beneficiary_name"] = data.get("name") or sup.name


def control_account(db: Session, sup: Supplier) -> int:
    return db.get(SupplierCategory, sup.category_id).ap_control_account_id


def advance_account(db: Session, sup: Supplier) -> int:
    cat = db.get(SupplierCategory, sup.category_id)
    if not cat.advance_account_id:
        raise ValidationFailed("Supplier category has no advance account")
    return cat.advance_account_id


# ------------------------------------------------------------------ documents
def _doc_number(db: Session, company_id: int, doc_type: APDocType) -> str:
    prefix = {"INVOICE": "PI", "CREDIT_NOTE": "PCN", "DEBIT_NOTE": "PDN"}[doc_type.value]
    return next_number(db, company_id, f"AP-{prefix}", f"{prefix}-", 6)


def save_document(db: Session, actor: Actor, company_id: int, data: dict, doc: APDocument | None = None) -> tuple[APDocument, list[str]]:
    actor.require("ap_invoice.create")
    lines = data.pop("lines")
    if not lines:
        raise ValidationFailed("At least one line is required")
    sup = db.get(Supplier, data["supplier_id"])
    if sup is None or not sup.is_active:
        raise ValidationFailed("Supplier not found or inactive (V14)")
    doc_type = APDocType(data.get("doc_type", "INVOICE"))
    inv_no = (data.get("supplier_invoice_no") or "").strip()
    if not inv_no:
        raise ValidationFailed("Supplier document number is required")
    dup = db.scalar(select(APDocument).where(APDocument.supplier_id == sup.id, APDocument.doc_type == doc_type,
                                             func.lower(APDocument.supplier_invoice_no) == inv_no.lower(),
                                             APDocument.status != DocStatus.CANCELLED,
                                             APDocument.id != (doc.id if doc else 0)))
    if dup:
        raise Conflict(f"Duplicate supplier document: {inv_no} already entered as {dup.number} (V17)",
                       code="duplicate_invoice")
    if doc is None:
        doc = APDocument(company_id=company_id, doc_type=doc_type, number=_doc_number(db, company_id, doc_type),
                         created_by_id=actor.id, status=DocStatus.DRAFT)
        db.add(doc)
    elif doc.status not in (DocStatus.DRAFT, DocStatus.SUBMITTED, DocStatus.CHECKED, DocStatus.APPROVED):
        raise Conflict("Only unposted documents can be edited")
    else:
        if doc.status != DocStatus.DRAFT:
            wf_reset(db, actor, "AP_INVOICE", doc)
    invoice_date = data["invoice_date"]
    doc.supplier_id = sup.id
    doc.doc_type = doc_type
    doc.supplier_invoice_no = inv_no
    doc.invoice_date = invoice_date
    doc.posting_date = data.get("posting_date") or invoice_date
    doc.due_date = data.get("due_date") or invoice_date + timedelta(days=sup.payment_terms_days or 0)
    doc.site_id = data.get("site_id")
    doc.description = data.get("description") or f"{sup.name} {inv_no}"
    doc.related_document_id = data.get("related_document_id")
    actor.require_site(doc.site_id)
    doc.lines.clear()
    subtotal = tax_total = ZERO
    for n, l in enumerate(lines, start=1):
        amount = money(l.get("amount") if l.get("amount") is not None else D(str(l.get("quantity", 1))) * D(str(l.get("unit_price", 0))))
        if amount <= 0:
            raise ValidationFailed(f"Line {n}: amount must be positive")
        st_code = l["st_tax_code_id"] if "st_tax_code_id" in l else sup.st_tax_code_id
        st_amount, st_rate = ZERO, None
        if st_code:
            if l.get("st_amount") is not None:
                st_amount = money(l["st_amount"])
                st_rate = (st_amount / amount).quantize(D("0.000001")) if amount else None
            else:
                calc = tax.compute(db, st_code, amount, invoice_date, site_id=l.get("site_id") or doc.site_id)
                st_amount, st_rate = calc.amount, calc.rate
        doc.lines.append(APDocumentLine(line_no=n, account_id=l["account_id"], site_id=l.get("site_id") or doc.site_id,
                                        cost_centre_id=l.get("cost_centre_id"), description=l.get("description"),
                                        quantity=D(str(l.get("quantity", 1))), unit_price=money(l.get("unit_price") or amount),
                                        amount=amount, st_tax_code_id=st_code, st_rate=st_rate, st_amount=st_amount,
                                        dimensions={str(k): int(v) for k, v in (l.get("dimensions") or {}).items() if v} or None,
                                        asset_id=l.get("asset_id")))
        subtotal += amount
        tax_total += st_amount
    doc.subtotal, doc.tax_total, doc.total = money(subtotal), money(tax_total), money(subtotal + tax_total)
    db.flush()
    _journal_lines(db, doc, sup, validate=True, actor=actor)
    warnings = []
    days = get_settings().duplicate_invoice_warning_days
    similar = db.scalars(select(APDocument).where(APDocument.supplier_id == sup.id, APDocument.total == doc.total,
                                                  APDocument.id != doc.id, APDocument.status != DocStatus.CANCELLED,
                                                  APDocument.invoice_date.between(invoice_date - timedelta(days=days),
                                                                                  invoice_date + timedelta(days=days)))).all()
    for s in similar:
        warnings.append(f"Same supplier and amount within {days} days: {s.number} ({s.supplier_invoice_no})")
    record(db, actor, "ap_document.save", "ap_document", doc.id, None,
           {"number": doc.number, "supplier": sup.code, "total": str(doc.total)})
    return doc, warnings


def wf_reset(db: Session, actor: Actor, doc_type: str, doc) -> None:
    from backend.workflow.models import WorkflowHistory
    db.add(WorkflowHistory(doc_type=doc_type, doc_id=doc.id, action="edit", from_status=doc.status.value,
                           to_status="DRAFT", user_id=actor.id, comment="Edited: approvals cleared"))
    doc.status = DocStatus.DRAFT


def _journal_lines(db: Session, doc: APDocument, sup: Supplier, *, validate: bool, actor: Actor | None) -> list[LineInput]:
    ctrl = control_account(db, sup)
    out: list[LineInput] = []
    credit_side = doc.doc_type != APDocType.INVOICE   # notes reduce the payable
    tax_lines: dict[int, list] = defaultdict(lambda: [ZERO, ZERO])
    for l in doc.lines:
        amt = l.amount
        tc = tax.get_code(db, l.st_tax_code_id) if l.st_tax_code_id else None
        if tc is not None and not tc.is_recoverable:
            amt += l.st_amount  # inadmissible tax is part of the cost
        elif tc is not None and l.st_amount:
            tax_lines[tc.id][0] += l.st_amount
            tax_lines[tc.id][1] += l.amount
        li = LineInput(account_id=l.account_id, site_id=l.site_id, cost_centre_id=l.cost_centre_id,
                       description=l.description or doc.description, reference=doc.supplier_invoice_no,
                       dimensions={int(k): int(v) for k, v in (l.dimensions or {}).items()})
        if db.get(Account, l.account_id).party_type.value == "SUPPLIER":
            li.supplier_id = sup.id
        if credit_side:
            li.credit = amt
        else:
            li.debit = amt
        out.append(li)
    for tcid, (tamt, base) in tax_lines.items():
        tc = tax.get_code(db, tcid)
        li = LineInput(account_id=tc.account_id, tax_code_id=tc.id, tax_base=money(base), description=f"{tc.name} - {doc.supplier_invoice_no}",
                       reference=doc.supplier_invoice_no)
        if credit_side:
            li.credit = tamt
        else:
            li.debit = tamt
        out.append(li)
    ctrl_line = LineInput(account_id=ctrl, supplier_id=sup.id, description=doc.description, reference=doc.supplier_invoice_no)
    if credit_side:
        ctrl_line.debit = doc.total
    else:
        ctrl_line.credit = doc.total
    out.append(ctrl_line)
    if validate:
        engine.validate_lines(db, doc.company_id, out, manual=False, actor=actor, txn_date=doc.posting_date)
    return out


def _post_document(db: Session, doc: APDocument, actor: Actor) -> None:
    doc = db.scalar(select(APDocument).where(APDocument.id == doc.id).with_for_update())
    sup = db.get(Supplier, doc.supplier_id)
    lines = _journal_lines(db, doc, sup, validate=False, actor=actor)
    jt = JournalType.API if doc.doc_type == APDocType.INVOICE else JournalType.APC
    je = engine.create_and_post(db, actor, company_id=doc.company_id, journal_type=jt, transaction_date=doc.invoice_date,
                                posting_date=doc.posting_date, description=f"{doc.number} {doc.description}",
                                lines=lines, reference=doc.supplier_invoice_no, source_module=SourceModule.AP,
                                source_type="ap_document", source_id=doc.id, source_key=f"AP-DOC-{doc.id}")
    sign = 1 if doc.doc_type == APDocType.INVOICE else -1
    for l in doc.lines:
        if l.st_tax_code_id and l.st_amount:
            tc = tax.get_code(db, l.st_tax_code_id)
            if tc.is_recoverable:
                calc = tax.TaxCalc(tc, l.st_rate or ZERO, l.amount, l.st_amount, None)
                tax.record(db, company_id=doc.company_id, calc=calc, journal=je, journal_line=tax.line_for(je, tc.account_id, tc.id),
                           source_type="ap_document", source_id=doc.id, transaction_date=doc.posting_date, supplier=sup,
                           site_id=l.site_id, document_ref=doc.supplier_invoice_no, sign=sign)
    doc.journal_id = je.id
    doc.status = DocStatus.POSTED
    db.flush()
    if doc.doc_type != APDocType.INVOICE and doc.related_document_id:
        inv = db.get(APDocument, doc.related_document_id)
        if inv and inv.status == DocStatus.POSTED and inv.supplier_id == doc.supplier_id and inv.outstanding > 0:
            allocate_credit(db, actor, doc.id, inv.id, min(inv.outstanding, doc.outstanding), _skip_perm=True)


def doc_spec(db: Session, doc: APDocument) -> wf.WorkflowSpec:
    return wf.WorkflowSpec(doc_type="AP_INVOICE", perm_prefix="ap_invoice", amount=doc.total, site_id=doc.site_id,
                           poster=_post_document)


def act_document(db: Session, actor: Actor, doc: APDocument, action: str, comment: str | None = None) -> list[str]:
    warnings: list[str] = []
    if action == "submit":
        from backend.budgeting.service import check_budget
        warnings = check_budget(db, doc.company_id, doc.posting_date,
                                [(l.account_id, l.site_id, l.cost_centre_id, l.amount) for l in doc.lines]
                                if doc.doc_type == APDocType.INVOICE else [])
    wf.transition(db, doc, doc_spec(db, doc), action, actor, comment)
    return warnings


def reverse_document(db: Session, actor: Actor, doc: APDocument, reversal_date: date, reason: str) -> APDocument:
    actor.require("ap_invoice.reverse")
    if doc.status != DocStatus.POSTED:
        raise Conflict("Only posted documents can be reversed")
    active = db.scalar(select(func.count()).select_from(APAllocation).where(
        APAllocation.is_active.is_(True), or_(APAllocation.invoice_id == doc.id, APAllocation.credit_document_id == doc.id)))
    if active:
        raise Conflict("Document has payments or allocations; reverse or unallocate them first")
    rev = engine.create_reversal(db, doc.journal_id, actor, reversal_date, reason, post=True)
    tax.reverse_for_journal(db, doc.journal_id, rev)
    doc.status = DocStatus.REVERSED
    record(db, actor, "ap_document.reverse", "ap_document", doc.id, None, {"reversal_journal": rev.number, "reason": reason})
    return doc


# ------------------------------------------------------------------ allocations
def _apply(db: Session, inv: APDocument, amount: Decimal) -> None:
    inv.amount_settled = money(inv.amount_settled + amount)
    if inv.amount_settled > inv.total:
        raise ValidationFailed(f"Allocation exceeds the outstanding amount of {inv.number}")
    inv.payment_status = PaymentStatus.PAID if inv.amount_settled == inv.total else (
        PaymentStatus.PARTIAL if inv.amount_settled > 0 else PaymentStatus.UNPAID)


def allocate_credit(db: Session, actor: Actor, credit_doc_id: int, invoice_id: int, amount: Decimal, *,
                    _skip_perm: bool = False) -> APAllocation:
    if not _skip_perm:
        actor.require("ap_invoice.post")
    cn = db.scalar(select(APDocument).where(APDocument.id == credit_doc_id).with_for_update())
    inv = db.scalar(select(APDocument).where(APDocument.id == invoice_id).with_for_update())
    amount = money(amount)
    if cn is None or inv is None or cn.doc_type == APDocType.INVOICE or inv.doc_type != APDocType.INVOICE:
        raise ValidationFailed("Allocate a credit or debit note against an invoice")
    if cn.supplier_id != inv.supplier_id or cn.status != DocStatus.POSTED or inv.status != DocStatus.POSTED:
        raise ValidationFailed("Both documents must be posted and belong to the same supplier")
    if amount <= 0 or amount > cn.outstanding or amount > inv.outstanding:
        raise ValidationFailed("Allocation amount exceeds what is open on the note or the invoice")
    _apply(db, inv, amount)
    _apply(db, cn, amount)
    a = APAllocation(company_id=inv.company_id, invoice_id=inv.id, source_type=cn.doc_type.value,
                     credit_document_id=cn.id, amount=amount, allocation_date=max(cn.posting_date, inv.posting_date),
                     created_by_id=actor.id)
    db.add(a)
    db.flush()
    record(db, actor, "ap.allocate", "ap_document", inv.id, None, {"note": cn.number, "amount": str(amount)})
    return a


# ------------------------------------------------------------------ payments
def _payment_number(db: Session, company_id: int) -> str:
    return next_number(db, company_id, "AP-PAY", "PAY-", 6)


def default_bank(db: Session, company_id: int) -> BankAccount:
    ba = db.scalar(select(BankAccount).where(BankAccount.company_id == company_id, BankAccount.is_default_payment.is_(True),
                                             BankAccount.is_active.is_(True)))
    if ba is None:
        raise ValidationFailed("No default payment bank configured")
    return ba


def compute_payment_line(db: Session, sup: Supplier, pay_date: date, amount: Decimal, inv: APDocument | None,
                         override_rate: Decimal | None = None, reason: str | None = None) -> dict:
    """WHT on the amount paid excluding sales tax; STW on the sales tax portion paid (V20)."""
    amount = money(amount)
    st_portion = money(amount * inv.tax_total / inv.total) if inv is not None and inv.total else ZERO
    base = amount - st_portion
    payee = sup.supplier_type.value
    out = {"amount": amount, "wht_tax_code_id": sup.wht_tax_code_id, "wht_rate": ZERO, "wht_base": base,
           "wht_amount": ZERO, "stw_tax_code_id": sup.stw_tax_code_id, "stw_rate": ZERO, "stw_amount": ZERO,
           "rate_overridden": False, "override_reason": None}
    if sup.wht_tax_code_id:
        if override_rate is None and sup.wht_exemption_rate is not None and sup.wht_exemption_until and pay_date <= sup.wht_exemption_until:
            override_rate, reason = sup.wht_exemption_rate, "Exemption / reduced-rate certificate (s.159)"
        calc = tax.compute(db, sup.wht_tax_code_id, base, pay_date, payee_type=payee, atl_status=sup.atl_status,
                           override_rate=override_rate, reason=reason)
        out.update(wht_rate=calc.rate, wht_amount=calc.amount, rate_overridden=calc.overridden, override_reason=calc.reason)
    if sup.stw_tax_code_id and st_portion > 0:
        calc = tax.compute(db, sup.stw_tax_code_id, st_portion, pay_date, payee_type=payee, atl_status=sup.atl_status)
        out.update(stw_rate=calc.rate, stw_amount=calc.amount)
    return out


def save_payment(db: Session, actor: Actor, company_id: int, data: dict, pay: APPayment | None = None) -> APPayment:
    actor.require("ap_payment.create")
    sup = db.get(Supplier, data["supplier_id"])
    if sup is None or not sup.is_active:
        raise ValidationFailed("Supplier not found or inactive")
    if sup.payment_hold:
        raise ValidationFailed(f"Supplier {sup.code} is on payment hold", code="payment_hold")
    ba = db.get(BankAccount, data["bank_account_id"]) if data.get("bank_account_id") else default_bank(db, company_id)
    if ba is None or not ba.is_active or ba.company_id != company_id:
        raise ValidationFailed("Bank account not found")
    actor.require_site(ba.site_id)
    lines = data.get("lines") or []
    is_adv = bool(data.get("is_advance"))
    if is_adv and (len(lines) != 1 or lines[0].get("document_id")):
        raise ValidationFailed("An advance has exactly one line without an invoice")
    if not is_adv and not lines:
        raise ValidationFailed("Select at least one invoice to pay")
    if (data.get("override_rate") is not None or any(l.get("override_rate") is not None for l in lines)):
        actor.require("tax.override")
    if pay is None:
        pay = APPayment(company_id=company_id, number=_payment_number(db, company_id), created_by_id=actor.id,
                        status=DocStatus.DRAFT)
        db.add(pay)
    elif pay.status != DocStatus.DRAFT:
        wf_reset(db, actor, "AP_PAYMENT", pay)
    pay.supplier_id, pay.bank_account_id = sup.id, ba.id
    pay.payment_date = data["payment_date"]
    pay.payment_method = data.get("payment_method", "TRANSFER")
    pay.cheque_no, pay.reference = data.get("cheque_no"), data.get("reference")
    pay.description = data.get("description") or f"Payment to {sup.name}"
    pay.is_advance, pay.site_id = is_adv, data.get("site_id") or ba.site_id
    pay.lines.clear()
    seen = set()
    for l in lines:
        inv = None
        if l.get("document_id"):
            if l["document_id"] in seen:
                raise ValidationFailed("An invoice appears twice in the payment")
            seen.add(l["document_id"])
            inv = db.get(APDocument, l["document_id"])
            if inv is None or inv.supplier_id != sup.id or inv.doc_type != APDocType.INVOICE or inv.status != DocStatus.POSTED:
                raise ValidationFailed("Payments can only settle posted invoices of the same supplier (V31)")
            if money(l["amount"]) > inv.outstanding:
                raise ValidationFailed(f"Amount exceeds the outstanding balance of {inv.number} ({inv.outstanding:,.2f})")
        calc = compute_payment_line(db, sup, pay.payment_date, D(str(l["amount"])), inv, l.get("override_rate"),
                                    l.get("override_reason"))
        pay.lines.append(APPaymentLine(document_id=inv.id if inv else None, **calc))
    pay.gross_amount = money(sum((l.amount for l in pay.lines), ZERO))
    pay.wht_amount = money(sum((l.wht_amount for l in pay.lines), ZERO))
    pay.stw_amount = money(sum((l.stw_amount for l in pay.lines), ZERO))
    pay.net_amount = pay.gross_amount - pay.wht_amount - pay.stw_amount
    if pay.gross_amount <= 0 or pay.net_amount < 0:
        raise ValidationFailed("Payment amount must be positive")
    db.flush()
    _payment_lines(db, pay, sup, ba, validate=True, actor=actor)
    record(db, actor, "ap_payment.save", "ap_payment", pay.id, None,
           {"number": pay.number, "gross": str(pay.gross_amount), "wht": str(pay.wht_amount), "net": str(pay.net_amount)})
    return pay


def _payment_lines(db: Session, pay: APPayment, sup: Supplier, ba: BankAccount, *, validate: bool, actor) -> list[LineInput]:
    out = []
    debit_acc = advance_account(db, sup) if pay.is_advance else control_account(db, sup)
    out.append(LineInput(account_id=debit_acc, debit=pay.gross_amount, supplier_id=sup.id,
                         description=pay.description, reference=pay.number))
    wht: dict[int, list] = defaultdict(lambda: [ZERO, ZERO])
    stw: dict[int, list] = defaultdict(lambda: [ZERO, ZERO])
    for l in pay.lines:
        if l.wht_amount:
            wht[l.wht_tax_code_id][0] += l.wht_amount
            wht[l.wht_tax_code_id][1] += l.wht_base
        if l.stw_amount:
            stw[l.stw_tax_code_id][0] += l.stw_amount
            stw[l.stw_tax_code_id][1] += l.amount
    for group in (wht, stw):
        for tcid, (amt, base) in group.items():
            tc = tax.get_code(db, tcid)
            out.append(LineInput(account_id=tc.account_id, credit=amt, supplier_id=sup.id, tax_code_id=tc.id,
                                 tax_base=money(base), description=f"{tc.name} - {sup.name}", reference=pay.number))
    if pay.net_amount > 0:
        out.append(LineInput(account_id=ba.gl_account_id, credit=pay.net_amount, site_id=ba.site_id,
                             description=f"{pay.description} {pay.cheque_no or ''}".strip(), reference=pay.cheque_no or pay.number))
    if validate:
        engine.validate_lines(db, pay.company_id, out, manual=False, actor=actor, txn_date=pay.payment_date)
    return out


def _post_payment(db: Session, pay: APPayment, actor: Actor) -> None:
    pay = db.scalar(select(APPayment).where(APPayment.id == pay.id).with_for_update())
    sup = db.get(Supplier, pay.supplier_id)
    if sup.payment_hold:
        raise ValidationFailed(f"Supplier {sup.code} is on payment hold", code="payment_hold")
    ba = db.get(BankAccount, pay.bank_account_id)
    for l in pay.lines:  # lock and re-check invoices
        if l.document_id:
            inv = db.scalar(select(APDocument).where(APDocument.id == l.document_id).with_for_update())
            if l.amount > inv.outstanding:
                raise Conflict(f"{inv.number} outstanding changed ({inv.outstanding:,.2f}); recalculate the payment")
    je = engine.create_and_post(db, actor, company_id=pay.company_id, journal_type=JournalType.APP,
                                transaction_date=pay.payment_date, description=f"{pay.number} {pay.description}",
                                lines=_payment_lines(db, pay, sup, ba, validate=False, actor=actor),
                                reference=pay.cheque_no or pay.number, source_module=SourceModule.AP,
                                source_type="ap_payment", source_id=pay.id, source_key=f"AP-PAY-{pay.id}")
    for l in pay.lines:
        for tcid, amt, base, rate in ((l.wht_tax_code_id, l.wht_amount, l.wht_base, l.wht_rate),
                                      (l.stw_tax_code_id, l.stw_amount, l.amount, l.stw_rate)):
            if tcid and amt:
                tc = tax.get_code(db, tcid)
                calc = tax.TaxCalc(tc, rate, base, amt, None, l.rate_overridden and tc.tax_type == TaxType.WHT_DEDUCTED,
                                   l.override_reason)
                inv = db.get(APDocument, l.document_id) if l.document_id else None
                tax.record(db, company_id=pay.company_id, calc=calc, journal=je,
                           journal_line=tax.line_for(je, tc.account_id, tc.id), source_type="ap_payment",
                           source_id=pay.id, transaction_date=pay.payment_date, supplier=sup, site_id=pay.site_id,
                           document_ref=inv.supplier_invoice_no if inv else pay.number)
        if l.document_id:
            inv = db.get(APDocument, l.document_id)
            _apply(db, inv, l.amount)
            db.add(APAllocation(company_id=pay.company_id, invoice_id=inv.id, source_type="PAYMENT", payment_id=pay.id,
                                amount=l.amount, allocation_date=pay.payment_date, journal_id=je.id, created_by_id=actor.id))
    if pay.is_advance:
        pay.advance_unapplied = pay.gross_amount
    pay.journal_id = je.id
    pay.status = DocStatus.POSTED
    db.flush()


def payment_spec(db: Session, pay: APPayment) -> wf.WorkflowSpec:
    return wf.WorkflowSpec(doc_type="AP_PAYMENT", perm_prefix="ap_payment", amount=pay.gross_amount,
                           site_id=pay.site_id, poster=_post_payment)


def apply_advance(db: Session, actor: Actor, payment_id: int, invoice_id: int, amount: Decimal, on_date: date) -> APAllocation:
    actor.require("ap_payment.post")
    pay = db.scalar(select(APPayment).where(APPayment.id == payment_id).with_for_update())
    inv = db.scalar(select(APDocument).where(APDocument.id == invoice_id).with_for_update())
    amount = money(amount)
    if pay is None or not pay.is_advance or pay.status != DocStatus.POSTED:
        raise ValidationFailed("Select a posted advance payment")
    if inv is None or inv.supplier_id != pay.supplier_id or inv.status != DocStatus.POSTED or inv.doc_type != APDocType.INVOICE:
        raise ValidationFailed("Select a posted invoice of the same supplier")
    if amount <= 0 or amount > pay.advance_unapplied or amount > inv.outstanding:
        raise ValidationFailed("Amount exceeds the unapplied advance or the invoice outstanding")
    sup = db.get(Supplier, pay.supplier_id)
    je = engine.create_and_post(db, actor, company_id=pay.company_id, journal_type=JournalType.APA, transaction_date=on_date,
                                description=f"Advance {pay.number} applied to {inv.number}",
                                lines=[LineInput(account_id=control_account(db, sup), debit=amount, supplier_id=sup.id, reference=inv.supplier_invoice_no),
                                       LineInput(account_id=advance_account(db, sup), credit=amount, supplier_id=sup.id, reference=pay.number)],
                                source_module=SourceModule.AP, source_type="ap_advance_application", source_id=pay.id)
    pay.advance_unapplied = money(pay.advance_unapplied - amount)
    _apply(db, inv, amount)
    a = APAllocation(company_id=pay.company_id, invoice_id=inv.id, source_type="ADVANCE", payment_id=pay.id,
                     amount=amount, allocation_date=on_date, journal_id=je.id, created_by_id=actor.id)
    db.add(a)
    db.flush()
    return a


def reverse_payment(db: Session, actor: Actor, pay: APPayment, reversal_date: date, reason: str) -> APPayment:
    actor.require("ap_payment.reverse")
    if pay.status != DocStatus.POSTED:
        raise Conflict("Only posted payments can be reversed")
    if pay.is_advance and pay.advance_unapplied != pay.gross_amount:
        raise Conflict("Part of this advance has been applied; reverse the applications first")
    rev = engine.create_reversal(db, pay.journal_id, actor, reversal_date, reason, post=True)
    tax.reverse_for_journal(db, pay.journal_id, rev)
    for a in db.scalars(select(APAllocation).where(APAllocation.payment_id == pay.id, APAllocation.is_active.is_(True),
                                                   APAllocation.source_type == "PAYMENT")).all():
        inv = db.scalar(select(APDocument).where(APDocument.id == a.invoice_id).with_for_update())
        _apply(db, inv, -a.amount)
        a.is_active = False
    pay.advance_unapplied = ZERO
    pay.status = DocStatus.REVERSED
    record(db, actor, "ap_payment.reverse", "ap_payment", pay.id, None, {"reversal_journal": rev.number, "reason": reason})
    return pay


# ------------------------------------------------------------------ reports
BUCKETS = [("current", "Not yet due", None, 0), ("b1", "1-30", 1, 30), ("b2", "31-60", 31, 60),
           ("b3", "61-90", 61, 90), ("b4", "91-180", 91, 180), ("b5", "Over 180", 181, None)]


def _settled_as_of(db: Session, model_alloc, doc_ids: list[int], as_of: date, field: str) -> dict[int, Decimal]:
    if not doc_ids:
        return {}
    col = getattr(model_alloc, field)
    q = select(col, func.sum(model_alloc.amount)).where(col.in_(doc_ids), model_alloc.allocation_date <= as_of,
                                                         model_alloc.is_active.is_(True)).group_by(col)
    return {k: D(v) for k, v in db.execute(q).all()}


def open_items(db: Session, company_id: int, as_of: date, supplier_id: int | None = None) -> list[dict]:
    q = select(APDocument).where(APDocument.company_id == company_id, APDocument.posting_date <= as_of,
                                 or_(APDocument.status == DocStatus.POSTED,
                                     and_(APDocument.status == DocStatus.REVERSED,
                                          APDocument.journal_id.in_(select(JournalEntry.reversal_of_id).where(
                                              JournalEntry.posting_date > as_of, JournalEntry.reversal_of_id.is_not(None))))))
    if supplier_id:
        q = q.where(APDocument.supplier_id == supplier_id)
    docs = db.scalars(q).all()
    ids = [d.id for d in docs]
    by_inv = _settled_as_of(db, APAllocation, ids, as_of, "invoice_id")
    by_note = _settled_as_of(db, APAllocation, ids, as_of, "credit_document_id")
    out = []
    for d in docs:
        settled = by_inv.get(d.id, ZERO) + by_note.get(d.id, ZERO)
        open_amt = d.total - settled
        if open_amt == 0:
            continue
        sign = 1 if d.doc_type == APDocType.INVOICE else -1
        out.append({"document_id": d.id, "number": d.number, "doc_type": d.doc_type.value, "supplier_id": d.supplier_id,
                    "supplier_invoice_no": d.supplier_invoice_no, "invoice_date": d.invoice_date, "due_date": d.due_date,
                    "total": d.total, "open": open_amt * sign, "days_overdue": (as_of - d.due_date).days,
                    "site_id": d.site_id})
    # unapplied advances (debit balances)
    pq = select(APPayment).where(APPayment.company_id == company_id, APPayment.is_advance.is_(True),
                                 APPayment.status == DocStatus.POSTED, APPayment.payment_date <= as_of)
    if supplier_id:
        pq = pq.where(APPayment.supplier_id == supplier_id)
    for p in db.scalars(pq).all():
        applied = D(db.scalar(select(func.coalesce(func.sum(APAllocation.amount), 0)).where(
            APAllocation.payment_id == p.id, APAllocation.source_type == "ADVANCE", APAllocation.is_active.is_(True),
            APAllocation.allocation_date <= as_of)) or 0)
        if p.gross_amount - applied:
            out.append({"document_id": None, "payment_id": p.id, "number": p.number, "doc_type": "ADVANCE",
                        "supplier_id": p.supplier_id, "supplier_invoice_no": p.reference, "invoice_date": p.payment_date,
                        "due_date": p.payment_date, "total": p.gross_amount, "open": -(p.gross_amount - applied),
                        "days_overdue": 0, "site_id": p.site_id, "is_advance": True})
    return out


def aging(db: Session, company_id: int, as_of: date, supplier_id: int | None = None) -> dict:
    items = open_items(db, company_id, as_of, supplier_id)
    sups = {s.id: s for s in db.scalars(select(Supplier)).all()}
    per: dict[int, dict] = {}
    for it in items:
        row = per.setdefault(it["supplier_id"], {"supplier_id": it["supplier_id"], "code": sups[it["supplier_id"]].code,
                                                 "label": sups[it["supplier_id"]].name, "level": 1, "style": "line",
                                                 **{k: ZERO for k, *_ in BUCKETS}, "unapplied": ZERO, "total": ZERO})
        amt = it["open"]
        if it["doc_type"] in ("ADVANCE", "CREDIT_NOTE", "DEBIT_NOTE"):
            row["unapplied"] += amt
        else:
            days = it["days_overdue"]
            for key, _lbl, lo, hi in BUCKETS:
                if (lo is None and days <= 0) or (lo is not None and days >= lo and (hi is None or days <= hi)):
                    row[key] += amt
                    break
        row["total"] += amt
    rows_out = sorted(per.values(), key=lambda r: r["code"])
    for r in rows_out:
        r["drill"] = {"supplier_id": r["supplier_id"]}
    tot = {"label": "TOTAL", "level": 0, "style": "grand"}
    for k in [b[0] for b in BUCKETS] + ["unapplied", "total"]:
        tot[k] = money(sum((r[k] for r in rows_out), ZERO))
    rows_out.append(tot)
    cols = [{"key": "code", "label": "Code", "type": "text"}, {"key": "label", "label": "Supplier", "type": "text"}] + [
        {"key": k, "label": lbl, "type": "money"} for k, lbl, *_ in BUCKETS] + [
        {"key": "unapplied", "label": "Unapplied credits / advances", "type": "money"}, {"key": "total", "label": "Net payable", "type": "money"}]
    return {"title": "Accounts Payable Aging", "subtitle": f"As at {as_of.strftime('%d %b %Y')} (days past due date)",
            "columns": cols, "rows": rows_out, "meta": {"items": items}}


def reconciliation(db: Session, company_id: int, as_of: date) -> dict:
    """AP sub-ledger (open documents and advances) vs GL control and advance accounts."""
    items = open_items(db, company_id, as_of)
    cats = db.scalars(select(SupplierCategory)).all()
    ctrl_ids = sorted({c.ap_control_account_id for c in cats})
    adv_ids = sorted({c.advance_account_id for c in cats if c.advance_account_id})
    def gl(ids):
        return D(db.scalar(select(func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0)).where(
            JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.posting_date <= as_of,
            JournalLine.account_id.in_(ids))) or 0)
    sub_payable = money(sum((i["open"] for i in items if i["doc_type"] != "ADVANCE"), ZERO))
    sub_adv = money(-sum((i["open"] for i in items if i["doc_type"] == "ADVANCE"), ZERO))
    gl_payable = money(gl(ctrl_ids))
    gl_adv = money(-gl(adv_ids))
    non_module = db.execute(select(JournalLine.journal_id, JournalEntry.number, JournalLine.debit, JournalLine.credit)
                            .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
                            .where(JournalLine.company_id == company_id, JournalLine.is_posted.is_(True),
                                   JournalLine.posting_date <= as_of, JournalLine.account_id.in_(ctrl_ids + adv_ids),
                                   JournalLine.source_module.not_in(["AP", "OPENING"]))).all()
    rows_out = [
        {"label": "Trade payables (AP control accounts)", "c0": sub_payable, "c1": gl_payable, "c2": sub_payable - gl_payable, "style": "line", "level": 1},
        {"label": "Advances to suppliers", "c0": sub_adv, "c1": gl_adv, "c2": sub_adv - gl_adv, "style": "line", "level": 1},
    ]
    diff = money(sub_payable - gl_payable) == 0 and money(sub_adv - gl_adv) == 0
    return {"title": "AP Sub-ledger to GL Reconciliation", "subtitle": f"As at {as_of.strftime('%d %b %Y')}",
            "columns": [{"key": "label", "label": "", "type": "text"}, {"key": "c0", "label": "Sub-ledger", "type": "money"},
                        {"key": "c1", "label": "General ledger", "type": "money"}, {"key": "c2", "label": "Difference", "type": "money"}],
            "rows": rows_out, "meta": {"reconciled": diff, "non_module_lines": [
                {"journal_id": j, "number": n, "debit": d, "credit": c} for j, n, d, c in non_module]}}


def supplier_statement(db: Session, company_id: int, supplier_id: int, date_from: date, date_to: date) -> dict:
    sup = db.get(Supplier, supplier_id)
    if sup is None:
        raise NotFound("Supplier not found")
    cats = db.scalars(select(SupplierCategory)).all()
    acc_ids = list({c.ap_control_account_id for c in cats} | {c.advance_account_id for c in cats if c.advance_account_id})
    base = select(JournalLine, JournalEntry).join(JournalEntry, JournalEntry.id == JournalLine.journal_id).where(
        JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.supplier_id == supplier_id,
        JournalLine.account_id.in_(acc_ids))
    opening = D(db.scalar(select(func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0)).where(
        JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.supplier_id == supplier_id,
        JournalLine.account_id.in_(acc_ids), JournalLine.posting_date < date_from)) or 0)
    bal = opening
    rows_out = [{"label": "Opening balance", "style": "subtotal", "level": 0, "balance": money(opening)}]
    for l, j in db.execute(base.where(JournalLine.posting_date.between(date_from, date_to))
                           .order_by(JournalLine.posting_date, JournalLine.id)).all():
        bal += l.credit - l.debit
        rows_out.append({"label": l.posting_date.isoformat(), "number": j.number, "journal_id": j.id,
                         "description": l.description or j.description, "reference": l.reference, "debit": l.debit,
                         "credit": l.credit, "balance": money(bal), "level": 1, "style": "line"})
    rows_out.append({"label": "Closing balance (payable)", "style": "grand", "level": 0, "balance": money(bal)})
    return {"title": f"Supplier Statement - {sup.code} {sup.name}", "subtitle": f"{date_from} to {date_to}",
            "columns": [{"key": "label", "label": "Date", "type": "text"}, {"key": "number", "label": "Journal", "type": "text"},
                        {"key": "description", "label": "Description", "type": "text"}, {"key": "reference", "label": "Reference", "type": "text"},
                        {"key": "debit", "label": "Debit (paid)", "type": "money"}, {"key": "credit", "label": "Credit (billed)", "type": "money"},
                        {"key": "balance", "label": "Balance", "type": "money"}],
            "rows": rows_out, "meta": {"opening": money(opening), "closing": money(bal)}}
