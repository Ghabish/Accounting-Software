"""Idempotent seeding of reference data, the Universal Cinemas company and (optionally) sample data.

    python -m scripts.seed               # reference + company + admin user
    python -m scripts.seed --demo        # + clearly-labelled demo masters and demo users
"""
from __future__ import annotations

import secrets
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.accounting.models import Account
from backend.accounting.periods import create_fiscal_year
from backend.ap.models import Supplier, SupplierCategory
from backend.ar.models import Customer, CustomerCategory
from backend.assets.models import AssetCategory
from backend.authentication.models import Permission, Role, User, UserSiteAccess
from backend.authentication.permissions import PERMISSIONS, ROLES
from backend.authentication.security import hash_password
from backend.banking.models import BankAccount
from backend.cinema.models import Film, FilmTerm, PaymentMethod, RevenueType, Screen
from backend.database.seed import reference as R
from backend.database.seed.coa_data import build_chart
from backend.masters.models import Company, CostCentre, DimensionType, DimensionValue, Employee, Site
from backend.tax.models import TaxCode, TaxRate, TaxSlab
from backend.workflow.models import ApprovalLimit, WorkflowDefinition


def _get(db: Session, model, **kw):
    return db.scalar(select(model).filter_by(**kw))


def acc(db: Session, code: str) -> Account:
    a = _get(db, Account, code=code)
    if a is None:
        raise KeyError(f"account {code} not seeded")
    return a


def seed_security(db: Session) -> None:
    perms = {}
    for code, desc in PERMISSIONS.items():
        p = _get(db, Permission, code=code)
        if p is None:
            p = Permission(code=code, module=code.split(".")[0], description=desc)
            db.add(p)
        perms[code] = p
    db.flush()
    for code, (name, plist, _all) in ROLES.items():
        role = _get(db, Role, code=code)
        if role is None:
            role = Role(code=code, name=name, is_system=True)
            db.add(role)
        role.permissions = [perms[p] for p in sorted(plist)]
    db.flush()


def seed_chart(db: Session) -> int:
    created = 0
    by_code: dict[str, Account] = {a.code: a for a in db.scalars(select(Account)).all()}
    for row in build_chart():
        if row["code"] in by_code:
            continue
        parent = by_code.get(row["parent_code"]) if row["parent_code"] else None
        data = {k: v for k, v in row.items() if k not in ("parent_code",)}
        if row["level"] < 4:
            data.setdefault("normal_balance", "D" if row["account_type"] in ("ASSET", "EXPENSE") else "C")
        a = Account(parent_id=parent.id if parent else None, **data)
        db.add(a)
        db.flush()
        by_code[a.code] = a
        created += 1
    return created


def seed_company(db: Session) -> Company:
    co = _get(db, Company, code=R.COMPANY["code"])
    if co is None:
        co = Company(**R.COMPANY)
        db.add(co)
        db.flush()
    for code, name, stype, city, prov, auth, pos in R.SITES:
        if _get(db, Site, company_id=co.id, code=code) is None:
            db.add(Site(company_id=co.id, code=code, name=name, site_type=stype, city=city, province=prov,
                        tax_authority=auth, pos_code=pos,
                        notes="City to confirm" if code in ("001", "102") else None))
    db.flush()
    for code, name, sec, secname, func, owner in R.COST_CENTRES:
        cc = _get(db, CostCentre, company_id=co.id, code=code)
        if cc is None:
            cc = CostCentre(company_id=co.id, code=code, name=name, section_code=sec, section_name=secname,
                            function=func, budget_owner=owner)
            db.add(cc)
            db.flush()
    return co


def seed_dimensions(db: Session) -> None:
    for code, name, system in R.DIMENSION_TYPES:
        if _get(db, DimensionType, code=code) is None:
            db.add(DimensionType(code=code, name=name, is_system=system))
    db.flush()


def seed_tax(db: Session) -> None:
    for code, name, ttype, auth, sec, base, account, recov, conf, notes in R.TAX_CODES:
        if _get(db, TaxCode, code=code) is None:
            db.add(TaxCode(code=code, name=name, tax_type=ttype, authority=auth, law_section=sec, base=base,
                           account_id=acc(db, account).id, is_recoverable=recov, needs_confirmation=conf,
                           notes=notes))
    db.flush()
    for code, name, payee, atl, rate in R.TAX_RATES:
        tc = _get(db, TaxCode, code=code)
        if _get(db, TaxRate, tax_code_id=tc.id, name=name) is None:
            db.add(TaxRate(tax_code_id=tc.id, name=name, payee_type=payee, atl_status=atl, rate=Decimal(rate),
                           effective_from=R.TAX_EFFECTIVE,
                           source_ref="Generation COA v9.2 Tax Rates (TY2027) - confirm for Universal Cinemas"))
    for code, slabs in (("WHT-155", R.RENT_SLABS), ("WHT-149", R.SALARY_SLABS)):
        tc = _get(db, TaxCode, code=code)
        if db.scalar(select(TaxSlab.id).where(TaxSlab.tax_code_id == tc.id)) is None:
            for lo, hi, fixed, rate in slabs:
                db.add(TaxSlab(tax_code_id=tc.id, effective_from=R.TAX_EFFECTIVE, amount_from=lo, amount_to=hi,
                               fixed_tax=fixed, rate=rate))
    db.flush()


