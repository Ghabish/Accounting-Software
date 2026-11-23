from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

T = TypeVar("T")

MAX_PAGE_SIZE = 500


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


def paginate(db: Session, stmt: Select, page: int = 1, page_size: int = 50) -> tuple[list[Any], int]:
    page = max(page, 1)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).all()
    return list(rows), int(total)
