"""Accounts receivable: customers, invoices / credit / debit notes, receipts, allocations."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.accounting.models import DocStatus
from backend.ap.models import PaymentStatus
from backend.database.base import MONEY, QTY, RATE, AuditColumnsMixin, Base, StrEnum, enum_col, fk


class ARDocType(StrEnum):
    INVOICE = "INVOICE"
    DEBIT_NOTE = "DEBIT_NOTE"    # increases receivable
    CREDIT_NOTE = "CREDIT_NOTE"  # reduces receivable


class CustomerCategory(AuditColumnsMixin, Base):
    __tablename__ = "customer_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    ar_control_account_id: Mapped[int] = fk("accounts.id", nullable=False)
    advance_account_id: Mapped[int | None] = fk("accounts.id")
    default_revenue_account_id: Mapped[int | None] = fk("accounts.id")
    default_output_tax_code_id: Mapped[int | None] = fk("tax_codes.id")


class Customer(AuditColumnsMixin, Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category_id: Mapped[int] = fk("customer_categories.id", nullable=False)
    customer_type: Mapped[str] = mapped_column(String(20), default="COMPANY")
    ntn: Mapped[str | None] = mapped_column(String(20), index=True)
    strn: Mapped[str | None] = mapped_column(String(20))
    cnic: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(160))
    contact_person: Mapped[str | None] = mapped_column(String(120))
    credit_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    wht_tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class ARDocument(AuditColumnsMixin, Base):
    __tablename__ = "ar_documents"
    __table_args__ = (UniqueConstraint("company_id", "number"), Index("ix_ardoc_customer", "customer_id", "status"),
                      CheckConstraint("total >= 0", name="total_non_negative"))
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    doc_type: Mapped[ARDocType] = mapped_column(enum_col(ARDocType), default=ARDocType.INVOICE)
    number: Mapped[str] = mapped_column(String(30))
    customer_id: Mapped[int] = fk("customers.id", nullable=False, index=False)
    customer_reference: Mapped[str | None] = mapped_column(String(60))
    invoice_date: Mapped[date] = mapped_column(Date)
    posting_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    site_id: Mapped[int | None] = fk("sites.id")
    description: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    subtotal: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tax_total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    amount_settled: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    payment_status: Mapped[PaymentStatus] = mapped_column(enum_col(PaymentStatus), default=PaymentStatus.UNPAID)
    status: Mapped[DocStatus] = mapped_column(enum_col(DocStatus), default=DocStatus.DRAFT, index=True)
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    related_document_id: Mapped[int | None] = fk("ar_documents.id")
    is_opening: Mapped[bool] = mapped_column(Boolean, default=False)
    lines: Mapped[list["ARDocumentLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin",
                                                         order_by="ARDocumentLine.line_no")

    @property
    def outstanding(self) -> Decimal:
        return (self.total or Decimal("0")) - (self.amount_settled or Decimal("0"))


class ARDocumentLine(Base):
    __tablename__ = "ar_document_lines"
    __table_args__ = (CheckConstraint("amount >= 0 AND tax_amount >= 0", name="non_negative"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("ar_documents.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[int] = fk("accounts.id", nullable=False)
    site_id: Mapped[int | None] = fk("sites.id")
    cost_centre_id: Mapped[int | None] = fk("cost_centres.id")
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(QTY, default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    tax_rate: Mapped[Decimal | None] = mapped_column(RATE)
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    dimensions: Mapped[dict | None] = mapped_column(JSON)


class ARReceipt(AuditColumnsMixin, Base):
    __tablename__ = "ar_receipts"
    __table_args__ = (UniqueConstraint("company_id", "number"),
                      CheckConstraint("amount_received >= 0 AND tax_deducted >= 0", name="non_negative"))
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    number: Mapped[str] = mapped_column(String(30))
    customer_id: Mapped[int] = fk("customers.id", nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date)
    bank_account_id: Mapped[int] = fk("bank_accounts.id", nullable=False)
    receipt_method: Mapped[str] = mapped_column(String(20), default="TRANSFER")
    reference: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    is_advance: Mapped[bool] = mapped_column(Boolean, default=False)
    site_id: Mapped[int | None] = fk("sites.id")
    amount_received: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tax_deducted: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    wht_tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    gross_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    unapplied_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    status: Mapped[DocStatus] = mapped_column(enum_col(DocStatus), default=DocStatus.DRAFT, index=True)
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    lines: Mapped[list["ARReceiptLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin",
                                                        order_by="ARReceiptLine.id")


class ARReceiptLine(Base):
    __tablename__ = "ar_receipt_lines"
    __table_args__ = (CheckConstraint("amount > 0", name="positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("ar_receipts.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = fk("ar_documents.id", nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY)


class ARAllocation(AuditColumnsMixin, Base):
    __tablename__ = "ar_allocations"
    __table_args__ = (CheckConstraint("amount > 0", name="positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    invoice_id: Mapped[int] = fk("ar_documents.id", nullable=False)
    source_type: Mapped[str] = mapped_column(String(20))  # RECEIPT | CREDIT_NOTE | ADVANCE
    receipt_id: Mapped[int | None] = fk("ar_receipts.id")
    credit_document_id: Mapped[int | None] = fk("ar_documents.id")
    amount: Mapped[Decimal] = mapped_column(MONEY)
    allocation_date: Mapped[date] = mapped_column(Date)
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
