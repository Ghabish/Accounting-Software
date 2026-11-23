"""Budgets with versions (revisions keep history)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import MONEY, AuditColumnsMixin, Base, fk


class Budget(AuditColumnsMixin, Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = fk("companies.id", nullable=False)
    fiscal_year_id: Mapped[int] = fk("fiscal_years.id", nullable=False)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    active_version_id: Mapped[int | None] = mapped_column(ForeignKey("budget_versions.id", use_alter=True), nullable=True)


class BudgetVersion(AuditColumnsMixin, Base):
    __tablename__ = "budget_versions"
    __table_args__ = (UniqueConstraint("budget_id", "version_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    budget_id: Mapped[int] = fk("budgets.id", nullable=False)
    version_no: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")  # DRAFT | APPROVED | SUPERSEDED
    reason: Mapped[str | None] = mapped_column(Text)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lines: Mapped[list["BudgetLine"]] = relationship(cascade="all, delete-orphan", lazy="noload")


class BudgetLine(Base):
    __tablename__ = "budget_lines"
    __table_args__ = (
        UniqueConstraint("version_id", "account_id", "site_id", "cost_centre_id", "dimension_value_id", "period_id",
                         name="uq_budget_line_key"),
        Index("ix_budget_line_lookup", "version_id", "period_id", "account_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("budget_versions.id", ondelete="CASCADE"))
    account_id: Mapped[int] = fk("accounts.id", nullable=False, index=False)
    site_id: Mapped[int | None] = fk("sites.id", index=False)
    cost_centre_id: Mapped[int | None] = fk("cost_centres.id", index=False)
    dimension_value_id: Mapped[int | None] = fk("dimension_values.id", index=False)
    period_id: Mapped[int] = fk("accounting_periods.id", nullable=False, index=False)
    amount: Mapped[Decimal] = mapped_column(MONEY)
