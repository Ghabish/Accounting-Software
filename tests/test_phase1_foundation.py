"""Phase 1: chart, masters, authentication, RBAC, site restriction, periods, audit."""
from __future__ import annotations

from sqlalchemy import select

from backend.accounting.models import Account, AccountingPeriod, PeriodStatus
from backend.audit.models import AuditLog
from backend.database.seed.coa_data import build_chart


def test_chart_seeded_with_hierarchy(db):
    ledgers = db.scalars(select(Account).where(Account.level == 4)).all()
    assert len(ledgers) == len([r for r in build_chart() if r["level"] == 4]) == 295
    for a in ledgers:
        parent = db.get(Account, a.parent_id)
        assert parent.level == 3 and a.code.startswith(parent.code)
        assert a.is_postable
    # contra accounts have opposite normal balance
    acc_dep = db.scalar(select(Account).where(Account.code == "01-01-01-0007"))
    assert acc_dep.is_contra and acc_dep.normal_balance == "C"
    assert db.scalar(select(Account).where(Account.code == "04-01-02-0001")).normal_balance == "D"


def test_login_and_profile(client, H):
    r = client.get("/api/auth/me", headers=H["cfo"])
    assert r.status_code == 200
    me = r.json()
    assert "CFO" in me["roles"] and "journal.approve" in me["permissions"] and me["all_sites"]


def test_bad_password_and_lockout(client):
    for _ in range(5):
        r = client.post("/api/auth/login", json={"username": "auditor", "password": "wrong-password"})
        assert r.status_code == 401
    r = client.post("/api/auth/login", json={"username": "auditor", "password": "Demo@2026pass"})
    assert r.status_code == 401 and r.json()["error"] == "account_locked"


def test_unauthenticated_rejected(client):
    assert client.get("/api/accounts").status_code == 401
    assert client.get("/api/accounts", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_rbac_denies_without_permission(client, H):
    # AP officer cannot manage the chart of accounts or users
    r = client.post("/api/accounts", headers=H["ap"], json={"parent_code": "06-06-06", "name": "Test expense"})
    assert r.status_code == 403
    assert client.get("/api/admin/users", headers=H["ap"]).status_code == 403
    # admin can list users
    assert client.get("/api/admin/users", headers=H["admin"]).status_code == 200


def test_create_account_next_free_code_and_unique_name(client, H):
    r = client.post("/api/accounts", headers=H["cfo"], json={"parent_code": "06-06-06", "name": "Cinema hall decoration"})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["code"] == "06-06-06-0005" and a["cost_centre_rule"] == "REQ" and a["normal_balance"] == "D"
    r = client.post("/api/accounts", headers=H["cfo"], json={"parent_code": "06-06-06", "name": "cinema HALL decoration"})
    assert r.status_code == 409


def test_site_and_cost_centre_creation(client, H):
    r = client.post("/api/sites", headers=H["cfo"], json={"code": "104", "name": "Future Cinema Islamabad",
                                                          "city": "Islamabad", "province": "ICT"})
    assert r.status_code == 201, r.text
    r = client.post("/api/cost-centres", headers=H["cfo"], json={"code": "010501", "name": "IMAX Operations"})
    assert r.status_code == 201 and r.json()["section_code"] == "01"
    r = client.post("/api/sites", headers=H["cfo"], json={"code": "104", "name": "Duplicate"})
    assert r.status_code == 409


def test_site_scoped_user_sees_only_own_site(client, H):
    sites = client.get("/api/sites", headers=H["manager.emp"]).json()["items"]
    assert sites  # site list is visible (masters.view) ...
    me = client.get("/api/auth/me", headers=H["manager.emp"]).json()
    assert me["all_sites"] is False and len(me["site_ids"]) == 1


def test_periods_created_and_reopen_needs_authority(client, H, db):
    periods = client.get("/api/periods", headers=H["cfo"]).json()
    assert len(periods) == 24 and periods[0]["name"] == "Jul-2026"
    pid = periods[0]["id"]
    r = client.post(f"/api/periods/{pid}/status", headers=H["accountant"], json={"status": "SOFT_CLOSED"})
    assert r.status_code == 403
    r = client.post(f"/api/periods/{pid}/status", headers=H["fm"], json={"status": "SOFT_CLOSED"})
    assert r.status_code == 200 and r.json()["status"] == "SOFT_CLOSED"
    r = client.post(f"/api/periods/{pid}/status", headers=H["fm"], json={"status": "OPEN"})
    assert r.status_code == 200
    assert db.get(AccountingPeriod, pid).status == PeriodStatus.OPEN


def test_audit_log_records_actions(client, H, db):
    entries = db.scalars(select(AuditLog).where(AuditLog.action == "account.create")).all()
    assert entries and entries[-1].username == "cfo" and entries[-1].new_values["code"] == "06-06-06-0005"
    r = client.get("/api/admin/audit", headers=H["admin"], params={"action": "period"})
    assert r.status_code == 200 and r.json()["total"] >= 2
