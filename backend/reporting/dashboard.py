"""CFO dashboard: every figure is computed from the posted GL / sub-ledgers at request time."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from backend.accounting.models import Account, JournalLine
from backend.core.actor import Actor
from backend.core.money import ZERO, money
from backend.masters.models import CostCentre
from backend.reporting import financial as fin
from backend.reporting.common import LineFilter


def _pct(a: Decimal, b: Decimal) -> Decimal | None:
    return (a / b * 100).quantize(Decimal("0.1")) if b else None


def _balance(db: Session, flt: LineFilter, as_of: date, where) -> Decimal:
    q = select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).join(Account, Account.id == JournalLine.account_id).where(where)
    f = LineFilter(**{**flt.__dict__})
    f.exclude_sources = ()
    return money(db.scalar(f.apply(q, date_to=as_of)) or 0)


def cfo_dashboard(db: Session, company_id: int, actor: Actor, date_from: date, date_to: date, *, site_ids=None,
                  cost_centre_ids=None, revenue_stream: str | None = None) -> dict:
    flt = LineFilter.build(company_id, actor, site_ids=site_ids, cost_centre_ids=cost_centre_ids)
    fy = fin.fiscal_year_for(db, company_id, date_to)
    period_pl = fin.profit_and_loss(db, company_id, actor, [fin.Column("P", date_from, date_to)], detail="group", flt=flt)
    ytd_pl = fin.profit_and_loss(db, company_id, actor, [fin.Column("YTD", fy.start_date, date_to)], detail="group",
                                 flt=LineFilter(**{**flt.__dict__}))
    s, y = period_pl["meta"]["summary"][0], ytd_pl["meta"]["summary"][0]

    # revenue by stream (period) - honours the revenue stream filter
    q = select(Account.revenue_stream, func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0)).join(
        Account, Account.id == JournalLine.account_id).where(Account.pl_section == "REVENUE")
    f = LineFilter(**{**flt.__dict__})
    f.exclude_sources = ("CLOSING",)
    streams = {k or "OTHER": money(v) for k, v in db.execute(f.apply(q, date_from=date_from, date_to=date_to).group_by(Account.revenue_stream)).all()}
    revenue = streams.get(revenue_stream, ZERO) if revenue_stream else s["REVENUE"]

    # monthly trend across the fiscal year to date
    months = fin.month_ranges(fy.start_date, date_to)
    mpl = fin.profit_and_loss(db, company_id, actor, [fin.Column(l, a, b) for l, a, b in months], detail="group",
                              flt=LineFilter(**{**flt.__dict__}))
    trend = []
    mq = select(extract("year", JournalLine.posting_date), extract("month", JournalLine.posting_date), Account.revenue_stream,
                func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0)).join(Account, Account.id == JournalLine.account_id).where(
        Account.pl_section == "REVENUE")
    by_month_stream: dict[tuple, dict] = defaultdict(dict)
    for yy, mm, stream, v in db.execute(f.apply(mq, date_from=fy.start_date, date_to=date_to).group_by(
            extract("year", JournalLine.posting_date), extract("month", JournalLine.posting_date), Account.revenue_stream)).all():
        by_month_stream[(int(yy), int(mm))][stream or "OTHER"] = money(v)
    for i, (lbl, a, _b) in enumerate(months):
        ms = mpl["meta"]["summary"][i]
        trend.append({"month": lbl, "revenue": ms["REVENUE"], "gross_profit": ms["GROSS_PROFIT"], "ebitda": ms["EBITDA"],
                      "pat": ms["PAT"], "opex": ms["OPEX"], "streams": by_month_stream.get((a.year, a.month), {})})

    # balances
    bal = lambda where: _balance(db, flt, date_to, where)  # noqa: E731
    cash = bal(Account.control_type == "CASH")
    bank = bal(Account.control_type == "BANK")
    in_transit = bal((Account.cash_flow_line == "CASH") & (Account.control_type == "CLEARING"))
    receivables = bal(Account.code.like("01-02-02-%"))
    payables = -bal(Account.code.like("02-02-01-%"))
    tax_payable = -bal(Account.code.like("02-02-03-%"))
    tax_recoverable = bal(Account.code.like("01-02-05-%"))

    # budget vs actual (YTD)
    budget = None
    from backend.budgeting.service import active_version_id
    vid = active_version_id(db, company_id, fy.id)
    if vid:
        bpl = fin.profit_and_loss(db, company_id, actor, [fin.Column("A", fy.start_date, date_to),
                                                          fin.Column("B", fy.start_date, date_to, kind="budget", budget_version_id=vid)],
                                  detail="group", flt=LineFilter(**{**flt.__dict__}))
        a, b = bpl["meta"]["summary"]
        budget = {k: {"actual": a[k], "budget": b[k], "variance": a[k] - b[k]} for k in ("REVENUE", "COST_OF_SALES", "OPEX", "EBITDA", "PAT")}

    # site performance
    site_rep = fin.pl_preset(db, company_id, actor, "site", date_from, date_to, flt=LineFilter(**{**flt.__dict__}), detail="group")
    sites = [{"site": c["label"], "revenue": site_rep["meta"]["summary"][i]["REVENUE"], "ebitda": site_rep["meta"]["summary"][i]["EBITDA"],
              "gross_profit": site_rep["meta"]["summary"][i]["GROSS_PROFIT"]}
             for i, c in enumerate(site_rep["columns"][1:]) if c["label"] != "Total"]

    # cost-centre performance and top expenses
    eq = select(JournalLine.cost_centre_id, func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).join(
        Account, Account.id == JournalLine.account_id).where(Account.pl_section.in_(["OPEX", "COST_OF_SALES"]))
    ccs = {c.id: c for c in db.scalars(select(CostCentre))}
    cc_perf = sorted([{"cost_centre": f"{ccs[k].code} {ccs[k].name}" if k else "(none)", "expense": money(v)}
                      for k, v in db.execute(f.apply(eq, date_from=date_from, date_to=date_to).group_by(JournalLine.cost_centre_id)).all()],
                     key=lambda x: -x["expense"])[:10]
    tq = select(Account.code, Account.name, func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).join(
        Account, Account.id == JournalLine.account_id).where(Account.pl_section.in_(["OPEX", "COST_OF_SALES", "DEPRECIATION"]))
    top = sorted([{"account": f"{c} {n}", "amount": money(v)} for c, n, v in
                  db.execute(f.apply(tq, date_from=date_from, date_to=date_to).group_by(Account.code, Account.name)).all()],
                 key=lambda x: -x["amount"])[:10]

    # AP / AR aging summaries
    from backend.ap import service as ap
    from backend.ar import service as ar
    ap_tot = ap.aging(db, company_id, date_to)["rows"][-1]
    ar_tot = ar.aging(db, company_id, date_to)["rows"][-1]
    buckets = [b[0] for b in ap.BUCKETS] + ["unapplied", "total"]

    cf = fin.cash_flow(db, company_id, actor, fy.start_date, date_to, flt=LineFilter(**{**flt.__dict__}))
    from backend.cinema.reports import kpis
    cinema = kpis(db, company_id, date_from, date_to, site_ids=flt.site_ids, actor=actor)
    return {
        "period": {"from": date_from, "to": date_to, "fiscal_year": fy.code},
        "kpis": {"revenue": revenue, "gross_profit": s["GROSS_PROFIT"], "gross_margin": _pct(s["GROSS_PROFIT"], s["REVENUE"]),
                 "ebitda": s["EBITDA"], "ebitda_margin": _pct(s["EBITDA"], s["REVENUE"]), "net_profit": s["PAT"],
                 "net_margin": _pct(s["PAT"], s["REVENUE"]), "cash_balance": cash, "bank_balance": bank, "cash_in_transit": in_transit,
                 "receivables": receivables, "payables": payables, "tax_payable": tax_payable, "tax_recoverable": tax_recoverable,
                 "ytd_revenue": y["REVENUE"], "ytd_ebitda": y["EBITDA"], "ytd_net_profit": y["PAT"]},
        "revenue_by_stream": streams, "trend": trend, "budget_vs_actual": budget, "sites": sites,
        "cost_centres": cc_perf, "top_expenses": top,
        "ap_aging": {k: ap_tot.get(k, ZERO) for k in buckets}, "ar_aging": {k: ar_tot.get(k, ZERO) for k in buckets},
        "cash_flow": {"operating": cf["meta"]["sections"]["OPERATING"], "investing": cf["meta"]["sections"]["INVESTING"],
                      "financing": cf["meta"]["sections"]["FINANCING"], "opening_cash": cf["meta"]["opening_cash"],
                      "closing_cash": cf["meta"]["closing_cash"]},
        "cinema": cinema,
    }


def ratios(db: Session, company_id: int, actor: Actor | None, as_of: date) -> dict:
    """Working capital and key ratios from the balance sheet and YTD P&L."""
    flt = LineFilter.build(company_id, actor)
    bal = lambda where: _balance(db, flt, as_of, where)  # noqa: E731
    ca = bal(Account.code.like("01-02-%"))
    cl = -bal(Account.code.like("02-02-%"))
    inv = bal(Account.code.like("01-02-01-%"))
    recv = bal(Account.code.like("01-02-02-%"))
    pay = -bal(Account.code.like("02-02-01-%"))
    cash = bal(Account.cash_flow_line == "CASH")
    debt = -bal(Account.code.like("02-01-01-%")) - bal(Account.code.like("02-02-04-%")) - bal(Account.code.like("02-01-02-%"))
    bs = fin.balance_sheet(db, company_id, actor, [as_of], flt=LineFilter.build(company_id, actor), detail="subgroup")
    equity = bs["meta"]["total_equity"][0]
    fy = fin.fiscal_year_for(db, company_id, as_of)
    pl = fin.profit_and_loss(db, company_id, actor, [fin.Column("YTD", fy.start_date, as_of)], detail="group")["meta"]["summary"][0]
    days = (as_of - fy.start_date).days + 1
    return {"current_assets": ca, "current_liabilities": cl, "working_capital": ca - cl,
            "current_ratio": (ca / cl).quantize(Decimal("0.01")) if cl else None,
            "quick_ratio": ((ca - inv) / cl).quantize(Decimal("0.01")) if cl else None,
            "cash_ratio": (cash / cl).quantize(Decimal("0.01")) if cl else None,
            "gross_margin_pct": _pct(pl["GROSS_PROFIT"], pl["REVENUE"]), "ebitda_margin_pct": _pct(pl["EBITDA"], pl["REVENUE"]),
            "net_margin_pct": _pct(pl["PAT"], pl["REVENUE"]),
            "debt_to_equity": (debt / equity).quantize(Decimal("0.01")) if equity else None,
            "receivable_days": (recv / pl["REVENUE"] * days).quantize(Decimal("0.1")) if pl["REVENUE"] else None,
            "payable_days": (pay / (pl["COST_OF_SALES"] + pl["OPEX"]) * days).quantize(Decimal("0.1")) if (pl["COST_OF_SALES"] + pl["OPEX"]) else None,
            "total_equity": equity, "total_debt": debt}
