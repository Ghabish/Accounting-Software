"""Security: headers, production configuration guard, site scoping, read-only roles, token revocation, attachments."""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import login
from tests.helpers import acc, cc, post_journal, site

D = Decimal


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_production_requires_strong_secret(monkeypatch):
    from backend import config
    monkeypatch.setenv("UCF_ENVIRONMENT", "production")
    monkeypatch.setenv("UCF_SECRET_KEY", config.DEFAULT_SECRET)
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        config.get_settings()
    monkeypatch.setenv("UCF_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("UCF_DATABASE_URL", "sqlite:///x.db")
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        config.get_settings()
    monkeypatch.undo()
    config.get_settings.cache_clear()


def test_site_restricted_user_sees_only_own_site(client, H):
    elec, accr = acc("06-02-02-0001"), acc("02-02-02-0007")
    post_journal(client, H, [
        {"account_id": elec, "debit": "1000", "site_id": site("101"), "cost_centre_id": cc("010101")},
        {"account_id": elec, "debit": "9000", "site_id": site("103"), "cost_centre_id": cc("010101")},
        {"account_id": accr, "credit": "1000", "site_id": site("101")},
        {"account_id": accr, "credit": "9000", "site_id": site("103")}], description="Electricity accrual two sites")
    post_journal(client, H, [
        {"account_id": elec, "debit": "500", "site_id": site("103"), "cost_centre_id": cc("010101")},
        {"account_id": accr, "credit": "500", "site_id": site("103")}], description="Grand only accrual")
    q = {"date_from": "2026-07-01", "date_to": "2026-07-31", "account_ids": str(elec)}
    assert D(client.get("/api/reports/gl", headers=H["cfo"], params=q).json()["closing"]) == D("10500.00")
    assert D(client.get("/api/reports/gl", headers=H["manager.emp"], params=q).json()["closing"]) == D("1000.00")
    pl = client.get("/api/reports/profit-loss", headers=H["manager.emp"], params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).json()
    assert D(pl["meta"]["summary"][0]["OPEX"]) == D("1000.00")
    assert client.get("/api/journals", headers=H["manager.emp"]).status_code == 403   # site managers have no journal access
    r = client.post("/api/admin/users", headers=H["admin"], json={"username": "acct.emp", "full_name": "Emporium accountant",
                                                                   "password": "SiteAcct2026pass", "role_codes": ["ACCOUNTANT"],
                                                                   "site_ids": [site("101")], "must_change_password": False})
    assert r.status_code == 201, r.text
    emp_acct = login(client, "acct.emp", "SiteAcct2026pass")
    descs = [j["description"] for j in client.get("/api/journals", headers=emp_acct, params={"journal_type": "JV"}).json()["items"]]
    assert "Electricity accrual two sites" in descs and "Grand only accrual" not in descs
    gid = next(j["id"] for j in client.get("/api/journals", headers=H["cfo"], params={"q": "Grand only"}).json()["items"])
    assert client.get(f"/api/journals/{gid}", headers=emp_acct).status_code == 404
    # and cannot post to a site outside its scope
    r = client.post("/api/journals", headers=emp_acct, json={"transaction_date": "2026-07-12", "description": "Grand attempt",
        "lines": [{"account_id": elec, "debit": "10", "site_id": site("103"), "cost_centre_id": cc("010101")},
                  {"account_id": accr, "credit": "10", "site_id": site("103")}]})
    assert r.status_code == 422 and "not authorised for site" in " ".join(r.json()["details"])


def test_auditor_is_read_only(client, H):
    assert client.get("/api/reports/trial-balance", headers=H["auditor"], params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).status_code == 200
    assert client.post("/api/sites", headers=H["auditor"], json={"code": "999", "name": "x"}).status_code == 403
    assert client.post("/api/ap/suppliers", headers=H["auditor"], json={"name": "xx", "category_id": 1}).status_code == 403
    r = client.post("/api/journals", headers=H["auditor"], json={"transaction_date": "2026-07-10", "description": "auditor attempt",
                                                                 "lines": [{"account_id": 1, "debit": "1"}, {"account_id": 2, "credit": "1"}]})
    assert r.status_code == 403


def test_password_change_revokes_tokens(client, H):
    from tests.conftest import DEMO_PASSWORD
    old = login(client, "ar")
    r = client.post("/api/auth/change-password", headers=old, json={"current_password": DEMO_PASSWORD, "new_password": "short"})
    assert r.status_code == 422
    r = client.post("/api/auth/change-password", headers=old, json={"current_password": DEMO_PASSWORD, "new_password": "NewSecure2027pass"})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert client.get("/api/auth/me", headers=login(client, "ar", "NewSecure2027pass")).status_code == 200


def test_attachment_controls(client, H):
    j = post_journal(client, H, [
        {"account_id": acc("06-02-02-0001"), "debit": "100", "site_id": site("101"), "cost_centre_id": cc("010101")},
        {"account_id": acc("02-02-02-0007"), "credit": "100", "site_id": site("101")}], description="With attachment")
    bad = client.post("/api/attachments", headers=H["accountant"], data={"entity_type": "journal", "entity_id": str(j["id"])},
                      files={"file": ("x.exe", b"MZ...", "application/x-msdownload")})
    assert bad.status_code == 422
    ok = client.post("/api/attachments", headers=H["accountant"], data={"entity_type": "journal", "entity_id": str(j["id"])},
                     files={"file": ("../../etc/passwd.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert ok.status_code == 201
    att = ok.json()
    assert "/" not in att["filename"] and "storage_path" not in att
    dl = client.get(f"/api/attachments/{att['id']}/download", headers=H["cfo"])
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF")
    assert client.delete(f"/api/attachments/{att['id']}", headers=H["accountant"]).status_code == 409  # journal is posted
