"""Tax framework: tax codes, effective-dated rates, slabs, tax transactions."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import MONEY, RATE, AuditColumnsMixin, Base, BigId, StrEnum, enum_col, fk


class TaxType(StrEnum):
    SALES_TAX_OUTPUT = "SALES_TAX_OUTPUT"      # charged to customers (FBR goods)
    PST_OUTPUT = "PST_OUTPUT"                  # provincial sales tax on services charged
    ENTERTAINMENT_DUTY = "ENTERTAINMENT_DUTY"  # levy on admissions (if applicable)
    SALES_TAX_INPUT = "SALES_TAX_INPUT"        # charged by suppliers (FBR)
    PST_INPUT = "PST_INPUT"                    # provincial sales tax on services charged by suppliers
    WHT_DEDUCTED = "WHT_DEDUCTED"              # income tax withheld from suppliers / employees (payable)
    ST_WITHHELD = "ST_WITHHELD"                # sales tax withheld from suppliers (payable)
    WHT_SUFFERED = "WHT_SUFFERED"              # tax deducted by customers / banks (refundable)
    ADVANCE_TAX = "ADVANCE_TAX"                # advance tax collected on utility bills etc.


class TaxBase(StrEnum):
    NET_AMOUNT = "NET_AMOUNT"              # value excluding sales tax
    GROSS_AMOUNT = "GROSS_AMOUNT"          # value including sales tax
    SALES_TAX_AMOUNT = "SALES_TAX_AMOUNT"  # sales tax withholding: fraction of the tax


class TaxCode(AuditColumnsMixin, Base):
    __tablename__ = "tax_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    tax_type: Mapped[TaxType] = mapped_column(enum_col(TaxType))
    authority: Mapped[str] = mapped_column(String(20))
    law_section: Mapped[str | None] = mapped_column(String(120))
    base: Mapped[TaxBase] = mapped_column(enum_col(TaxBase), default=TaxBase.NET_AMOUNT)
    account_id: Mapped[int] = fk("accounts.id", nullable=False)
    is_recoverable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_inclusive_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class TaxRate(AuditColumnsMixin, Base):
    """Rate for a tax code, selected by payee type, ATL status, effective date and optionally site."""
    __tablename__ = "tax_rates"
    __table_args__ = (Index("ix_taxrate_lookup", "tax_code_id", "effective_from"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tax_code_id: Mapped[int] = fk("tax_codes.id", nullable=False, index=False)
    name: Mapped[str] = mapped_column(String(120))
    payee_type: Mapped[str] = mapped_column(String(20), default="ALL")   # ALL | COMPANY | INDIVIDUAL | AOP | NON_RESIDENT
    atl_status: Mapped[str] = mapped_column(String(10), default="ALL")   # ALL | ATL | NON_ATL
    rate: Mapped[Decimal] = mapped_column(RATE)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    site_id: Mapped[int | None] = fk("sites.id")
    transaction_type: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source_ref: Mapped[str | None] = mapped_column(String(160))


class TaxSlab(Base):
    __tablename__ = "tax_slabs"
    id: Mapped[int] = mapped_column(primary_key=True)
    tax_code_id: Mapped[int] = fk("tax_codes.id", nullable=False)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    amount_from: Mapped[Decimal] = mapped_column(MONEY)
    amount_to: Mapped[Decimal | None] = mapped_column(MONEY)
    fixed_tax: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    rate: Mapped[Decimal] = mapped_column(RATE)


class TaxTransaction(Base):
    """One row per tax effect posted to the GL (input, output, withheld, suffered)."""
    __tablename__ = "tax_transactions"
    __table_args__ = (Index("ix_taxtxn_code_date", "tax_code_id", "transaction_date"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    tax_code_id: Mapped[int] = fk("tax_codes.id", nullable=False, index=False)
    tax_rate_id: Mapped[int | None] = fk("tax_rates.id")
    journal_id: Mapped[int] = fk("journal_entries.id", nullable=False)
    journal_line_id: Mapped[int | None] = mapped_column(ForeignKey("journal_lines.id"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[int | None] = mapped_column(Integer)
    transaction_date: Mapped[date] = mapped_column(Date)
    period_id: Mapped[int | None] = fk("accounting_periods.id")
    direction: Mapped[str] = mapped_column(String(10))  # OUTPUT | INPUT | WITHHELD | SUFFERED
    supplier_id: Mapped[int | None] = fk("suppliers.id")
    customer_id: Mapped[int | None] = fk("customers.id")
    site_id: Mapped[int | None] = fk("sites.id")
    party_ntn: Mapped[str | None] = mapped_column(String(20))
    party_name: Mapped[str | None] = mapped_column(String(200))
    document_ref: Mapped[str | None] = mapped_column(String(120))
    base_amount: Mapped[Decimal] = mapped_column(MONEY)
    rate: Mapped[Decimal] = mapped_column(RATE)
    tax_amount: Mapped[Decimal] = mapped_column(MONEY)
    rate_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text)
    is_reversal: Mapped[bool] = mapped_column(Boolean, default=False)
    deposited: Mapped[bool] = mapped_column(Boolean, default=False)
    deposit_reference: Mapped[str | None] = mapped_column(String(60))
    deposit_date: Mapped[date | None] = mapped_column(Date)