def _tax(db: Session, code: str | None) -> int | None:
    return _get(db, TaxCode, code=code).id if code else None


def seed_categories(db: Session) -> None:
    for code, name, ctrl, adv, exp, wht, st, stw in R.SUPPLIER_CATEGORIES:
        if _get(db, SupplierCategory, code=code) is None:
            db.add(SupplierCategory(code=code, name=name, ap_control_account_id=acc(db, ctrl).id,
                                    advance_account_id=acc(db, adv).id, default_expense_account_id=acc(db, exp).id,
                                    default_wht_tax_code_id=_tax(db, wht), default_st_tax_code_id=_tax(db, st),
                                    default_stw_tax_code_id=_tax(db, stw)))
    for code, name, ctrl, adv, rev, tax in R.CUSTOMER_CATEGORIES:
        if _get(db, CustomerCategory, code=code) is None:
            db.add(CustomerCategory(code=code, name=name, ar_control_account_id=acc(db, ctrl).id,
                                    advance_account_id=acc(db, adv).id if adv else None,
                                    default_revenue_account_id=acc(db, rev).id if rev else None,
                                    default_output_tax_code_id=_tax(db, tax)))
    for code, name, cost, accum, dep, life in R.ASSET_CATEGORIES:
        if _get(db, AssetCategory, code=code) is None:
            db.add(AssetCategory(code=code, name=name, cost_account_id=acc(db, cost).id,
                                 accum_dep_account_id=acc(db, accum).id if accum else None,
                                 dep_expense_account_id=acc(db, dep).id if dep else None,
                                 gain_account_id=acc(db, "07-01-02-0001").id,
                                 loss_account_id=acc(db, "07-02-01-0001").id,
                                 impairment_account_id=acc(db, "06-07-03-0002").id,
                                 default_useful_life_months=life or 1, is_depreciable=bool(accum)))
    db.flush()


def seed_workflow(db: Session) -> None:
    for doc_type, name, check, auto in R.WORKFLOWS:
        if _get(db, WorkflowDefinition, doc_type=doc_type) is None:
            db.add(WorkflowDefinition(doc_type=doc_type, name=name, require_check=check,
                                      segregation_of_duties=True, auto_post_on_approval=auto))
        for role_code, limit in R.APPROVAL_LIMITS.items():
            role = _get(db, Role, code=role_code)
            if _get(db, ApprovalLimit, doc_type=doc_type, role_id=role.id) is None:
                db.add(ApprovalLimit(doc_type=doc_type, role_id=role.id, max_amount=limit))
    db.flush()


