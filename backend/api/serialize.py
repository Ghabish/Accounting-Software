"""Small helpers to turn ORM rows into JSON-safe dicts (Decimal -> str, dates -> ISO)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable

from sqlalchemy import inspect


def jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def row(obj: Any, exclude: Iterable[str] = ("password_hash",), extra: dict | None = None) -> dict:
    if obj is None:
        return None  # type: ignore[return-value]
    mapper = inspect(obj).mapper
    out = {c.key: jsonable(getattr(obj, c.key)) for c in mapper.column_attrs if c.key not in exclude}
    if extra:
        out.update({k: jsonable(v) for k, v in extra.items()})
    return out


def rows(objs: Iterable[Any], **kw) -> list[dict]:
    return [row(o, **kw) for o in objs]


def page(items: list, total: int, page_no: int, page_size: int) -> dict:
    return {"items": items, "total": total, "page": page_no, "page_size": page_size}


def line_rows(db, lines) -> list[dict]:
    """Document lines with account code / name, site and cost-centre codes for display."""
    from backend.accounting.models import Account
    from backend.masters.models import CostCentre, Site
    out = []
    for l in lines:
        acc = db.get(Account, l.account_id) if getattr(l, "account_id", None) else None
        site = db.get(Site, l.site_id) if getattr(l, "site_id", None) else None
        cc = db.get(CostCentre, l.cost_centre_id) if getattr(l, "cost_centre_id", None) else None
        out.append(row(l, extra={"account_code": acc.code if acc else None, "account_name": acc.name if acc else None,
                                 "site_code": site.code if site else None, "cost_centre_code": cc.code if cc else None}))
    return out
