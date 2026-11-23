"""Configurable approval workflow: definitions, approval limits, history."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import MONEY, Base, BigId, TimestampMixin, fk, utcnow


class WorkflowDefinition(TimestampMixin, Base):
    __tablename__ = "workflow_definitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    require_check: Mapped[bool] = mapped_column(Boolean, default=False)
    segregation_of_duties: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_post_on_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    require_attachment: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ApprovalLimit(TimestampMixin, Base):
    """Approver authority: doc type x (role or user) x optional site x maximum amount (NULL = unlimited)."""
    __tablename__ = "approval_limits"
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(30), index=True)
    role_id: Mapped[int | None] = fk("roles.id")
    user_id: Mapped[int | None] = fk("users.id")
    site_id: Mapped[int | None] = fk("sites.id")
    max_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkflowHistory(Base):
    __tablename__ = "workflow_history"
    __table_args__ = (Index("ix_wfh_doc", "doc_type", "doc_id"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    doc_type: Mapped[str] = mapped_column(String(30))
    doc_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    comment: Mapped[str | None] = mapped_column(Text)
