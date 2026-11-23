from __future__ import annotations

from functools import lru_cache

from sqlalchemy import select

from backend.accounting.models import Account
from backend.database.session import SessionLocal
from backend.masters.models import CostCentre, Site


def _lookup(model, code):
    with SessionLocal() as db:
        obj = db.scalar(select(model).where(model.code == code))
        assert obj is not None, f"{model.__name__} {code} missing"
        return obj.id


def acc(code: str) -> int:
    return _lookup(Account, code)


def site(code: str) -> int:
    return _lookup(Site, code)


def cc(code: str) -> int:
    return _lookup(CostCentre, code)


def lookup(model, **kw) -> int:
    with SessionLocal() as db:
        obj = db.scalar(select(model).filter_by(**kw))
        assert obj is not None, f"{model.__name__} {kw} missing"
        return obj.id


def run_workflow(client, H, base: str, doc_id: int, steps: list[tuple[str, str]]):
    """steps: [(action, user)]; returns last response json."""
    r = None
    for action, user in steps:
        r = client.post(f"{base}/{doc_id}/{action}", headers=H[user], json={"comment": f"{action} by {user}"})
        assert r.status_code == 200, f"{action} by {user}: {r.text}"
    return r.json() if r is not None else None


def journal(client, H, user, lines, date="2026-07-15", description="Test journal", **kw):
    body = {"transaction_date": date, "description": description, "lines": lines, **kw}
    return client.post("/api/journals", headers=H[user], json=body)


def post_journal(client, H, lines, date="2026-07-15", description="Test journal", **kw) -> dict:
    """Accountant prepares and checks, FM approves, CFO posts (segregation of duties)."""
    r = journal(client, H, "accountant", lines, date, description, **kw)
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    client.post(f"/api/journals/{jid}/submit", headers=H["accountant"], json={})
    for action, user in (("check", "fm"), ("approve", "cfo"), ("post", "fm")):
        r = client.post(f"/api/journals/{jid}/{action}", headers=H[user], json={})
        assert r.status_code == 200, f"{action}: {r.text}"
    return r.json()
