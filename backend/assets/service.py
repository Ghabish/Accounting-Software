"""Fixed assets: register, capitalisation, depreciation runs, transfer, disposal, impairment, reports.

Depreciation policy (documented in 03_ACCOUNTING_WORKFLOWS.md):
  * a full month's charge from the month of the depreciation start date (default: capitalisation date);
  * straight-line: (NBV at start of month - residual) / remaining months, so impairments are spread
    over the remaining life automatically;
  * reducing balance: NBV x annual rate / 12;
  * catch-up for months missed; never below residual value.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.accounting import engine
from backend.accounting.engine import LineInput
from backend.accounting.models import Account, AccountingPeriod, JournalLine, JournalType, SourceModule
from backend.accounting.numbering import next_number
from backend.ap.models import APDocument, APDocumentLine
from backend.assets.models import (
    AssetCategory, AssetStatus, AssetTransaction, DepreciationLine, DepreciationMethod, DepreciationRun, FixedAsset,
)
from backend.audit.service import record
from backend.banking.models import BankAccount
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.money import ZERO, money
from backend.masters.models import CostCentre

D = Decimal
OB_CLEARING = "03-01-03-0001"


def _months_between(start: date, end: date) -> int:
    """Number of month boundaries from start-month to end-month inclusive of start month."""
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def create_asset(db: Session, actor: Actor, company_id: int, data: dict) -> FixedAsset:
    actor.require("asset.manage")
    cat = db.get(AssetCategory, data["category_id"])
    if cat is None:
        raise ValidationFailed("Asset category not found")
    actor.require_site(data["site_id"])
    a = FixedAsset(company_id=company_id, code=data.get("code") or next_number(db, company_id, "FA", "FA-", 6),
                   name=data["name"], description=data.get("description"), category_id=cat.id, site_id=data["site_id"],
                   cost_centre_id=data["cost_centre_id"], supplier_id=data.get("supplier_id"),
                   purchase_date=data["purchase_date"], capitalisation_date=data.get("capitalisation_date") or data["purchase_date"],
                   cost=money(data["cost"]), residual_value=money(data.get("residual_value") or 0),
                   useful_life_months=data.get("useful_life_months") or cat.default_useful_life_months,
                   method=data.get("method") or cat.default_method, reducing_rate=data.get("reducing_rate"),
                   serial_no=data.get("serial_no"), tag_no=data.get("tag_no"), status=AssetStatus.DRAFT,
                   created_by_id=actor.id)
    a.depreciation_start_date = data.get("depreciation_start_date") or a.capitalisation_date
    if a.cost <= 0:
        raise ValidationFailed("Asset cost must be positive")
    if a.residual_value > a.cost:
        raise ValidationFailed("Residual value cannot exceed cost")
    if a.method == DepreciationMethod.REDUCING_BALANCE and not a.reducing_rate:
        raise ValidationFailed("Reducing balance needs an annual rate")
    db.add(a)
    db.flush()
    record(db, actor, "asset.create", "fixed_asset", a.id, None, {"code": a.code, "cost": str(a.cost)})
    return a


def capitalise(db: Session, actor: Actor, asset: FixedAsset, *, source: str, ap_document_line_id: int | None = None,
               offset_account_id: int | None = None, opening_accumulated: Decimal | None = None) -> FixedAsset:
    """source = AP_INVOICE (cost already posted by the supplier invoice), JOURNAL (Dr cost / Cr offset e.g. CWIP),
    or OPENING (migrated asset: Dr cost / Cr accumulated depreciation / Cr opening balance clearing)."""
    actor.require("asset.manage")
    if asset.status != AssetStatus.DRAFT:
        raise Conflict("Asset is already capitalised")
    cat = db.get(AssetCategory, asset.category_id)
    if source == "AP_INVOICE":
        line = db.get(APDocumentLine, ap_document_line_id or 0)
        if line is None:
            raise ValidationFailed("Invoice line not found")
        doc = db.get(APDocument, line.document_id)
        if doc.status.value != "POSTED":
            raise ValidationFailed("The supplier invoice must be posted")
        if line.account_id != cat.cost_account_id:
            raise ValidationFailed("The invoice line was not charged to this category's cost account")
        if line.asset_id and line.asset_id != asset.id:
            raise Conflict("This invoice line is already linked to another asset")
        if money(line.amount) != asset.cost:
            raise ValidationFailed(f"Asset cost {asset.cost:,.2f} differs from the invoice line {line.amount:,.2f}")
        line.asset_id = asset.id
        asset.ap_document_id, asset.supplier_id = doc.id, doc.supplier_id
        asset.acquisition_journal_id = doc.journal_id
        txn_amount = asset.cost
    elif source in ("JOURNAL", "OPENING"):
        if source == "OPENING":
            actor.require("opening.manage")
            offset_account_id = db.scalar(select(Account.id).where(Account.code == OB_CLEARING))
        if not offset_account_id:
            raise ValidationFailed("Offset account (e.g. CWIP) is required")
        lines = [LineInput(account_id=cat.cost_account_id, debit=asset.cost, site_id=asset.site_id, description=f"{asset.code} {asset.name}")]
        acc_open = money(opening_accumulated or 0)
        if acc_open:
            if not cat.accum_dep_account_id:
                raise ValidationFailed("Category is not depreciable")
            lines.append(LineInput(account_id=cat.accum_dep_account_id, credit=acc_open, site_id=asset.site_id,
                                   description=f"{asset.code} opening accumulated depreciation"))
        off_acc = db.get(Account, offset_account_id)
        lines.append(LineInput(account_id=offset_account_id, credit=asset.cost - acc_open,
                               site_id=asset.site_id if off_acc.site_rule.value != "NONE" else None,
                               supplier_id=asset.supplier_id if off_acc.party_type.value == "SUPPLIER" else None,
                               description=f"Capitalisation {asset.code}"))
        je = engine.create_and_post(db, actor, company_id=asset.company_id, journal_type=JournalType.OBV if source == "OPENING" else JournalType.FAT,
                                    transaction_date=asset.capitalisation_date, description=f"Capitalisation of {asset.code} {asset.name}",
                                    lines=lines, source_module=SourceModule.OPENING if source == "OPENING" else SourceModule.ASSETS,
                                    source_type="fixed_asset", source_id=asset.id, source_key=f"FA-CAP-{asset.id}")
        asset.acquisition_journal_id = je.id
        asset.accumulated_depreciation = acc_open
        asset.is_opening = source == "OPENING"
        txn_amount = asset.cost
    else:
        raise ValidationFailed("source must be AP_INVOICE, JOURNAL or OPENING")
    asset.status = AssetStatus.ACTIVE
    db.add(AssetTransaction(asset_id=asset.id, txn_type="OPENING" if source == "OPENING" else "CAPITALISATION",
                            txn_date=asset.capitalisation_date, to_site_id=asset.site_id, to_cost_centre_id=asset.cost_centre_id,
                            amount=txn_amount, journal_id=asset.acquisition_journal_id, created_by_id=actor.id, notes=source))
    db.flush()
    record(db, actor, "asset.capitalise", "fixed_asset", asset.id, None, {"source": source})
    return asset


def monthly_charge(asset: FixedAsset, month_start: date, accumulated: Decimal | None = None) -> Decimal:
    acc = asset.accumulated_depreciation if accumulated is None else accumulated
    nbv = asset.cost - acc - (asset.impairment_total or ZERO)
    depreciable = nbv - asset.residual_value
    if depreciable <= 0:
        return ZERO
    if asset.method == DepreciationMethod.REDUCING_BALANCE:
        return min(money(nbv * D(asset.reducing_rate) / 12), depreciable)
    elapsed = _months_between(asset.depreciation_start_date, month_start) - 1
    remaining = asset.useful_life_months - elapsed
    if remaining <= 1:
        return money(depreciable)
    return min(money(depreciable / remaining), depreciable)


def compute_run(db: Session, actor: Actor, company_id: int, period_id: int) -> DepreciationRun:
    actor.require("asset.depreciate")
    period = db.get(AccountingPeriod, period_id)
    if period is None or period.company_id != company_id:
        raise NotFound("Period not found")
    existing = db.scalar(select(DepreciationRun).where(DepreciationRun.company_id == company_id,
                                                       DepreciationRun.period_id == period_id,
                                                       DepreciationRun.status.in_(["DRAFT", "POSTED"])))
    if existing and existing.status == "POSTED":
        raise Conflict(f"Depreciation for {period.name} is already posted")
    if existing:
        db.delete(existing)
        db.flush()
    run = DepreciationRun(company_id=company_id, period_id=period_id, run_date=period.end_date, status="DRAFT",
                          created_by_id=actor.id)
    db.add(run)
    total = ZERO
    assets = db.scalars(select(FixedAsset).where(FixedAsset.company_id == company_id, FixedAsset.status == AssetStatus.ACTIVE,
                                                 FixedAsset.depreciation_start_date <= period.end_date)).all()
    for a in assets:
        cat = db.get(AssetCategory, a.category_id)
        if not cat.is_depreciable:
            continue
        start = a.last_depreciation_date
        first_month = date(a.depreciation_start_date.year, a.depreciation_start_date.month, 1)
        month = first_month if start is None else date(start.year + (start.month // 12), start.month % 12 + 1, 1)
        if month > period.start_date:
            continue  # already depreciated for this period
        amount = ZERO
        sim_acc = a.accumulated_depreciation
        while month <= period.start_date:
            charge = monthly_charge(a, month, sim_acc)
            sim_acc += charge
            amount += charge
            month = date(month.year + (month.month // 12), month.month % 12 + 1, 1)
        nbv_before = a.net_book_value
        if amount <= 0:
            continue
        run.lines.append(DepreciationLine(asset_id=a.id, amount=money(amount), site_id=a.site_id, cost_centre_id=a.cost_centre_id,
                                          nbv_before=money(nbv_before), nbv_after=money(nbv_before - amount)))
        total += amount
    run.total = money(total)
    db.flush()
    return run


def post_run(db: Session, actor: Actor, run_id: int) -> DepreciationRun:
    actor.require("asset.depreciate")
    run = db.scalar(select(DepreciationRun).where(DepreciationRun.id == run_id).with_for_update())
    if run is None or run.status != "DRAFT":
        raise Conflict("Only draft runs can be posted")
    if not run.lines:
        raise ValidationFailed("Nothing to depreciate")
    if run.created_by_id == actor.id and not actor.has("period.close"):
        raise Conflict("Segregation of duties: another user must post the depreciation run")
    period = db.get(AccountingPeriod, run.period_id)
    grouped: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
    credit: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
    for l in run.lines:
        a = db.get(FixedAsset, l.asset_id)
        cat = db.get(AssetCategory, a.category_id)
        grouped[(cat.dep_expense_account_id, l.site_id, l.cost_centre_id)] += l.amount
        credit[(cat.accum_dep_account_id, l.site_id)] += l.amount
    lines = [LineInput(account_id=k[0], debit=v, site_id=k[1], cost_centre_id=k[2], description=f"Depreciation {period.name}")
             for k, v in grouped.items()]
    lines += [LineInput(account_id=k[0], credit=v, site_id=k[1], description=f"Accumulated depreciation {period.name}")
              for k, v in credit.items()]
    je = engine.create_and_post(db, actor, company_id=run.company_id, journal_type=JournalType.DEP, transaction_date=period.end_date,
                                description=f"Depreciation run {period.name}", lines=lines, source_module=SourceModule.ASSETS,
                                source_type="depreciation_run", source_id=run.id, source_key=f"DEP-{run.company_id}-{period.id}-{run.id}")
    for l in run.lines:
        a = db.get(FixedAsset, l.asset_id)
        a.accumulated_depreciation = money(a.accumulated_depreciation + l.amount)
        a.last_depreciation_date = period.end_date
        if a.net_book_value <= a.residual_value:
            a.status = AssetStatus.FULLY_DEPRECIATED
    run.journal_id = je.id
    run.status = "POSTED"
    db.flush()
    record(db, actor, "asset.depreciation_post", "depreciation_run", run.id, None, {"period": period.name, "total": str(run.total)})
    return run


def reverse_run(db: Session, actor: Actor, run_id: int, reason: str) -> DepreciationRun:
    actor.require("asset.depreciate")
    run = db.scalar(select(DepreciationRun).where(DepreciationRun.id == run_id).with_for_update())
    if run is None or run.status != "POSTED":
        raise Conflict("Only posted runs can be reversed")
    later = db.scalar(select(func.count()).select_from(DepreciationRun).join(AccountingPeriod, AccountingPeriod.id == DepreciationRun.period_id)
                      .where(DepreciationRun.company_id == run.company_id, DepreciationRun.status == "POSTED",
                             AccountingPeriod.start_date > db.get(AccountingPeriod, run.period_id).start_date))
    if later:
        raise Conflict("Reverse later depreciation runs first")
    period = db.get(AccountingPeriod, run.period_id)
    engine.create_reversal(db, run.journal_id, actor, period.end_date, reason, post=True)
    for l in run.lines:
        a = db.get(FixedAsset, l.asset_id)
        a.accumulated_depreciation = money(a.accumulated_depreciation - l.amount)
        a.status = AssetStatus.ACTIVE
        prev = db.scalar(select(AccountingPeriod).where(AccountingPeriod.company_id == run.company_id,
                                                        AccountingPeriod.end_date < period.start_date)
                         .order_by(AccountingPeriod.end_date.desc()))
        a.last_depreciation_date = prev.end_date if prev and prev.end_date >= a.depreciation_start_date else None
    run.status = "REVERSED"
    db.flush()
    return run


def transfer(db: Session, actor: Actor, asset: FixedAsset, on_date: date, to_site_id: int, to_cost_centre_id: int,
             notes: str | None = None) -> AssetTransaction:
    actor.require("asset.dispose")
    if asset.status not in (AssetStatus.ACTIVE, AssetStatus.FULLY_DEPRECIATED):
        raise Conflict("Only active assets can be transferred")
    actor.require_site(asset.site_id)
    cat = db.get(AssetCategory, asset.category_id)
    je_id = None
    if to_site_id != asset.site_id:
        lines = [LineInput(account_id=cat.cost_account_id, debit=asset.cost, site_id=to_site_id, description=f"Transfer in {asset.code}"),
                 LineInput(account_id=cat.cost_account_id, credit=asset.cost, site_id=asset.site_id, description=f"Transfer out {asset.code}")]
        acc_total = asset.accumulated_depreciation + asset.impairment_total
        if acc_total and cat.accum_dep_account_id:
            lines += [LineInput(account_id=cat.accum_dep_account_id, debit=acc_total, site_id=asset.site_id, description=f"Transfer out {asset.code}"),
                      LineInput(account_id=cat.accum_dep_account_id, credit=acc_total, site_id=to_site_id, description=f"Transfer in {asset.code}")]
        je = engine.create_and_post(db, actor, company_id=asset.company_id, journal_type=JournalType.FAT, transaction_date=on_date,
                                    description=f"Asset transfer {asset.code}", lines=lines, source_module=SourceModule.ASSETS,
                                    source_type="asset_transfer", source_id=asset.id)
        je_id = je.id
    t = AssetTransaction(asset_id=asset.id, txn_type="TRANSFER", txn_date=on_date, from_site_id=asset.site_id, to_site_id=to_site_id,
                         from_cost_centre_id=asset.cost_centre_id, to_cost_centre_id=to_cost_centre_id, amount=asset.cost,
                         journal_id=je_id, notes=notes, created_by_id=actor.id)
    asset.site_id, asset.cost_centre_id = to_site_id, to_cost_centre_id
    db.add(t)
    db.flush()
    return t


def dispose(db: Session, actor: Actor, asset: FixedAsset, on_date: date, proceeds: Decimal, bank_account_id: int | None,
            notes: str | None = None) -> AssetTransaction:
    actor.require("asset.dispose")
    if asset.status not in (AssetStatus.ACTIVE, AssetStatus.FULLY_DEPRECIATED):
        raise Conflict("Only active assets can be disposed")
    cat = db.get(AssetCategory, asset.category_id)
    proceeds = money(proceeds)
    nbv = asset.net_book_value
    corp = db.scalar(select(CostCentre.id).where(CostCentre.company_id == asset.company_id, CostCentre.code == "090101"))
    lines = [LineInput(account_id=cat.cost_account_id, credit=asset.cost, site_id=asset.site_id, description=f"Disposal {asset.code}")]
    acc_total = asset.accumulated_depreciation + asset.impairment_total
    if acc_total:
        lines.append(LineInput(account_id=cat.accum_dep_account_id, debit=acc_total, site_id=asset.site_id, description=f"Disposal {asset.code}"))
    if proceeds:
        ba = db.get(BankAccount, bank_account_id or 0)
        if ba is None:
            raise ValidationFailed("Bank / cash account for proceeds is required")
        lines.append(LineInput(account_id=ba.gl_account_id, debit=proceeds, site_id=ba.site_id, description=f"Disposal proceeds {asset.code}"))
    gain = proceeds - nbv
    if gain > 0:
        lines.append(LineInput(account_id=cat.gain_account_id, credit=gain, cost_centre_id=corp, site_id=asset.site_id, description="Gain on disposal"))
    elif gain < 0:
        lines.append(LineInput(account_id=cat.loss_account_id, debit=-gain, cost_centre_id=corp, site_id=asset.site_id, description="Loss on disposal"))
    je = engine.create_and_post(db, actor, company_id=asset.company_id, journal_type=JournalType.FAT, transaction_date=on_date,
                                description=f"Disposal of {asset.code} {asset.name}", lines=lines, source_module=SourceModule.ASSETS,
                                source_type="asset_disposal", source_id=asset.id, source_key=f"FA-DSP-{asset.id}")
    asset.status, asset.disposal_date, asset.disposal_proceeds = AssetStatus.DISPOSED, on_date, proceeds
    t = AssetTransaction(asset_id=asset.id, txn_type="DISPOSAL", txn_date=on_date, from_site_id=asset.site_id, amount=asset.cost,
                         proceeds=proceeds, gain_loss=money(gain), journal_id=je.id, notes=notes, created_by_id=actor.id)
    db.add(t)
    db.flush()
    record(db, actor, "asset.dispose", "fixed_asset", asset.id, None, {"proceeds": str(proceeds), "gain_loss": str(gain)})
    return t


def impair(db: Session, actor: Actor, asset: FixedAsset, on_date: date, amount: Decimal, reason: str) -> AssetTransaction:
    actor.require("asset.dispose")
    amount = money(amount)
    if amount <= 0 or amount > asset.net_book_value - asset.residual_value:
        raise ValidationFailed("Impairment must be positive and not exceed NBV less residual value")
    cat = db.get(AssetCategory, asset.category_id)
    je = engine.create_and_post(db, actor, company_id=asset.company_id, journal_type=JournalType.FAT, transaction_date=on_date,
                                description=f"Impairment of {asset.code}: {reason}",
                                lines=[LineInput(account_id=cat.impairment_account_id, debit=amount, site_id=asset.site_id,
                                                 cost_centre_id=asset.cost_centre_id, description=reason),
                                       LineInput(account_id=cat.accum_dep_account_id, credit=amount, site_id=asset.site_id,
                                                 description=f"Impairment {asset.code}")],
                                source_module=SourceModule.ASSETS, source_type="asset_impairment", source_id=asset.id)
    asset.impairment_total = money(asset.impairment_total + amount)
    t = AssetTransaction(asset_id=asset.id, txn_type="IMPAIRMENT", txn_date=on_date, amount=amount, journal_id=je.id,
                         notes=reason, created_by_id=actor.id)
    db.add(t)
    db.flush()
    return t


# ------------------------------------------------------------------ reports
def register(db: Session, company_id: int, as_of: date, site_id: int | None = None) -> dict:
    q = select(FixedAsset).where(FixedAsset.company_id == company_id, FixedAsset.status != AssetStatus.DRAFT,
                                 FixedAsset.capitalisation_date <= as_of)
    if site_id:
        q = q.where(FixedAsset.site_id == site_id)
    cats = {c.id: c for c in db.scalars(select(AssetCategory)).all()}
    rows_out = []
    tot = [ZERO] * 3
    for a in db.scalars(q.order_by(FixedAsset.code)).all():
        if a.disposal_date and a.disposal_date <= as_of:
            continue
        dep = D(db.scalar(select(func.coalesce(func.sum(DepreciationLine.amount), 0)).join(DepreciationRun).join(
            AccountingPeriod, AccountingPeriod.id == DepreciationRun.period_id).where(
            DepreciationLine.asset_id == a.id, DepreciationRun.status == "POSTED", AccountingPeriod.end_date <= as_of)) or 0)
        opening_acc = a.accumulated_depreciation - D(db.scalar(select(func.coalesce(func.sum(DepreciationLine.amount), 0)).join(DepreciationRun)
                                                           .where(DepreciationLine.asset_id == a.id, DepreciationRun.status == "POSTED")) or 0)
        acc = opening_acc + dep + a.impairment_total
        vals = [a.cost, money(acc), money(a.cost - acc)]
        tot = [x + y for x, y in zip(tot, vals)]
        rows_out.append({"label": a.code, "name": a.name, "category": cats[a.category_id].name, "site_id": a.site_id,
                         "capitalised": a.capitalisation_date.isoformat(), "life": a.useful_life_months,
                         "cost": vals[0], "accumulated": vals[1], "nbv": vals[2], "status": a.status.value,
                         "level": 1, "style": "line", "asset_id": a.id})
    rows_out.append({"label": "TOTAL", "cost": money(tot[0]), "accumulated": money(tot[1]), "nbv": money(tot[2]), "level": 0, "style": "grand"})
    return {"title": "Fixed Asset Register", "subtitle": f"As at {as_of.strftime('%d %b %Y')}",
            "columns": [{"key": "label", "label": "Asset", "type": "text"}, {"key": "name", "label": "Description", "type": "text"},
                        {"key": "category", "label": "Category", "type": "text"}, {"key": "capitalised", "label": "Capitalised", "type": "text"},
                        {"key": "life", "label": "Life (m)", "type": "int"}, {"key": "cost", "label": "Cost", "type": "money"},
                        {"key": "accumulated", "label": "Acc. depreciation", "type": "money"}, {"key": "nbv", "label": "NBV", "type": "money"},
                        {"key": "status", "label": "Status", "type": "text"}],
            "rows": rows_out, "meta": {"totals": tot}}


def reconciliation(db: Session, company_id: int, as_of: date) -> dict:
    """Register (by category) vs GL cost and accumulated depreciation accounts."""
    reg = register(db, company_id, as_of)
    by_cat: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for r in reg["rows"][:-1]:
        by_cat[r["category"]][0] += r["cost"]
        by_cat[r["category"]][1] += r["accumulated"]
    rows_out = []
    ok = True
    for cat in db.scalars(select(AssetCategory).order_by(AssetCategory.code)).all():
        def gl(acc_id):
            if not acc_id:
                return ZERO
            return D(db.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
                JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.account_id == acc_id,
                JournalLine.posting_date <= as_of)) or 0)
        reg_cost, reg_acc = by_cat.get(cat.name, [ZERO, ZERO])
        gl_cost, gl_acc = gl(cat.cost_account_id), -gl(cat.accum_dep_account_id)
        if not any([reg_cost, reg_acc, gl_cost, gl_acc]):
            continue
        d1, d2 = money(reg_cost - gl_cost), money(reg_acc - gl_acc)
        ok = ok and d1 == 0 and d2 == 0
        rows_out.append({"label": cat.name, "c0": money(reg_cost), "c1": money(gl_cost), "c2": d1,
                         "c3": money(reg_acc), "c4": money(gl_acc), "c5": d2, "level": 1, "style": "line"})
    return {"title": "Fixed Assets Register to GL Reconciliation", "subtitle": f"As at {as_of.strftime('%d %b %Y')}",
            "columns": [{"key": "label", "label": "Category", "type": "text"},
                        {"key": "c0", "label": "Cost - register", "type": "money"}, {"key": "c1", "label": "Cost - GL", "type": "money"},
                        {"key": "c2", "label": "Difference", "type": "money"}, {"key": "c3", "label": "Acc. dep. - register", "type": "money"},
                        {"key": "c4", "label": "Acc. dep. - GL", "type": "money"}, {"key": "c5", "label": "Difference", "type": "money"}],
            "rows": rows_out, "meta": {"reconciled": ok}}
