"""Month-end checklist."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, fk


class PeriodChecklistItem(Base):
    __tablename__ = "period_checklist_items"
    __table_args__ = (UniqueConstraint("period_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = fk("accounting_periods.id", nullable=False)
    code: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    is_auto: Mapped[bool] = mapped_column(Boolean, default=True)
    is_blocking: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(10), default="PENDING")  # PENDING | PASS | FAIL | DONE | WAIVED
    detail: Mapped[str | None] = mapped_column(Text)
    signed_off_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
