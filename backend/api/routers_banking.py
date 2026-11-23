"""Cash and bank API: accounts, vouchers, transfers, cash position (reconciliation endpoints appended below)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from backend.api.crud import register_crud
from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import page, row, rows
from backend.banking import service as svc
from backend.banking.models import BankAccount, BankAccountKind, BankTransfer, CashBankVoucher
from backend.core.exceptions import NotFound
from backend.core.pagination import paginate
from backend.reporting.exports import respond
from backend.workflow import engine as wf
from backend.workflow.engine import history

router = APIRouter(prefix="/api/banking", tags=["cash and bank"])


class BankAccountIn(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str
    kind: BankAccountKind = BankAccountKind.BANK
    bank_name: str | None = None
    branch: str | None = None
    account_number: str | None = None
    iban: str | None = None
    currency: str = "PKR"
    gl_account_id: int
    site_id: int | None = None
    imprest_amount: Decimal | None = None
    is_default_payment: bool = False
    is_active: bool = True


class BankAccountUpdate(BaseModel):
    name: str | None = None
    bank_name: str | None = None
    branch: str | None = None
    account_number: str | None = None
    iban: str | None = None
    imprest_amount: Decimal | None = None
    is_default_payment: bool | None = None
    is_active: bool | None = None


def _ba_out(db, ba: BankAccount) -> dict:
    return row(ba, extra={"gl_balance": svc.gl_balance(db, ba, date.today())})


register_crud(router, "/accounts", BankAccount, BankAccountIn, BankAccountUpdate, view_perm="bank.view",
              manage_perm="bank.manage", company_scoped=True, filters=("kind", "site_id"),
              site_scoped_field="site_id", validate=svc.validate_bank_account, serializer=_ba_out)


class ActIn(BaseModel):
    comment: str | None = None


class ReverseIn(BaseModel):
    reversal_date: date
    reason: str = Field(min_length=3)


# ------------------------------------------------------------------ vouchers
class VLineIn(BaseModel):
    account_id: int
    site_id: int | None = None
    cost_centre_id: int | None = None
    supplier_id: int | None = None
    customer_id: int | None = None
    employee_id: int | None = None
    description: str | None = None
    amount: Decimal = Field(gt=0)
    tax_code_id: int | None = None
    tax_amount: Decimal | None = Field(default=None, ge=0)
    dimensions: dict[str, int | None] = {}


class VoucherIn(BaseModel):
    direction: str = Field(pattern="^(PAYMENT|RECEIPT)$")
    bank_account_id: int
    voucher_date: date
    counterparty: str | None = None
    cheque_no: str | None = None
    reference: str | None = None
    description: str | None = None
    lines: list[VLineIn] = Field(min_length=1)


def _v_out(db, v: CashBankVoucher) -> dict:
    return row(v, extra={"lines": rows(v.lines), "history": rows(history(db, "CASH_VOUCHER", v.id))})


def _visible_accounts(db, actor):
    if actor.site_ids is None:
        return None
    return [b.id for b in db.scalars(select(BankAccount).where(or_(BankAccount.site_id.is_(None),
                                                                   BankAccount.site_id.in_(actor.site_ids))))]


@router.get("/vouchers")
def list_vouchers(db: DB, actor: CurrentActor, company_id: CompanyId, voucher_type: str | None = None,
                  status: str | None = None, bank_account_id: int | None = None, date_from: date | None = None,
                  date_to: date | None = None, page_no: int = Query(1, alias="page"), page_size: int = 50):
    actor.require("cash_voucher.view")
    stmt = select(CashBankVoucher).where(CashBankVoucher.company_id == company_id)
    if voucher_type:
        stmt = stmt.where(CashBankVoucher.voucher_type == voucher_type)
    if status:
        stmt = stmt.where(CashBankVoucher.status.in_(status.split(",")))
    if bank_account_id:
        stmt = stmt.where(CashBankVoucher.bank_account_id == bank_account_id)
    if date_from:
        stmt = stmt.where(CashBankVoucher.voucher_date >= date_from)
    if date_to:
        stmt = stmt.where(CashBankVoucher.voucher_date <= date_to)
    vis = _visible_accounts(db, actor)
    if vis is not None:
        stmt = stmt.where(CashBankVoucher.bank_account_id.in_(vis))
    items, total = paginate(db, stmt.order_by(CashBankVoucher.voucher_date.desc(), CashBankVoucher.id.desc()), page_no, page_size)
    return page(rows(items), total, page_no, page_size)


@router.get("/vouchers/{vid}")
def get_voucher(vid: int, db: DB, actor: CurrentActor):
    actor.require("cash_voucher.view")
    v = db.get(CashBankVoucher, vid)
    if v is None:
        raise NotFound("Voucher not found")
    actor.require_site(db.get(BankAccount, v.bank_account_id).site_id)
    return _v_out(db, v)


@router.post("/vouchers", status_code=201)
def create_voucher(body: VoucherIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    v = svc.save_voucher(db, actor, company_id, body.model_dump())
    db.commit()
    return _v_out(db, v)


@router.put("/vouchers/{vid}")
def update_voucher(vid: int, body: VoucherIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    v = db.get(CashBankVoucher, vid)
    if v is None:
        raise NotFound("Voucher not found")
    v = svc.save_voucher(db, actor, company_id, body.model_dump(), v)
    db.commit()
    return _v_out(db, v)


@router.post("/vouchers/{vid}/reverse")
def reverse_voucher(vid: int, body: ReverseIn, db: DB, actor: CurrentActor):
    v = db.get(CashBankVoucher, vid)
    if v is None:
        raise NotFound("Voucher not found")
    svc.reverse_voucher(db, actor, v, body.reversal_date, body.reason)
    db.commit()
    return _v_out(db, v)


@router.post("/vouchers/{vid}/{action}")
def act_voucher(vid: int, action: str, body: ActIn, db: DB, actor: CurrentActor):
    v = db.get(CashBankVoucher, vid)
    if v is None:
        raise NotFound("Voucher not found")
    wf.transition(db, v, svc.voucher_spec(db, v), action, actor, body.comment)
    db.commit()
    return _v_out(db, v)


# ------------------------------------------------------------------ transfers
class TransferIn(BaseModel):
    from_account_id: int
    to_account_id: int
    transfer_date: date
    amount: Decimal = Field(gt=0)
    charges: Decimal = Field(default=Decimal("0"), ge=0)
    via_transit: bool = False
    reference: str | None = None
    description: str | None = None


def _t_out(db, t: BankTransfer) -> dict:
    return row(t, extra={"history": rows(history(db, "BANK_TRANSFER", t.id))})


@router.get("/transfers")
def list_transfers(db: DB, actor: CurrentActor, company_id: CompanyId, status: str | None = None,
                   page_no: int = Query(1, alias="page"), page_size: int = 50):
    actor.require("bank_transfer.view")
    stmt = select(BankTransfer).where(BankTransfer.company_id == company_id)
    if status:
        stmt = stmt.where(BankTransfer.status.in_(status.split(",")))
    vis = _visible_accounts(db, actor)
    if vis is not None:
        stmt = stmt.where(or_(BankTransfer.from_account_id.in_(vis), BankTransfer.to_account_id.in_(vis)))
    items, total = paginate(db, stmt.order_by(BankTransfer.transfer_date.desc(), BankTransfer.id.desc()), page_no, page_size)
    return page(rows(items), total, page_no, page_size)


@router.get("/transfers/{tid}")
def get_transfer(tid: int, db: DB, actor: CurrentActor):
    actor.require("bank_transfer.view")
    t = db.get(BankTransfer, tid)
    if t is None:
        raise NotFound("Transfer not found")
    return _t_out(db, t)


@router.post("/transfers", status_code=201)
def create_transfer(body: TransferIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    t = svc.save_transfer(db, actor, company_id, body.model_dump())
    db.commit()
    return _t_out(db, t)


class ReceiveIn(BaseModel):
    received_date: date


@router.post("/transfers/{tid}/receive")
def receive(tid: int, body: ReceiveIn, db: DB, actor: CurrentActor):
    t = db.get(BankTransfer, tid)
    if t is None:
        raise NotFound("Transfer not found")
    svc.receive_transfer(db, actor, t, body.received_date)
    db.commit()
    return _t_out(db, db.get(BankTransfer, tid))


@router.post("/transfers/{tid}/{action}")
def act_transfer(tid: int, action: str, body: ActIn, db: DB, actor: CurrentActor):
    t = db.get(BankTransfer, tid)
    if t is None:
        raise NotFound("Transfer not found")
    wf.transition(db, t, svc.transfer_spec(db, t), action, actor, body.comment)
    db.commit()
    return _t_out(db, t)


@router.get("/cash-position")
def cash_position(db: DB, actor: CurrentActor, company_id: CompanyId, on_date: date, format: str = "json"):
    actor.require("bank.view")
    return respond(svc.daily_cash_position(db, company_id, actor, on_date), format)
