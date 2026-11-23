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


# ------------------------------------------------------------------ bank reconciliation
from fastapi import File, Form, UploadFile  # noqa: E402

from backend.api.serialize import jsonable  # noqa: E402
from backend.banking import reconciliation as rec  # noqa: E402
from backend.banking.models import BankReconciliation, BankStatement  # noqa: E402


class StatementLineIn(BaseModel):
    txn_date: date
    value_date: date | None = None
    description: str | None = None
    reference: str | None = None
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)
    balance: Decimal | None = None


class StatementIn(BaseModel):
    bank_account_id: int
    opening_balance: Decimal
    closing_balance: Decimal | None = None
    lines: list[StatementLineIn] = Field(min_length=1)


@router.post("/statements", status_code=201)
def statement_create(body: StatementIn, db: DB, actor: CurrentActor):
    st = rec.import_statement(db, actor, body.bank_account_id, [l.model_dump() for l in body.lines],
                              opening_balance=body.opening_balance, closing_balance=body.closing_balance)
    db.commit()
    return row(st, extra={"lines": rows(st.lines)})


@router.post("/statements/import", status_code=201)
async def statement_import(db: DB, actor: CurrentActor, bank_account_id: int = Form(...), opening_balance: Decimal = Form(...),
                           closing_balance: Decimal | None = Form(None), column_map: str | None = Form(None),
                           file: UploadFile = File(...)):
    import json
    content = await file.read()
    lines = rec.parse_statement_file(content, file.filename or "statement.csv", json.loads(column_map) if column_map else None)
    st = rec.import_statement(db, actor, bank_account_id, lines, opening_balance=opening_balance,
                              closing_balance=closing_balance, filename=file.filename)
    db.commit()
    return row(st, extra={"lines": rows(st.lines)})


@router.get("/statements")
def statements(db: DB, actor: CurrentActor, bank_account_id: int):
    actor.require("bank.view")
    return rows(db.scalars(select(BankStatement).where(BankStatement.bank_account_id == bank_account_id)
                           .order_by(BankStatement.date_to.desc())).all())


@router.get("/statements/{statement_id}")
def statement_get(statement_id: int, db: DB, actor: CurrentActor):
    actor.require("bank.view")
    st = db.get(BankStatement, statement_id)
    if st is None:
        raise NotFound("Statement not found")
    from backend.banking.models import BankMatch
    out = []
    for sl in st.lines:
        ms = db.scalars(select(BankMatch).where(BankMatch.statement_line_id == sl.id, BankMatch.is_active.is_(True))).all()
        out.append(row(sl, extra={"matches": rows(ms)}))
    return row(st, extra={"lines": out})


@router.get("/accounts/{bank_account_id}/unreconciled")
def unreconciled(bank_account_id: int, db: DB, actor: CurrentActor, as_of: date | None = None):
    actor.require("bank.view")
    ba = db.get(BankAccount, bank_account_id)
    if ba is None:
        raise NotFound("Bank account not found")
    return jsonable(rec.unreconciled_gl(db, ba, as_of))


@router.post("/statements/{statement_id}/auto-match")
def auto_match(statement_id: int, db: DB, actor: CurrentActor, date_window: int = 5):
    n = rec.auto_match(db, actor, statement_id, date_window)
    db.commit()
    return {"matched": n}


class MatchPair(BaseModel):
    statement_line_id: int
    journal_line_id: int
    amount: Decimal | None = Field(default=None, gt=0)


@router.post("/matches")
def match(body: list[MatchPair], db: DB, actor: CurrentActor):
    ms = rec.match(db, actor, [p.model_dump() for p in body])
    db.commit()
    return rows(ms)


@router.delete("/matches/{match_id}")
def unmatch(match_id: int, db: DB, actor: CurrentActor):
    rec.unmatch(db, actor, match_id)
    db.commit()
    return {"ok": True}


class AdjustIn(BaseModel):
    statement_line_id: int
    account_id: int
    cost_centre_id: int | None = None
    site_id: int | None = None
    description: str | None = None


@router.post("/adjustments", status_code=201)
def adjustment(body: AdjustIn, db: DB, actor: CurrentActor):
    je = rec.create_adjustment(db, actor, body.statement_line_id, body.account_id, cost_centre_id=body.cost_centre_id,
                               site_id=body.site_id, description=body.description)
    db.commit()
    return {"journal_id": je.id, "number": je.number}


@router.get("/reconciliation")
def reconciliation(db: DB, actor: CurrentActor, bank_account_id: int, as_of: date, statement_id: int | None = None):
    actor.require("bank.view")
    return jsonable(rec.reconciliation_report(db, bank_account_id, as_of, statement_id))


class CompleteIn(BaseModel):
    bank_account_id: int
    as_of: date
    statement_id: int | None = None
    notes: str | None = None


@router.post("/reconciliation/complete", status_code=201)
def reconciliation_complete(body: CompleteIn, db: DB, actor: CurrentActor):
    r = rec.complete(db, actor, body.bank_account_id, body.as_of, body.statement_id, body.notes)
    db.commit()
    return row(r)


@router.get("/reconciliations")
def reconciliation_history(db: DB, actor: CurrentActor, bank_account_id: int | None = None):
    actor.require("bank.view")
    stmt = select(BankReconciliation).order_by(BankReconciliation.as_of_date.desc(), BankReconciliation.id.desc())
    if bank_account_id:
        stmt = stmt.where(BankReconciliation.bank_account_id == bank_account_id)
    return rows(db.scalars(stmt).all())
