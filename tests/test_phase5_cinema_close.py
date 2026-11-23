"""Phase 5: cinema revenue accounting, collections, distributor settlement, management reports, dashboard, month-end."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.accounting.models import AccountingPeriod
from backend.ap.models import Supplier
from backend.banking.models import BankAccount
from backend.cinema.models import PaymentMethod
from tests.helpers import acc, lookup, site

D = Decimal


@pytest.fixture(scope="module")
def ids(client):
    return dict(emp=site("101"), col=lookup(BankAccount, code="BNK-COL"), dist1=lookup(Supplier, code="V00001"),
                gateway=lookup(PaymentMethod, code="GATEWAY"), card=lookup(PaymentMethod, code="CARD-A"))


def _gl(client, H, code, date_to="2026-10-31", **params):
    r = client.get("/api/reports/gl", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": date_to,
                                                                  "account_ids": str(acc(code)), **params})
    return D(r.json()["closing"])


BO = [
    {"site_code": "101", "business_date": "2026-10-03", "screen_code": "S1", "film_code": "F0001", "show_date": "2026-10-03",
     "show_time": "19:00", "revenue_type_code": "TKT-COUNTER", "payment_method_code": "CASH", "tickets_sold": 100,
     "complimentary_tickets": 4, "complimentary_value": "4000", "refund_tickets": 1, "gross_amount": "100000",
     "discount_amount": "5000", "refund_amount": "1000", "source_ref": "POS-EMP-0001"},
    {"site_code": "101", "business_date": "2026-10-03", "screen_code": "S1", "film_code": "F0001", "show_date": "2026-10-03",
     "show_time": "19:00", "revenue_type_code": "TKT-ONLINE", "payment_method_code": "GATEWAY", "tickets_sold": 50,
     "gross_amount": "60000", "source_ref": "POS-EMP-0002"},
    {"site_code": "101", "business_date": "2026-10-03", "screen_code": "S2", "film_code": "F0002", "show_date": "2026-10-10",
     "show_time": "21:00", "revenue_type_code": "TKT-ONLINE", "payment_method_code": "CARD-A", "tickets_sold": 20,
     "gross_amount": "24000", "source_ref": "POS-EMP-0003"},
]
FNB = [
    {"site_code": "101", "business_date": "2026-10-03", "revenue_type_code": "FNB-COMBO", "payment_method_code": "CASH",
     "quantity": 40, "gross_amount": "23200"},
    {"site_code": "101", "business_date": "2026-10-03", "revenue_type_code": "FNB-BEV", "payment_method_code": "CARD-A",
     "quantity": 50, "gross_amount": "11600"},
]


def test_import_validation(client, H):
    bad = [dict(BO[0], film_code="NOPE")]
    r = client.post("/api/cinema/imports/box-office", headers=H["manager.emp"], json=bad)
    assert r.status_code == 422 and r.json()["error"] == "import_failed"
    grand = [dict(BO[0], site_code="103", screen_code="S1", source_ref="X1")]
    r = client.post("/api/cinema/imports/box-office", headers=H["manager.emp"], json=grand)
    assert r.status_code == 422 and "not authorised" in r.json()["details"][0]


def test_import_and_day_close(client, H, ids):
    assert client.post("/api/cinema/imports/box-office", headers=H["manager.emp"], json=BO).status_code == 201
    assert client.post("/api/cinema/imports/fnb", headers=H["manager.emp"], json=FNB).status_code == 201
    r = client.post("/api/cinema/imports/box-office", headers=H["manager.emp"], json=BO[:1])
    assert r.status_code == 422  # duplicate POS reference
    prev = client.get("/api/cinema/day-close/preview", headers=H["manager.emp"], params={"site_id": ids["emp"], "business_date": "2026-10-03"}).json()
    assert prev["tickets"] == 170 and D(prev["collections"]["CASH"]) == D("117200")
    r = client.post("/api/cinema/day-close", headers=H["manager.emp"], json={"site_id": ids["emp"], "business_date": "2026-10-03",
                                                                             "cash_declared": "117000"})
    assert r.status_code == 201, r.text
    dc = r.json()
    assert D(dc["ticket_net_revenue"]) == D("154000.00") and D(dc["deferred_amount"]) == D("24000.00")
    assert D(dc["fnb_net_revenue"]) == D("30000.00") and D(dc["tax_total"]) == D("4800.00")
    assert D(dc["film_rental"]) == D("77000.00") and D(dc["cash_over_short"]) == D("-200.00")
    assert _gl(client, H, "04-01-01-0001") == D("-100000.00")
    assert _gl(client, H, "04-01-02-0001") == D("5000.00")
    assert _gl(client, H, "04-01-01-0002") == D("-60000.00")
    assert _gl(client, H, "02-02-02-0012") == D("-24000.00")
    assert _gl(client, H, "02-02-03-0002") == D("-4800.00")
    assert _gl(client, H, "05-01-01-0001") == D("77000.00")
    assert _gl(client, H, "01-02-07-0002") == D("93800.00")   # box office cash after the 200 shortage
    assert _gl(client, H, "01-02-07-0003") == D("23200.00")
    assert _gl(client, H, "06-04-02-0004") == D("200.00")
    # dimensions: film revenue can be reported per film
    r = client.post("/api/cinema/day-close", headers=H["manager.emp"], json={"site_id": ids["emp"], "business_date": "2026-10-03"})
    assert r.status_code == 409


def test_advance_sales_released_on_show_date(client, H, ids):
    r = client.post("/api/cinema/day-close", headers=H["manager.emp"], json={"site_id": ids["emp"], "business_date": "2026-10-10"})
    assert r.status_code == 201, r.text
    dc = r.json()
    assert D(dc["released_amount"]) == D("24000.00") and D(dc["film_rental"]) == D("10800.00")
    assert _gl(client, H, "02-02-02-0012") == 0
    assert _gl(client, H, "04-01-01-0002") == D("-84000.00")


def test_settlements_and_collections_reconciliation(client, H, ids):
    batches = client.get("/api/cinema/collections", headers=H["cfo"], params={"status": "OPEN"}).json()
    assert {(b["payment_method_id"], b["expected_amount"]) for b in batches} == {(ids["gateway"], "60000.00"), (ids["card"], "35600.00")}
    r = client.post("/api/cinema/settlements", headers=H["accountant"], json={
        "payment_method_id": ids["gateway"], "bank_account_id": ids["col"], "settlement_date": "2026-10-05",
        "gross_amount": "60000", "fee_amount": "1500", "tax_deducted": "600", "reference": "GW-STL-1001"})
    assert r.status_code == 201, r.text
    assert D(r.json()["net_amount"]) == D("57900.00")
    r = client.post("/api/cinema/settlements", headers=H["accountant"], json={
        "payment_method_id": ids["card"], "bank_account_id": ids["col"], "settlement_date": "2026-10-05",
        "gross_amount": "20000", "fee_amount": "400", "reference": "CARD-STL-77"})
    assert r.status_code == 201
    r = client.post("/api/cinema/settlements", headers=H["accountant"], json={
        "payment_method_id": ids["card"], "bank_account_id": ids["col"], "settlement_date": "2026-10-06",
        "gross_amount": "99999", "reference": "too much"})
    assert r.status_code == 422 and r.json()["error"] == "over_settlement"
    assert _gl(client, H, "01-02-02-0003") == 0                       # gateway receivable cleared
    assert _gl(client, H, "01-02-02-0001") == D("15600.00")           # card clearing outstanding
    assert _gl(client, H, "01-02-07-0007") == D("77500.00")           # 57,900 + 19,600
    rep = client.get("/api/cinema/reports/collections-reconciliation", headers=H["cfo"],
                     params={"date_from": "2026-10-01", "date_to": "2026-10-31"}).json()
    assert D(rep["meta"]["open_difference"]) == D("15600.00")
    statuses = {r["method"]: r["status"] for r in rep["rows"] if r.get("status")}
    assert statuses["Online payment gateway"] == "SETTLED" and statuses["Card - acquirer bank A"] == "PARTIAL"
    assert statuses["Cash (counted)"] == "OVER/SHORT"
    gl = client.get("/api/cinema/reports/gl-reconciliation", headers=H["cfo"], params={"date_from": "2026-10-01", "date_to": "2026-10-31"}).json()
    assert gl["meta"]["reconciled"], gl


def test_distributor_settlement_creates_ap_invoice(client, H, ids):
    r = client.post("/api/cinema/distributor-settlements", headers=H["accountant"], json={
        "distributor_id": ids["dist1"], "period_from": "2026-10-01", "period_to": "2026-10-31", "reference": "SSD-OCT-26"})
    assert r.status_code == 201, r.text
    s = r.json()
    assert D(s["accrued_amount"]) == D("77000.00") and D(s["net_box_office"]) == D("154000.00")
    r = client.post(f"/api/cinema/distributor-settlements/{s['id']}/invoice", headers=H["ap"],
                    json={"invoice_no": "SSD-INV-1026", "invoice_date": "2026-10-31"})
    assert r.status_code == 200, r.text
    doc_id = r.json()["ap_document_id"]
    for a, u in (("submit", "ap"), ("approve", "fm")):
        assert client.post(f"/api/ap/documents/{doc_id}/{a}", headers=H[u], json={}).status_code == 200
    assert _gl(client, H, "02-02-02-0006") == D("-10800.00")   # only Lollywood's F0002 rental still accrued
    assert _gl(client, H, "02-02-01-0001") == D("-77000.00")   # distributor payable
    r = client.post("/api/cinema/distributor-settlements", headers=H["accountant"], json={
        "distributor_id": ids["dist1"], "period_from": "2026-10-01", "period_to": "2026-10-31"})
    assert r.status_code == 422  # nothing left to settle - no double settlement


def test_management_reports_and_kpis(client, H):
    r = client.get("/api/cinema/reports/revenue", headers=H["cfo"], params={"date_from": "2026-10-01", "date_to": "2026-10-31",
                                                                            "group_by": "film"}).json()
    films = {x["label"]: x for x in r["rows"]}
    assert films["[DEMO] The Northern Star"]["tickets"] == 150 and D(films["[DEMO] The Northern Star"]["ticket_net"]) == D("154000.00")
    k = client.get("/api/cinema/reports/kpis", headers=H["cfo"], params={"date_from": "2026-10-01", "date_to": "2026-10-31"}).json()
    assert k["admissions"] == 170 and D(k["average_ticket_price"]) == D("1047.06") and D(k["spend_per_head"]) == D("176.47")
    for g in ("site", "screen", "show", "payment_method", "revenue_type", "date", "distributor"):
        assert client.get("/api/cinema/reports/revenue", headers=H["cfo"], params={
            "date_from": "2026-10-01", "date_to": "2026-10-31", "group_by": g}).status_code == 200
    # film dimension drill-down in the GL
    films_dv = client.get("/api/dimension-values", headers=H["cfo"], params={"q": "F0001"}).json()["items"][0]["id"]
    g = client.get("/api/reports/gl", headers=H["cfo"], params={"date_from": "2026-10-01", "date_to": "2026-10-31",
                                                                 "account_prefix": "04-01", "dimension_value_ids": str(films_dv)}).json()
    assert D(g["closing"]) == D("-154000.00")


def test_cfo_dashboard_and_pack(client, H, db):
    d = client.get("/api/cfo/dashboard", headers=H["cfo"], params={"date_from": "2026-10-01", "date_to": "2026-10-31"}).json()
    assert D(d["kpis"]["revenue"]) == D("208000.00")
    assert D(d["revenue_by_stream"]["TICKETING"]) == D("178000.00") and D(d["revenue_by_stream"]["FNB"]) == D("30000.00")
    assert D(d["kpis"]["ebitda"]) == D("208000") - D("87800") - D("200") - D("1900")
    d2 = client.get("/api/cfo/dashboard", headers=H["cfo"], params={"date_from": "2026-10-01", "date_to": "2026-10-31",
                                                                    "revenue_stream": "FNB"}).json()
    assert D(d2["kpis"]["revenue"]) == D("30000.00")
    assert client.get("/api/cfo/ratios", headers=H["cfo"], params={"as_of": "2026-10-31"}).status_code == 200
    pid = db.scalar(select(AccountingPeriod.id).where(AccountingPeriod.name == "Oct-2026"))
    for fmt in ("pdf", "xlsx"):
        r = client.get("/api/cfo/pack", headers=H["cfo"], params={"period_id": pid, "format": fmt})
        assert r.status_code == 200 and len(r.content) > 5000, r.text[:300]


def _close(client, H, pid):
    items = client.get(f"/api/closing/{pid}/checklist", headers=H["fm"]).json()
    for it in items:
        if not it["is_auto"] and it["status"] == "PENDING":
            assert client.post(f"/api/closing/{pid}/checklist/{it['code']}", headers=H["fm"],
                               json={"status": "DONE", "comment": "reviewed"}).status_code == 200
    return client.post(f"/api/closing/{pid}/close", headers=H["fm"])


def test_month_end_close_and_reopen(client, H, ids, db):
    periods = {p["name"]: p["id"] for p in client.get("/api/periods", headers=H["cfo"]).json()}
    for name in ("Jul-2026", "Aug-2026", "Sep-2026"):
        r = _close(client, H, periods[name])
        assert r.status_code == 200, r.text
    r = _close(client, H, periods["Oct-2026"])
    assert r.status_code == 422 and r.json()["error"] == "checklist_incomplete"
    assert any("bank" in d.lower() for d in r.json()["details"])
    # reconcile the collections bank account for October
    unrec = client.get(f"/api/banking/accounts/{ids['col']}/unreconciled", headers=H["cfo"]).json()
    lines = [{"txn_date": u["date"], "description": u["description"], "reference": u["reference"], "debit": u["credit"], "credit": u["debit"]} for u in unrec]
    st = client.post("/api/banking/statements", headers=H["accountant"], json={"bank_account_id": ids["col"], "opening_balance": "0", "lines": lines}).json()
    client.post(f"/api/banking/statements/{st['id']}/auto-match", headers=H["accountant"])
    assert client.post("/api/banking/reconciliation/complete", headers=H["accountant"],
                       json={"bank_account_id": ids["col"], "as_of": "2026-10-31"}).status_code == 201
    r = _close(client, H, periods["Oct-2026"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CLOSED"
    # posting into the closed period is blocked
    r = client.post("/api/ap/documents", headers=H["ap"], json={
        "supplier_id": lookup(Supplier, code="V00006"), "supplier_invoice_no": "LATE-OCT", "invoice_date": "2026-10-20",
        "site_id": ids["emp"], "lines": [{"account_id": acc("06-03-01-0001"), "cost_centre_id": lookup(__import__("backend.masters.models", fromlist=["CostCentre"]).CostCentre, code="050102"), "amount": "1000"}]})
    doc = r.json()
    client.post(f"/api/ap/documents/{doc['id']}/submit", headers=H["ap"], json={})
    r = client.post(f"/api/ap/documents/{doc['id']}/approve", headers=H["fm"], json={})
    assert r.status_code == 409 and r.json()["error"] == "period_closed"
    # reopening needs CFO authority and a reason; it is audited
    assert client.post(f"/api/closing/{periods['Oct-2026']}/reopen", headers=H["fm"], json={"reason": "Late invoice"}).status_code == 403
    assert client.post(f"/api/closing/{periods['Sep-2026']}/reopen", headers=H["cfo"], json={"reason": "Wrong order"}).status_code == 409
    r = client.post(f"/api/closing/{periods['Oct-2026']}/reopen", headers=H["cfo"], json={"reason": "Late maintenance invoice"})
    assert r.status_code == 200 and r.json()["status"] == "OPEN"
    audit = client.get("/api/admin/audit", headers=H["auditor"], params={"action": "period.open"}).json()["items"]
    assert audit and audit[0]["notes"] == "Late maintenance invoice" and audit[0]["username"] == "cfo"
