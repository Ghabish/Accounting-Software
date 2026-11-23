"""Organisation masters, chart of accounts, periods."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.accounting.models import (
    AbnormalBalance, Account, AccountingPeriod, AccountType, BudgetControl, ControlType, CostCentreRule,
    FiscalYear, JournalLine, ManualJournal, PartyType, PeriodStatus, Rule,
)
from backend.accounting import periods as period_svc
from backend.api.crud import register_crud
from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import row, rows
from backend.audit.service import record
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.masters.models import (
    AccountDimensionRule, Company, CostCentre, CostCentreFunction, DimensionRule, DimensionType, DimensionValue,
    Employee, Setting, Site, SiteType,
)

router = APIRouter(prefix="/api", tags=["masters"])


# ------------------------------------------------------------------ schemas
class SiteIn(BaseModel):
    code: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=1, max_length=120)
    site_type: SiteType = SiteType.CINEMA
    city: str | None = None
    province: str | None = None
    tax_authority: str | None = None
    pos_code: str | None = None
    opening_date: date | None = None
    is_active: bool = True
    notes: str | None = None


class SiteUpdate(BaseModel):
    name: str | None = None
    site_type: SiteType | None = None
    city: str | None = None
    province: str | None = None
    tax_authority: str | None = None
    pos_code: str | None = None
    opening_date: date | None = None
    is_active: bool | None = None
    notes: str | None = None


class CostCentreIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None
    section_code: str | None = None
    section_name: str | None = None
    function: CostCentreFunction = CostCentreFunction.SITE_OPERATIONS
    budget_owner: str | None = None
    is_postable: bool = True
    is_active: bool = True


class CostCentreUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    section_name: str | None = None
    function: CostCentreFunction | None = None
    budget_owner: str | None = None
    is_postable: bool | None = None
    is_active: bool | None = None


class DimTypeIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_]{2,20}$")
    name: str
    description: str | None = None
    is_active: bool = True


class DimTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class DimValueIn(BaseModel):
    dimension_type_id: int
    code: str = Field(min_length=1, max_length=40)
    name: str
    parent_id: int | None = None
    site_id: int | None = None
    is_active: bool = True


class DimValueUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    site_id: int | None = None
    is_active: bool | None = None


class EmployeeIn(BaseModel):
    code: str
    name: str
    cnic: str | None = None
    site_id: int | None = None
    cost_centre_id: int | None = None
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    name: str | None = None
    cnic: str | None = None
    site_id: int | None = None
    cost_centre_id: int | None = None
    is_active: bool | None = None


def _cc_validate(db, actor, obj, data):
    code = data.get("code") or obj.code
    if code and "code" in data and not data.get("section_code"):
        data["section_code"] = code[:2]


register_crud(router, "/sites", Site, SiteIn, SiteUpdate, view_perm="masters.view", manage_perm="masters.manage",
              company_scoped=True, filters=("site_type",))
register_crud(router, "/cost-centres", CostCentre, CostCentreIn, CostCentreUpdate, view_perm="masters.view",
              manage_perm="masters.manage", company_scoped=True, filters=("section_code", "function"),
              validate=_cc_validate)
register_crud(router, "/dimension-types", DimensionType, DimTypeIn, DimTypeUpdate, view_perm="masters.view",
              manage_perm="masters.manage")
register_crud(router, "/dimension-values", DimensionValue, DimValueIn, DimValueUpdate, view_perm="masters.view",
              manage_perm="masters.manage", filters=("dimension_type_id",))
register_crud(router, "/employees", Employee, EmployeeIn, EmployeeUpdate, view_perm="masters.view",
              manage_perm="masters.manage", company_scoped=True)


@router.get("/companies")
def companies(db: DB, actor: CurrentActor):
    return rows(db.scalars(select(Company).order_by(Company.code)).all())


@router.get("/settings")
def settings_list(db: DB, actor: CurrentActor, company_id: CompanyId):
    actor.require("admin.settings")
    return rows(db.scalars(select(Setting).where((Setting.company_id == company_id) | Setting.company_id.is_(None))).all())


class SettingIn(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_.]{2,80}$")
    value: str
    description: str | None = None


@router.put("/settings")
def settings_put(body: SettingIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    actor.require("admin.settings")
    s = db.scalar(select(Setting).where(Setting.company_id == company_id, Setting.key == body.key))
    old = {"value": s.value} if s else None
    if s is None:
        s = Setting(company_id=company_id, key=body.key, value=body.value, description=body.description)
        db.add(s)
    else:
        s.value, s.description = body.value, body.description or s.description
    db.flush()
    record(db, actor, "setting.update", "setting", s.id, old, {"key": body.key, "value": body.value})
    db.commit()
    return row(s)


# ------------------------------------------------------------------ chart of accounts
class AccountIn(BaseModel):
    parent_code: str = Field(pattern=r"^\d{2}(-\d{2}){0,2}$")
    code: str | None = Field(default=None, pattern=r"^\d{2}(-\d{2}){0,2}(-\d{4})?$")
    name: str = Field(min_length=2, max_length=160)
    is_contra: bool = False
    control_type: ControlType = ControlType.NONE
    party_type: PartyType = PartyType.NONE
    party_rule: Rule = Rule.NONE
    site_rule: Rule = Rule.OPT
    cost_centre_rule: CostCentreRule | None = None
    pl_section: str | None = None
    revenue_stream: str | None = None
    cash_flow_line: str | None = None
    cf_adjustment: str | None = None
    cf_counter_line: str | None = None
    manual_journal: ManualJournal = ManualJournal.ALLOWED
    abnormal_balance: AbnormalBalance = AbnormalBalance.ALERT
    reconcile_required: bool = False
    budget_control: BudgetControl = BudgetControl.NONE
    is_intercompany: bool = False
    zero_at_period_end: bool = False
    requires_attachment: bool = False
    description: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    control_type: ControlType | None = None
    party_type: PartyType | None = None
    party_rule: Rule | None = None
    site_rule: Rule | None = None
    cost_centre_rule: CostCentreRule | None = None
    pl_section: str | None = None
    revenue_stream: str | None = None
    cash_flow_line: str | None = None
    cf_adjustment: str | None = None
    cf_counter_line: str | None = None
    manual_journal: ManualJournal | None = None
    abnormal_balance: AbnormalBalance | None = None
    reconcile_required: bool | None = None
    budget_control: BudgetControl | None = None
    is_intercompany: bool | None = None
    zero_at_period_end: bool | None = None
    requires_attachment: bool | None = None
    is_active: bool | None = None
    effective_to: date | None = None
    description: str | None = None


def _norm(name: str) -> str:
    return "".join(name.lower().split())


@router.get("/accounts")
def accounts(db: DB, actor: CurrentActor, q: str | None = None, postable: bool | None = None,
             active: bool | None = None, control_type: str | None = None, party_type: str | None = None):
    actor.require("coa.view")
    stmt = select(Account).order_by(Account.code)
    if q:
        stmt = stmt.where((Account.code.ilike(f"{q}%")) | (Account.name.ilike(f"%{q}%")))
    if postable is not None:
        stmt = stmt.where(Account.is_postable.is_(postable))
    if active is not None:
        stmt = stmt.where(Account.is_active.is_(active))
    if control_type:
        stmt = stmt.where(Account.control_type == control_type)
    if party_type:
        stmt = stmt.where(Account.party_type == party_type)
    return rows(db.scalars(stmt).all())


@router.get("/accounts/{account_id}")
def account_get(account_id: int, db: DB, actor: CurrentActor):
    actor.require("coa.view")
    a = db.get(Account, account_id)
    if a is None:
        raise NotFound("Account not found")
    used = db.scalar(select(func.count()).select_from(JournalLine).where(JournalLine.account_id == a.id)) or 0
    rules = db.scalars(select(AccountDimensionRule).where(AccountDimensionRule.account_id == a.id)).all()
    return row(a, extra={"line_count": used, "dimension_rules": [{"dimension_type_id": r.dimension_type_id,
                                                                   "rule": r.rule.value} for r in rules]})


@router.post("/accounts", status_code=201)
def account_create(body: AccountIn, db: DB, actor: CurrentActor):
    actor.require("coa.manage")
    parent = db.scalar(select(Account).where(Account.code == body.parent_code))
    if parent is None:
        raise ValidationFailed("Parent account not found")
    if parent.level >= 4:
        raise ValidationFailed("Ledgers cannot have children")
    level = parent.level + 1
    if body.code:
        code = body.code
        if not code.startswith(parent.code + "-") or code.count("-") != level - 1:
            raise ValidationFailed("Code must sit directly under its parent")
    else:  # next free number in the parent (V29: codes are never reused)
        siblings = db.scalars(select(Account.code).where(Account.parent_id == parent.id)).all()
        width = 4 if level == 4 else 2
        nums = [int(c.split("-")[-1]) for c in siblings] or [0]
        code = f"{parent.code}-{str(max(nums) + 1).zfill(width)}"
    if db.scalar(select(Account.id).where(Account.code == code)):
        raise Conflict(f"Account code {code} already exists")
    if level == 4:
        for other in db.scalars(select(Account.name).where(Account.is_postable.is_(True))).all():
            if _norm(other) == _norm(body.name):
                raise Conflict("A posting account with this name already exists (V40)")
    atype = parent.account_type
    normal = "D" if atype in (AccountType.ASSET, AccountType.EXPENSE) else "C"
    if body.is_contra:
        normal = "C" if normal == "D" else "D"
    data = body.model_dump(exclude={"parent_code", "code"})
    if data.get("cost_centre_rule") is None:
        data["cost_centre_rule"] = CostCentreRule.REQ if atype in (AccountType.INCOME, AccountType.EXPENSE) else CostCentreRule.BS
    a = Account(code=code, level=level, parent_id=parent.id, account_type=atype, normal_balance=normal,
                is_postable=level == 4, created_by_id=actor.id, gen_ref="NEW", **data)
    db.add(a)
    db.flush()
    record(db, actor, "account.create", "account", a.id, None, row(a))
    db.commit()
    return row(a)


@router.patch("/accounts/{account_id}")
def account_update(account_id: int, body: AccountUpdate, db: DB, actor: CurrentActor):
    actor.require("coa.manage")
    a = db.get(Account, account_id)
    if a is None:
        raise NotFound("Account not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and a.is_postable:
        for other in db.scalars(select(Account).where(Account.is_postable.is_(True), Account.id != a.id)).all():
            if _norm(other.name) == _norm(data["name"]):
                raise Conflict("A posting account with this name already exists (V40)")
    if data.get("is_active") is False and a.is_postable:
        bal = db.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
                        .where(JournalLine.account_id == a.id, JournalLine.is_posted.is_(True)))
        if bal:
            raise Conflict("Account has a balance; transfer it before deactivating")
    old = {k: row(a).get(k) for k in data}
    for k, v in data.items():
        setattr(a, k, v)
    db.flush()
    record(db, actor, "account.update", "account", a.id, old, {k: row(a).get(k) for k in data})
    db.commit()
    return row(a)


class DimRuleIn(BaseModel):
    dimension_type_id: int
    rule: DimensionRule


@router.put("/accounts/{account_id}/dimension-rules")
def account_dim_rules(account_id: int, body: list[DimRuleIn], db: DB, actor: CurrentActor):
    actor.require("coa.manage")
    if db.get(Account, account_id) is None:
        raise NotFound("Account not found")
    existing = {r.dimension_type_id: r for r in db.scalars(
        select(AccountDimensionRule).where(AccountDimensionRule.account_id == account_id)).all()}
    for item in body:
        r = existing.get(item.dimension_type_id)
        if r is None:
            db.add(AccountDimensionRule(account_id=account_id, dimension_type_id=item.dimension_type_id, rule=item.rule))
        else:
            r.rule = item.rule
    record(db, actor, "account.dimension_rules", "account", account_id, None, {"rules": [b.model_dump() for b in body]})
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ periods
@router.get("/fiscal-years")
def fiscal_years(db: DB, actor: CurrentActor, company_id: CompanyId):
    actor.require("period.view")
    return rows(db.scalars(select(FiscalYear).where(FiscalYear.company_id == company_id).order_by(FiscalYear.start_date)).all())


class FiscalYearIn(BaseModel):
    start_date: date


@router.post("/fiscal-years", status_code=201)
def fiscal_year_create(body: FiscalYearIn, db: DB, actor: CurrentActor, company_id: CompanyId):
    actor.require("period.manage")
    co = db.get(Company, company_id)
    fy = period_svc.create_fiscal_year(db, company_id, body.start_date, co.fiscal_year_start_month)
    record(db, actor, "fiscal_year.create", "fiscal_year", fy.id, None, {"code": fy.code})
    db.commit()
    return row(fy)


@router.get("/periods")
def periods(db: DB, actor: CurrentActor, company_id: CompanyId, fiscal_year_id: int | None = None):
    actor.require("period.view")
    stmt = select(AccountingPeriod).where(AccountingPeriod.company_id == company_id)
    if fiscal_year_id:
        stmt = stmt.where(AccountingPeriod.fiscal_year_id == fiscal_year_id)
    return rows(db.scalars(stmt.order_by(AccountingPeriod.start_date)).all())


class PeriodStatusIn(BaseModel):
    status: PeriodStatus
    reason: str | None = None


@router.post("/periods/{period_id}/status")
def period_status(period_id: int, body: PeriodStatusIn, db: DB, actor: CurrentActor):
    if body.status == PeriodStatus.CLOSED:
        raise ValidationFailed("Use the month-end close endpoint (/api/closing/{period}/close) to close a period")
    p = period_svc.change_status(db, period_id, body.status, actor, body.reason)
    db.commit()
    return row(p)
