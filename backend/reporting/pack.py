"""Monthly CFO reporting pack (PDF / Excel): management accounts derived entirely from the GL and sub-ledgers."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from backend.core.actor import Actor
from backend.reporting import financial as fin
from backend.reporting.common import LineFilter
from backend.reporting.dashboard import cfo_dashboard, ratios


def _kv_report(title: str, pairs: list[tuple[str, object, str]], subtitle: str = "") -> dict:
    return {"title": title, "subtitle": subtitle, "columns": [{"key": "label", "label": "Measure", "type": "text"},
                                                              {"key": "value", "label": "Value", "type": "text"}],
            "rows": [{"label": k, "value": (f"{v:,.2f}" if t == "money" and v is not None else
                                            (f"{v}%" if t == "pct" and v is not None else ("-" if v is None else str(v)))),
                      "level": 1, "style": "line"} for k, v, t in pairs], "meta": {}}


def monthly_pack(db: Session, company_id: int, actor: Actor, period_start: date, period_end: date) -> list[dict]:
    from backend.ap import service as ap
    from backend.ar import service as ar
    from backend.cinema import reports as crep
    from backend.tax import service as tax
    fy = fin.fiscal_year_for(db, company_id, period_end)
    dash = cfo_dashboard(db, company_id, actor, period_start, period_end)
    k = dash["kpis"]
    r = ratios(db, company_id, actor, period_end)
    c = dash["cinema"]
    label = period_end.strftime("%B %Y")
    summary = _kv_report(f"Management Accounts - {label}", [
        ("Revenue (month)", k["revenue"], "money"), ("Gross profit", k["gross_profit"], "money"), ("Gross margin", k["gross_margin"], "pct"),
        ("EBITDA", k["ebitda"], "money"), ("EBITDA margin", k["ebitda_margin"], "pct"), ("Net profit after tax", k["net_profit"], "money"),
        ("Revenue - year to date", k["ytd_revenue"], "money"), ("EBITDA - year to date", k["ytd_ebitda"], "money"),
        ("Net profit - year to date", k["ytd_net_profit"], "money"), ("Cash in hand", k["cash_balance"], "money"),
        ("Bank balances", k["bank_balance"], "money"), ("Receivables", k["receivables"], "money"), ("Payables", k["payables"], "money"),
        ("Net tax payable", k["tax_payable"], "money"), ("Working capital", r["working_capital"], "money"),
        ("Current ratio", r["current_ratio"], "text"), ("Quick ratio", r["quick_ratio"], "text"),
        ("Debt to equity", r["debt_to_equity"], "text"), ("Receivable days", r["receivable_days"], "text"),
        ("Payable days", r["payable_days"], "text"), ("Admissions", c["admissions"], "text"),
        ("Average ticket price", c["average_ticket_price"], "money"), ("F&B spend per head", c["spend_per_head"], "money"),
        ("Film rental % of ticket revenue", c["film_rental_pct"], "pct")], subtitle=f"Fiscal year {fy.code}")
    summary["sheet"] = "Summary"
    flt = lambda: LineFilter.build(company_id, actor)  # noqa: E731
    reports = [summary,
               {**fin.pl_preset(db, company_id, actor, "ytd", period_start, period_end, flt=flt(), detail="subgroup"), "sheet": "P&L"},
               {**fin.pl_preset(db, company_id, actor, "monthly", fy.start_date, period_end, flt=flt(), detail="group"), "sheet": "P&L monthly"},
               {**fin.pl_preset(db, company_id, actor, "budget", period_start, period_end, flt=flt(), detail="group"), "sheet": "Budget vs actual"},
               {**fin.pl_preset(db, company_id, actor, "site", period_start, period_end, flt=flt(), detail="group"), "sheet": "Site P&L"},
               {**fin.balance_sheet(db, company_id, actor, [period_end, period_start - timedelta(days=1)], flt=flt(), detail="subgroup"), "sheet": "Balance sheet"},
               {**fin.cash_flow(db, company_id, actor, fy.start_date, period_end, flt=flt()), "sheet": "Cash flow YTD"},
               {**fin.cash_by_account(db, company_id, actor, period_start, period_end), "sheet": "Cash position"},
               {**ap.aging(db, company_id, period_end), "sheet": "AP aging"},
               {**ar.aging(db, company_id, period_end), "sheet": "AR aging"},
               {**tax.summary(db, company_id, period_start, period_end), "sheet": "Tax position"},
               {**crep.revenue_analysis(db, company_id, period_start, period_end, "site", actor=actor), "sheet": "Cinema revenue"},
               {**crep.revenue_analysis(db, company_id, period_start, period_end, "film", actor=actor), "sheet": "Revenue by film"}]
    for rep in reports:
        rep.setdefault("company", reports[1].get("company", ""))
        rep.get("meta", {}).pop("items", None)
    return reports
