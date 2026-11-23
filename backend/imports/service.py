"""Data imports: chart of accounts, suppliers, customers, journals and opening balances (GL / AP / AR).

Opening balance method: every migrated balance posts against 03-01-03-0001 Opening balance clearing.
After GL, supplier, customer and fixed-asset openings are loaded the clearing account must be nil
(checked by ``opening_status`` and by the month-end checklist).  Control accounts (AP / AR) and the
fixed-asset register accounts can only be opened through their sub-ledgers so that sub-ledgers agree to the GL.
"""
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
from backend.ap.models import APDocType, APDocument, APDocumentLine, Supplier, SupplierCategory
from backend.ar.models import ARDocType, ARDocument, ARDocumentLine, Customer, CustomerCategory
from backend.audit.service import record
from backend.core.actor import Actor
from backend.core.exceptions import ValidationFailed
from backend.core.money import ZERO, D, money
from backend.imports.parsers import as_date
from backend.masters.models import CostCentre, Site

OB_CLEARING = "03-01-03-0001"
REGISTER_PREFIXES = ("01-01-01", "01-01-02", "01-01-03", "01-01-04")


def _maps(db: Session, company_id: int):
    accts = {a.code: a for a in db.scalars(select(Account))}
    sites = {s.code: s for s in db.scalars(select(Site).where(Site.company_id == company_id))}
    ccs = {c.code: c for c in db.scalars(select(CostCentre).where(CostCentre.company_id == company_id))}
    return accts, sites, ccs


def import_gl_opening(db: Session, actor: Actor, company_id: int, rows: list[dict], cutover: date):
    """rows: account_code, site_code, cost_centre_code, debit, credit, description."""
    actor.require("opening.manage")
    accts, sites, ccs = _maps(db, company_id)
    errors, lines = [], []
    for i, r in enumerate(rows, start=1):
        a = accts.get(str(r.get("account_code", "")).strip())
        if a is None or not a.is_postable:
            errors.append(f"Row {i}: unknown or non-posting account {r.get('account_code')}")
            continue
        if a.control_type in (ControlType.AP_CONTROL, ControlType.AR_CONTROL):
            errors.append(f"Row {i}: {a.code} is a supplier / customer control account - load it through the AP / AR opening import")
            continue
        if a.code.startswith(REGISTER_PREFIXES):
            errors.append(f"Row {i}: {a.code} is a fixed-asset register account - load it through the fixed asset opening")
            continue
        if a.code == OB_CLEARING:
            errors.append(f"Row {i}: do not load the clearing account directly")
            continue
        site = sites.get(str(r.get("site_code") or "").strip()) if r.get("site_code") else None
        cc = ccs.get(str(r.get("cost_centre_code") or "").strip()) if r.get("cost_centre_code") else None
        dr, cr = money(r.get("debit") or 0), money(r.get("credit") or 0)
        lines.append(LineInput(account_id=a.id, debit=dr, credit=cr, site_id=site.id if site else None,
                               cost_centre_id=cc.id if cc else None, description=r.get("description") or "Opening balance"))
    if errors:
        raise ValidationFailed("Opening balance import rejected", code="import_failed", details=errors)
    tdr = sum((l.debit for l in lines), ZERO)
    tcr = sum((l.credit for l in lines), ZERO)
    diff = money(tdr - tcr)
    if diff:
        # the difference is what the sub-ledger openings (AP / AR / fixed assets) will bring
        clearing = accts[OB_CLEARING]
        lines.append(LineInput(account_id=clearing.id, debit=-diff if diff < 0 else ZERO, credit=diff if diff > 0 else ZERO,
                               description="Balance carried to opening clearing (sub-ledger openings)"))
    je = engine.create_and_post(db, actor, company_id=company_id, journal_type=JournalType.OBV, transaction_date=cutover,
                                description=f"Opening balances at cut-over {cutover.isoformat()}", lines=lines,
                                source_module=SourceModule.OPENING, source_type="opening_gl")
    record(db, actor, "opening.gl", "journal", je.id, None, {"lines": len(lines), "clearing": str(diff)})
    return je, diff