def seed_banking_and_cinema(db: Session, co: Company) -> None:
    sites = {s.code: s for s in db.scalars(select(Site).where(Site.company_id == co.id)).all()}
    for code, name, kind, gl, site_code, bank in R.BANK_ACCOUNTS:
        if _get(db, BankAccount, company_id=co.id, code=code) is None:
            db.add(BankAccount(company_id=co.id, code=code, name=name, kind=kind, gl_account_id=acc(db, gl).id,
                               site_id=sites[site_code].id if site_code else None, bank_name=bank,
                               is_default_payment=(code == "BNK-OPS"),
                               imprest_amount=Decimal("50000") if kind == "PETTY_CASH" else None, is_sample=True))
    db.flush()
    # platform customers used as clearing parties for gateway / wallet / platform collections
    platform_customers = {"C00901": ("Online payment gateway (configure)", "GATEWAY"),
                          "C00902": ("Mobile wallet provider (configure)", "WALLET"),
                          "C00903": ("Third-party ticketing platform (configure)", "PLATFORM")}
    for ccode, (cname, cat) in platform_customers.items():
        if _get(db, Customer, code=ccode) is None:
            db.add(Customer(code=ccode, name=cname, category_id=_get(db, CustomerCategory, code=cat).id,
                            payment_terms_days=3, is_sample=True))
    db.flush()
    bank_col = _get(db, BankAccount, company_id=co.id, code="BNK-COL")
    for code, name, mtype, clearing, cust, fee in R.PAYMENT_METHODS:
        if _get(db, PaymentMethod, code=code) is None:
            clearing_acc = acc(db, clearing or "01-02-07-0002")
            fee_acc = "06-04-02-0002" if mtype == "WALLET" else "06-04-02-0001"
            db.add(PaymentMethod(code=code, name=name, method_type=mtype, clearing_account_id=clearing_acc.id,
                                 customer_id=_get(db, Customer, code=cust).id if cust else None,
                                 fee_pct=Decimal(fee), fee_account_id=acc(db, fee_acc).id if Decimal(fee) else None,
                                 settlement_bank_account_id=bank_col.id if mtype not in ("CASH", "VOUCHER", "CORPORATE") else None))
    for code, name, stream, rev, disc, ref, cc, taxes, film in R.REVENUE_TYPES:
        if _get(db, RevenueType, code=code) is None:
            db.add(RevenueType(code=code, name=name, stream=stream, revenue_account_id=acc(db, rev).id,
                               discount_account_id=acc(db, disc).id if disc else None,
                               refund_account_id=acc(db, ref).id if ref else None,
                               cost_centre_id=_get(db, CostCentre, company_id=co.id, code=cc).id,
                               tax_code_ids=",".join(str(_tax(db, t)) for t in taxes) or None,
                               applies_film_rental=film))
    db.flush()


def seed_fiscal_years(db: Session, co: Company, first: date = date(2026, 7, 1), years: int = 2) -> None:
    for i in range(years):
        create_fiscal_year(db, co.id, date(first.year + i, first.month, 1), co.fiscal_year_start_month)


def seed_admin(db: Session, password: str | None = None) -> tuple[User, str | None]:
    user = _get(db, User, username="admin")
    if user:
        return user, None
    pwd = password or secrets.token_urlsafe(12) + "A1"
    user = User(username="admin", full_name="System Administrator", password_hash=hash_password(pwd),
                is_superuser=True, all_sites=True, must_change_password=password is None)
    user.roles = [_get(db, Role, code="ADMIN")]
    db.add(user)
    db.flush()
    return user, pwd


DEMO_PASSWORD = "Demo@2026pass"
DEMO_USERS = [
    ("cfo", "Demo CFO", "CFO", None), ("fm", "Demo Finance Manager", "FINANCE_MANAGER", None),
    ("accountant", "Demo Accountant", "ACCOUNTANT", None), ("ap", "Demo AP Officer", "AP_OFFICER", None),
    ("ar", "Demo AR Officer", "AR_OFFICER", None), ("cashier.emp", "Demo Cashier Emporium", "CASHIER", "101"),
    ("manager.emp", "Demo Site Manager Emporium", "SITE_MANAGER", "101"), ("auditor", "Demo Auditor", "AUDITOR", None),
]


