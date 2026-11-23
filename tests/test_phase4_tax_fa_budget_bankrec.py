"""Phase 4: tax engine and reports, fixed assets, budgeting, bank reconciliation, sub-ledger reconciliations."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.accounting.models import AccountingPeriod
from backend.ap.models import Supplier
from backend.assets.models import AssetCategory
from backend.banking.models import BankAccount
from backend.tax.models import TaxCode
from tests.helpers import acc, cc, lookup, site

D = Decimal


@pytest.fixture(scope="module")
def ids(client):
    return dict(landlord=lookup(Supplier, code="V00004"), capex=lookup(Supplier, code="V00008"),
                prof=lookup(Supplier, code="V00010"), bank=lookup(BankAccount, code="BNK-OPS"),
                emp=site("101"), grand=site("103"), wht153a=lookup(TaxCode, code="WHT-153A"),
                wht155=lookup(TaxCode, code="WHT-155"), pst_in=lookup(TaxCode, code="PST-IN-PRA"),
                proj=lookup(AssetCategory, code="PROJ"))


def _wf(client, H, base, did, steps):
    r = None
    for a, u in steps:
        r = client.post(f"{base}/{did}/{a}", headers=H[u], json={})
        assert r.status_code == 200, f"{a}: {r.text}"
    return r.json()


def _period(db, name):
    return db.scalar(select(AccountingPeriod).where(AccountingPeriod.name == name)).id


# ------------------------------------------------------------------ tax
def test_rate_selection_by_payee_and_atl(client, H, ids):
    def rate(payee, atl):
        return client.get("/api/tax/rate-lookup", headers=H["cfo"], params={
            "tax_code_id": ids["wht153a"], "on_date": "2026-09-01", "payee_type": payee, "atl_status": atl}).json()["rate"]
    assert D(rate("COMPANY", "ATL")) == D("0.05")
    assert D(rate("COMPANY", "NON_ATL")) == D("0.10")
    assert D(rate("INDIVIDUAL", "ATL")) == D("0.055")
    assert D(rate("AOP", "NON_ATL")) == D("0.11")
    # before the effective date there is no rate
    r = client.get("/api/tax/rate-lookup", headers=H["cfo"], params={"tax_code_id": ids["wht153a"], "on_date": "2026-06-30"})
    assert r.status_code == 404


def test_slab_calculation(client, H, ids):
    r = client.get("/api/tax/slab-calc", headers=H["cfo"], params={"tax_code_id": ids["wht155"], "annual_amount": "1000000",
                                                                   "on_date": "2026-09-01"}).json()
    assert D(r["annual_tax"]) == D("55000.00")      # 15,000 + (1,000,000 - 600,000) x 10%
    r = client.get("/api/tax/slab-calc", headers=H["cfo"], params={"tax_code_id": ids["wht155"], "annual_amount": "250000",
                                                                   "on_date": "2026-09-01"}).json()
    assert D(r["annual_tax"]) == 0


def test_new_rate_closes_previous(client, H, ids):
    r = client.post("/api/tax/rates", headers=H["cfo"], json={"tax_code_id": ids["pst_in"], "name": "PST 17% PRA (test change)",
                                                              "rate": "0.17", "effective_from": "2027-01-01"})
    assert r.status_code == 201, r.text
    code = client.get(f"/api/tax/codes/{ids['pst_in']}", headers=H["cfo"]).json()
    old = next(x for x in code["rates"] if x["rate"] == "0.160000")
    assert old["effective_to"] == "2026-12-31"
    look = lambda d: client.get("/api/tax/rate-lookup", headers=H["cfo"], params={"tax_code_id": ids["pst_in"], "on_date": d}).json()["rate"]  # noqa: E731
    assert D(look("2026-12-31")) == D("0.16") and D(look("2027-01-15")) == D("0.17")
    assert client.post("/api/tax/rates", headers=H["ap"], json={"tax_code_id": ids["pst_in"], "name": "x", "rate": "0.1",
                                                                 "effective_from": "2027-02-01"}).status_code == 403


def test_tax_reports_and_deposit(client, H, ids):
    inv = client.post("/api/ap/documents", headers=H["ap"], json={
        "supplier_id": ids["landlord"], "supplier_invoice_no": "RENT-SEP-26", "invoice_date": "2026-09-01",
        "site_id": ids["emp"], "lines": [{"account_id": acc("06-02-01-0001"), "cost_centre_id": cc("010101"), "amount": "200000"}]}).json()
    _wf(client, H, "/api/ap/documents", inv["id"], [("submit", "ap"), ("approve", "fm")])
    pay = client.post("/api/ap/payments", headers=H["ap"], json={"supplier_id": ids["landlord"], "payment_date": "2026-09-05",
                                                                 "cheque_no": "CHQ-5001",
                                                                 "lines": [{"document_id": inv["id"], "amount": "232000"}]}).json()
    _wf(client, H, "/api/ap/payments", pay["id"], [("submit", "ap"), ("check", "fm"), ("approve", "cfo")])
    pytest.rent_payment_net = D(pay["net_amount"])  # 232,000 - 30,000 - 6,400
    s = client.get("/api/tax/reports/summary", headers=H["cfo"], params={"date_from": "2026-09-01", "date_to": "2026-09-30"}).json()
    assert D(s["meta"]["totals"]["INPUT"]) == D("32000.00")
    assert D(s["meta"]["totals"]["WITHHELD"]) == D("36400.00")
    rec = client.get("/api/tax/reports/reconciliation", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-09-30"}).json()
    assert rec["meta"]["reconciled"], rec
    r = client.post("/api/tax/deposits", headers=H["cfo"], json={
        "tax_code_ids": [ids["wht155"]], "date_from": "2026-09-01", "date_to": "2026-09-30", "bank_account_id": ids["bank"],
        "deposit_date": "2026-10-15", "cpr_number": "CPR-2026-000123"})
    assert r.status_code == 201, r.text
    assert D(r.json()["amount"]) == D("30000.00")
    lst = client.get("/api/tax/reports/transactions", headers=H["cfo"], params={
        "date_from": "2026-09-01", "date_to": "2026-09-30", "tax_code_id": ids["wht155"]}).json()
    assert all(x.get("deposit") == "CPR-2026-000123" for x in lst["rows"][:-1])
    rec = client.get("/api/tax/reports/reconciliation", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-10-31"}).json()
    assert rec["meta"]["reconciled"], rec
    wp = client.get("/api/tax/reports/working-papers", headers=H["cfo"], params={"date_from": "2026-09-01", "date_to": "2026-09-30"})
    assert wp.status_code == 200 and len(wp.content) > 3000


# ------------------------------------------------------------------ fixed assets
def test_asset_lifecycle(client, H, ids, db):
    inv = client.post("/api/ap/documents", headers=H["ap"], json={
        "supplier_id": ids["capex"], "supplier_invoice_no": "PROJ-9001", "invoice_date": "2026-08-25", "site_id": ids["emp"],
        "lines": [{"account_id": acc("01-01-01-0006"), "amount": "2016000", "description": "Laser projector Screen 1"}]}).json()
    inv = _wf(client, H, "/api/ap/documents", inv["id"], [("submit", "ap"), ("approve", "cfo")])
    a = client.post("/api/assets", headers=H["accountant"], json={
        "name": "Laser projector - Emporium Screen 1 (demo)", "category_id": ids["proj"], "site_id": ids["emp"],
        "cost_centre_id": cc("010301"), "purchase_date": "2026-08-25", "cost": "2016000", "useful_life_months": 84}).json()
    assert a["status"] == "DRAFT"
    r = client.post(f"/api/assets/{a['id']}/capitalise", headers=H["accountant"],
                    json={"source": "AP_INVOICE", "ap_document_line_id": inv["lines"][0]["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ACTIVE"
    # the same invoice line cannot capitalise a second asset
    b = client.post("/api/assets", headers=H["accountant"], json={
        "name": "Duplicate", "category_id": ids["proj"], "site_id": ids["emp"], "cost_centre_id": cc("010301"),
        "purchase_date": "2026-08-25", "cost": "2016000"}).json()
    assert client.post(f"/api/assets/{b['id']}/capitalise", headers=H["accountant"],
                       json={"source": "AP_INVOICE", "ap_document_line_id": inv["lines"][0]["id"]}).status_code == 409
    run = client.post("/api/assets/runs", headers=H["accountant"], json={"period_id": _period(db, "Sep-2026")}).json()
    assert D(run["total"]) == D("48000.00")  # Aug + Sep catch-up: 2,016,000 / 84 = 24,000 per month
    r = client.post(f"/api/assets/runs/{run['id']}/post", headers=H["fm"])
    assert r.status_code == 200, r.text
    assert client.post("/api/assets/runs", headers=H["accountant"], json={"period_id": _period(db, "Sep-2026")}).status_code == 409
    run = client.post("/api/assets/runs", headers=H["accountant"], json={"period_id": _period(db, "Oct-2026")}).json()
    assert D(run["total"]) == D("24000.00")
    client.post(f"/api/assets/runs/{run['id']}/post", headers=H["fm"])
    asset = client.get(f"/api/assets/{a['id']}", headers=H["cfo"]).json()
    assert asset["accumulated_depreciation"] == "72000.00" and asset["net_book_value"] == "1944000.00"
    rec = client.get("/api/assets/reports/reconciliation", headers=H["cfo"], params={"as_of": "2026-10-31"}).json()
    assert rec["meta"]["reconciled"], rec
    # impairment then remaining life spreads the lower NBV
    r = client.post(f"/api/assets/{a['id']}/impair", headers=H["fm"], json={"date": "2026-10-31", "amount": "100000", "reason": "Lamp damage"})
    assert r.status_code == 200 and r.json()["net_book_value"] == "1844000.00"
    # transfer to The Grand moves cost and accumulated depreciation between sites
    r = client.post(f"/api/assets/{a['id']}/transfer", headers=H["fm"], json={"date": "2026-11-01", "to_site_id": ids["grand"],
                                                                                "to_cost_centre_id": cc("010301")})
    assert r.status_code == 200
    gl = client.get("/api/reports/gl", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-11-30",
                                                                  "account_ids": str(acc("01-01-01-0006")), "site_ids": str(ids["grand"])}).json()
    assert D(gl["closing"]) == D("2016000.00")
    rec = client.get("/api/assets/reports/reconciliation", headers=H["cfo"], params={"as_of": "2026-11-30"}).json()
    assert rec["meta"]["reconciled"], rec
    # disposal for 1,500,000 -> loss of 344,000
    r = client.post(f"/api/assets/{a['id']}/dispose", headers=H["fm"], json={"date": "2026-11-15", "proceeds": "1500000",
                                                                               "bank_account_id": ids["bank"]})
    assert r.status_code == 200, r.text
    t = r.json()["transactions"][-1]
    assert t["txn_type"] == "DISPOSAL" and D(t["gain_loss"]) == D("-344000.00")
    rec = client.get("/api/assets/reports/reconciliation", headers=H["cfo"], params={"as_of": "2026-11-30"}).json()
    assert rec["meta"]["reconciled"], rec


# ------------------------------------------------------------------ budgeting
def test_budget_versions_and_variance(client, H, ids, db):
    fy = client.get("/api/fiscal-years", headers=H["cfo"]).json()[0]
    b = client.post("/api/budgets", headers=H["accountant"], json={"fiscal_year_id": fy["id"], "name": "FY2026-27 Operating Budget"}).json()
    v1 = client.get("/api/budgets", headers=H["cfo"]).json()[0]["versions"][0]
    lines = [{"account_id": acc("06-02-01-0001"), "site_id": ids["emp"], "cost_centre_id": cc("010101"),
              "period_id": _period(db, "Sep-2026"), "amount": "150000"},
             {"account_id": acc("04-01-01-0001"), "site_id": ids["emp"], "cost_centre_id": cc("010201"),
              "period_id": _period(db, "Sep-2026"), "amount": "5000000"}]
    assert client.put(f"/api/budgets/versions/{v1['id']}/lines", headers=H["accountant"], json=lines).status_code == 200
    assert client.post(f"/api/budgets/versions/{v1['id']}/approve", headers=H["accountant"]).status_code in (403, 409)
    assert client.post(f"/api/budgets/versions/{v1['id']}/approve", headers=H["cfo"]).status_code == 200
    assert client.put(f"/api/budgets/versions/{v1['id']}/lines", headers=H["accountant"], json=lines).status_code == 409
    var = client.get("/api/budgets/reports/variance", headers=H["cfo"], params={"date_from": "2026-09-01", "date_to": "2026-09-30"}).json()
    rent = next(r for r in var["rows"] if r["label"].startswith("06-02-01-0001"))
    assert D(rent["c0"]) == D("200000.00") and D(rent["c1"]) == D("150000.00") and D(rent["c2"]) == D("50000.00")
    assert rent["favourable"] is False
    pl = client.get("/api/reports/profit-loss", headers=H["cfo"], params={"date_from": "2026-09-01", "date_to": "2026-09-30",
                                                                          "preset": "budget"}).json()
    assert pl["columns"][2]["label"] == "Budget"
    # revision keeps history
    r = client.post(f"/api/budgets/{b['id']}/revise", headers=H["accountant"], json={"reason": "Rent escalation agreed"})
    assert r.status_code == 200 and r.json()["version_no"] == 2
    v2 = r.json()
    lines[0]["amount"] = "200000"
    client.put(f"/api/budgets/versions/{v2['id']}/lines", headers=H["accountant"], json=lines[:1])
    client.post(f"/api/budgets/versions/{v2['id']}/approve", headers=H["fm"])
    versions = client.get("/api/budgets", headers=H["cfo"]).json()[0]["versions"]
    assert [v["status"] for v in versions] == ["SUPERSEDED", "APPROVED"]
    var = client.get("/api/budgets/reports/variance", headers=H["cfo"], params={"date_from": "2026-09-01", "date_to": "2026-09-30"}).json()
    rent = next(r for r in var["rows"] if r["label"].startswith("06-02-01-0001"))
    assert D(rent["c2"]) == 0
    # advisory budget control warns on an AP invoice that exceeds the budget
    inv = client.post("/api/ap/documents", headers=H["ap"], json={
        "supplier_id": ids["landlord"], "supplier_invoice_no": "RENT-EXTRA-SEP", "invoice_date": "2026-09-20",
        "site_id": ids["emp"], "lines": [{"account_id": acc("06-02-01-0001"), "cost_centre_id": cc("010101"), "amount": "10000"}]}).json()
    r = client.post(f"/api/ap/documents/{inv['id']}/submit", headers=H["ap"], json={})
    assert r.status_code == 200 and any("exceeds budget" in w for w in r.json()["warnings"])


# ------------------------------------------------------------------ bank reconciliation
def test_bank_reconciliation(client, H, ids):
    unrec = client.get(f"/api/banking/accounts/{ids['bank']}/unreconciled", headers=H["cfo"], params={"as_of": "2026-10-31"}).json()
    gl_bal = sum(D(x["debit"]) - D(x["credit"]) for x in unrec)
    st_lines = []
    for x in unrec:
        if x["date"] <= "2026-10-15":   # everything except the late items clears the bank
            st_lines.append({"txn_date": x["date"], "description": x["description"], "reference": x["reference"],
                             "debit": x["credit"], "credit": x["debit"]})
    st_lines.append({"txn_date": "2026-10-31", "description": "Bank charges October", "debit": "1500", "credit": "0"})
    cleared = sum(D(l["credit"]) - D(l["debit"]) for l in st_lines)
    r = client.post("/api/banking/statements", headers=H["accountant"], json={
        "bank_account_id": ids["bank"], "opening_balance": "0", "closing_balance": str(cleared), "lines": st_lines})
    assert r.status_code == 201, r.text
    st = r.json()
    n = client.post(f"/api/banking/statements/{st['id']}/auto-match", headers=H["accountant"]).json()["matched"]
    assert n == len(st_lines) - 1
    rep = client.get("/api/banking/reconciliation", headers=H["cfo"], params={"bank_account_id": ids["bank"], "as_of": "2026-10-31"}).json()
    assert rep["can_complete"] is False and len(rep["unmatched_statement_lines"]) == 1
    assert client.post("/api/banking/reconciliation/complete", headers=H["accountant"],
                       json={"bank_account_id": ids["bank"], "as_of": "2026-10-31"}).status_code == 422
    charge_line = rep["unmatched_statement_lines"][0]
    r = client.post("/api/banking/adjustments", headers=H["accountant"], json={
        "statement_line_id": charge_line["id"], "account_id": acc("08-01-01-0003"), "cost_centre_id": cc("090101")})
    assert r.status_code == 201, r.text
    rep = client.get("/api/banking/reconciliation", headers=H["cfo"], params={"bank_account_id": ids["bank"], "as_of": "2026-10-31"}).json()
    assert D(rep["gl_balance"]) == gl_bal - D("1500")
    assert D(rep["difference"]) == 0 and rep["can_complete"], rep
    r = client.post("/api/banking/reconciliation/complete", headers=H["accountant"], json={"bank_account_id": ids["bank"], "as_of": "2026-10-31"})
    assert r.status_code == 201
    hist = client.get("/api/banking/reconciliations", headers=H["cfo"], params={"bank_account_id": ids["bank"]}).json()
    assert hist[0]["status"] == "COMPLETED"


def test_subledger_reconciliation_summary(client, H):
    r = client.get("/api/reports/subledger-reconciliation", headers=H["cfo"], params={"as_of": "2026-10-31"}).json()
    assert r["meta"]["AP"] and r["meta"]["AR"] and r["meta"]["FIXED_ASSETS"] and r["meta"]["TAX"], r["meta"]
    tb = client.get("/api/reports/trial-balance", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-12-31"}).json()
    assert tb["meta"]["balanced"]
    bs = client.get("/api/reports/balance-sheet", headers=H["cfo"], params={"as_of": "2026-11-30"}).json()
    assert bs["meta"]["balanced"], bs["meta"]
    cf = client.get("/api/reports/cash-flow", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-11-30"}).json()
    assert cf["meta"]["reconciles"], cf["meta"]
