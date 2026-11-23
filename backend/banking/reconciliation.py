"""Bank reconciliation: statement import, matching (auto / manual / partial), adjustments, reconciliation report.

Sign convention: a statement CREDIT (deposit) matches a GL DEBIT on the bank ledger, and vice versa.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.accounting import engine
from backend.accounting.engine import LineInput
from backend.accounting.models import JournalEntry, JournalLine, JournalType, SourceModule
from backend.audit.service import record
from backend.banking.models import BankAccount, BankMatch, BankReconciliation, BankStatement, BankStatementLine
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.money import ZERO, D, money
from backend.database.base import utcnow

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%m/%d/%Y", "%d.%m.%Y")


def _parse_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    raise ValidationFailed(f"Unrecognised date '{s}'")


def parse_statement_file(content: bytes, filename: str, mapping: dict | None = None) -> list[dict]:
    """CSV or XLSX. Default columns: date, description, reference, debit, credit, balance (or a signed 'amount')."""
    m = {"date": "date", "description": "description", "reference": "reference", "debit": "debit", "credit": "credit",
         "amount": "amount", "balance": "balance", "value_date": "value_date"}
    m.update({k: v for k, v in (mapping or {}).items() if v})
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header = [str(h or "").strip().lower() for h in next(it)]
        raw = [dict(zip(header, r)) for r in it if any(c not in (None, "") for c in r)]
    else:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        raw = [{(k or "").strip().lower(): v for k, v in r.items()} for r in reader]
    out = []
    for i, r in enumerate(raw, start=1):
        get = lambda key: r.get(m[key].lower()) if m.get(key) else None  # noqa: E731
        if not get("date"):
            continue
        debit, credit = D(get("debit") or 0), D(get("credit") or 0)
        if not debit and not credit and get("amount") not in (None, ""):
            amt = D(get("amount"))
            credit, debit = (amt, ZERO) if amt > 0 else (ZERO, -amt)
        if debit < 0 or credit < 0:
            raise ValidationFailed(f"Row {i}: negative debit / credit")
        out.append({"txn_date": _parse_date(get("date")),
                    "value_date": _parse_date(get("value_date")) if get("value_date") else None,
                    "description": (str(get("description") or "")).strip()[:500] or None,
                    "reference": (str(get("reference") or "")).strip()[:120] or None,
                    "debit": money(debit), "credit": money(credit),
                    "balance": money(get("balance")) if get("balance") not in (None, "") else None})
    if not out:
        raise ValidationFailed("No statement lines found")
    return out


def import_statement(db: Session, actor: Actor, bank_account_id: int, lines: list[dict], *, opening_balance: Decimal,
                     closing_balance: Decimal | None = None, filename: str | None = None) -> BankStatement:
    actor.require("bank.reconcile")
    ba = db.get(BankAccount, bank_account_id)
    if ba is None:
        raise NotFound("Bank account not found")
    actor.require_site(ba.site_id)
    computed = money(opening_balance + sum((l["credit"] - l["debit"] for l in lines), ZERO))
    if closing_balance is not None and money(closing_balance) != computed:
        raise ValidationFailed(f"Statement does not add up: opening {opening_balance:,.2f} + movements = {computed:,.2f}, "
                               f"closing shown {money(closing_balance):,.2f}")
    st = BankStatement(bank_account_id=ba.id, date_from=min(l["txn_date"] for l in lines),
                       date_to=max(l["txn_date"] for l in lines), opening_balance=money(opening_balance),
                       closing_balance=computed, filename=filename, created_by_id=actor.id)
    for n, l in enumerate(sorted(lines, key=lambda x: x["txn_date"]), start=1):
        st.lines.append(BankStatementLine(line_no=n, **l))
    db.add(st)
    db.flush()
    record(db, actor, "bank.statement_import", "bank_statement", st.id, None,
           {"bank_account": ba.code, "lines": len(lines), "closing": str(computed)})
    return st


def _gl_lines_query(ba: BankAccount):
    q = select(JournalLine).where(JournalLine.is_posted.is_(True), JournalLine.account_id == ba.gl_account_id)
    if ba.site_id:
        q = q.where(JournalLine.site_id == ba.site_id)
    return q


def _matched_gl(db: Session, line_ids: list[int]) -> dict[int, Decimal]:
    if not line_ids:
        return {}
    return {k: D(v) for k, v in db.execute(select(BankMatch.journal_line_id, func.sum(BankMatch.amount)).where(
        BankMatch.journal_line_id.in_(line_ids), BankMatch.is_active.is_(True)).group_by(BankMatch.journal_line_id)).all()}


def unreconciled_gl(db: Session, ba: BankAccount, as_of: date | None = None) -> list[dict]:
    q = _gl_lines_query(ba)
    if as_of:
        q = q.where(JournalLine.posting_date <= as_of)
    lines = db.scalars(q.order_by(JournalLine.posting_date, JournalLine.id)).all()
    matched = _matched_gl(db, [l.id for l in lines])
    out = []
    for l in lines:
        amt = l.debit or l.credit
        rem = amt - matched.get(l.id, ZERO)
        if rem > 0:
            je = db.get(JournalEntry, l.journal_id)
            out.append({"journal_line_id": l.id, "journal_id": l.journal_id, "number": je.number, "date": l.posting_date,
                        "description": l.description or je.description, "reference": l.reference or je.reference,
                        "debit": l.debit, "credit": l.credit, "remaining": rem,
                        "direction": "IN" if l.debit else "OUT"})
    return out


def _stmt_remaining(sl: BankStatementLine) -> Decimal:
    return (sl.debit or sl.credit) - sl.matched_amount


def _refresh_status(sl: BankStatementLine) -> None:
    rem = _stmt_remaining(sl)
    sl.status = "MATCHED" if rem == 0 else ("PARTIAL" if sl.matched_amount > 0 else "UNMATCHED")


def match(db: Session, actor: Actor, pairs: list[dict], match_type: str = "MANUAL") -> list[BankMatch]:
    """pairs: [{statement_line_id, journal_line_id, amount}] - supports one-to-many and partial matching."""
    actor.require("bank.reconcile")
    created = []
    for p in pairs:
        sl = db.scalar(select(BankStatementLine).where(BankStatementLine.id == p["statement_line_id"]).with_for_update())
        jl = db.get(JournalLine, p["journal_line_id"])
        if sl is None or jl is None or not jl.is_posted:
            raise ValidationFailed("Statement line or posted ledger line not found")
        st = db.get(BankStatement, sl.statement_id)
        ba = db.get(BankAccount, st.bank_account_id)
        if jl.account_id != ba.gl_account_id or (ba.site_id and jl.site_id != ba.site_id):
            raise ValidationFailed("Ledger line is not on this bank account")
        if (sl.credit > 0) != (jl.debit > 0):
            raise ValidationFailed("Direction mismatch: deposits match ledger debits, withdrawals match ledger credits")
        amount = money(p.get("amount") or min(_stmt_remaining(sl), (jl.debit or jl.credit) - _matched_gl(db, [jl.id]).get(jl.id, ZERO)))
        if amount <= 0 or amount > _stmt_remaining(sl):
            raise ValidationFailed("Amount exceeds what remains unmatched on the statement line")
        if amount > (jl.debit or jl.credit) - _matched_gl(db, [jl.id]).get(jl.id, ZERO):
            raise ValidationFailed("Amount exceeds what remains unmatched on the ledger line")
        m = BankMatch(statement_line_id=sl.id, journal_line_id=jl.id, amount=amount, match_type=match_type, matched_by_id=actor.id)
        db.add(m)
        sl.matched_amount = money(sl.matched_amount + amount)
        _refresh_status(sl)
        db.flush()
        created.append(m)
    if created:
        record(db, actor, "bank.match", "bank_statement", db.get(BankStatementLine, created[0].statement_line_id).statement_id,
               None, {"matches": len(created), "type": match_type})
    return created


def unmatch(db: Session, actor: Actor, match_id: int) -> None:
    actor.require("bank.reconcile")
    m = db.get(BankMatch, match_id)
    if m is None or not m.is_active:
        raise NotFound("Match not found")
    if m.reconciliation_id and db.get(BankReconciliation, m.reconciliation_id).status == "COMPLETED":
        raise Conflict("Match belongs to a completed reconciliation")
    sl = db.get(BankStatementLine, m.statement_line_id)
    m.is_active, m.unmatched_by_id, m.unmatched_at = False, actor.id, utcnow()
    sl.matched_amount = money(sl.matched_amount - m.amount)
    _refresh_status(sl)
    record(db, actor, "bank.unmatch", "bank_match", m.id, {"amount": str(m.amount)}, None)


def auto_match(db: Session, actor: Actor, statement_id: int, date_window: int = 5) -> int:
    """Exact amount + direction within a date window; reference match wins; only unambiguous pairs are matched."""
    actor.require("bank.reconcile")
    st = db.get(BankStatement, statement_id)
    if st is None:
        raise NotFound("Statement not found")
    ba = db.get(BankAccount, st.bank_account_id)
    open_gl = unreconciled_gl(db, ba)
    used: set[int] = set()
    n = 0
    for sl in st.lines:
        rem = _stmt_remaining(sl)
        if rem <= 0:
            continue
        direction = "IN" if sl.credit else "OUT"
        cands = [g for g in open_gl if g["journal_line_id"] not in used and g["direction"] == direction
                 and g["remaining"] == rem and abs((g["date"] - sl.txn_date).days) <= date_window]
        if sl.reference:
            ref = [g for g in cands if g["reference"] and (sl.reference.lower() in str(g["reference"]).lower()
                                                            or str(g["reference"]).lower() in sl.reference.lower())]
            if len(ref) == 1:
                cands = ref
        if len(cands) > 1:
            same_day = [g for g in cands if g["date"] == sl.txn_date]
            cands = same_day if len(same_day) == 1 else cands
        if len(cands) == 1:
            match(db, actor, [{"statement_line_id": sl.id, "journal_line_id": cands[0]["journal_line_id"], "amount": rem}], "AUTO")
            used.add(cands[0]["journal_line_id"])
            n += 1
    return n


def create_adjustment(db: Session, actor: Actor, statement_line_id: int, account_id: int, *, cost_centre_id: int | None = None,
                      site_id: int | None = None, description: str | None = None) -> JournalEntry:
    """Post bank charges / interest / direct debits / credits found on the statement and match them."""
    actor.require("bank.reconcile")
    sl = db.get(BankStatementLine, statement_line_id)
    if sl is None:
        raise NotFound("Statement line not found")
    rem = _stmt_remaining(sl)
    if rem <= 0:
        raise Conflict("Statement line is already matched")
    st = db.get(BankStatement, sl.statement_id)
    ba = db.get(BankAccount, st.bank_account_id)
    desc = description or sl.description or "Bank statement adjustment"
    if sl.credit:
        lines = [LineInput(account_id=ba.gl_account_id, debit=rem, site_id=ba.site_id, description=desc, reference=sl.reference),
                 LineInput(account_id=account_id, credit=rem, site_id=site_id, cost_centre_id=cost_centre_id, description=desc)]
    else:
        lines = [LineInput(account_id=account_id, debit=rem, site_id=site_id, cost_centre_id=cost_centre_id, description=desc),
                 LineInput(account_id=ba.gl_account_id, credit=rem, site_id=ba.site_id, description=desc, reference=sl.reference)]
    je = engine.create_and_post(db, actor, company_id=ba.company_id, journal_type=JournalType.BRA, transaction_date=sl.txn_date,
                                description=f"Bank reconciliation adjustment: {desc}", lines=lines, reference=sl.reference,
                                source_module=SourceModule.BANK, source_type="bank_statement_line", source_id=sl.id,
                                source_key=f"BRA-{sl.id}")
    bank_line = next(l for l in je.lines if l.account_id == ba.gl_account_id)
    match(db, actor, [{"statement_line_id": sl.id, "journal_line_id": bank_line.id, "amount": rem}], "MANUAL")
    return je


def reconciliation_report(db: Session, bank_account_id: int, as_of: date, statement_id: int | None = None) -> dict:
    ba = db.get(BankAccount, bank_account_id)
    if ba is None:
        raise NotFound("Bank account not found")
    st = db.get(BankStatement, statement_id) if statement_id else db.scalar(
        select(BankStatement).where(BankStatement.bank_account_id == ba.id, BankStatement.date_to <= as_of)
        .order_by(BankStatement.date_to.desc(), BankStatement.id.desc()))
    gl_bal = money(db.scalar(_gl_lines_query(ba).with_only_columns(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
                             .where(JournalLine.posting_date <= as_of)) or 0)
    open_gl = unreconciled_gl(db, ba, as_of)
    # Ledger lines matched only to statement lines dated after as_of are still outstanding at as_of
    outstanding_pay = money(sum((g["remaining"] for g in open_gl if g["direction"] == "OUT"), ZERO))
    in_transit = money(sum((g["remaining"] for g in open_gl if g["direction"] == "IN"), ZERO))
    stmt_bal = st.closing_balance if st else ZERO
    unmatched_stmt = [sl for sl in (st.lines if st else []) if _stmt_remaining(sl) > 0]
    um_dr = money(sum((_stmt_remaining(s) for s in unmatched_stmt if s.debit), ZERO))
    um_cr = money(sum((_stmt_remaining(s) for s in unmatched_stmt if s.credit), ZERO))
    adjusted_bank = money(stmt_bal + in_transit - outstanding_pay)
    adjusted_gl = money(gl_bal + um_cr - um_dr)
    difference = money(adjusted_bank - gl_bal - (um_cr - um_dr))
    return {"bank_account": {"id": ba.id, "code": ba.code, "name": ba.name}, "as_of": as_of,
            "statement_id": st.id if st else None, "statement_balance": stmt_bal, "gl_balance": gl_bal,
            "deposits_in_transit": in_transit, "outstanding_payments": outstanding_pay,
            "unmatched_statement_debits": um_dr, "unmatched_statement_credits": um_cr,
            "adjusted_bank_balance": adjusted_bank, "adjusted_gl_balance": adjusted_gl, "difference": difference,
            "outstanding_items": open_gl,
            "unmatched_statement_lines": [{"id": s.id, "date": s.txn_date, "description": s.description,
                                           "reference": s.reference, "debit": s.debit, "credit": s.credit,
                                           "remaining": _stmt_remaining(s)} for s in unmatched_stmt],
            "can_complete": difference == 0 and not unmatched_stmt}


def complete(db: Session, actor: Actor, bank_account_id: int, as_of: date, statement_id: int | None = None,
             notes: str | None = None) -> BankReconciliation:
    actor.require("bank.reconcile")
    rep = reconciliation_report(db, bank_account_id, as_of, statement_id)
    if not rep["can_complete"]:
        raise ValidationFailed("Reconciliation cannot be completed: resolve unmatched statement lines and differences first",
                               code="reconciliation_open", details={"difference": str(rep["difference"])})
    from backend.api.serialize import jsonable
    rec = BankReconciliation(bank_account_id=bank_account_id, statement_id=rep["statement_id"], as_of_date=as_of,
                             statement_balance=rep["statement_balance"], gl_balance=rep["gl_balance"],
                             outstanding_payments=rep["outstanding_payments"], deposits_in_transit=rep["deposits_in_transit"],
                             unmatched_statement_debits=rep["unmatched_statement_debits"],
                             unmatched_statement_credits=rep["unmatched_statement_credits"], difference=rep["difference"],
                             status="COMPLETED", completed_by_id=actor.id, completed_at=utcnow(), notes=notes,
                             detail=jsonable({"outstanding_items": rep["outstanding_items"]}), created_by_id=actor.id)
    db.add(rec)
    db.flush()
    if rep["statement_id"]:
        st = db.get(BankStatement, rep["statement_id"])
        st.status = "RECONCILED"
        for sl in st.lines:
            for m in db.scalars(select(BankMatch).where(BankMatch.statement_line_id == sl.id, BankMatch.is_active.is_(True))):
                m.reconciliation_id = rec.id
    record(db, actor, "bank.reconciliation_complete", "bank_reconciliation", rec.id, None,
           {"bank_account_id": bank_account_id, "as_of": as_of.isoformat(), "gl_balance": str(rep["gl_balance"])})
    return rec


def status_for_period(db: Session, company_id: int, period_end: date) -> list[dict]:
    """Month-end check: every active bank account has a completed reconciliation at or after the period end."""
    out = []
    for ba in db.scalars(select(BankAccount).where(BankAccount.company_id == company_id, BankAccount.is_active.is_(True),
                                                   BankAccount.kind == "BANK")).all():
        last = db.scalar(select(BankReconciliation).where(BankReconciliation.bank_account_id == ba.id,
                                                          BankReconciliation.status == "COMPLETED")
                         .order_by(BankReconciliation.as_of_date.desc()))
        has_activity = db.scalar(_gl_lines_query(ba).with_only_columns(func.count()).where(JournalLine.posting_date <= period_end))
        out.append({"bank_account_id": ba.id, "code": ba.code, "name": ba.name,
                    "last_reconciled": last.as_of_date if last else None,
                    "ok": (not has_activity) or (last is not None and last.as_of_date >= period_end)})
    return out