def seed_demo(db: Session, co: Company) -> None:
    """Clearly-labelled DEMO masters. No real Universal Cinemas figures are created."""
    sites = {s.code: s for s in db.scalars(select(Site).where(Site.company_id == co.id)).all()}
    for uname, full, role_code, site_code in DEMO_USERS:
        if _get(db, User, username=uname) is None:
            _name, _perms, all_sites = ROLES[role_code]
            u = User(username=uname, full_name=f"[DEMO] {full}", password_hash=hash_password(DEMO_PASSWORD),
                     all_sites=all_sites, default_company_id=co.id)
            u.roles = [_get(db, Role, code=role_code)]
            if site_code:
                u.site_access = [UserSiteAccess(site_id=sites[site_code].id)]
            db.add(u)
    cats = {c.code: c for c in db.scalars(select(SupplierCategory)).all()}
    demo_suppliers = [
        ("V00001", "[DEMO] Silver Screen Distributors", "DISTRIBUTOR", "COMPANY"),
        ("V00002", "[DEMO] Lollywood Films Distribution", "DISTRIBUTOR", "COMPANY"),
        ("V00003", "[DEMO] Popcorn & Snacks Supplies", "FNB", "COMPANY"),
        ("V00004", "[DEMO] Mall Management Company", "LANDLORD", "COMPANY"),
        ("V00005", "[DEMO] Electricity Distribution Co", "UTILITIES", "COMPANY"),
        ("V00006", "[DEMO] Cinema Tech Services", "MAINTENANCE", "COMPANY"),
        ("V00007", "[DEMO] Brightlight Media Agency", "MARKETING", "COMPANY"),
        ("V00008", "[DEMO] Digital Projection Systems", "CAPEX", "COMPANY"),
        ("V00009", "[DEMO] Ticketing Software Pvt", "IT", "COMPANY"),
        ("V00010", "[DEMO] Chartered Accountants & Co", "PROFESSIONAL", "AOP"),
    ]
    for code, name, cat, stype in demo_suppliers:
        if _get(db, Supplier, code=code) is None:
            c = cats[cat]
            db.add(Supplier(code=code, name=name, category_id=c.id, supplier_type=stype, atl_status="ATL",
                            ntn=f"DEMO{code[1:]}", payment_terms_days=30, wht_tax_code_id=c.default_wht_tax_code_id,
                            st_tax_code_id=c.default_st_tax_code_id, stw_tax_code_id=c.default_stw_tax_code_id,
                            is_sample=True))
    ccats = {c.code: c for c in db.scalars(select(CustomerCategory)).all()}
    for code, name, cat in [("C00001", "[DEMO] Fizz Beverages (advertiser)", "ADVERTISING"),
                            ("C00002", "[DEMO] Telco Brand (sponsor)", "ADVERTISING"),
                            ("C00003", "[DEMO] Corporate Client Ltd", "CORPORATE")]:
        if _get(db, Customer, code=code) is None:
            db.add(Customer(code=code, name=name, category_id=ccats[cat].id, ntn=f"DEMO{code[1:]}",
                            payment_terms_days=30, is_sample=True))
    db.flush()
    dt = {d.code: d for d in db.scalars(select(DimensionType)).all()}
    screens = {"101": 6, "102": 4, "103": 5}
    for scode, n in screens.items():
        for i in range(1, n + 1):
            code = f"S{i}"
            if _get(db, Screen, site_id=sites[scode].id, code=code) is None:
                dv = DimensionValue(dimension_type_id=dt["SCREEN"].id, code=f"{scode}-{code}",
                                    name=f"{sites[scode].name} Screen {i}", site_id=sites[scode].id)
                db.add(dv)
                db.flush()
                db.add(Screen(site_id=sites[scode].id, code=code, name=f"Screen {i}", seats=120 + 20 * (i % 3),
                              screen_type="GOLD" if i == 1 else "STANDARD", dimension_value_id=dv.id, is_sample=True))
    db.flush()
    films = [("F0001", "[DEMO] The Northern Star", "V00001", date(2026, 10, 2), [("1", "1", "0.50"), ("2", "2", "0.45"), ("3", "999", "0.40")]),
             ("F0002", "[DEMO] Lahore Nights", "V00002", date(2026, 10, 9), [("1", "999", "0.45")]),
             ("F0003", "[DEMO] Animated Adventure", "V00001", date(2026, 9, 25), [("1", "2", "0.50"), ("3", "999", "0.40")])]
    for code, title, dist, rel, terms in films:
        if _get(db, Film, code=code) is None:
            sup = _get(db, Supplier, code=dist)
            dv = DimensionValue(dimension_type_id=dt["FILM"].id, code=code, name=title)
            db.add(dv)
            db.flush()
            f = Film(code=code, title=title, distributor_id=sup.id, release_date=rel, language="Urdu/English",
                     rating="PG", runtime_minutes=130, dimension_value_id=dv.id, is_sample=True)
            f.terms = [FilmTerm(week_from=int(a), week_to=int(b), share_pct=Decimal(p)) for a, b, p in terms]
            db.add(f)
    for code, name in [("DEMO-V00001", "[DEMO] Silver Screen Distributors"), ("DEMO-V00002", "[DEMO] Lollywood Films Distribution")]:
        if _get(db, DimensionValue, dimension_type_id=dt["DISTRIBUTOR"].id, code=code[5:]) is None:
            db.add(DimensionValue(dimension_type_id=dt["DISTRIBUTOR"].id, code=code[5:], name=name))
    if _get(db, Employee, company_id=co.id, code="E0001") is None:
        db.add(Employee(company_id=co.id, code="E0001", name="[DEMO] Box Office Supervisor", site_id=sites["101"].id,
                        is_sample=True))
    db.flush()


def seed_all(db: Session, *, demo: bool = False, admin_password: str | None = None) -> dict:
    seed_security(db)
    created = seed_chart(db)
    seed_dimensions(db)
    co = seed_company(db)
    seed_tax(db)
    seed_categories(db)
    seed_workflow(db)
    seed_banking_and_cinema(db, co)
    seed_fiscal_years(db, co)
    admin, pwd = seed_admin(db, admin_password)
    if demo:
        seed_demo(db, co)
    db.flush()
    return {"company_id": co.id, "accounts_created": created, "admin_password": pwd}
