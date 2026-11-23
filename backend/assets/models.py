"""Fixed assets: categories, register, depreciation runs, transactions."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import MONEY, RATE, AuditColumnsMixin, Base, StrEnum, enum_col, fk


class DepreciationMethod(StrEnum):
    STRAIGHT_LINE = "STRAIGHT_LINE"
    REDUCING_BALANCE = "REDUCING_BALANCE"


class AssetStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    FULLY_DEPRECIATED = "FULLY_DEPRECIATED"
    DISPOSED = "DISPOSED"


class AssetCategory(AuditColumnsMixin, Base):
    __tablename__ = "asset_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    cost_account_id: Mapped[int] = fk("accounts.id", nullable=False)
    accum_dep_account_id: Mapped[int | None] = fk("accounts.id")
    dep_expense_account_id: Mapped[int | None] = fk("accounts.id")
    gain_account_id: Mapped[int] = fk("accounts.id", nullable=False)
    loss_account_id: Mapped[int] = fk("accounts.id", nullable=False)
    impairment_account_id: Mapped[int | None] = fk("accounts.id")
    default_useful_life_months: Mapped[int] = mapped_column(Integer, default=60)
    default_method: Mapped[DepreciationMethod] = mapped_column(enum_col(DepreciationMethod), default=DepreciationMethod.STRAIGHT_LINE)
    default_residual_pct: Mapped[Decimal] = mapped_column(RATE, default=Decimal("0"))
    is_depreciable: Mapped[bool] = mapped_column(Boolean, default=True)


class FixedAsset(AuditColumnsMixin, Base):
    __tablename__ = "fixed_assets"
    __table_args__ = (UniqueConstraint("company_id", "code"),
                      CheckConstraint("cost >= 0 AND residual_value >= 0", name="non_negative"),
                      CheckConstraint("useful_life_months > 0", name="life_positive"))
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int] = fk("asset_categories.id", nullable=False)
    site_id: Mapped[int] = fk("sites.id", nullable=False)
    cost_centre_id: Mapped[int] = fk("cost_centres.id", nullable=False)
    supplier_id: Mapped[int | None] = fk("suppliers.id")
    ap_document_id: Mapped[int | None] = fk("ap_documents.id")
    purchase_date: Mapped[date] = mapped_column(Date)
    capitalisation_date: Mapped[date] = mapped_column(Date)
    depreciation_start_date: Mapped[date] = mapped_column(Date)
    cost: Mapped[Decimal] = mapped_column(MONEY)
    residual_value: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    useful_life_months: Mapped[int] = mapped_column(Integer)
    method: Mapped[DepreciationMethod] = mapped_column(enum_col(DepreciationMethod), default=DepreciationMethod.STRAIGHT_LINE)
    reducing_rate: Mapped[Decimal | None] = mapped_column(RATE)
    accumulated_depreciation: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    impairment_total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    status: Mapped[AssetStatus] = mapped_column(enum_col(AssetStatus), default=AssetStatus.DRAFT, index=True)
    last_depreciation_date: Mapped[date | None] = mapped_column(Date)
    disposal_date: Mapped[date | None] = mapped_column(Date)
    disposal_proceeds: Mapped[Decimal | None] = mapped_column(MONEY)
    acquisition_journal_id: Mapped[int | None] = fk("journal_entries.id")
    serial_no: Mapped[str | None] = mapped_column(String(80))
    tag_no: Mapped[str | None] = mapped_column(String(80))
    is_opening: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def net_book_value(self) -> Decimal:
        return (self.cost or Decimal("0")) - (self.accumulated_depreciation or Decimal("0")) - (self.impairment_total or Decimal("0"))


class DepreciationRun(AuditColumnsMixin, Base):
    __tablename__ = "depreciation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    period_id: Mapped[int] = fk("accounting_periods.id", nullable=False)
    run_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")  # DRAFT | POSTED | REVERSED
    total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    lines: Mapped[list["DepreciationLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class DepreciationLine(Base):
    __tablename__ = "depreciation_lines"
    __table_args__ = (UniqueConstraint("run_id", "asset_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("depreciation_runs.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int] = fk("fixed_assets.id", nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    site_id: Mapped[int] = fk("sites.id", nullable=False)
    cost_centre_id: Mapped[int] = fk("cost_centres.id", nullable=False)
    nbv_before: Mapped[Decimal] = mapped_column(MONEY)
    nbv_after: Mapped[Decimal] = mapped_column(MONEY)


class AssetTransaction(AuditColumnsMixin, Base):
    __tablename__ = "asset_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = fk("fixed_assets.id", nullable=False)
    txn_type: Mapped[str] = mapped_column(String(20))  # CAPITALISATION | TRANSFER | DISPOSAL | IMPAIRMENT | OPENING
    txn_date: Mapped[date] = mapped_column(Date)
    from_site_id: Mapped[int | None] = fk("sites.id")
    to_site_id: Mapped[int | None] = fk("sites.id")
    from_cost_centre_id: Mapped[int | None] = fk("cost_centres.id")
    to_cost_centre_id: Mapped[int | None] = fk("cost_centres.id")
    amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    proceeds: Mapped[Decimal | None] = mapped_column(MONEY)
    gain_loss: Mapped[Decimal | None] = mapped_column(MONEY)
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    notes: Mapped[str | None] = mapped_column(Text)
