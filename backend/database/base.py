"""Declarative base, naming conventions and common column helpers."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, MetaData, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# BigInteger that still autoincrements on SQLite (used by tests / dev).
BigId = BigInteger().with_variant(Integer(), "sqlite")

MONEY = Numeric(18, 2)
RATE = Numeric(9, 6)
QTY = Numeric(18, 3)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {Decimal: MONEY, datetime: DateTime(timezone=True)}


def enum_col(enum_cls: type[enum.Enum], **kw):
    """Store a str-Enum as VARCHAR with a CHECK constraint (portable)."""
    return Enum(enum_cls, native_enum=False, create_constraint=True, length=32,
                values_callable=lambda e: [m.value for m in e], validate_strings=True, **kw)


def fk(target: str, *, nullable: bool = True, index: bool = True, ondelete: str = "RESTRICT"):
    return mapped_column(ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index)


def code_col(length: int = 32, **kw):
    return mapped_column(String(length), **kw)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditColumnsMixin(TimestampMixin):
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


class StrEnum(str, enum.Enum):
    def __str__(self) -> str:  # pragma: no cover
        return self.value
