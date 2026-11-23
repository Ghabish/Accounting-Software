"""Organisation masters: companies, sites, cost centres, dimensions, employees, settings."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import AuditColumnsMixin, Base, StrEnum, enum_col, fk


class SiteType(StrEnum):
    CINEMA = "CINEMA"
    HEAD_OFFICE = "HEAD_OFFICE"
    WAREHOUSE = "WAREHOUSE"
    OTHER = "OTHER"


class CostCentreFunction(StrEnum):
    SITE_OPERATIONS = "SITE_OPERATIONS"
    HEAD_OFFICE = "HEAD_OFFICE"
    COMPANY_LEVEL = "COMPANY_LEVEL"
    NOT_PL = "NOT_PL"


class DimensionRule(StrEnum):
    REQ = "REQ"
    OPT = "OPT"
    NONE = "NONE"


class Company(AuditColumnsMixin, Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(4), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(200))
    ntn: Mapped[str | None] = mapped_column(String(20))
    strn: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    base_currency: Mapped[str] = mapped_column(String(3), default="PKR")
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=7)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Site(AuditColumnsMixin, Base):
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("company_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(120))
    site_type: Mapped[SiteType] = mapped_column(enum_col(SiteType), default=SiteType.CINEMA)
    city: Mapped[str | None] = mapped_column(String(80))
    province: Mapped[str | None] = mapped_column(String(40))
    tax_authority: Mapped[str | None] = mapped_column(String(20))
    pos_code: Mapped[str | None] = mapped_column(String(20))
    opening_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class CostCentre(AuditColumnsMixin, Base):
    __tablename__ = "cost_centres"
    __table_args__ = (UniqueConstraint("company_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[int | None] = fk("cost_centres.id")
    section_code: Mapped[str | None] = mapped_column(String(2))
    section_name: Mapped[str | None] = mapped_column(String(80))
    function: Mapped[CostCentreFunction] = mapped_column(enum_col(CostCentreFunction), default=CostCentreFunction.SITE_OPERATIONS)
    budget_owner: Mapped[str | None] = mapped_column(String(120))
    is_postable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DimensionType(AuditColumnsMixin, Base):
    """Extra analysis dimensions (Screen, Film, Distributor, Project, Campaign ...). Unlimited."""
    __tablename__ = "dimension_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    values: Mapped[list["DimensionValue"]] = relationship(back_populates="dimension_type")


class DimensionValue(AuditColumnsMixin, Base):
    __tablename__ = "dimension_values"
    __table_args__ = (UniqueConstraint("dimension_type_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dimension_type_id: Mapped[int] = fk("dimension_types.id", nullable=False)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = fk("dimension_values.id")
    site_id: Mapped[int | None] = fk("sites.id")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    dimension_type: Mapped[DimensionType] = relationship(back_populates="values")


class AccountDimensionRule(Base):
    """Per-account requirement for an extra dimension (default: optional)."""
    __tablename__ = "account_dimension_rules"
    __table_args__ = (UniqueConstraint("account_id", "dimension_type_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = fk("accounts.id", nullable=False)
    dimension_type_id: Mapped[int] = fk("dimension_types.id", nullable=False)
    rule: Mapped[DimensionRule] = mapped_column(enum_col(DimensionRule), default=DimensionRule.OPT)


class Employee(AuditColumnsMixin, Base):
    """Minimal employee master used as a sub-ledger party (payroll module is future scope)."""
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("company_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    cnic: Mapped[str | None] = mapped_column(String(20))
    site_id: Mapped[int | None] = fk("sites.id")
    cost_centre_id: Mapped[int | None] = fk("cost_centres.id")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class Setting(Base):
    """Key/value parameters maintained by Finance (e.g. default bank account)."""
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("company_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
