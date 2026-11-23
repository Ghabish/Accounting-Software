"""Phase 5: opening balances (GL, AP, AR, fixed assets), imports, year-end close."""
from __future__ import annotations

import io
from decimal import Decimal

from sqlalchemy import select

from backend.accounting.models import AccountingPeriod
from backend.assets.models import AssetCategory
from backend.banking.models import BankAccount
from tests.helpers import acc, cc, lookup, post_journal, site

D = Decimal


def _csv(rows: list[list]) -> bytes:
    return "\n".join(",".join(str(c) for c in r) for r in rows).encode()


def test_templates_available(client, H):
    r = client.get("/api/imports/templates/gl-opening", headers=H["cfo"])
    assert r.status_code == 200 and r.text.startswith("account_code,site_code")


def test_opening_balances(client, H):
    gl = _csv([["account_code", "site_code", "cost_centre_code", "debit", "credit", "description"],
               ["01-02-07-0006", "", "", "10000000", "0", "Bank at cut-over"],
               ["01-02-01-0001", "101", "", "200000", "0", "F&B stock Emporium"],
               ["03-01-01-0001", "", "", "0", "8000000", "Share capital"],
               ["03-01-02-0001", "", "", "0", "2300000", "Retained earnings"],
               ["02-01-01-0001", "", "", "0", "1000000", "Bank loan"]])
    r = client.post("/api/imports/gl-opening", headers=H["cfo"], files={"file": ("gl.csv", gl, "text/csv")},
                    data={"cutover_date": "2026-07-01"})
    assert r.status_code == 200, r.text
    assert D(r.json()["carried_to_clearing"]) == D("-1100000.00")
    bad = _csv([["account_code", "debit", "credit"], ["02-02-01-0003", "0", "5"]])
    r = client.post("/api/imports/gl-opening", headers=H["cfo"], files={"file": ("bad.csv", bad, "text/csv")},
                    data={"cutover_date": "2026-07-01"})
    assert r.status_code == 422 and "control account" in r.json()["details"][0]
    st = client.get("/api/imports/opening/status", headers=H["cfo"], params={"cutover_date": "2026-07-01"}).json()
    assert st["clearing_is_nil"] is False
    ap = _csv([["supplier_code", "invoice_no", "invoice_date", "due_date", "amount", "doc_type"],
               ["V00003", "OB-F-1", "2026-06-20", "2026-07-20", "300000", "INVOICE"]])
    assert client.post("/api/imports/supplier-opening", headers=H["cfo"], files={"file": ("ap.csv", ap, "text/csv")},
                       data={"cutover_date": "2026-07-01"}).status_code == 200
    ar = _csv([["customer_code", "invoice_no", "invoice_date", "due_date", "amount"],
               ["C00001", "OB-A-1", "2026-06-15", "2026-07-15", "400000"]])
    assert client.post("/api/imports/customer-opening", headers=H["cfo"], files={"file": ("ar.csv", ar, "text/csv")},
                       data={"cutover_date": "2026-07-01"}).status_code == 200
    land = client.post("/api/assets", headers=H["cfo"], json={
        "name": "Freehold land - The Grand (demo)", "category_id": lookup(AssetCategory, code="LAND"), "site_id": site("103"),
        "cost_centre_id": cc("010101"), "purchase_date": "2015-01-01", "capitalisation_date": "2026-07-01", "cost": "1000000",
        "useful_life_months": 1}).json()
    r = client.post(f"/api/assets/{land['id']}/capitalise", headers=H["cfo"], json={"source": "OPENING"})
    assert r.status_code == 200, r.text
    st = client.get("/api/imports/opening/status", headers=H["cfo"], params={"cutover_date": "2026-07-01"}).json()
    assert st["clearing_is_nil"] and st["equation_holds"] and st["complete"], st
    assert D(st["assets"]) == D("11600000.00")  # bank 10.0m + stock 0.2m + AR 0.4m + land 1.0m
    ag = client.get("/api/ap/aging", headers=H["cfo"], params={"as_of": "2026-07-31"}).json()
    assert D(ag["rows"][-1]["b1"]) == D("300000.00")
    for path in ("/api/ap/reconciliation", "/api/ar/reconciliation", "/api/assets/reports/reconciliation"):
        assert client.get(path, headers=H["cfo"], params={"as_of": "2026-07-31"}).json()["meta"]["reconciled"], path
    cf = client.get("/api/reports/cash-flow", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).json()
    assert cf["meta"]["reconciles"], cf["meta"]


