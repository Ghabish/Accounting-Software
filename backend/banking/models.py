"""Cash and bank: bank/cash accounts, vouchers, transfers, statements, reconciliation."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.accounting.models import DocStatus
from backend.database.base import MONEY, RATE, AuditColumnsMixin, Base, BigId, StrEnum, enum_col, fk, utcnow


class BankAccountKind(StrEnum):
    BANK = "BANK"
    CASH = "CASH"
    PETTY_CASH = "PETTY_CASH"


class BankAccount(AuditColumnsMixin, Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (UniqueConstraint("company_id", "code"), UniqueConstraint("gl_account_id", "site_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[BankAccountKind] = mapped_column(enum_col(BankAccountKind), default=BankAccountKind.BANK)
    bank_name: Mapped[str | None] = mapped_column(String(120))
    branch: Mapped[str | None] = mapped_column(String(120))
    account_number: Mapped[str | None] = mapped_column(String(40))
    iban: Mapped[str | None] = mapped_column(String(34))
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    gl_account_id: Mapped[int] = fk("accounts.id", nullable=False)
    site_id: Mapped[int | None] = fk("sites.id")
    imprest_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    is_default_payment: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class CashBankVoucher(AuditColumnsMixin, Base):
    """Receipts and payments that are not AP / AR documents (BPV, BRV, CPV, CRV)."""
    __tablename__ = "cash_bank_vouchers"
    __table_args__ = (UniqueConstraint("company_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    voucher_type: Mapped[str] = mapped_column(String(3))  # BPV | BRV | CPV | CRV
    number: Mapped[str] = mapped_column(String(30))
    bank_account_id: Mapped[int] = fk("bank_accounts.id", nullable=False)
    voucher_date: Mapped[date] = mapped_column(Date)
    counterparty: Mapped[str | None] = mapped_column(String(200))
    cheque_no: Mapped[str | None] = mapped_column(String(30))
    reference: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    gross_total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tax_total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    net_total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    status: Mapped[DocStatus] = mapped_column(enum_col(DocStatus), default=DocStatus.DRAFT, index=True)
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    lines: Mapped[list["CashBankVoucherLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin",
                                                              order_by="CashBankVoucherLine.line_no")


class CashBankVoucherLine(Base):
    __tablename__ = "cash_bank_voucher_lines"
    __table_args__ = (CheckConstraint("amount > 0", name="positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    voucher_id: Mapped[int] = mapped_column(ForeignKey("cash_bank_vouchers.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[int] = fk("accounts.id", nullable=False)
    site_id: Mapped[int | None] = fk("sites.id")
    cost_centre_id: Mapped[int | None] = fk("cost_centres.id")
    supplier_id: Mapped[int | None] = fk("suppliers.id")
    customer_id: Mapped[int | None] = fk("customers.id")
    employee_id: Mapped[int | None] = fk("employees.id")
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    tax_rate: Mapped[Decimal | None] = mapped_column(RATE)
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    dimensions: Mapped[dict | None] = mapped_column(JSON)


class BankTransfer(AuditColumnsMixin, Base):
    __tablename__ = "bank_transfers"
    __table_args__ = (UniqueConstraint("company_id", "number"), CheckConstraint("amount > 0", name="positive"),
                      CheckConstraint("from_account_id <> to_account_id", name="different_accounts"))
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    number: Mapped[str] = mapped_column(String(30))
    from_account_id: Mapped[int] = fk("bank_accounts.id", nullable=False)
    to_account_id: Mapped[int] = fk("bank_accounts.id", nullable=False)
    transfer_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    charges: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    via_transit: Mapped[bool] = mapped_column(Boolean, default=False)
    received_date: Mapped[date | None] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[DocStatus] = mapped_column(enum_col(DocStatus), default=DocStatus.DRAFT, index=True)
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    receive_journal_id: Mapped[int | None] = fk("journal_entries.id")


class BankStatement(AuditColumnsMixin, Base):
    __tablename__ = "bank_statements"
    id: Mapped[int] = mapped_column(primary_key=True)
    bank_account_id: Mapped[int] = fk("bank_accounts.id", nullable=False)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    opening_balance: Mapped[Decimal] = mapped_column(MONEY)
    closing_balance: Mapped[Decimal] = mapped_column(MONEY)
    filename: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(12), default="OPEN")  # OPEN | RECONCILED
    lines: Mapped[list["BankStatementLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin",
                                                            order_by="BankStatementLine.line_no")


class BankStatementLine(Base):
    __tablename__ = "bank_statement_lines"
    __table_args__ = (CheckConstraint("debit >= 0 AND credit >= 0 AND (debit = 0 OR credit = 0)", name="one_side"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("bank_statements.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    txn_date: Mapped[date] = mapped_column(Date)
    value_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(120))
    debit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))    # withdrawal
    credit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))   # deposit
    balance: Mapped[Decimal | None] = mapped_column(MONEY)
    matched_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(12), default="UNMATCHED")  # UNMATCHED | PARTIAL | MATCHED


class BankMatch(Base):
    __tablename__ = "bank_matches"
    __table_args__ = (Index("ix_bankmatch_jl", "journal_line_id"), CheckConstraint("amount > 0", name="positive"))
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    statement_line_id: Mapped[int] = mapped_column(ForeignKey("bank_statement_lines.id"), index=True)
    journal_line_id: Mapped[int] = mapped_column(ForeignKey("journal_lines.id"))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    match_type: Mapped[str] = mapped_column(String(10), default="MANUAL")  # AUTO | MANUAL
    matched_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    unmatched_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    unmatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciliation_id: Mapped[int | None] = fk("bank_reconciliations.id")


class BankReconciliation(AuditColumnsMixin, Base):
    __tablename__ = "bank_reconciliations"
    id: Mapped[int] = mapped_column(primary_key=True)
    bank_account_id: Mapped[int] = fk("bank_accounts.id", nullable=False)
    statement_id: Mapped[int | None] = fk("bank_statements.id")
    as_of_date: Mapped[date] = mapped_column(Date)
    statement_balance: Mapped[Decimal] = mapped_column(MONEY)
    gl_balance: Mapped[Decimal] = mapped_column(MONEY)
    outstanding_payments: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    deposits_in_transit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    unmatched_statement_debits: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    unmatched_statement_credits: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    difference: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")  # DRAFT | COMPLETED
    completed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict | None] = mapped_column(JSON)
