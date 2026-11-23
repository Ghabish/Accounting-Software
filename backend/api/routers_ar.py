"""Accounts receivable API."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from backend.api.crud import register_crud
from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import jsonable, page, row, rows
from backend.ar import service as svc
from backend.ar.models import ARAllocation, ARDocType, ARDocument, ARReceipt, Customer, CustomerCategory
from backend.core.exceptions import NotFound
from backend.core.pagination import paginate
from backend.reporting.exports import respond
from backend.workflow import engine as wf
from backend.workflow.engine import history

router = APIRouter(prefix="/api/ar", tags=["accounts receivable"])


class CustomerIn(BaseModel):
    code: str | None = None
    name: str = Field(min_length=2, max_length=200)
    category_id: int
    customer_type: str = "COMPANY"
    ntn: str | None = None
    strn: str | None = None
    cnic: str | None = None
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None
    contact_person: str | None = None
    credit_limit: Decimal | None = Field(default=None, ge=0)
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    wht_tax_code_id: int | None = None
    is_active: bool = True
    notes: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    category_id: int | None = None
    customer_type: str | None = None
    ntn: str | None = None
    strn: str | None = None
    cnic: str | None = None
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None
    contact_person: str | None = None
    credit_limit: Decimal | None = None
    payment_terms_days: int | None = None
    wht_tax_code_id: int | None = None
    is_active: bool | None = None
    notes: str | None = None


register_crud(router, "/customers", Customer, CustomerIn, CustomerUpdate, view_perm="customer.view",
              manage_perm="customer.manage", search_fields=("code", "name", "ntn"), filters=("category_id",),
              validate=svc.validate_customer)


@router.get("/customer-categories")
def categories(db: DB, actor: CurrentActor):
    actor.require("customer.view")
    return rows(db.scalars(select(CustomerCategory).order_by(CustomerCategory.code)).all())


class DocLineIn(BaseModel):
    account_id: int | None = None
    site_id: int | None = None
    cost_centre_id: int | None = None
    description: str | None = None
    quantity: Decimal = Decimal("1")
    unit_price: Decimal | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    tax_code_id: int | None = None
    dimensions: dict[str, int | None] = {}


class DocIn(BaseModel):
    doc_type: ARDocType = ARDocType.INVOICE
    customer_id: int
    customer_reference: str | None = None
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


def _doc_out(db, d: ARDocument) -> dict:
    cus = db.get(Customer, d.customer_id)
    allocs = db.scalars(select(ARAllocation).where(or_(ARAllocation.invoice_id == d.id, ARAllocation.credit_document_id == d.id))).all()
    return row(d, extra={"customer": {"id": cus.id, "code": cus.code, "name": cus.name}, "outstanding": d.outstanding,
                         "lines": [row(l) for l in d.lines], "allocations": rows(allocs),
                         "history": rows(history(db, "AR_INVOICE", d.id))})


def _payload(body: DocIn) -> dict:
    """Omitted tax code -> customer category default; explicit null -> no output tax."""
    data = body.model_dump(exclude={"lines"})
    data["lines"] = [l.model_dump(exclude_unset=True) for l in body.lines]
    return data


@router.get("/documents")
def list_docs(db: DB, actor: CurrentActor, company_id: CompanyId, customer_id: int | None = None, status: str | None = None,
              doc_type: str | None = None, payment_status: str | None = None, date_from: date | None = None,
              date_to: date | None = None, q: str | None = None, page_no: int = Query(1, alias="page"), page_size: int = 50):
    actor.require("ar_invoice.view")
    stmt = select(ARDocument).where(ARDocument.company_id == company_id)
    if customer_id:
        stmt = stmt.where(ARDocument.customer_id == customer_id)
    if doc_type:
        stmt = stmt.where(ARDocument.doc_type == doc_type)
    if status:
        stmt = stmt.where(ARDocument.status.in_(status.split(",")))
    if payment_status:
        stmt = stmt.where(ARDocument.payment_status.in_(payment_status.split(",")))
    if date_from:
        stmt = stmt.where(ARDocument.invoice_date >= date_from)
    if date_to:
        stmt = stmt.where(ARDocument.invoice_date <= date_to)
    if q:
        stmt = stmt.where(or_(ARDocument.number.ilike(f"%{q}%"), ARDocument.description.ilike(f"%{q}%"),
                              ARDocument.customer_reference.ilike(f"%{q}%")))
    if actor.site_ids is not None:
        stmt = stmt.where(or_(ARDocument.site_id.is_(None), ARDocument.site_id.in_(actor.site_ids)))
    items, total = paginate(db, stmt.order_by(ARDocument.invoice_date.desc(), ARDocument.id.desc()), page_no, page_size)
    cus = {c.id: c.name for c in db.scalars(select(Customer).where(Customer.id.in_({i.customer_id for i in items} or {0})))}
    return page([row(i, extra={"customer_name": cus[i.customer_id], "outstanding": i.outstanding}) for i in items],
                total, page_no, page_size)


@router.get("/documents/{doc_id}")
def get_doc(doc_id: int, db: DB, actor: CurrentActor):
    actor.require("ar_invoice.view")
    d = db.get(ARDocument, doc_id)
    if d is None:
        raise NotFound("Document not found")
    return _doc_out(db, d)


@router.post("/documents", status_code=201)
def create_doc(body: DocIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    d = svc.save_document(db, actor, company_id, _payload(body))
    db.commit()
    return _doc_out(db, d)


@router.put("/documents/{doc_id}")
def update_doc(doc_id: int, body: DocIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    d = db.get(ARDocument, doc_id)
    if d is None:
        raise NotFound("Document not found")
    d = svc.save_document(db, actor, company_id, _payload(body), d)
    db.commit()
    return _doc_out(db, d)


@router.post("/documents/{doc_id}/reverse")
def reverse_doc(doc_id: int, body: ReverseIn, db: DB, actor: CurrentActor):
    d = db.get(ARDocument, doc_id)
    if d is None:
        raise NotFound("Document not found")
    svc.reverse_document(db, actor, d, body.reversal_date, body.reason)
    db.commit()
    return _doc_out(db, d)


@router.post("/documents/{doc_id}/{action}")
def act_doc(doc_id: int, action: str, body: ActIn, db: DB, actor: CurrentActor):
    d = db.get(ARDocument, doc_id)
    if d is None:
        raise NotFound("Document not found")
    wf.transition(db, d, svc.doc_spec(db, d), action, actor, body.comment)
    db.commit()
    return _doc_out(db, d)


class AllocIn(BaseModel):
    credit_document_id: int
    invoice_id: int
    amount: Decimal = Field(gt=0)


@router.post("/allocations")
def allocate(body: AllocIn, db: DB, actor: CurrentActor):
    a = svc.allocate_credit(db, actor, body.credit_document_id, body.invoice_id, body.amount)
    db.commit()
    return row(a)


class RecLineIn(BaseModel):
    document_id: int
    amount: Decimal = Field(gt=0)


class ReceiptIn(BaseModel):
    customer_id: int
    bank_account_id: int
    receipt_date: date
    receipt_method: str = "TRANSFER"
    reference: str | None = None
    description: str | None = None
    amount_received: Decimal = Field(ge=0)
    tax_deducted: Decimal = Field(default=Decimal("0"), ge=0)
    wht_tax_code_id: int | None = None
    is_advance: bool = False
    site_id: int | None = None
    lines: list[RecLineIn] = []


def _rec_out(db, r: ARReceipt) -> dict:
    cus = db.get(Customer, r.customer_id)
    return row(r, extra={"customer": {"id": cus.id, "code": cus.code, "name": cus.name},
                         "lines": [row(l, extra={"invoice_number": db.get(ARDocument, l.document_id).number}) for l in r.lines],
                         "history": rows(history(db, "AR_RECEIPT", r.id))})


@router.get("/receipts")
def list_receipts(db: DB, actor: CurrentActor, company_id: CompanyId, customer_id: int | None = None,
                  status: str | None = None, date_from: date | None = None, date_to: date | None = None,
                  page_no: int = Query(1, alias="page"), page_size: int = 50):
    actor.require("ar_receipt.view")
    stmt = select(ARReceipt).where(ARReceipt.company_id == company_id)
    if customer_id:
        stmt = stmt.where(ARReceipt.customer_id == customer_id)
    if status:
        stmt = stmt.where(ARReceipt.status.in_(status.split(",")))
    if date_from:
        stmt = stmt.where(ARReceipt.receipt_date >= date_from)
    if date_to:
        stmt = stmt.where(ARReceipt.receipt_date <= date_to)
    items, total = paginate(db, stmt.order_by(ARReceipt.receipt_date.desc(), ARReceipt.id.desc()), page_no, page_size)
    cus = {c.id: c.name for c in db.scalars(select(Customer).where(Customer.id.in_({i.customer_id for i in items} or {0})))}
    return page([row(i, extra={"customer_name": cus[i.customer_id]}) for i in items], total, page_no, page_size)


@router.get("/receipts/{rec_id}")
def get_receipt(rec_id: int, db: DB, actor: CurrentActor):
    actor.require("ar_receipt.view")
    r = db.get(ARReceipt, rec_id)
    if r is None:
        raise NotFound("Receipt not found")
    return _rec_out(db, r)


@router.post("/receipts", status_code=201)
def create_receipt(body: ReceiptIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    r = svc.save_receipt(db, actor, company_id, body.model_dump())
    db.commit()
    return _rec_out(db, r)


@router.put("/receipts/{rec_id}")
def update_receipt(rec_id: int, body: ReceiptIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    r = db.get(ARReceipt, rec_id)
    if r is None:
        raise NotFound("Receipt not found")
    r = svc.save_receipt(db, actor, company_id, body.model_dump(), r)
    db.commit()
    return _rec_out(db, r)


@router.post("/receipts/{rec_id}/reverse")
def reverse_receipt(rec_id: int, body: ReverseIn, db: DB, actor: CurrentActor):
    r = db.get(ARReceipt, rec_id)
    if r is None:
        raise NotFound("Receipt not found")
    svc.reverse_receipt(db, actor, r, body.reversal_date, body.reason)
    db.commit()
    return _rec_out(db, r)


class ApplyAdvIn(BaseModel):
    invoice_id: int
    amount: Decimal = Field(gt=0)
    date: date


@router.post("/receipts/{rec_id}/apply-advance")
def apply_adv(rec_id: int, body: ApplyAdvIn, db: DB, actor: CurrentActor):
    a = svc.apply_advance(db, actor, rec_id, body.invoice_id, body.amount, body.date)
    db.commit()
    return row(a)


@router.post("/receipts/{rec_id}/{action}")
def act_receipt(rec_id: int, action: str, body: ActIn, db: DB, actor: CurrentActor):
    r = db.get(ARReceipt, rec_id)
    if r is None:
        raise NotFound("Receipt not found")
    wf.transition(db, r, svc.receipt_spec(db, r), action, actor, body.comment)
    db.commit()
    return _rec_out(db, r)


@router.get("/open-items")
def open_items(db: DB, actor: CurrentActor, company_id: CompanyId, as_of: date, customer_id: int | None = None):
    actor.require("ar_invoice.view")
    return jsonable(svc.open_items(db, company_id, as_of, customer_id))


@router.get("/aging")
def aging(db: DB, actor: CurrentActor, company_id: CompanyId, as_of: date, customer_id: int | None = None,
          format: str = "json"):
    actor.require("ar_invoice.view")
    return respond(svc.aging(db, company_id, as_of, customer_id), format)


@router.get("/reconciliation")
def reconciliation(db: DB, actor: CurrentActor, company_id: CompanyId, as_of: date, format: str = "json"):
    actor.require("report.view")
    return respond(svc.reconciliation(db, company_id, as_of), format)


@router.get("/customers/{customer_id}/statement")
def statement(customer_id: int, db: DB, actor: CurrentActor, company_id: CompanyId, date_from: date, date_to: date,
              format: str = "json"):
    actor.require("customer.view")
    return respond(svc.customer_statement(db, company_id, customer_id, date_from, date_to), format)