def import_supplier_opening(db: Session, actor: Actor, company_id: int, rows: list[dict], cutover: date) -> list[APDocument]:
    """rows: supplier_code, invoice_no, invoice_date, due_date, amount, doc_type (INVOICE | CREDIT_NOTE)."""
    actor.require("opening.manage")
    clearing = db.scalar(select(Account).where(Account.code == OB_CLEARING))
    sups = {s.code: s for s in db.scalars(select(Supplier))}
    docs, errors = [], []
    for i, r in enumerate(rows, start=1):
        sup = sups.get(str(r.get("supplier_code", "")).strip())
        amount = money(r.get("amount") or 0)
        dtype = APDocType(str(r.get("doc_type") or "INVOICE").upper())
        if sup is None or amount <= 0:
            errors.append(f"Row {i}: unknown supplier or non-positive amount")
            continue
        inv_date = as_date(r.get("invoice_date") or cutover)
        doc = APDocument(company_id=company_id, doc_type=dtype, number=next_number(db, company_id, "AP-OB", "POB-", 6),
                         supplier_id=sup.id, supplier_invoice_no=str(r.get("invoice_no") or f"OB-{i}"), invoice_date=inv_date,
                         posting_date=cutover, due_date=as_date(r.get("due_date") or inv_date), description=f"Opening balance {r.get('invoice_no') or ''}".strip(),
                         subtotal=amount, total=amount, is_opening=True, created_by_id=actor.id, status=DocStatus.DRAFT)
        doc.lines = [APDocumentLine(line_no=1, account_id=clearing.id, amount=amount, unit_price=amount, description="Opening balance")]
        db.add(doc)
        docs.append(doc)
    if errors:
        raise ValidationFailed("Supplier opening import rejected", code="import_failed", details=errors)
    db.flush()
    from backend.ap.service import _post_document
    for doc in docs:
        doc.status = DocStatus.APPROVED
        _post_document(db, doc, actor)
    record(db, actor, "opening.suppliers", "ap_document", None, None, {"documents": len(docs)})
    return docs


def import_customer_opening(db: Session, actor: Actor, company_id: int, rows: list[dict], cutover: date) -> list[ARDocument]:
    actor.require("opening.manage")
    clearing = db.scalar(select(Account).where(Account.code == OB_CLEARING))
    cus = {c.code: c for c in db.scalars(select(Customer))}
    docs, errors = [], []
    for i, r in enumerate(rows, start=1):
        c = cus.get(str(r.get("customer_code", "")).strip())
        amount = money(r.get("amount") or 0)
        dtype = ARDocType(str(r.get("doc_type") or "INVOICE").upper())
        if c is None or amount <= 0:
            errors.append(f"Row {i}: unknown customer or non-positive amount")
            continue
        inv_date = as_date(r.get("invoice_date") or cutover)
        doc = ARDocument(company_id=company_id, doc_type=dtype, number=next_number(db, company_id, "AR-OB", "SOB-", 6),
                         customer_id=c.id, customer_reference=str(r.get("invoice_no") or ""), invoice_date=inv_date,
                         posting_date=cutover, due_date=as_date(r.get("due_date") or inv_date),
                         description=f"Opening balance {r.get('invoice_no') or ''}".strip(), subtotal=amount, total=amount,
                         is_opening=True, created_by_id=actor.id, status=DocStatus.DRAFT)
        doc.lines = [ARDocumentLine(line_no=1, account_id=clearing.id, amount=amount, unit_price=amount, description="Opening balance")]
        db.add(doc)
        docs.append(doc)
    if errors:
        raise ValidationFailed("Customer opening import rejected", code="import_failed", details=errors)
    db.flush()
    from backend.ar.service import _post_document
    for doc in docs:
        doc.status = DocStatus.APPROVED
        _post_document(db, doc, actor)
    record(db, actor, "opening.customers", "ar_document", None, None, {"documents": len(docs)})
    return docs


