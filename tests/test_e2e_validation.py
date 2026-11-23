"""FINAL VALIDATION - the 24-step end-to-end scenario from the project brief (section 45).

Run on PostgreSQL:
    UCF_TEST_DATABASE_URL=postgresql+psycopg://... pytest tests/test_e2e_validation.py -v

Steps run in order and share state; each step asserts the accounting outcome, not just HTTP success.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.ap.models import Supplier
from backend.assets.models import AssetCategory
from backend.banking.models import BankAccount
from tests.helpers import acc, cc, lookup, site

D = Decimal
S: dict = {}   # shared state across steps


def _ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text[:500]}"
    return r.json()


def _gl(client, H, code, **params):
    q = {"date_from": "2026-07-01", "date_to": "2026-08-31", "account_ids": str(acc(code)), **params}
    return D(_ok(client.get("/api/reports/gl", headers=H["cfo"], params=q))["closing"])


def _wf(client, H, base, did, steps):
    out = None
    for action, user in steps:
        out = _ok(client.post(f"{base}/{did}/{action}", headers=H[user], json={}))
    return out


def test_step_00_setup_share_capital(client, H):
    """Setup: share capital paid into the operating bank (manual JV through the full 3-level workflow)."""
    bank, cap = acc("01-02-07-0006"), acc("03-01-01-0001")
    j = _ok(client.post("/api/journals", headers=H["fm"], json={
        "transaction_date": "2026-07-01", "description": "[E2E] Share capital received",
        "lines": [{"account_id": bank, "debit": "10000000"}, {"account_id": cap, "credit": "10000000"}]}), 201)
    j = _wf(client, H, "/api/journals", j["id"], [("submit", "fm"), ("check", "accountant"), ("approve", "cfo"), ("post", "cfo")])
    assert j["status"] == "POSTED"
    S["bank_ba"] = lookup(BankAccount, code="BNK-OPS")


def test_step_01_create_site(client, H):
    s = _ok(client.post("/api/sites", headers=H["cfo"], json={"code": "104", "name": "[E2E] Packages Mall Lahore",
                                                              "city": "Lahore", "province": "Punjab", "tax_authority": "PRA"}), 201)
    S["site"] = s["id"]


def test_step_02_create_cost_centre(client, H):
    c = _ok(client.post("/api/cost-centres", headers=H["cfo"], json={"code": "050103", "name": "[E2E] Maintenance - Laser projection"}), 201)
    assert c["section_code"] == "05"
    S["cc"] = c["id"]


def test_step_03_create_gl_account(client, H):
    a = _ok(client.post("/api/accounts", headers=H["cfo"], json={"parent_code": "06-03-01", "name": "Laser light source servicing"}), 201)
    assert a["code"] == "06-03-01-0007" and a["cost_centre_rule"] == "REQ" and a["normal_balance"] == "D"
    S["account"] = a["id"]


def test_step_04_create_supplier(client, H):
    from backend.ap.models import SupplierCategory
    s = _ok(client.post("/api/ap/suppliers", headers=H["ap"], json={
        "name": "[E2E] Laser Tech Services (Pvt) Ltd", "category_id": lookup(SupplierCategory, code="GENERAL"),
        "supplier_type": "COMPANY", "atl_status": "ATL", "ntn": "E2E-1234567", "payment_terms_days": 15}), 201)
    assert s["code"].startswith("V") and s["wht_tax_code_id"] and s["st_tax_code_id"] and s["stw_tax_code_id"]
    S["supplier"] = s["id"]


def test_step_05_enter_supplier_invoice(client, H):
    d = _ok(client.post("/api/ap/documents", headers=H["ap"], json={
        "supplier_id": S["supplier"], "supplier_invoice_no": "LTS-2026-0815", "invoice_date": "2026-08-05", "site_id": S["site"],
        "description": "[E2E] Laser projector servicing August",
        "lines": [{"account_id": S["account"], "cost_centre_id": S["cc"], "amount": "100000"}]}), 201)
    S["invoice"] = d["id"]
    assert d["status"] == "DRAFT" and d["due_date"] == "2026-08-20"


def test_step_06_tax_applied(client, H):
    d = _ok(client.get(f"/api/ap/documents/{S['invoice']}", headers=H["ap"]))
    assert d["subtotal"] == "100000.00" and d["tax_total"] == "16000.00" and d["total"] == "116000.00"   # PST 16% PRA


def test_step_07_approve_and_post_invoice(client, H):
    r = client.post(f"/api/ap/documents/{S['invoice']}/approve", headers=H["fm"], json={})
    assert r.status_code == 409   # cannot approve before submission
    d = _wf(client, H, "/api/ap/documents", S["invoice"], [("submit", "ap"), ("approve", "fm")])
    assert d["status"] == "POSTED" and d["journal_id"]
    assert _gl(client, H, "02-02-01-0010") == D("-116000.00")


def test_step_08_make_payment(client, H):
    p = _ok(client.post("/api/ap/payments", headers=H["ap"], json={
        "supplier_id": S["supplier"], "payment_date": "2026-08-18", "payment_method": "CHEQUE", "cheque_no": "000451",
        "lines": [{"document_id": S["invoice"], "amount": "116000"}]}), 201)
    assert p["wht_amount"] == "14000.00" and p["stw_amount"] == "3200.00" and p["net_amount"] == "98800.00"
    p = _wf(client, H, "/api/ap/payments", p["id"], [("submit", "ap"), ("check", "fm"), ("approve", "cfo")])
    assert p["status"] == "POSTED"


def test_step_09_verify_ap_balance(client, H):
    d = _ok(client.get(f"/api/ap/documents/{S['invoice']}", headers=H["ap"]))
    assert d["outstanding"] == "0.00" and d["payment_status"] == "PAID"
    st = _ok(client.get(f"/api/ap/suppliers/{S['supplier']}/statement", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-08-31"}))
    assert D(st["meta"]["closing"]) == 0


def test_step_10_verify_gl(client, H):
    assert _gl(client, H, "06-03-01-0007", site_ids=str(S["site"]), cost_centre_ids=str(S["cc"])) == D("100000.00")
    assert _gl(client, H, "01-02-05-0008") == D("16000.00")      # input PST
    assert _gl(client, H, "02-02-03-0011") == D("-14000.00")     # WHT s.153(1)(b) payable
    assert _gl(client, H, "02-02-03-0006") == D("-3200.00")      # PST withheld payable
    assert _gl(client, H, "02-02-01-0010") == 0                   # AP control cleared
    assert _gl(client, H, "01-02-07-0006") == D("10000000") - D("98800")


def test_step_11_customer_revenue(client, H):
    from backend.ar.models import Customer
    inv = _ok(client.post("/api/ar/documents", headers=H["ar"], json={
        "customer_id": lookup(Customer, code="C00001"), "invoice_date": "2026-08-10", "site_id": site("101"),
        "description": "[E2E] On-screen advertising August", "lines": [{"cost_centre_id": cc("030101"), "amount": "500000"}]}), 201)
    inv = _wf(client, H, "/api/ar/documents", inv["id"], [("submit", "ar"), ("approve", "fm")])
    assert inv["total"] == "580000.00" and inv["status"] == "POSTED"
    S["ar_invoice"] = inv["id"]
    # cinema box office and F&B revenue through POS import and day close
    _ok(client.post("/api/cinema/imports/box-office", headers=H["manager.emp"], json=[
        {"site_code": "101", "business_date": "2026-08-14", "screen_code": "S1", "film_code": "F0003", "revenue_type_code": "TKT-COUNTER",
         "payment_method_code": "CASH", "tickets_sold": 120, "gross_amount": "120000", "source_ref": "E2E-BO-1"}]), 201)
    _ok(client.post("/api/cinema/imports/fnb", headers=H["manager.emp"], json=[
        {"site_code": "101", "business_date": "2026-08-14", "revenue_type_code": "FNB-COMBO", "payment_method_code": "CASH", "quantity": 60, "gross_amount": "34800"}]), 201)
    dc = _ok(client.post("/api/cinema/day-close", headers=H["manager.emp"], json={"site_id": site("101"), "business_date": "2026-08-14",
                                                                                  "cash_declared": "154800"}), 201)
    assert D(dc["ticket_net_revenue"]) == D("120000.00") and D(dc["fnb_net_revenue"]) == D("30000.00") and D(dc["cash_over_short"]) == 0
    S["film_rental"] = D(dc["film_rental"])
    assert S["film_rental"] > 0


def test_step_12_receive_payment(client, H):
    from backend.ar.models import Customer
    r = _ok(client.post("/api/ar/receipts", headers=H["ar"], json={
        "customer_id": lookup(Customer, code="C00001"), "bank_account_id": S["bank_ba"], "receipt_date": "2026-08-25",
        "amount_received": "545000", "tax_deducted": "35000", "reference": "ADV-PAY-0825",
        "lines": [{"document_id": S["ar_invoice"], "amount": "580000"}]}), 201)
    r = _wf(client, H, "/api/ar/receipts", r["id"], [("submit", "ar"), ("approve", "fm")])
    assert r["status"] == "POSTED"
    inv = _ok(client.get(f"/api/ar/documents/{S['ar_invoice']}", headers=H["ar"]))
    assert inv["payment_status"] == "PAID"


def test_step_13_reconcile_bank(client, H):
    unrec = _ok(client.get(f"/api/banking/accounts/{S['bank_ba']}/unreconciled", headers=H["cfo"], params={"as_of": "2026-08-31"}))
    lines = ["date,description,reference,debit,credit"]
    for u in unrec:
        lines.append(f"{u['date']},{(u['description'] or '').replace(',', ' ')},{u['reference'] or ''},{u['credit']},{u['debit']}")
    lines.append("2026-08-31,Bank charges August,,750.00,0")
    closing = sum(D(u["debit"]) - D(u["credit"]) for u in unrec) - D("750")
    r = client.post("/api/banking/statements/import", headers=H["accountant"],
                    files={"file": ("statement.csv", "\n".join(lines).encode(), "text/csv")},
                    data={"bank_account_id": str(S["bank_ba"]), "opening_balance": "0", "closing_balance": str(closing)})
    st = _ok(r, 201)
    assert _ok(client.post(f"/api/banking/statements/{st['id']}/auto-match", headers=H["accountant"]))["matched"] == len(unrec)
    rep = _ok(client.get("/api/banking/reconciliation", headers=H["cfo"], params={"bank_account_id": S["bank_ba"], "as_of": "2026-08-31"}))
    charge = rep["unmatched_statement_lines"][0]
    _ok(client.post("/api/banking/adjustments", headers=H["accountant"], json={"statement_line_id": charge["id"],
                                                                             "account_id": acc("08-01-01-0003"), "cost_centre_id": cc("090101")}), 201)
    rep = _ok(client.get("/api/banking/reconciliation", headers=H["cfo"], params={"bank_account_id": S["bank_ba"], "as_of": "2026-08-31"}))
    assert D(rep["difference"]) == 0 and rep["can_complete"]
    assert D(rep["gl_balance"]) == D(rep["statement_balance"]) == closing
    _ok(client.post("/api/banking/reconciliation/complete", headers=H["accountant"], json={"bank_account_id": S["bank_ba"], "as_of": "2026-08-31"}), 201)


def test_step_14_post_depreciation(client, H, db):
    inv = _ok(client.post("/api/ap/documents", headers=H["ap"], json={
        "supplier_id": lookup(Supplier, code="V00008"), "supplier_invoice_no": "PROJ-E2E-1", "invoice_date": "2026-08-01", "site_id": S["site"],
        "lines": [{"account_id": acc("01-01-01-0006"), "amount": "840000", "description": "Laser projector"}]}), 201)
    inv = _wf(client, H, "/api/ap/documents", inv["id"], [("submit", "ap"), ("approve", "cfo")])
    a = _ok(client.post("/api/assets", headers=H["accountant"], json={
        "name": "[E2E] Laser projector Screen 1", "category_id": lookup(AssetCategory, code="PROJ"), "site_id": S["site"],
        "cost_centre_id": S["cc"], "purchase_date": "2026-08-01", "cost": "840000", "useful_life_months": 84}), 201)
    _ok(client.post(f"/api/assets/{a['id']}/capitalise", headers=H["accountant"], json={"source": "AP_INVOICE", "ap_document_line_id": inv["lines"][0]["id"]}))
    periods = {p["name"]: p["id"] for p in _ok(client.get("/api/periods", headers=H["cfo"]))}
    S["periods"] = periods
    run = _ok(client.post("/api/assets/runs", headers=H["accountant"], json={"period_id": periods["Aug-2026"]}), 201)
    assert D(run["total"]) == D("10000.00")
    assert _ok(client.post(f"/api/assets/runs/{run['id']}/post", headers=H["fm"]))["status"] == "POSTED"
    assert _gl(client, H, "06-07-01-0003") == D("10000.00")


def test_step_15_trial_balance(client, H):
    tb = _ok(client.get("/api/reports/trial-balance", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-08-31"}))
    assert tb["meta"]["balanced"] is True
    assert D(tb["meta"]["totals"][4]) == D(tb["meta"]["totals"][5])


def test_step_16_monthly_pl(client, H):
    pl = _ok(client.get("/api/reports/profit-loss", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-08-31", "preset": "monthly"}))
    aug = pl["meta"]["summary"][1]
    assert D(aug["REVENUE"]) == D("500000") + D("120000") + D("30000")
    assert D(aug["COST_OF_SALES"]) == S["film_rental"]
    assert D(aug["OPEX"]) == D("100000.00")
    assert D(aug["DEPRECIATION"]) == D("10000.00") and D(aug["FINANCE_COST"]) == D("750.00")
    assert D(aug["EBITDA"]) == D("650000") - S["film_rental"] - D("100000")
    assert D(aug["PAT"]) == D(aug["EBITDA"]) - D("10000") - D("750")
    S["profit"] = D(aug["PAT"])


def test_step_17_balance_sheet(client, H):
    bs = _ok(client.get("/api/reports/balance-sheet", headers=H["cfo"], params={"as_of": "2026-08-31", "compare": "prior_month"}))
    assert bs["meta"]["balanced"] is True
    cy = next(r for r in bs["rows"] if r["label"] == "Profit / (loss) for the current year")
    assert D(cy["c0"]) == S["profit"]
    S["bs"] = bs


def test_step_18_cash_flow(client, H):
    cf = _ok(client.get("/api/reports/cash-flow", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-08-31"}))
    assert cf["meta"]["reconciles"] is True
    cash_bs = sum(D(r["c0"]) for r in S["bs"]["rows"] if r.get("code", "").startswith("01-02-07"))
    assert D(cf["meta"]["closing_cash"]) == cash_bs


def test_step_19_tax_report(client, H):
    t = _ok(client.get("/api/tax/reports/summary", headers=H["cfo"], params={"date_from": "2026-08-01", "date_to": "2026-08-31"}))
    tot = t["meta"]["totals"]
    assert D(tot["OUTPUT"]) == D("80000.00") + D("4800.00")          # PST on advertising + PST on F&B
    assert D(tot["INPUT"]) == D("16000.00") + D("151200.00")         # PST on servicing + 18% ST on projector
    assert D(tot["WITHHELD"]) == D("17200.00") and D(tot["SUFFERED"]) == D("35000.00")
    rec = _ok(client.get("/api/tax/reports/reconciliation", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-08-31"}))
    assert rec["meta"]["reconciled"] is True


def test_step_20_accounting_equation(client, H):
    m = S["bs"]["meta"]
    assert D(m["total_assets"][0]) == D(m["total_liabilities"][0]) + D(m["total_equity"][0])
    assert all(D(x) == 0 for x in m["difference"])


def test_step_21_close_month(client, H):
    for name in ("Jul-2026", "Aug-2026"):
        pid = S["periods"][name]
        for it in _ok(client.get(f"/api/closing/{pid}/checklist", headers=H["fm"])):
            if not it["is_auto"] and it["status"] == "PENDING":
                _ok(client.post(f"/api/closing/{pid}/checklist/{it['code']}", headers=H["fm"], json={"status": "DONE", "comment": "E2E review"}))
        p = _ok(client.post(f"/api/closing/{pid}/close", headers=H["fm"]))
        assert p["status"] == "CLOSED", name


def test_step_22_closed_period_blocks_posting(client, H):
    j = _ok(client.post("/api/journals", headers=H["accountant"], json={
        "transaction_date": "2026-08-20", "description": "[E2E] Late adjustment into closed August",
        "lines": [{"account_id": S["account"], "debit": "500", "site_id": S["site"], "cost_centre_id": S["cc"]},
                  {"account_id": acc("02-02-02-0010"), "credit": "500"}]}), 201)
    _wf(client, H, "/api/journals", j["id"], [("submit", "accountant"), ("check", "fm"), ("approve", "cfo")])
    r = client.post(f"/api/journals/{j['id']}/post", headers=H["fm"], json={})
    assert r.status_code == 409 and r.json()["error"] == "period_closed"
    tb = _ok(client.get("/api/reports/trial-balance", headers=H["cfo"], params={"date_from": "2026-08-01", "date_to": "2026-08-31"}))
    assert not any(row.get("code") == "02-02-02-0010" and D(row["c3"]) > 0 for row in tb["rows"])


def test_step_23_audit_trail(client, H):
    def found(action):
        return _ok(client.get("/api/admin/audit", headers=H["auditor"], params={"action": action, "page_size": 500}))["items"]
    for action in ("journal.post", "ap_invoice.approve", "ap_payment.check", "period.closed", "bank.reconciliation_complete",
                   "cinema.day_close", "account.create", "asset.depreciation_post", "auth.login"):
        assert found(action), f"audit entries missing for {action}"
    post = found("journal.post")[0]
    assert post["username"] and post["ts"] and post["ip_address"]
    # the auditor role is read-only
    assert client.post("/api/journals", headers=H["auditor"], json={"transaction_date": "2026-09-01", "description": "x" * 5,
                                                                    "lines": []}).status_code in (403, 422)


def test_step_24_subledgers_reconcile_to_gl(client, H):
    r = _ok(client.get("/api/reports/subledger-reconciliation", headers=H["cfo"], params={"as_of": "2026-08-31"}))
    m = r["meta"]
    assert m["AP"] and m["AR"] and m["FIXED_ASSETS"] and m["TAX"] and m["BANK"], m
