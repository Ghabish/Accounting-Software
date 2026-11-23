"""Phase 2: double-entry engine, workflow, reversal, TB, P&L, balance sheet, cash flow, exports."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select, text

from backend.accounting.models import JournalEntry, JournalLine
from backend.core.exceptions import Conflict
from tests.helpers import acc, cc, journal, post_journal, site

D = Decimal


@pytest.fixture(scope="module")
def ids(client):
    return dict(bank=acc("01-02-07-0006"), capital=acc("03-01-01-0001"), tickets=acc("04-01-01-0001"),
                cash_bo=acc("01-02-07-0002"), elec=acc("06-02-02-0001"), accr_util=acc("02-02-02-0007"),
                markup=acc("08-01-01-0001"), loan=acc("02-01-01-0001"), emp=site("101"), ho=site("001"),
                cc_tkt=cc("010201"), cc_ops=cc("010101"), cc_corp=cc("090101"), cc_fin=cc("060201"))


def test_unbalanced_journal_rejected(client, H, ids):
    r = journal(client, H, "accountant", [
        {"account_id": ids["elec"], "debit": "1000", "site_id": ids["emp"], "cost_centre_id": ids["cc_ops"]},
        {"account_id": ids["accr_util"], "credit": "900", "site_id": ids["emp"]}])
    assert r.status_code == 422
    assert any("not balanced" in d for d in r.json()["details"])


def test_line_rules_enforced(client, H, ids):
    # both debit and credit on one line, negative amount, missing site / cost centre on P&L, CC on BS account
    r = journal(client, H, "accountant", [
        {"account_id": ids["elec"], "debit": "100", "credit": "100", "site_id": ids["emp"], "cost_centre_id": ids["cc_ops"]},
        {"account_id": ids["accr_util"], "credit": "0", "site_id": ids["emp"]}])
    assert r.status_code == 422
    r = journal(client, H, "accountant", [{"account_id": ids["elec"], "debit": "-5"},
                                          {"account_id": ids["accr_util"], "credit": "-5"}])
    assert r.status_code == 422
    r = journal(client, H, "accountant", [
        {"account_id": ids["elec"], "debit": "100"},
        {"account_id": ids["bank"], "credit": "100", "cost_centre_id": ids["cc_ops"]}])
    det = " ".join(r.json()["details"])
    assert "site is mandatory" in det and "cost centre is mandatory" in det and "balance sheet account" in det
    # CORP rule: finance cost must use 090101; REQ rule rejects company-level
    r = journal(client, H, "accountant", [
        {"account_id": ids["markup"], "debit": "100", "cost_centre_id": ids["cc_ops"]},
        {"account_id": ids["elec"], "credit": "100", "site_id": ids["emp"], "cost_centre_id": ids["cc_corp"]}])
    det = " ".join(r.json()["details"])
    assert "company-level cost centre (090101)" in det and "not company level" in det


def test_restricted_account_needs_authority(client, H, ids):
    r = journal(client, H, "accountant", [{"account_id": ids["bank"], "debit": "100"},
                                          {"account_id": ids["capital"], "credit": "100"}])
    assert r.status_code == 422 and "restricted" in " ".join(r.json()["details"])


def test_workflow_segregation_and_limits(client, H, ids):
    lines = [{"account_id": ids["bank"], "debit": "50000000"}, {"account_id": ids["capital"], "credit": "50000000"}]
    r = journal(client, H, "fm", lines, date="2026-07-01", description="Share capital injected (demo)")
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    assert client.post(f"/api/journals/{jid}/post", headers=H["cfo"], json={}).status_code == 409  # not approved
    client.post(f"/api/journals/{jid}/submit", headers=H["fm"], json={})
    r = client.post(f"/api/journals/{jid}/check", headers=H["fm"], json={})
    assert r.status_code == 403 and r.json()["error"] == "sod"  # preparer cannot check
    assert client.post(f"/api/journals/{jid}/check", headers=H["accountant"], json={}).status_code == 200
    r = client.post(f"/api/journals/{jid}/approve", headers=H["accountant"], json={})
    assert r.status_code == 403  # no approve permission
    r = client.post(f"/api/journals/{jid}/approve", headers=H["cfo"], json={})
    assert r.status_code == 200
    r = client.post(f"/api/journals/{jid}/post", headers=H["fm"], json={})
    assert r.status_code == 403 and r.json()["error"] == "sod"  # preparer cannot post
    r = client.post(f"/api/journals/{jid}/post", headers=H["cfo"], json={})
    assert r.status_code == 200 and r.json()["status"] == "POSTED" and r.json()["number"].startswith("JV-2627-")


def test_approval_limit_exceeded(client, H, ids):
    lines = [{"account_id": ids["elec"], "debit": "3000000", "site_id": ids["emp"], "cost_centre_id": ids["cc_ops"]},
             {"account_id": ids["accr_util"], "credit": "3000000", "site_id": ids["emp"]}]
    jid = journal(client, H, "accountant", lines, description="Large accrual").json()["id"]
    client.post(f"/api/journals/{jid}/submit", headers=H["accountant"], json={})
    client.post(f"/api/journals/{jid}/check", headers=H["fm"], json={})
    r = client.post(f"/api/journals/{jid}/approve", headers=H["fm"], json={})
    assert r.status_code == 403 and r.json()["error"] == "sod"  # fm checked it
    # reject back to draft with reason, then cancel
    assert client.post(f"/api/journals/{jid}/reject", headers=H["cfo"], json={}).status_code == 422
    assert client.post(f"/api/journals/{jid}/reject", headers=H["cfo"], json={"comment": "too large"}).json()["status"] == "DRAFT"
    assert client.post(f"/api/journals/{jid}/cancel", headers=H["accountant"], json={}).json()["status"] == "CANCELLED"
    # limit: FM (2.5m) cannot approve 3m even when not the checker
    jid = journal(client, H, "accountant", lines, description="Large accrual 2").json()["id"]
    client.post(f"/api/journals/{jid}/submit", headers=H["accountant"], json={})
    client.post(f"/api/journals/{jid}/check", headers=H["cfo"], json={})
    r = client.post(f"/api/journals/{jid}/approve", headers=H["fm"], json={})
    assert r.status_code == 403 and r.json()["error"] == "limit_exceeded"


def test_posting_and_immutability(client, H, ids, db):
    j = post_journal(client, H, [
        {"account_id": ids["cash_bo"], "debit": "250000", "site_id": ids["emp"]},
        {"account_id": ids["tickets"], "credit": "250000", "site_id": ids["emp"], "cost_centre_id": ids["cc_tkt"]}],
        date="2026-07-20", description="Box office takings (demo)")
    assert j["status"] == "POSTED"
    je = db.get(JournalEntry, j["id"])
    line = je.lines[0]
    line.debit = D("1")
    with pytest.raises(Conflict):
        db.flush()
    db.rollback()
    if db.bind.dialect.name == "postgresql":  # database trigger blocks direct SQL too
        with pytest.raises(Exception):
            db.execute(text("UPDATE journal_lines SET debit = 1 WHERE journal_id = :j"), {"j": j["id"]})
            db.flush()
        db.rollback()
        with pytest.raises(Exception):
            db.execute(text("DELETE FROM journal_entries WHERE id = :j"), {"j": j["id"]})
        db.rollback()
    # cannot edit via API
    r = client.put(f"/api/journals/{j['id']}", headers=H["accountant"], json={
        "transaction_date": "2026-07-20", "description": "attempted edit", "lines": [
            {"account_id": ids["cash_bo"], "debit": "1", "site_id": ids["emp"]},
            {"account_id": ids["tickets"], "credit": "1", "site_id": ids["emp"], "cost_centre_id": ids["cc_tkt"]}]})
    assert r.status_code == 409


def test_abnormal_balance_blocked(client, H, ids):
    # cash in hand (BLOCK) cannot go negative at a site
    r = journal(client, H, "accountant", [
        {"account_id": ids["elec"], "debit": "999999999", "site_id": ids["ho"], "cost_centre_id": ids["cc_fin"]},
        {"account_id": acc("01-02-07-0001"), "credit": "999999999", "site_id": ids["ho"]}], description="overdraw cash")
    jid = r.json()["id"]
    client.post(f"/api/journals/{jid}/submit", headers=H["accountant"], json={})
    client.post(f"/api/journals/{jid}/check", headers=H["fm"], json={})
    client.post(f"/api/journals/{jid}/approve", headers=H["cfo"], json={})
    r = client.post(f"/api/journals/{jid}/post", headers=H["fm"], json={})
    assert r.status_code == 422 and r.json()["error"] == "abnormal_balance"


def test_reversal(client, H, ids, db):
    j = post_journal(client, H, [
        {"account_id": ids["elec"], "debit": "40000", "site_id": ids["emp"], "cost_centre_id": ids["cc_ops"]},
        {"account_id": ids["accr_util"], "credit": "40000", "site_id": ids["emp"]}], description="Electricity accrual (demo)")
    r = client.post(f"/api/journals/{j['id']}/reverse/request", headers=H["accountant"],
                    json={"reversal_date": "2026-07-31", "reason": "Booked in error"})
    assert r.status_code == 200, r.text
    rev = r.json()
    assert rev["reversal_of_id"] == j["id"] and rev["lines"][0]["credit"] == "40000.00"
    for action, user in (("submit", "accountant"), ("check", "fm"), ("approve", "cfo"), ("post", "fm")):
        assert client.post(f"/api/journals/{rev['id']}/{action}", headers=H[user], json={}).status_code == 200
    assert client.get(f"/api/journals/{j['id']}", headers=H["cfo"]).json()["status"] == "REVERSED"
    # second reversal not allowed
    r = client.post(f"/api/journals/{j['id']}/reverse/request", headers=H["accountant"],
                    json={"reversal_date": "2026-07-31", "reason": "again"})
    assert r.status_code == 409


def test_accrual_auto_reverses(client, H, ids):
    j = post_journal(client, H, [
        {"account_id": ids["elec"], "debit": "12000", "site_id": ids["emp"], "cost_centre_id": ids["cc_ops"]},
        {"account_id": ids["accr_util"], "credit": "12000", "site_id": ids["emp"]}],
        date="2026-07-31", description="Month-end electricity accrual", is_accrual=True)
    det = client.get(f"/api/journals/{j['id']}", headers=H["cfo"]).json()
    assert det["status"] == "REVERSED" and det["reversed_by_journal"]["status"] == "POSTED"
    rev = client.get(f"/api/journals/{det['reversed_by_journal']['id']}", headers=H["cfo"]).json()
    assert rev["posting_date"] == "2026-08-01"


def test_trial_balance_balances(client, H):
    r = client.get("/api/reports/trial-balance", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-07-31"})
    assert r.status_code == 200
    tb = r.json()
    assert tb["meta"]["balanced"] is True
    tot = tb["meta"]["totals"]
    assert D(tot[2]) == D(tot[3]) and D(tot[2]) > 0


def test_profit_and_loss_structure(client, H):
    r = client.get("/api/reports/profit-loss", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-07-31"})
    pl = r.json()
    s = pl["meta"]["summary"][0]
    assert D(s["REVENUE"]) == D("250000.00")
    assert D(s["OPEX"]) == D("12000.00")  # accrual (reversed on 1 Aug, outside July)
    assert D(s["EBITDA"]) == D("238000.00") and D(s["PAT"]) == D("238000.00")
    labels = [x["label"] for x in pl["rows"]]
    for k in ("GROSS PROFIT", "EBITDA", "EBIT (OPERATING PROFIT)", "PROFIT BEFORE TAXATION", "PROFIT AFTER TAXATION"):
        assert k in labels
    # site-wise
    r = client.get("/api/reports/profit-loss", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-07-31", "preset": "site"})
    assert any(c["label"] == "Emporium Lahore" for c in r.json()["columns"])
    # monthly
    r = client.get("/api/reports/profit-loss", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-08-31", "preset": "monthly"})
    s = r.json()["meta"]["summary"]
    assert D(s[0]["OPEX"]) == D("12000") and D(s[1]["OPEX"]) == D("-12000") and D(s[2]["OPEX"]) == 0


def test_balance_sheet_balances(client, H):
    r = client.get("/api/reports/balance-sheet", headers=H["cfo"], params={"as_of": "2026-07-31", "compare": "prior_month"})
    bs = r.json()
    assert bs["meta"]["balanced"] is True, bs["meta"]
    assert D(bs["meta"]["total_assets"][0]) == D("50250000.00")


def test_cash_flow_reconciles(client, H):
    r = client.get("/api/reports/cash-flow", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-07-31"})
    cf = r.json()
    assert cf["meta"]["reconciles"] is True, cf["meta"]
    assert D(cf["meta"]["closing_cash"]) == D("50250000.00")
    r = client.get("/api/reports/cash-flow", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-07-31", "method": "direct"})
    assert D(r.json()["meta"]["net"]) == D("50250000.00")


def test_gl_detail_running_balance(client, H, ids):
    r = client.get("/api/reports/gl", headers=H["cfo"], params={"date_from": "2026-07-01", "date_to": "2026-08-31",
                                                                  "account_ids": str(ids["accr_util"])})
    g = r.json()
    assert g["items"][-1]["balance"] == g["closing"] == "0.00"
    assert D(g["period_credit"]) == D("52000.00")


def test_exports(client, H):
    for fmt, ctype in (("xlsx", "spreadsheet"), ("pdf", "pdf"), ("csv", "csv")):
        r = client.get("/api/reports/trial-balance", headers=H["cfo"],
                       params={"date_from": "2026-07-01", "date_to": "2026-07-31", "format": fmt})
        assert r.status_code == 200 and ctype in r.headers["content-type"] and len(r.content) > 500


def test_closed_period_blocks_posting(client, H, ids, db):
    from backend.accounting.models import AccountingPeriod, PeriodStatus
    p = db.scalar(select(AccountingPeriod).where(AccountingPeriod.name == "Jun-2027"))
    p.status = PeriodStatus.CLOSED
    db.commit()
    r = journal(client, H, "accountant", [
        {"account_id": ids["elec"], "debit": "100", "site_id": ids["emp"], "cost_centre_id": ids["cc_ops"]},
        {"account_id": ids["accr_util"], "credit": "100", "site_id": ids["emp"]}], date="2027-06-10")
    jid = r.json()["id"]
    client.post(f"/api/journals/{jid}/submit", headers=H["accountant"], json={})
    client.post(f"/api/journals/{jid}/check", headers=H["fm"], json={})
    client.post(f"/api/journals/{jid}/approve", headers=H["cfo"], json={})
    r = client.post(f"/api/journals/{jid}/post", headers=H["fm"], json={})
    assert r.status_code == 409 and r.json()["error"] == "period_closed"
    p = db.get(AccountingPeriod, p.id)
    p.status = PeriodStatus.OPEN
    db.commit()


def test_recurring_journal(client, H, ids):
    body = {"name": "Monthly security contract", "description": "Security services accrual", "frequency": "MONTHLY",
            "next_run_date": "2026-07-25", "auto_submit": True, "lines": [
                {"account_id": acc("06-02-03-0003"), "debit": "85000", "site_id": ids["emp"], "cost_centre_id": cc("050201")},
                {"account_id": acc("02-02-02-0010"), "credit": "85000"}]}
    r = client.post("/api/recurring-journals", headers=H["accountant"], json=body)
    assert r.status_code == 201, r.text
    r = client.post("/api/recurring-journals/run", headers=H["accountant"], json={"as_of": "2026-09-30"})
    created = r.json()["created"]
    assert len(created) == 3 and all(c["status"] == "SUBMITTED" for c in created)
    r = client.post("/api/recurring-journals/run", headers=H["accountant"], json={"as_of": "2026-09-30"})
    assert r.json()["created"] == []  # no duplicates