def test_master_and_journal_imports(client, H):
    sup = _csv([["name", "category_code", "ntn", "supplier_type"], ["[DEMO] Imported Popcorn Co", "FNB", "IMP-001", "COMPANY"]])
    r = client.post("/api/imports/suppliers", headers=H["cfo"], files={"file": ("s.csv", sup, "text/csv")})
    assert r.status_code == 200 and r.json()["created"] == 1
    r = client.post("/api/imports/suppliers", headers=H["cfo"], files={"file": ("s.csv", sup, "text/csv")})
    assert r.status_code == 422  # duplicate NTN
    jr = _csv([["journal_ref", "date", "description", "account_code", "site_code", "cost_centre_code", "debit", "credit"],
               ["J1", "2026-08-31", "Imported accrual", "06-02-02-0001", "101", "010101", "5000", "0"],
               ["J1", "2026-08-31", "Imported accrual", "02-02-02-0007", "101", "", "0", "5000"]])
    r = client.post("/api/imports/journals", headers=H["ap"], files={"file": ("j.csv", jr, "text/csv")})
    assert r.status_code == 403  # AP officers have no import permission
    r = client.post("/api/imports/journals", headers=H["accountant"], files={"file": ("j.csv", jr, "text/csv")})
    assert r.status_code == 200 and len(r.json()["journals"]) == 1


def test_year_end_close(client, H, db):
    bank, sales, cash = acc("01-02-07-0006"), acc("04-01-01-0001"), acc("01-02-07-0002")
    post_journal(client, H, [{"account_id": cash, "debit": "500000", "site_id": site("101")},
                             {"account_id": sales, "credit": "500000", "site_id": site("101"), "cost_centre_id": cc("010201")}],
                 date="2026-08-15", description="Demo takings")
    post_journal(client, H, [{"account_id": acc("06-02-02-0001"), "debit": "200000", "site_id": site("101"), "cost_centre_id": cc("010101")},
                             {"account_id": bank, "credit": "200000"}], date="2026-09-15", description="Demo electricity paid")
    # cancel the imported draft journal so that August has no unposted items
    for j in client.get("/api/journals", headers=H["fm"], params={"status": "DRAFT"}).json()["items"]:
        client.post(f"/api/journals/{j['id']}/cancel", headers=H["fm"], json={})
    # bank reconciliation for the year: opening at cut-over and the September payment
    ba = lookup(BankAccount, code="BNK-OPS")
    unrec = client.get(f"/api/banking/accounts/{ba}/unreconciled", headers=H["cfo"]).json()
    lines = [{"txn_date": u["date"], "description": u["description"], "debit": u["credit"], "credit": u["debit"]} for u in unrec]
    st = client.post("/api/banking/statements", headers=H["fm"], json={"bank_account_id": ba, "opening_balance": "0", "lines": lines}).json()
    client.post(f"/api/banking/statements/{st['id']}/auto-match", headers=H["fm"])
    assert client.post("/api/banking/reconciliation/complete", headers=H["fm"], json={"bank_account_id": ba, "as_of": "2027-06-30"}).status_code == 201
    fy = client.get("/api/fiscal-years", headers=H["cfo"]).json()[0]
    assert client.post("/api/closing/year-end", headers=H["cfo"], json={"fiscal_year_id": fy["id"]}).status_code == 409
    periods = [p for p in client.get("/api/periods", headers=H["cfo"], params={"fiscal_year_id": fy["id"]}).json()]
    for p in periods[:11]:
        for it in client.get(f"/api/closing/{p['id']}/checklist", headers=H["fm"]).json():
            if not it["is_auto"] and it["status"] == "PENDING":
                client.post(f"/api/closing/{p['id']}/checklist/{it['code']}", headers=H["fm"], json={"status": "DONE"})
        r = client.post(f"/api/closing/{p['id']}/close", headers=H["fm"])
        assert r.status_code == 200, (p["name"], r.text)
    r = client.post("/api/closing/year-end", headers=H["cfo"], json={"fiscal_year_id": fy["id"]})
    assert r.status_code == 200, r.text
    tb = client.get("/api/reports/trial-balance", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2027-06-30"}).json()
    assert tb["meta"]["balanced"]
    pl_accounts = [r for r in tb["rows"] if r.get("code", "").startswith(("04", "05", "06", "07", "08"))]
    assert all(D(r["c4"]) == 0 and D(r["c5"]) == 0 for r in pl_accounts)   # P&L accounts closed
    re_row = next(r for r in tb["rows"] if r.get("code") == "03-01-02-0001")
    assert D(re_row["c5"]) == D("2300000") + D("300000")
    pl = client.get("/api/reports/profit-loss", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2027-06-30"}).json()
    assert D(pl["meta"]["summary"][0]["PAT"]) == D("300000.00")   # P&L still reports the year's result
    bs = client.get("/api/reports/balance-sheet", headers=H["cfo"], params={"as_of": "2027-06-30"}).json()
    assert bs["meta"]["balanced"]
    assert client.post("/api/closing/year-end", headers=H["cfo"], json={"fiscal_year_id": fy["id"]}).status_code == 409