def opening_status(db: Session, company_id: int, cutover: date) -> dict:
    """Validates opening balances against the accounting equation and the clearing account."""
    def bal(prefix):
        return money(db.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).join(
            Account, Account.id == JournalLine.account_id).where(
            JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.posting_date <= cutover,
            Account.code.like(f"{prefix}%"))) or 0)
    assets, liabilities, equity = bal("01"), -bal("02"), -bal("03")
    pl = -sum((bal(c) for c in ("04", "05", "06", "07", "08")), ZERO)
    clearing = bal(OB_CLEARING)
    return {"assets": assets, "liabilities": liabilities, "equity_incl_clearing": equity, "unclosed_pl": pl,
            "clearing_balance": clearing, "equation_holds": money(assets - liabilities - equity - pl) == 0,
            "clearing_is_nil": clearing == 0, "complete": clearing == 0 and money(assets - liabilities - equity - pl) == 0}


# ------------------------------------------------------------------ masters
def import_suppliers(db: Session, actor: Actor, rows: list[dict]) -> int:
    from backend.ap.service import validate_supplier
    actor.require("supplier.manage")
    cats = {c.code: c for c in db.scalars(select(SupplierCategory))}
    n, errors = 0, []
    for i, r in enumerate(rows, start=1):
        cat = cats.get(str(r.get("category_code", "")).strip().upper())
        if cat is None or not r.get("name"):
            errors.append(f"Row {i}: name and a valid category_code are required")
            continue
        data = {k: (str(v).strip() if v is not None else None) for k, v in r.items() if k in (
            "code", "name", "ntn", "strn", "cnic", "address", "city", "phone", "email", "contact_person", "bank_name",
            "bank_account_title", "bank_account_no", "iban", "beneficiary_name")}
        data = {k: v for k, v in data.items() if v}
        data["category_id"] = cat.id
        data["supplier_type"] = str(r.get("supplier_type") or "COMPANY").upper()
        data["atl_status"] = str(r.get("atl_status") or "ATL").upper()
        data["payment_terms_days"] = int(r.get("payment_terms_days") or 30)
        s = Supplier()
        try:
            validate_supplier(db, actor, s, data)
        except Exception as exc:  # noqa: BLE001 - collect all row errors
            errors.append(f"Row {i}: {getattr(exc, 'message', exc)}")
            continue
        for k, v in data.items():
            setattr(s, k, v)
        s.created_by_id = actor.id
        db.add(s)
        db.flush()
        n += 1
    if errors:
        raise ValidationFailed("Supplier import rejected", code="import_failed", details=errors)
    record(db, actor, "import.suppliers", "supplier", None, None, {"rows": n})
    return n


def import_customers(db: Session, actor: Actor, rows: list[dict]) -> int:
    from backend.ar.service import validate_customer
    actor.require("customer.manage")
    cats = {c.code: c for c in db.scalars(select(CustomerCategory))}
    n, errors = 0, []
    for i, r in enumerate(rows, start=1):
        cat = cats.get(str(r.get("category_code", "")).strip().upper())
        if cat is None or not r.get("name"):
            errors.append(f"Row {i}: name and a valid category_code are required")
            continue
        data = {k: str(v).strip() for k, v in r.items() if v and k in ("code", "name", "ntn", "strn", "cnic", "address", "city",
                                                                        "phone", "email", "contact_person")}
        data["category_id"] = cat.id
        data["payment_terms_days"] = int(r.get("payment_terms_days") or 30)
        c = Customer()
        try:
            validate_customer(db, actor, c, data)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Row {i}: {getattr(exc, 'message', exc)}")
            continue
        for k, v in data.items():
            setattr(c, k, v)
        c.created_by_id = actor.id
        db.add(c)
        db.flush()
        n += 1
    if errors:
        raise ValidationFailed("Customer import rejected", code="import_failed", details=errors)
    record(db, actor, "import.customers", "customer", None, None, {"rows": n})
    return n


