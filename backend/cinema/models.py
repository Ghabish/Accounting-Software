"""Cinema operations: screens, films, distributor terms, shows, sales, day close, collections."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import MONEY, RATE, AuditColumnsMixin, Base, BigId, fk


class Screen(AuditColumnsMixin, Base):
    __tablename__ = "screens"
    __table_args__ = (UniqueConstraint("site_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = fk("sites.id", nullable=False)
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(80))
    seats: Mapped[int] = mapped_column(Integer, default=0)
    screen_type: Mapped[str] = mapped_column(String(20), default="STANDARD")
    dimension_value_id: Mapped[int | None] = fk("dimension_values.id")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class Film(AuditColumnsMixin, Base):
    __tablename__ = "films"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    distributor_id: Mapped[int] = fk("suppliers.id", nullable=False)
    language: Mapped[str | None] = mapped_column(String(40))
    rating: Mapped[str | None] = mapped_column(String(10))
    release_date: Mapped[date] = mapped_column(Date)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer)
    dimension_value_id: Mapped[int | None] = fk("dimension_values.id")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    terms: Mapped[list["FilmTerm"]] = relationship(cascade="all, delete-orphan", lazy="selectin",
                                                   order_by="FilmTerm.week_from")


class FilmTerm(Base):
    """Distributor share by week since release (optionally per site)."""
    __tablename__ = "film_terms"
    __table_args__ = (CheckConstraint("share_pct >= 0 AND share_pct <= 1", name="share_range"),
                      CheckConstraint("week_to >= week_from", name="weeks"))
    id: Mapped[int] = mapped_column(primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[int | None] = fk("sites.id")
    week_from: Mapped[int] = mapped_column(Integer, default=1)
    week_to: Mapped[int] = mapped_column(Integer, default=999)
    share_pct: Mapped[Decimal] = mapped_column(RATE)
    minimum_guarantee: Mapped[Decimal | None] = mapped_column(MONEY)


class Show(AuditColumnsMixin, Base):
    __tablename__ = "shows"
    __table_args__ = (UniqueConstraint("screen_id", "show_time"), Index("ix_show_site_date", "site_id", "business_date"))
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = fk("sites.id", nullable=False, index=False)
    screen_id: Mapped[int] = fk("screens.id", nullable=False)
    film_id: Mapped[int] = fk("films.id", nullable=False)
    business_date: Mapped[date] = mapped_column(Date)
    show_time: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="SCHEDULED")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class PaymentMethod(AuditColumnsMixin, Base):
    __tablename__ = "payment_methods"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    method_type: Mapped[str] = mapped_column(String(20))  # CASH | CARD | GATEWAY | WALLET | CORPORATE | VOUCHER | PLATFORM
    clearing_account_id: Mapped[int] = fk("accounts.id", nullable=False)
    customer_id: Mapped[int | None] = fk("customers.id")
    fee_pct: Mapped[Decimal] = mapped_column(RATE, default=Decimal("0"))
    fee_account_id: Mapped[int | None] = fk("accounts.id")
    settlement_bank_account_id: Mapped[int | None] = fk("bank_accounts.id")
    settlement_days: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RevenueType(AuditColumnsMixin, Base):
    """Maps a POS revenue category to GL accounts and the tax code used to split tax-inclusive prices."""
    __tablename__ = "revenue_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    stream: Mapped[str] = mapped_column(String(20))  # TICKETING | FNB | ADVERTISING | OTHER
    revenue_account_id: Mapped[int] = fk("accounts.id", nullable=False)
    discount_account_id: Mapped[int | None] = fk("accounts.id")
    refund_account_id: Mapped[int | None] = fk("accounts.id")
    cost_centre_id: Mapped[int] = fk("cost_centres.id", nullable=False)
    tax_code_ids: Mapped[str | None] = mapped_column(String(100))  # comma separated tax code ids (inclusive)
    applies_film_rental: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SalesImportBatch(AuditColumnsMixin, Base):
    __tablename__ = "sales_import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(12))  # BOX_OFFICE | FNB
    filename: Mapped[str | None] = mapped_column(String(255))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="IMPORTED")


class BoxOfficeSale(AuditColumnsMixin, Base):
    """Summarised ticket sales per show x revenue type x payment method (POS export)."""
    __tablename__ = "box_office_sales"
    __table_args__ = (Index("ix_bos_site_date", "site_id", "business_date"),
                      CheckConstraint("gross_amount >= 0 AND discount_amount >= 0 AND refund_amount >= 0", name="non_negative"))
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    site_id: Mapped[int] = fk("sites.id", nullable=False, index=False)
    business_date: Mapped[date] = mapped_column(Date)
    show_id: Mapped[int | None] = fk("shows.id")
    screen_id: Mapped[int] = fk("screens.id", nullable=False)
    film_id: Mapped[int] = fk("films.id", nullable=False)
    revenue_type_id: Mapped[int] = fk("revenue_types.id", nullable=False)
    payment_method_id: Mapped[int] = fk("payment_methods.id", nullable=False)
    tickets_sold: Mapped[int] = mapped_column(Integer, default=0)
    complimentary_tickets: Mapped[int] = mapped_column(Integer, default=0)
    complimentary_value: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    refund_tickets: Mapped[int] = mapped_column(Integer, default=0)
    gross_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    refund_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    import_batch_id: Mapped[int | None] = fk("sales_import_batches.id")
    day_close_id: Mapped[int | None] = fk("day_closes.id")
    source_ref: Mapped[str | None] = mapped_column(String(80), index=True)
    # filled at day close (ex-tax values used by management reports and distributor settlements)
    net_revenue: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    film_rental_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    is_deferred: Mapped[bool] = mapped_column(Boolean, default=False)       # sold for a future show date
    released_day_close_id: Mapped[int | None] = fk("day_closes.id")           # day close that recognised it
    distributor_settlement_id: Mapped[int | None] = fk("distributor_settlements.id")

    @property
    def net_collected(self) -> Decimal:
        return self.gross_amount - self.discount_amount - self.refund_amount


class FnBSale(AuditColumnsMixin, Base):
    __tablename__ = "fnb_sales"
    __table_args__ = (Index("ix_fnb_site_date", "site_id", "business_date"),
                      CheckConstraint("gross_amount >= 0 AND discount_amount >= 0 AND refund_amount >= 0", name="non_negative"))
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    site_id: Mapped[int] = fk("sites.id", nullable=False, index=False)
    business_date: Mapped[date] = mapped_column(Date)
    revenue_type_id: Mapped[int] = fk("revenue_types.id", nullable=False)
    payment_method_id: Mapped[int] = fk("payment_methods.id", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    gross_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    refund_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    import_batch_id: Mapped[int | None] = fk("sales_import_batches.id")
    day_close_id: Mapped[int | None] = fk("day_closes.id")
    source_ref: Mapped[str | None] = mapped_column(String(80), index=True)
    net_revenue: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))

    @property
    def net_collected(self) -> Decimal:
        return self.gross_amount - self.discount_amount - self.refund_amount


class DayClose(AuditColumnsMixin, Base):
    __tablename__ = "day_closes"
    __table_args__ = (Index("ix_dayclose_site_date", "site_id", "business_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    site_id: Mapped[int] = fk("sites.id", nullable=False, index=False)
    business_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")  # DRAFT | POSTED | REVERSED
    ticket_gross: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    ticket_net_revenue: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    fnb_gross: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    fnb_net_revenue: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tax_total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    film_rental: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    cash_expected: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    cash_declared: Mapped[Decimal | None] = mapped_column(MONEY)
    cash_over_short: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    deferred_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    released_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    film_rental_journal_id: Mapped[int | None] = fk("journal_entries.id")
    notes: Mapped[str | None] = mapped_column(Text)


class CollectionBatch(Base):
    """Expected collection for one site / business date / payment method, tracked to settlement."""
    __tablename__ = "collection_batches"
    __table_args__ = (UniqueConstraint("day_close_id", "payment_method_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    site_id: Mapped[int] = fk("sites.id", nullable=False)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    payment_method_id: Mapped[int] = fk("payment_methods.id", nullable=False)
    day_close_id: Mapped[int] = fk("day_closes.id", nullable=False)
    expected_amount: Mapped[Decimal] = mapped_column(MONEY)
    settled_gross: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    fee_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tax_deducted: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    net_received: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(12), default="OPEN")  # OPEN | PARTIAL | SETTLED | DIFFERENCE

    @property
    def difference(self) -> Decimal:
        return self.expected_amount - self.settled_gross


class CollectionSettlement(AuditColumnsMixin, Base):
    __tablename__ = "collection_settlements"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    payment_method_id: Mapped[int] = fk("payment_methods.id", nullable=False)
    bank_account_id: Mapped[int] = fk("bank_accounts.id", nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date)
    gross_amount: Mapped[Decimal] = mapped_column(MONEY)
    fee_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tax_deducted: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(MONEY)
    reference: Mapped[str | None] = mapped_column(String(120))
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    status: Mapped[str] = mapped_column(String(12), default="POSTED")
    allocations: Mapped[list["CollectionAllocation"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class CollectionAllocation(Base):
    __tablename__ = "collection_allocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("collection_settlements.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[int] = fk("collection_batches.id", nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY)


class DistributorSettlement(AuditColumnsMixin, Base):
    __tablename__ = "distributor_settlements"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str | None] = mapped_column(String(60))
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    distributor_id: Mapped[int] = fk("suppliers.id", nullable=False)
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)
    net_box_office: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    accrued_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    adjustment: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")  # DRAFT | INVOICED | CANCELLED
    ap_document_id: Mapped[int | None] = fk("ap_documents.id")
    notes: Mapped[str | None] = mapped_column(Text)
    lines: Mapped[list["DistributorSettlementLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class DistributorSettlementLine(Base):
    __tablename__ = "distributor_settlement_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("distributor_settlements.id", ondelete="CASCADE"), index=True)
    film_id: Mapped[int] = fk("films.id", nullable=False)
    site_id: Mapped[int] = fk("sites.id", nullable=False)
    tickets: Mapped[int] = mapped_column(Integer, default=0)
    net_box_office: Mapped[Decimal] = mapped_column(MONEY)
    accrued_amount: Mapped[Decimal] = mapped_column(MONEY)
