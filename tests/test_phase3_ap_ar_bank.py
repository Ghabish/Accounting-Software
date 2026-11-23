"""Phase 3: AP, AR, cash and bank."""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.ap.models import Supplier
from backend.ar.models import Customer
from backend.banking.models import BankAccount
from tests.helpers import acc, cc, lookup, site

D = Decimal


@pytest.fixture(scope="module")
def ids(client):
    return dict(landlord=lookup(Supplier, code="V00004"), maint=lookup(Supplier, code="V00006"),
                capex=lookup(Supplier, code="V00008"), fnb=lookup(Supplier, code="V00003"),
                adv_cus=lookup(Customer, code="C00001"), corp=lookup(Customer, code="C00003"),
                bank=lookup(BankAccount, code="BNK-OPS"), col=lookup(BankAccount, code="BNK-COL"),
                petty_emp=lookup(BankAccount, code="PETTY-101"), petty_grand=lookup(BankAccount, code="PETTY-103"),
                emp=site("101"), grand=site("103"))


def _approve_doc(client, H, base, doc_id, steps=(("submit", "ap"), ("approve", "fm"))):
    r = None
    for action, user in steps:
        r = client.post(f"{base}/{doc_id}/{action}", headers=H[user], json={})
        assert r.status_code == 200, f"{action}: {r.text}"
    return r.json()


def _gl(client, H, code, date_to="2026-12-31", **params):
    r = client.get("/api/reports/gl", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": date_to,
                                                                  "account_ids": str(acc(code)), **params})
    return D(r.json()["closing"])


def test_ap_invoice_posts_with_input_tax(client, H, ids):
    body = {"supplier_id": ids["landlord"], "supplier_invoice_no": "RENT-AUG-26", "invoice_date": "2026-08-01",
            "site_id": ids["emp"], "description": "Cinema rent August (demo)",
            "lines": [{"account_id": acc("06-02-01-0001"), "cost_centre_id": cc("010101"), "amount": "100000"}]}
    r = client.post("/api/ap/documents", headers=H["ap"], json=body)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["total"] == "116000.00" and doc["tax_total"] == "16000.00" and doc["due_date"] == "2026-08-31"
    doc = _approve_doc(client, H, "/api/ap/documents", doc["id"])
    assert doc["status"] == "POSTED" and doc["journal_id"]
    pytest.landlord_inv = doc["id"]
    assert _gl(client, H, "02-02-01-0003") == D("-116000.00")
    assert _gl(client, H, "01-02-05-0008") == D("16000.00")


def test_duplicate_supplier_invoice_blocked(client, H, ids):
    body = {"supplier_id": ids["landlord"], "supplier_invoice_no": "rent-aug-26", "invoice_date": "2026-08-02",
            "site_id": ids["emp"], "lines": [{"account_id": acc("06-02-01-0001"), "cost_centre_id": cc("010101"), "amount": "1"}]}
    r = client.post("/api/ap/documents", headers=H["ap"], json=body)
    assert r.status_code == 409 and r.json()["error"] == "duplicate_invoice"


def test_payment_with_wht_and_stw(client, H, ids):
    body = {"supplier_id": ids["landlord"], "payment_date": "2026-08-10", "cheque_no": "100201",
            "lines": [{"document_id": pytest.landlord_inv, "amount": "116000"}]}
    prev = client.post("/api/ap/payments/preview", headers=H["ap"], json=body).json()
    assert D(prev["wht"]) == D("15000") and D(prev["stw"]) == D("3200") and D(prev["net"]) == D("97800")
    r = client.post("/api/ap/payments", headers=H["ap"], json=body)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["bank_account_id"] == ids["bank"]  # default payment bank
    p = _approve_doc(client, H, "/api/ap/payments", p["id"], (("submit", "ap"), ("check", "fm"), ("approve", "cfo")))
    assert p["status"] == "POSTED"
    inv = client.get(f"/api/ap/documents/{pytest.landlord_inv}", headers=H["ap"]).json()
    assert inv["payment_status"] == "PAID" and inv["outstanding"] == "0.00"
    assert _gl(client, H, "02-02-01-0003") == 0
    assert _gl(client, H, "02-02-03-0009") == D("-15000.00")   # WHT s.155 payable
    assert _gl(client, H, "02-02-03-0006") == D("-3200.00")    # STW PRA payable
    assert _gl(client, H, "01-02-07-0006") == D("-97800.00")   # bank


