"""Accounts payable: suppliers, invoices / credit / debit notes, payments, allocations."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.accounting.models import DocStatus
from backend.database.base import MONEY, QTY, RATE, AuditColumnsMixin, Base, StrEnum, enum_col, fk


class SupplierType(StrEnum):
    COMPANY = "COMPANY"
    INDIVIDUAL = "INDIVIDUAL"
    AOP = "AOP"
    NON_RESIDENT = "NON_RESIDENT"


class APDocType(StrEnum):
    INVOICE = "INVOICE"
    CREDIT_NOTE = "CREDIT_NOTE"   # issued by the supplier - reduces payable
    DEBIT_NOTE = "DEBIT_NOTE"     # issued by us to the supplier - reduces payable


class PaymentStatus(StrEnum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"


class SupplierCategory(AuditColumnsMixin, Base):
    __tablename__ = "supplier_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    ap_control_account_id: Mapped[int] = fk("accounts.id", nullable=False)
    advance_account_id: Mapped[int | None] = fk("accounts.id")
    default_expense_account_id: Mapped[int | None] = fk("accounts.id")
    default_wht_tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    default_st_tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    default_stw_tax_code_id: Mapped[int | None] = fk("tax_codes.id")


class Supplier(AuditColumnsMixin, Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    beneficiary_name: Mapped[str | None] = mapped_column(String(200))
    category_id: Mapped[int] = fk("supplier_categories.id", nullable=False)
    supplier_type: Mapped[SupplierType] = mapped_column(enum_col(SupplierType), default=SupplierType.COMPANY)
    ntn: Mapped[str | None] = mapped_column(String(20), index=True)
    strn: Mapped[str | None] = mapped_column(String(20))
    cnic: Mapped[str | None] = mapped_column(String(20), index=True)
    atl_status: Mapped[str] = mapped_column(String(10), default="ATL")
    st_registered: Mapped[bool] = mapped_column(Boolean, default=True)
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(160))
    contact_person: Mapped[str | None] = mapped_column(String(120))
    bank_name: Mapped[str | None] = mapped_column(String(120))
    bank_account_title: Mapped[str | None] = mapped_column(String(160))
    bank_account_no: Mapped[str | None] = mapped_column(String(40))
    iban: Mapped[str | None] = mapped_column(String(34))
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    wht_tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    st_tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    stw_tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    wht_exemption_rate: Mapped[Decimal | None] = mapped_column(RATE)
    wht_exemption_until: Mapped[date | None] = mapped_column(Date)
    payment_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class APDocument(AuditColumnsMixin, Base):
    __tablename__ = "ap_documents"
    __table_args__ = (
        UniqueConstraint("company_id", "number"),
        Index("ix_apdoc_supplier", "supplier_id", "status"),
        CheckConstraint("total >= 0", name="total_non_negative"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    doc_type: Mapped[APDocType] = mapped_column(enum_col(APDocType), default=APDocType.INVOICE)
    number: Mapped[str] = mapped_column(String(30))
    supplier_id: Mapped[int] = fk("suppliers.id", nullable=False, index=False)
    supplier_invoice_no: Mapped[str] = mapped_column(String(60))
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
    related_document_id: Mapped[int | None] = fk("ap_documents.id")
    is_opening: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[str | None] = mapped_column(String(40))
    source_id: Mapped[int | None] = mapped_column(Integer)
    lines: Mapped[list["APDocumentLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin",
                                                         order_by="APDocumentLine.line_no")

    @property
    def outstanding(self) -> Decimal:
        return (self.total or Decimal("0")) - (self.amount_settled or Decimal("0"))


class APDocumentLine(Base):
    __tablename__ = "ap_document_lines"
    __table_args__ = (CheckConstraint("amount >= 0 AND st_amount >= 0", name="non_negative"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("ap_documents.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[int] = fk("accounts.id", nullable=False)
    site_id: Mapped[int | None] = fk("sites.id")
    cost_centre_id: Mapped[int | None] = fk("cost_centres.id")
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(QTY, default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    st_tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    st_rate: Mapped[Decimal | None] = mapped_column(RATE)
    st_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    dimensions: Mapped[dict | None] = mapped_column(JSON)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("fixed_assets.id", use_alter=True), nullable=True)


class APPayment(AuditColumnsMixin, Base):
    __tablename__ = "ap_payments"
    __table_args__ = (UniqueConstraint("company_id", "number"),
                      CheckConstraint("net_amount >= 0", name="net_non_negative"))
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    number: Mapped[str] = mapped_column(String(30))
    supplier_id: Mapped[int] = fk("suppliers.id", nullable=False)
    payment_date: Mapped[date] = mapped_column(Date)
    bank_account_id: Mapped[int] = fk("bank_accounts.id", nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), default="TRANSFER")
    cheque_no: Mapped[str | None] = mapped_column(String(30))
    reference: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    is_advance: Mapped[bool] = mapped_column(Boolean, default=False)
    site_id: Mapped[int | None] = fk("sites.id")
    gross_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    wht_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    stw_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    advance_unapplied: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    status: Mapped[DocStatus] = mapped_column(enum_col(DocStatus), default=DocStatus.DRAFT, index=True)
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    lines: Mapped[list["APPaymentLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin",
                                                        order_by="APPaymentLine.id")


class APPaymentLine(Base):
    __tablename__ = "ap_payment_lines"
    __table_args__ = (CheckConstraint("amount > 0", name="positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("ap_payments.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = fk("ap_documents.id")
    amount: Mapped[Decimal] = mapped_column(MONEY)  # gross amount settled
    wht_tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    wht_rate: Mapped[Decimal] = mapped_column(RATE, default=Decimal("0"))
    wht_base: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    wht_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    stw_tax_code_id: Mapped[int | None] = fk("tax_codes.id")
    stw_rate: Mapped[Decimal] = mapped_column(RATE, default=Decimal("0"))
    stw_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    rate_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text)


class APAllocation(AuditColumnsMixin, Base):
    """Settlement of an invoice by a payment, credit/debit note, or an advance."""
    __tablename__ = "ap_allocations"
    __table_args__ = (CheckConstraint("amount > 0", name="positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    invoice_id: Mapped[int] = fk("ap_documents.id", nullable=False)
    source_type: Mapped[str] = mapped_column(String(20))  # PAYMENT | CREDIT_NOTE | DEBIT_NOTE | ADVANCE
    payment_id: Mapped[int | None] = fk("ap_payments.id")
    credit_document_id: Mapped[int | None] = fk("ap_documents.id")
    amount: Mapped[Decimal] = mapped_column(MONEY)
    allocation_date: Mapped[date] = mapped_column(Date)
    journal_id: Mapped[int | None] = fk("journal_entries.id")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
