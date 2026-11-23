"""Core accounting entities: chart of accounts, periods, journals."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import MONEY, RATE, AuditColumnsMixin, Base, BigId, StrEnum, enum_col, fk, utcnow


# ---------------------------------------------------------------- enums
class AccountType(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class ControlType(StrEnum):
    NONE = "NONE"
    AP_CONTROL = "AP_CONTROL"
    AR_CONTROL = "AR_CONTROL"
    BANK = "BANK"
    CASH = "CASH"
    CLEARING = "CLEARING"
    TAX = "TAX"
    REGISTER = "REGISTER"


class PartyType(StrEnum):
    NONE = "NONE"
    SUPPLIER = "SUPPLIER"
    CUSTOMER = "CUSTOMER"
    EMPLOYEE = "EMPLOYEE"


class Rule(StrEnum):
    REQ = "REQ"
    OPT = "OPT"
    NONE = "NONE"


class CostCentreRule(StrEnum):
    BS = "BS"      # no cost centre (balance sheet)
    LOC = "LOC"    # optional, any active cost centre except company level
    REQ = "REQ"    # mandatory, any active P&L cost centre (not 000000)
    CORP = "CORP"  # must be the company-level cost centre 090101


class ManualJournal(StrEnum):
    ALLOWED = "ALLOWED"
    RESTRICTED = "RESTRICTED"
    NOT_ALLOWED = "NOT_ALLOWED"


class AbnormalBalance(StrEnum):
    BLOCK = "BLOCK"
    ALERT = "ALERT"
    ALLOW = "ALLOW"


class BudgetControl(StrEnum):
    NONE = "NONE"
    ADVISORY = "ADVISORY"
    ABSOLUTE = "ABSOLUTE"


class PeriodStatus(StrEnum):
    OPEN = "OPEN"
    SOFT_CLOSED = "SOFT_CLOSED"
    CLOSED = "CLOSED"
    LOCKED = "LOCKED"


class DocStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    CHECKED = "CHECKED"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    REVERSED = "REVERSED"
    CANCELLED = "CANCELLED"


class JournalType(StrEnum):
    JV = "JV"     # manual journal voucher
    API = "API"   # AP invoice
    APC = "APC"   # AP credit / debit note
    APP = "APP"   # AP payment
    APA = "APA"   # AP advance application
    ARI = "ARI"   # AR invoice / debit note
    ARC = "ARC"   # AR credit note
    ARR = "ARR"   # AR receipt
    ARA = "ARA"   # AR advance application
    BPV = "BPV"   # bank payment voucher (non-AP)
    BRV = "BRV"   # bank receipt voucher (non-AR)
    CPV = "CPV"   # cash payment voucher
    CRV = "CRV"   # cash receipt voucher
    TRF = "TRF"   # bank / cash transfer
    BRA = "BRA"   # bank reconciliation adjustment
    DEP = "DEP"   # depreciation run
    FAT = "FAT"   # fixed asset transaction (capitalisation, transfer, disposal, impairment)
    DCL = "DCL"   # cinema day close
    STL = "STL"   # collection settlement (card / gateway / wallet)
    FRA = "FRA"   # film rental accrual
    OBV = "OBV"   # opening balance voucher
    YEC = "YEC"   # year-end close
    REC = "REC"   # recurring journal


class SourceModule(StrEnum):
    MANUAL = "MANUAL"
    AP = "AP"
    AR = "AR"
    BANK = "BANK"
    ASSETS = "ASSETS"
    CINEMA = "CINEMA"
    TAX = "TAX"
    OPENING = "OPENING"
    CLOSING = "CLOSING"
    RECURRING = "RECURRING"


# ---------------------------------------------------------------- accounts
class Account(AuditColumnsMixin, Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(13), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    level: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[int | None] = fk("accounts.id")
    account_type: Mapped[AccountType] = mapped_column(enum_col(AccountType))
    normal_balance: Mapped[str] = mapped_column(String(1), default="D")
    is_postable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_contra: Mapped[bool] = mapped_column(Boolean, default=False)
    control_type: Mapped[ControlType] = mapped_column(enum_col(ControlType), default=ControlType.NONE)
    party_type: Mapped[PartyType] = mapped_column(enum_col(PartyType), default=PartyType.NONE)
    party_rule: Mapped[Rule] = mapped_column(enum_col(Rule, name="party_rule"), default=Rule.NONE)
    site_rule: Mapped[Rule] = mapped_column(enum_col(Rule, name="site_rule"), default=Rule.OPT)
    cost_centre_rule: Mapped[CostCentreRule] = mapped_column(enum_col(CostCentreRule), default=CostCentreRule.BS)
    pl_section: Mapped[str | None] = mapped_column(String(20), index=True)
    revenue_stream: Mapped[str | None] = mapped_column(String(20))
    cash_flow_line: Mapped[str | None] = mapped_column(String(30))
    cf_adjustment: Mapped[str | None] = mapped_column(String(30))
    cf_counter_line: Mapped[str | None] = mapped_column(String(30))
    manual_journal: Mapped[ManualJournal] = mapped_column(enum_col(ManualJournal), default=ManualJournal.ALLOWED)
    abnormal_balance: Mapped[AbnormalBalance] = mapped_column(enum_col(AbnormalBalance), default=AbnormalBalance.ALERT)
    reconcile_required: Mapped[bool] = mapped_column(Boolean, default=False)
    budget_control: Mapped[BudgetControl] = mapped_column(enum_col(BudgetControl), default=BudgetControl.NONE)
    is_intercompany: Mapped[bool] = mapped_column(Boolean, default=False)
    zero_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_attachment: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    gen_ref: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)

    @property
    def sign(self) -> int:
        """+1 for debit-normal, -1 for credit-normal (reporting sign multiplier)."""
        return 1 if self.normal_balance == "D" else -1


# ---------------------------------------------------------------- periods
class FiscalYear(AuditColumnsMixin, Base):
    __tablename__ = "fiscal_years"
    __table_args__ = (UniqueConstraint("company_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    code: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="OPEN")
    closing_journal_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id", use_alter=True), nullable=True)


class AccountingPeriod(AuditColumnsMixin, Base):
    __tablename__ = "accounting_periods"
    __table_args__ = (UniqueConstraint("company_id", "start_date"), CheckConstraint("end_date >= start_date", name="dates"))
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    fiscal_year_id: Mapped[int] = fk("fiscal_years.id", nullable=False)
    period_no: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[PeriodStatus] = mapped_column(enum_col(PeriodStatus), default=PeriodStatus.OPEN)
    status_changed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NumberSequence(Base):
    __tablename__ = "number_sequences"
    __table_args__ = (UniqueConstraint("company_id", "seq_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    seq_key: Mapped[str] = mapped_column(String(40))
    prefix: Mapped[str] = mapped_column(String(30))
    next_value: Mapped[int] = mapped_column(Integer, default=1)
    padding: Mapped[int] = mapped_column(Integer, default=6)


# ---------------------------------------------------------------- journals
class JournalEntry(AuditColumnsMixin, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("company_id", "number"),
        UniqueConstraint("source_key"),
        Index("ix_journal_status_date", "company_id", "status", "posting_date"),
        CheckConstraint("total_debit >= 0 AND total_credit >= 0", name="totals_non_negative"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    journal_type: Mapped[JournalType] = mapped_column(enum_col(JournalType), index=True)
    number: Mapped[str | None] = mapped_column(String(40))
    transaction_date: Mapped[date] = mapped_column(Date)
    posting_date: Mapped[date] = mapped_column(Date)
    period_id: Mapped[int | None] = fk("accounting_periods.id")
    description: Mapped[str] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(120), index=True)
    source_module: Mapped[SourceModule] = mapped_column(enum_col(SourceModule), default=SourceModule.MANUAL)
    source_type: Mapped[str | None] = mapped_column(String(40))
    source_id: Mapped[int | None] = mapped_column(Integer)
    source_key: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[DocStatus] = mapped_column(enum_col(DocStatus), default=DocStatus.DRAFT, index=True)
    total_debit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    total_credit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_accrual: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_reverse_date: Mapped[date | None] = mapped_column(Date)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_of_id: Mapped[int | None] = fk("journal_entries.id")
    reversal_reason: Mapped[str | None] = mapped_column(Text)
    recurring_journal_id: Mapped[int | None] = fk("recurring_journals.id")
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="journal", cascade="all, delete-orphan", order_by="JournalLine.line_no")

    __mapper_args__ = {"version_id_col": version}


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0", name="non_negative"),
        CheckConstraint("(debit = 0 OR credit = 0)", name="one_side"),
        CheckConstraint("debit + credit > 0", name="non_zero"),
        CheckConstraint(
            "(CASE WHEN supplier_id IS NULL THEN 0 ELSE 1 END + CASE WHEN customer_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN employee_id IS NULL THEN 0 ELSE 1 END) <= 1", name="one_party"),
        Index("ix_jl_posted_account_date", "company_id", "account_id", "posting_date", postgresql_where=text("is_posted")),
        Index("ix_jl_posted_period", "period_id", "account_id"),
        Index("ix_jl_site_account", "site_id", "account_id"),
        Index("ix_jl_cc_account", "cost_centre_id", "account_id"),
        Index("ix_jl_supplier", "supplier_id"),
        Index("ix_jl_customer", "customer_id"),
    )
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[int] = fk("accounts.id", nullable=False, index=False)
    site_id: Mapped[int | None] = fk("sites.id", index=False)
    cost_centre_id: Mapped[int | None] = fk("cost_centres.id", index=False)
    supplier_id: Mapped[int | None] = fk("suppliers.id", index=False)
    customer_id: Mapped[int | None] = fk("customers.id", index=False)
    employee_id: Mapped[int | None] = fk("employees.id")
    partner_company_id: Mapped[int | None] = fk("companies.id")
    description: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(120))
    debit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1"))
    amount_fc: Mapped[Decimal | None] = mapped_column(MONEY)
    tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    tax_base: Mapped[Decimal | None] = mapped_column(MONEY)
    tax_rate: Mapped[Decimal | None] = mapped_column(RATE)
    # Denormalised at posting for fast reporting
    company_id: Mapped[int | None] = fk("companies.id", index=False)
    posting_date: Mapped[date | None] = mapped_column(Date)
    period_id: Mapped[int | None] = fk("accounting_periods.id", index=False)
    is_posted: Mapped[bool] = mapped_column(Boolean, default=False)
    source_module: Mapped[str | None] = mapped_column(String(20))

    journal: Mapped[JournalEntry] = relationship(back_populates="lines")
    dimensions: Mapped[list["JournalLineDimension"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")

    @property
    def net(self) -> Decimal:
        return (self.debit or Decimal("0")) - (self.credit or Decimal("0"))


class JournalLineDimension(Base):
    __tablename__ = "journal_line_dimensions"
    __table_args__ = (UniqueConstraint("journal_line_id", "dimension_type_id"),
                      Index("ix_jld_value", "dimension_value_id"))
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    journal_line_id: Mapped[int] = mapped_column(ForeignKey("journal_lines.id", ondelete="CASCADE"), index=True)
    dimension_type_id: Mapped[int] = fk("dimension_types.id", nullable=False, index=False)
    dimension_value_id: Mapped[int] = fk("dimension_values.id", nullable=False, index=False)


class RecurringJournal(AuditColumnsMixin, Base):
    __tablename__ = "recurring_journals"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(String(10), default="MONTHLY")  # MONTHLY | QUARTERLY | YEARLY
    next_run_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    auto_submit: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lines: Mapped[list["RecurringJournalLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin",
                                                                order_by="RecurringJournalLine.line_no")


class RecurringJournalLine(Base):
    __tablename__ = "recurring_journal_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    recurring_journal_id: Mapped[int] = mapped_column(ForeignKey("recurring_journals.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[int] = fk("accounts.id", nullable=False)
    site_id: Mapped[int | None] = fk("sites.id")
    cost_centre_id: Mapped[int | None] = fk("cost_centres.id")
    supplier_id: Mapped[int | None] = fk("suppliers.id")
    customer_id: Mapped[int | None] = fk("customers.id")
    employee_id: Mapped[int | None] = fk("employees.id")
    description: Mapped[str | None] = mapped_column(Text)
    debit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    dimensions: Mapped[dict | None] = mapped_column(Text)  # JSON {"FILM": value_id}


class PeriodStatusLog(Base):
    __tablename__ = "period_status_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = fk("accounting_periods.id", nullable=False)
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reason: Mapped[str | None] = mapped_column(Text)