def test_partial_payment_taxed_on_amount_paid(client, H, ids):
    body = {"supplier_id": ids["maint"], "supplier_invoice_no": "AMC-0091", "invoice_date": "2026-08-05", "site_id": ids["emp"],
            "lines": [{"account_id": acc("06-03-01-0001"), "cost_centre_id": cc("050102"), "amount": "50000"}]}
    inv = _approve_doc(client, H, "/api/ap/documents", client.post("/api/ap/documents", headers=H["ap"], json=body).json()["id"])
    assert inv["total"] == "58000.00"
    p = client.post("/api/ap/payments", headers=H["ap"], json={"supplier_id": ids["maint"], "payment_date": "2026-08-20",
                                                               "lines": [{"document_id": inv["id"], "amount": "29000"}]}).json()
    assert p["wht_amount"] == "3500.00" and p["stw_amount"] == "800.00" and p["net_amount"] == "24700.00"
    _approve_doc(client, H, "/api/ap/payments", p["id"], (("submit", "ap"), ("check", "fm"), ("approve", "cfo")))
    inv = client.get(f"/api/ap/documents/{inv['id']}", headers=H["ap"]).json()
    assert inv["payment_status"] == "PARTIAL" and inv["outstanding"] == "29000.00"
    # overpayment rejected
    r = client.post("/api/ap/payments", headers=H["ap"], json={"supplier_id": ids["maint"], "payment_date": "2026-08-21",
                                                               "lines": [{"document_id": inv["id"], "amount": "29001"}]})
    assert r.status_code == 422


def test_rate_override_requires_authority_and_reason(client, H, ids):
    inv_id = client.get("/api/ap/documents", headers=H["ap"], params={"supplier_id": ids["maint"]}).json()["items"][0]["id"]
    body = {"supplier_id": ids["maint"], "payment_date": "2026-08-22",
            "lines": [{"document_id": inv_id, "amount": "1000", "override_rate": "0.05", "override_reason": "certificate"}]}
    assert client.post("/api/ap/payments", headers=H["ap"], json=body).status_code == 403
    body["lines"][0]["override_reason"] = None
    assert client.post("/api/ap/payments", headers=H["fm"], json=body).status_code == 422


def test_advance_and_application(client, H, ids):
    p = client.post("/api/ap/payments", headers=H["ap"], json={"supplier_id": ids["capex"], "payment_date": "2026-08-01",
                                                               "is_advance": True, "lines": [{"amount": "1000000"}]}).json()
    assert p["wht_amount"] == "75000.00" and p["net_amount"] == "925000.00"
    p = _approve_doc(client, H, "/api/ap/payments", p["id"], (("submit", "ap"), ("check", "fm"), ("approve", "cfo")))
    assert p["advance_unapplied"] == "1000000.00"
    assert _gl(client, H, "01-01-02-0003") == D("1000000.00")
    inv = client.post("/api/ap/documents", headers=H["ap"], json={
        "supplier_id": ids["capex"], "supplier_invoice_no": "PROJ-7781", "invoice_date": "2026-08-25", "site_id": ids["emp"],
        "description": "Laser projector - Screen 1 (demo)",
        "lines": [{"account_id": acc("01-01-01-0006"), "amount": "2000000"}]}).json()
    inv = _approve_doc(client, H, "/api/ap/documents", inv["id"], (("submit", "ap"), ("approve", "cfo")))
    assert inv["total"] == "2360000.00"
    pytest.projector_invoice = inv["id"]
    r = client.post(f"/api/ap/payments/{p['id']}/apply-advance", headers=H["fm"],
                    json={"invoice_id": inv["id"], "amount": "1000000", "date": "2026-08-25"})
    assert r.status_code == 200, r.text
    inv = client.get(f"/api/ap/documents/{inv['id']}", headers=H["ap"]).json()
    assert inv["outstanding"] == "1360000.00"
    assert _gl(client, H, "01-01-02-0003") == 0