def import_accounts(db: Session, actor: Actor, rows: list[dict]) -> int:
    """rows: parent_code, name (+ optional attributes). Codes are assigned as the next free number."""
    actor.require("coa.manage")
    from backend.api.routers_masters import AccountIn, account_create  # reuse the same validation
    n = 0
    for r in rows:
        body = AccountIn(**{k: v for k, v in r.items() if v not in (None, "") and k in AccountIn.model_fields})
        account_create(body, db, actor)
        n += 1
    return n


def import_journals(db: Session, actor: Actor, company_id: int, rows: list[dict]) -> list[int]:
    """rows grouped by journal_ref: date, description, account_code, site_code, cost_centre_code, debit, credit,
    supplier_code, customer_code. Creates DRAFT manual journals that then follow the approval workflow."""
    from backend.accounting import service as jsvc
    accts, sites, ccs = _maps(db, company_id)
    sups = {s.code: s.id for s in db.scalars(select(Supplier))}
    cus = {c.code: c.id for c in db.scalars(select(Customer))}
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[str(r.get("journal_ref") or "1")].append(r)
    created = []
    for ref, rs in groups.items():
        first = rs[0]
        lines = []
        for r in rs:
            a = accts.get(str(r.get("account_code", "")).strip())
            if a is None:
                raise ValidationFailed(f"Journal {ref}: unknown account {r.get('account_code')}")
            lines.append(LineInput(account_id=a.id, debit=D(r.get("debit") or 0), credit=D(r.get("credit") or 0),
                                   site_id=sites[r["site_code"]].id if r.get("site_code") in sites else None,
                                   cost_centre_id=ccs[r["cost_centre_code"]].id if r.get("cost_centre_code") in ccs else None,
                                   supplier_id=sups.get(r.get("supplier_code")), customer_id=cus.get(r.get("customer_code")),
                                   description=r.get("line_description")))
        je, _w = jsvc.create_manual(db, actor, company_id, transaction_date=as_date(first["date"]),
                                    description=first.get("description") or f"Imported journal {ref}", lines=lines, reference=ref)
        created.append(je.id)
    return created


TEMPLATES = {
    "gl-opening": ["account_code", "site_code", "cost_centre_code", "debit", "credit", "description"],
    "supplier-opening": ["supplier_code", "invoice_no", "invoice_date", "due_date", "amount", "doc_type"],
    "customer-opening": ["customer_code", "invoice_no", "invoice_date", "due_date", "amount", "doc_type"],
    "suppliers": ["code", "name", "category_code", "supplier_type", "atl_status", "ntn", "strn", "cnic", "address", "city",
                  "phone", "email", "contact_person", "bank_name", "bank_account_title", "bank_account_no", "iban",
                  "beneficiary_name", "payment_terms_days"],
    "customers": ["code", "name", "category_code", "ntn", "strn", "cnic", "address", "city", "phone", "email",
                  "contact_person", "payment_terms_days"],
    "accounts": ["parent_code", "name", "site_rule", "cost_centre_rule", "manual_journal", "description"],
    "journals": ["journal_ref", "date", "description", "account_code", "site_code", "cost_centre_code", "supplier_code",
                 "customer_code", "debit", "credit", "line_description"],
    "box-office": ["site_code", "business_date", "screen_code", "film_code", "show_date", "show_time", "revenue_type_code",
                   "payment_method_code", "tickets_sold", "complimentary_tickets", "complimentary_value", "refund_tickets",
                   "gross_amount", "discount_amount", "refund_amount", "source_ref"],
    "fnb": ["site_code", "business_date", "revenue_type_code", "payment_method_code", "quantity", "gross_amount",
            "discount_amount", "refund_amount", "source_ref"],
    "bank-statement": ["date", "value_date", "description", "reference", "debit", "credit", "balance"],
}
