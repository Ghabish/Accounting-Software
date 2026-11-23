"""Shared filters for GL-based reports. All reports aggregate posted journal lines in SQL."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import and_, exists, select
from sqlalchemy.sql import Select

from backend.accounting.models import JournalLine, JournalLineDimension
from backend.core.actor import Actor


@dataclass
class LineFilter:
    company_id: int
    site_ids: list[int] | None = None
    cost_centre_ids: list[int] | None = None
    account_ids: list[int] | None = None
    supplier_id: int | None = None
    customer_id: int | None = None
    dimension_value_ids: list[int] = field(default_factory=list)
    exclude_sources: tuple[str, ...] = ()
    actor_sites: frozenset[int] | None = None

    @classmethod
    def build(cls, company_id: int, actor: Actor | None, site_ids=None, cost_centre_ids=None, account_ids=None,
              dimension_value_ids=None, supplier_id=None, customer_id=None, exclude_sources=()) -> "LineFilter":
        return cls(company_id=company_id, site_ids=_ids(site_ids), cost_centre_ids=_ids(cost_centre_ids),
                   account_ids=_ids(account_ids), dimension_value_ids=_ids(dimension_value_ids) or [],
                   supplier_id=supplier_id, customer_id=customer_id, exclude_sources=tuple(exclude_sources),
                   actor_sites=actor.site_ids if actor else None)

    def apply(self, stmt: Select, *, date_from: date | None = None, date_to: date | None = None,
              before: date | None = None) -> Select:
        L = JournalLine
        stmt = stmt.where(L.is_posted.is_(True), L.company_id == self.company_id)
        if date_from:
            stmt = stmt.where(L.posting_date >= date_from)
        if date_to:
            stmt = stmt.where(L.posting_date <= date_to)
        if before:
            stmt = stmt.where(L.posting_date < before)
        if self.site_ids:
            stmt = stmt.where(L.site_id.in_(self.site_ids))
        if self.actor_sites is not None:
            stmt = stmt.where(L.site_id.in_(self.actor_sites))
        if self.cost_centre_ids:
            stmt = stmt.where(L.cost_centre_id.in_(self.cost_centre_ids))
        if self.account_ids:
            stmt = stmt.where(L.account_id.in_(self.account_ids))
        if self.supplier_id:
            stmt = stmt.where(L.supplier_id == self.supplier_id)
        if self.customer_id:
            stmt = stmt.where(L.customer_id == self.customer_id)
        for dv in self.dimension_value_ids:
            stmt = stmt.where(exists().where(and_(JournalLineDimension.journal_line_id == L.id,
                                                  JournalLineDimension.dimension_value_id == dv)))
        if self.exclude_sources:
            stmt = stmt.where(L.source_module.not_in(self.exclude_sources))
        return stmt


def _ids(v) -> list[int] | None:
    if v is None or v == "":
        return None
    if isinstance(v, (list, tuple, set)):
        return [int(x) for x in v if x not in (None, "")] or None
    return [int(x) for x in str(v).split(",") if x.strip()] or None


def balances_by_account(db, flt: LineFilter, **date_kw) -> dict[int, tuple]:
    """account_id -> (debit, credit) for the filtered posted lines."""
    from sqlalchemy import func
    L = JournalLine
    stmt = flt.apply(select(L.account_id, func.coalesce(func.sum(L.debit), 0), func.coalesce(func.sum(L.credit), 0)),
                     **date_kw).group_by(L.account_id)
    from decimal import Decimal
    return {aid: (Decimal(dr), Decimal(cr)) for aid, dr, cr in db.execute(stmt).all()}