def test_credit_note_auto_allocates(client, H, ids):
    inv = client.post("/api/ap/documents", headers=H["ap"], json={
        "supplier_id": ids["fnb"], "supplier_invoice_no": "FNB-551", "invoice_date": "2026-08-03", "site_id": ids["emp"],
        "lines": [{"account_id": acc("01-02-01-0001"), "amount": "20000"}]}).json()
    inv = _approve_doc(client, H, "/api/ap/documents", inv["id"])
    cn = client.post("/api/ap/documents", headers=H["ap"], json={
        "doc_type": "CREDIT_NOTE", "supplier_id": ids["fnb"], "supplier_invoice_no": "CN-551", "invoice_date": "2026-08-06",
        "site_id": ids["emp"], "related_document_id": inv["id"],
        "lines": [{"account_id": acc("01-02-01-0001"), "amount": "5000"}]}).json()
    cn = _approve_doc(client, H, "/api/ap/documents", cn["id"])
    assert cn["status"] == "POSTED" and cn["outstanding"] == "0.00"
    inv = client.get(f"/api/ap/documents/{inv['id']}", headers=H["ap"]).json()
    assert inv["outstanding"] == "17700.00" and inv["payment_status"] == "PARTIAL"


def test_ap_aging_and_reconciliation(client, H, ids):
    ag = client.get("/api/ap/aging", headers=H["cfo"], params={"as_of": "2026-10-15"}).json()
    total = ag["rows"][-1]
    assert D(total["total"]) == D("29000") + D("1360000") + D("17700")
    rec = client.get("/api/ap/reconciliation", headers=H["cfo"], params={"as_of": "2026-10-15"}).json()
    assert rec["meta"]["reconciled"] is True, rec
    st = client.get(f"/api/ap/suppliers/{ids['maint']}/statement", headers=H["cfo"],
                    params={"date_from": "2026-07-01", "date_to": "2026-12-31"}).json()
    assert D(st["meta"]["closing"]) == D("29000.00")


def test_ap_invoice_reversal_blocked_when_paid(client, H, ids):
    r = client.post(f"/api/ap/documents/{pytest.landlord_inv}/reverse", headers=H["cfo"],
                    json={"reversal_date": "2026-08-31", "reason": "test"})
    assert r.status_code == 409


def test_ar_invoice_and_receipt_with_tax_deducted(client, H, ids):
    inv = client.post("/api/ar/documents", headers=H["ar"], json={
        "customer_id": ids["adv_cus"], "invoice_date": "2026-08-01", "site_id": ids["emp"],
        "description": "On-screen advertising August (demo)",
        "lines": [{"cost_centre_id": cc("030101"), "amount": "500000"}]}).json()
    assert inv["total"] == "580000.00" and inv["tax_total"] == "80000.00"
    inv = _approve_doc(client, H, "/api/ar/documents", inv["id"], (("submit", "ar"), ("approve", "fm")))
    assert inv["status"] == "POSTED"
    assert _gl(client, H, "04-03-01-0001") == D("-500000.00")
    assert _gl(client, H, "02-02-03-0002") == D("-80000.00")
    rec = client.post("/api/ar/receipts", headers=H["ar"], json={
        "customer_id": ids["adv_cus"], "bank_account_id": ids["col"], "receipt_date": "2026-08-28",
        "amount_received": "545000", "tax_deducted": "35000", "lines": [{"document_id": inv["id"], "amount": "580000"}]}).json()
    rec = _approve_doc(client, H, "/api/ar/receipts", rec["id"], (("submit", "ar"), ("approve", "fm")))
    assert rec["status"] == "POSTED"
    assert _gl(client, H, "01-02-02-0006") == 0
    assert _gl(client, H, "01-02-05-0006") == D("35000.00")
    assert _gl(client, H, "01-02-07-0007") == D("545000.00")


def test_ar_advance_and_application(client, H, ids):
    rec = client.post("/api/ar/receipts", headers=H["ar"], json={
        "customer_id": ids["corp"], "bank_account_id": ids["col"], "receipt_date": "2026-09-01",
        "amount_received": "100000", "is_advance": True, "description": "Advance for private screening (demo)"}).json()
    rec = _approve_doc(client, H, "/api/ar/receipts", rec["id"], (("submit", "ar"), ("approve", "fm")))
    assert rec["unapplied_amount"] == "100000.00"
    inv = client.post("/api/ar/documents", headers=H["ar"], json={
        "customer_id": ids["corp"], "invoice_date": "2026-09-10", "site_id": ids["emp"],
        "lines": [{"account_id": acc("04-04-01-0001"), "cost_centre_id": cc("010101"), "amount": "80000", "tax_code_id": None}]}).json()
    inv = _approve_doc(client, H, "/api/ar/documents", inv["id"], (("submit", "ar"), ("approve", "fm")))
    assert inv["total"] == "80000.00"
    r = client.post(f"/api/ar/receipts/{rec['id']}/apply-advance", headers=H["fm"],
                    json={"invoice_id": inv["id"], "amount": "80000", "date": "2026-09-10"})
    assert r.status_code == 200, r.text
    ag = client.get("/api/ar/aging", headers=H["cfo"], params={"as_of": "2026-09-30"}).json()
    assert D(ag["rows"][-1]["unapplied"]) == D("-20000.00")
    rec = client.get("/api/ar/reconciliation", headers=H["cfo"], params={"as_of": "2026-09-30"}).json()
    assert rec["meta"]["reconciled"] is True, rec


