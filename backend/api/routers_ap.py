"""Accounts payable API."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from backend.accounting.models import DocStatus
from backend.ap import service as svc
from backend.ap.models import APAllocation, APDocType, APDocument, APPayment, Supplier, SupplierCategory, SupplierType
from backend.api.crud import register_crud
from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import line_rows, page, row, rows
from backend.core.exceptions import NotFound
from backend.core.pagination import paginate
from backend.reporting.exports import respond
from backend.workflow.engine import history, history_rows  # noqa: F401

router = APIRouter(prefix="/api/ap", tags=["accounts payable"])


class SupplierIn(BaseModel):
    code: str | None = None
    name: str = Field(min_length=2, max_length=200)
    beneficiary_name: str | None = None
    category_id: int
    supplier_type: SupplierType = SupplierType.COMPANY
    ntn: str | None = None
    strn: str | None = None
    cnic: str | None = None
    atl_status: str = Field(default="ATL", pattern="^(ATL|NON_ATL)$")
    st_registered: bool = True
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None
    contact_person: str | None = None
    bank_name: str | None = None
    bank_account_title: str | None = None
    bank_account_no: str | None = None
    iban: str | None = None
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    wht_tax_code_id: int | None = None
    st_tax_code_id: int | None = None
    stw_tax_code_id: int | None = None
    wht_exemption_rate: Decimal | None = None
    wht_exemption_until: date | None = None
    payment_hold: bool = False
    is_active: bool = True
    notes: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = None
    beneficiary_name: str | None = None
    category_id: int | None = None
    supplier_type: SupplierType | None = None
    ntn: str | None = None
    strn: str | None = None
    cnic: str | None = None
    atl_status: str | None = Field(default=None, pattern="^(ATL|NON_ATL)$")
    st_registered: bool | None = None
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None
    contact_person: str | None = None
    bank_name: str | None = None
    bank_account_title: str | None = None
    bank_account_no: str | None = None
    iban: str | None = None
    payment_terms_days: int | None = None
    wht_tax_code_id: int | None = None
    st_tax_code_id: int | None = None
    stw_tax_code_id: int | None = None
    wht_exemption_rate: Decimal | None = None
    wht_exemption_until: date | None = None
    payment_hold: bool | None = None
    is_active: bool | None = None
    notes: str | None = None


register_crud(router, "/suppliers", Supplier, SupplierIn, SupplierUpdate, view_perm="supplier.view",
              manage_perm="supplier.manage", search_fields=("code", "name", "ntn"), filters=("category_id",),
              validate=svc.validate_supplier)


@router.get("/supplier-categories")
def categories(db: DB, actor: CurrentActor):
    actor.require("supplier.view")
    return rows(db.scalars(select(SupplierCategory).order_by(SupplierCategory.code)).all())


# ------------------------------------------------------------------ documents
class DocLineIn(BaseModel):
    account_id: int
    site_id: int | None = None
    cost_centre_id: int | None = None
    description: str | None = None
    quantity: Decimal = Decimal("1")
    unit_price: Decimal | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    st_tax_code_id: int | None = None
    st_amount: Decimal | None = Field(default=None, ge=0)
    dimensions: dict[str, int | None] = {}
    asset_id: int | None = None


class DocIn(BaseModel):
    doc_type: APDocType = APDocType.INVOICE
    supplier_id: int
    supplier_invoice_no: str = Field(min_length=1, max_length=60)
    invoice_date: date
    posting_date: date | None = None
    due_date: date | None = None
    site_id: int | None = None
    description: str | None = None
    related_document_id: int | None = None
    lines: list[DocLineIn] = Field(min_length=1)


class ActIn(BaseModel):
    comment: str | None = None


class ReverseIn(BaseModel):
    reversal_date: date
    reason: str = Field(min_length=3)


def _doc_out(db, d: APDocument) -> dict:
    sup = db.get(Supplier, d.supplier_id)
    allocs = db.scalars(select(APAllocation).where(or_(APAllocation.invoice_id == d.id, APAllocation.credit_document_id == d.id))).all()
    return row(d, extra={"supplier": {"id": sup.id, "code": sup.code, "name": sup.name}, "outstanding": d.outstanding,
                         "lines": line_rows(db, d.lines), "allocations": rows(allocs),
                         "history": history_rows(db, "AP_INVOICE", d.id)})


def _site_ok(actor, site_id):
    return actor.site_ids is None or site_id is None or site_id in actor.site_ids


@router.get("/documents")
def list_docs(db: DB, actor: CurrentActor, company_id: CompanyId, supplier_id: int | None = None, status: str | None = None,
              doc_type: str | None = None, payment_status: str | None = None, date_from: date | None = None,
              date_to: date | None = None, due_before: date | None = None, q: str | None = None,
              page_no: int = Query(1, alias="page"), page_size: int = 50):
    actor.require("ap_invoice.view")
    stmt = select(APDocument).where(APDocument.company_id == company_id)
    for col, val in ((APDocument.supplier_id, supplier_id), (APDocument.doc_type, doc_type)):
        if val:
            stmt = stmt.where(col == val)
    if status:
        stmt = stmt.where(APDocument.status.in_(status.split(",")))
    if payment_status:
        stmt = stmt.where(APDocument.payment_status.in_(payment_status.split(",")))
    if date_from:
        stmt = stmt.where(APDocument.invoice_date >= date_from)
    if date_to:
        stmt = stmt.where(APDocument.invoice_date <= date_to)
    if due_before:
        stmt = stmt.where(APDocument.due_date <= due_before)
    if q:
        stmt = stmt.where(or_(APDocument.number.ilike(f"%{q}%"), APDocument.supplier_invoice_no.ilike(f"%{q}%"),
                              APDocument.description.ilike(f"%{q}%")))
    if actor.site_ids is not None:
        stmt = stmt.where(or_(APDocument.site_id.is_(None), APDocument.site_id.in_(actor.site_ids)))
    items, total = paginate(db, stmt.order_by(APDocument.invoice_date.desc(), APDocument.id.desc()), page_no, page_size)
    sups = {s.id: s for s in db.scalars(select(Supplier).where(Supplier.id.in_({i.supplier_id for i in items} or {0})))}
    return page([row(i, extra={"supplier_name": sups[i.supplier_id].name, "outstanding": i.outstanding}) for i in items],
                total, page_no, page_size)


@router.get("/documents/{doc_id}")
def get_doc(doc_id: int, db: DB, actor: CurrentActor):
    actor.require("ap_invoice.view")
    d = db.get(APDocument, doc_id)
    if d is None or not _site_ok(actor, d.site_id):
        raise NotFound("Document not found")
    return _doc_out(db, d)


def _payload(body: DocIn) -> dict:
    """Lines keep only the fields sent, so an omitted tax code falls back to the supplier default
    while an explicit null means 'no sales tax'."""
    data = body.model_dump(exclude={"lines"})
    data["lines"] = [l.model_dump(exclude_unset=True) for l in body.lines]
    return data


@router.post("/documents", status_code=201)
def create_doc(body: DocIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    d, warnings = svc.save_document(db, actor, company_id, _payload(body))
    db.commit()
    return {**_doc_out(db, d), "warnings": warnings}


@router.put("/documents/{doc_id}")
def update_doc(doc_id: int, body: DocIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    d = db.get(APDocument, doc_id)
    if d is None:
        raise NotFound("Document not found")
    d, warnings = svc.save_document(db, actor, company_id, _payload(body), d)
    db.commit()
    return {**_doc_out(db, d), "warnings": warnings}


@router.post("/documents/{doc_id}/reverse")
def reverse_doc(doc_id: int, body: ReverseIn, db: DB, actor: CurrentActor):
    d = db.get(APDocument, doc_id)
    if d is None:
        raise NotFound("Document not found")
    svc.reverse_document(db, actor, d, body.reversal_date, body.reason)
    db.commit()
    return _doc_out(db, d)


@router.post("/documents/{doc_id}/{action}")
def act_doc(doc_id: int, action: str, body: ActIn, db: DB, actor: CurrentActor):
    d = db.get(APDocument, doc_id)
    if d is None:
        raise NotFound("Document not found")
    warnings = svc.act_document(db, actor, d, action, body.comment)
    db.commit()
    return {**_doc_out(db, d), "warnings": warnings}


class AllocIn(BaseModel):
    credit_document_id: int
    invoice_id: int
    amount: Decimal = Field(gt=0)


@router.post("/allocations")
def allocate(body: AllocIn, db: DB, actor: CurrentActor):
    a = svc.allocate_credit(db, actor, body.credit_document_id, body.invoice_id, body.amount)
    db.commit()
    return row(a)


# ------------------------------------------------------------------ payments
class PayLineIn(BaseModel):
    document_id: int | None = None
    amount: Decimal = Field(gt=0)
    override_rate: Decimal | None = Field(default=None, ge=0, le=1)
    override_reason: str | None = None


class PaymentIn(BaseModel):
    supplier_id: int
    bank_account_id: int | None = None
    payment_date: date
    payment_method: str = "TRANSFER"
    cheque_no: str | None = None
    reference: str | None = None
    description: str | None = None
    is_advance: bool = False
    site_id: int | None = None
    lines: list[PayLineIn] = Field(min_length=1)


def _pay_out(db, p: APPayment) -> dict:
    sup = db.get(Supplier, p.supplier_id)
    lines = []
    for l in p.lines:
        inv = db.get(APDocument, l.document_id) if l.document_id else None
        lines.append(row(l, extra={"invoice_number": inv.number if inv else None,
                                   "supplier_invoice_no": inv.supplier_invoice_no if inv else None}))
    return row(p, extra={"supplier": {"id": sup.id, "code": sup.code, "name": sup.name,
                                      "beneficiary_name": sup.beneficiary_name}, "lines": lines,
                         "history": history_rows(db, "AP_PAYMENT", p.id)})


@router.get("/payments")
def list_payments(db: DB, actor: CurrentActor, company_id: CompanyId, supplier_id: int | None = None,
                  status: str | None = None, date_from: date | None = None, date_to: date | None = None,
                  page_no: int = Query(1, alias="page"), page_size: int = 50):
    actor.require("ap_payment.view")
    stmt = select(APPayment).where(APPayment.company_id == company_id)
    if supplier_id:
        stmt = stmt.where(APPayment.supplier_id == supplier_id)
    if status:
        stmt = stmt.where(APPayment.status.in_(status.split(",")))
    if date_from:
        stmt = stmt.where(APPayment.payment_date >= date_from)
    if date_to:
        stmt = stmt.where(APPayment.payment_date <= date_to)
    items, total = paginate(db, stmt.order_by(APPayment.payment_date.desc(), APPayment.id.desc()), page_no, page_size)
    sups = {s.id: s.name for s in db.scalars(select(Supplier).where(Supplier.id.in_({i.supplier_id for i in items} or {0})))}
    return page([row(i, extra={"supplier_name": sups[i.supplier_id]}) for i in items], total, page_no, page_size)


@router.get("/payments/{pay_id}")
def get_payment(pay_id: int, db: DB, actor: CurrentActor):
    actor.require("ap_payment.view")
    p = db.get(APPayment, pay_id)
    if p is None:
        raise NotFound("Payment not found")
    return _pay_out(db, p)


@router.post("/payments/preview")
def preview_payment(body: PaymentIn, db: DB, actor: CurrentActor):
    """Calculate WHT / STW without saving (payment screen)."""
    actor.require("ap_payment.view")
    sup = db.get(Supplier, body.supplier_id)
    if sup is None:
        raise NotFound("Supplier not found")
    out = []
    for l in body.lines:
        inv = db.get(APDocument, l.document_id) if l.document_id else None
        out.append(svc.compute_payment_line(db, sup, body.payment_date, l.amount, inv, l.override_rate, l.override_reason))
    from backend.api.serialize import jsonable
    return jsonable({"lines": out, "gross": sum(x["amount"] for x in out),
                     "wht": sum(x["wht_amount"] for x in out), "stw": sum(x["stw_amount"] for x in out),
                     "net": sum(x["amount"] - x["wht_amount"] - x["stw_amount"] for x in out)})


@router.post("/payments", status_code=201)
def create_payment(body: PaymentIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    p = svc.save_payment(db, actor, company_id, body.model_dump())
    db.commit()
    return _pay_out(db, p)


@router.put("/payments/{pay_id}")
def update_payment(pay_id: int, body: PaymentIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    p = db.get(APPayment, pay_id)
    if p is None:
        raise NotFound("Payment not found")
    p = svc.save_payment(db, actor, company_id, body.model_dump(), p)
    db.commit()
    return _pay_out(db, p)


@router.post("/payments/{pay_id}/reverse")
def reverse_payment(pay_id: int, body: ReverseIn, db: DB, actor: CurrentActor):
    p = db.get(APPayment, pay_id)
    if p is None:
        raise NotFound("Payment not found")
    svc.reverse_payment(db, actor, p, body.reversal_date, body.reason)
    db.commit()
    return _pay_out(db, p)


class ApplyAdvIn(BaseModel):
    invoice_id: int
    amount: Decimal = Field(gt=0)
    date: date


@router.post("/payments/{pay_id}/apply-advance")
def apply_adv(pay_id: int, body: ApplyAdvIn, db: DB, actor: CurrentActor):
    a = svc.apply_advance(db, actor, pay_id, body.invoice_id, body.amount, body.date)
    db.commit()
    return row(a)


@router.post("/payments/{pay_id}/{action}")
def act_payment(pay_id: int, action: str, body: ActIn, db: DB, actor: CurrentActor):
    p = db.get(APPayment, pay_id)
    if p is None:
        raise NotFound("Payment not found")
    from backend.workflow import engine as wf
    wf.transition(db, p, svc.payment_spec(db, p), action, actor, body.comment)
    db.commit()
    return _pay_out(db, p)


# ------------------------------------------------------------------ reports
@router.get("/open-items")
def open_items(db: DB, actor: CurrentActor, company_id: CompanyId, as_of: date, supplier_id: int | None = None):
    actor.require("ap_invoice.view")
    from backend.api.serialize import jsonable
    return jsonable(svc.open_items(db, company_id, as_of, supplier_id))


@router.get("/aging")
def aging(db: DB, actor: CurrentActor, company_id: CompanyId, as_of: date, supplier_id: int | None = None,
          format: str = "json"):
    actor.require("ap_invoice.view")
    return respond(svc.aging(db, company_id, as_of, supplier_id), format)


@router.get("/reconciliation")
def reconciliation(db: DB, actor: CurrentActor, company_id: CompanyId, as_of: date, format: str = "json"):
    actor.require("report.view")
    return respond(svc.reconciliation(db, company_id, as_of), format)


@router.get("/suppliers/{supplier_id}/statement")
def statement(supplier_id: int, db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
              format: str = "json"):
    actor.require("supplier.view")
    return respond(svc.supplier_statement(db, company_id, supplier_id, date_from, date_to), format)