def test_cash_voucher_site_restriction_and_transfer(client, H, ids):
    t = client.post("/api/banking/transfers", headers=H["cashier.emp"], json={
        "from_account_id": ids["bank"], "to_account_id": ids["petty_emp"], "transfer_date": "2026-08-02",
        "amount": "50000", "description": "Petty cash imprest Emporium"}).json()
    t = _approve_doc(client, H, "/api/banking/transfers", t["id"], (("submit", "cashier.emp"), ("approve", "fm")))
    assert t["status"] == "POSTED"
    v = client.post("/api/banking/vouchers", headers=H["cashier.emp"], json={
        "direction": "PAYMENT", "bank_account_id": ids["petty_emp"], "voucher_date": "2026-08-05",
        "counterparty": "Local cleaner", "lines": [{"account_id": acc("06-02-03-0002"), "site_id": ids["emp"],
                                                    "cost_centre_id": cc("050301"), "amount": "3000"}]}).json()
    assert v["voucher_type"] == "CPV"
    v = _approve_doc(client, H, "/api/banking/vouchers", v["id"], (("submit", "cashier.emp"), ("approve", "fm")))
    assert v["status"] == "POSTED"
    r = client.post("/api/banking/vouchers", headers=H["cashier.emp"], json={
        "direction": "PAYMENT", "bank_account_id": ids["petty_grand"], "voucher_date": "2026-08-05",
        "lines": [{"account_id": acc("06-02-03-0002"), "site_id": ids["grand"], "cost_centre_id": cc("050301"), "amount": "100"}]})
    assert r.status_code == 403  # cashier is restricted to Emporium
    # vouchers cannot touch AP control accounts
    r = client.post("/api/banking/vouchers", headers=H["fm"], json={
        "direction": "PAYMENT", "bank_account_id": ids["bank"], "voucher_date": "2026-08-05",
        "lines": [{"account_id": acc("02-02-01-0003"), "supplier_id": ids["landlord"], "amount": "100"}]})
    assert r.status_code == 422
    # petty cash cannot go negative (BLOCK)
    v = client.post("/api/banking/vouchers", headers=H["cashier.emp"], json={
        "direction": "PAYMENT", "bank_account_id": ids["petty_emp"], "voucher_date": "2026-08-06",
        "lines": [{"account_id": acc("06-02-03-0002"), "site_id": ids["emp"], "cost_centre_id": cc("050301"), "amount": "60000"}]}).json()
    client.post(f"/api/banking/vouchers/{v['id']}/submit", headers=H["cashier.emp"], json={})
    r = client.post(f"/api/banking/vouchers/{v['id']}/approve", headers=H["fm"], json={})
    assert r.status_code == 422 and r.json()["error"] == "abnormal_balance"


def test_transfer_via_transit(client, H, ids):
    t = client.post("/api/banking/transfers", headers=H["fm"], json={
        "from_account_id": ids["petty_emp"], "to_account_id": ids["col"], "transfer_date": "2026-08-07",
        "amount": "10000", "via_transit": True, "description": "Cash deposited to bank"}).json()
    t = _approve_doc(client, H, "/api/banking/transfers", t["id"], (("submit", "fm"), ("approve", "cfo")))
    assert _gl(client, H, "01-02-07-0005", site_ids=str(ids["emp"])) == D("10000.00")
    r = client.post(f"/api/banking/transfers/{t['id']}/receive", headers=H["cfo"], json={"received_date": "2026-08-08"})
    assert r.status_code == 200, r.text
    assert _gl(client, H, "01-02-07-0005") == 0
    pos = client.get("/api/banking/cash-position", headers=H["cfo"], params={"on_date": "2026-08-08"}).json()
    row = next(r for r in pos["rows"] if r.get("bank_account_id") == ids["petty_emp"])
    assert D(row["c3"]) == D("37000.00")  # 50,000 - 3,000 - 10,000
    tb = client.get("/api/reports/trial-balance", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-12-31"}).json()
    assert tb["meta"]["balanced"]
