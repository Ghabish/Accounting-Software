"""Financial statements and GL reports, all derived from posted journal lines.

Report payload (also consumed by the Excel / CSV / PDF exporter):
    {"title", "subtitle", "columns": [{key,label,type}], "rows": [{label, level, style, c0.., drill}], "meta"}
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.accounting.models import (
    Account, AccountingPeriod, AccountType, FiscalYear, JournalEntry, JournalLine,
)
from backend.core.actor import Actor
from backend.core.exceptions import NotFound, ValidationFailed
from backend.core.money import ZERO, money
from backend.database.seed.coa_data import CASH_FLOW_LINES
from backend.masters.models import Company, CostCentre, Site
from backend.reporting.common import LineFilter, balances_by_account

INCOME_SECTIONS = {"REVENUE", "OTHER_INCOME"}
PL_LAYOUT = [
    # (key, label, sections, kind)
    ("REVENUE", "Revenue", ["REVENUE"], "section"),
    ("COST_OF_SALES", "Cost of sales", ["COST_OF_SALES"], "section"),
    ("GROSS_PROFIT", "Gross profit", None, "total"),
    ("OPEX", "Operating expenses", ["OPEX"], "section"),
    ("OTHER_INCOME", "Other income", ["OTHER_INCOME"], "section"),
    ("OTHER_EXPENSE", "Other expenses", ["OTHER_EXPENSE"], "section"),
    ("EBITDA", "EBITDA", None, "total"),
    ("DEPRECIATION", "Depreciation and amortisation", ["DEPRECIATION"], "section"),
    ("EBIT", "EBIT (operating profit)", None, "total"),
    ("FINANCE_COST", "Finance costs", ["FINANCE_COST"], "section"),
    ("PBT", "Profit before taxation", None, "total"),
    ("TAXATION", "Taxation", ["TAXATION"], "section"),
    ("PAT", "Profit after taxation", None, "total"),
]


def _totals(sec: dict[str, Decimal]) -> dict[str, Decimal]:
    g = lambda k: sec.get(k, ZERO)  # noqa: E731
    gp = g("REVENUE") - g("COST_OF_SALES")
    ebitda = gp - g("OPEX") + g("OTHER_INCOME") - g("OTHER_EXPENSE")
    ebit = ebitda - g("DEPRECIATION")
    pbt = ebit - g("FINANCE_COST")
    return {"GROSS_PROFIT": gp, "EBITDA": ebitda, "EBIT": ebit, "PBT": pbt, "PAT": pbt - g("TAXATION")}


class ChartCache:
    def __init__(self, db: Session):
        self.accounts = {a.id: a for a in db.scalars(select(Account)).all()}
        self.by_code = {a.code: a for a in self.accounts.values()}

    def ancestor(self, acc: Account, level: int) -> Account:
        return self.by_code[acc.code[: {1: 2, 2: 5, 3: 8, 4: 13}[level]]]


@dataclass
class Column:
    label: str
    date_from: date | None = None
    date_to: date | None = None
    kind: str = "actual"                 # actual | budget | variance | variance_pct
    site_ids: list[int] | None = None
    cost_centre_ids: list[int] | None = None
    budget_version_id: int | None = None
    base: tuple[int, int] | None = None  # for variance columns: (actual col index, budget col index)
    extra: dict = field(default_factory=dict)


def _company(db: Session, company_id: int) -> Company:
    co = db.get(Company, company_id)
    if co is None:
        raise NotFound("Company not found")
    return co


def fiscal_year_for(db: Session, company_id: int, d: date) -> FiscalYear:
    fy = db.scalar(select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.start_date <= d,
                                            FiscalYear.end_date >= d))
    if fy is None:
        raise ValidationFailed(f"No fiscal year covers {d.isoformat()}")
    return fy


def _column_values(db: Session, flt: LineFilter, col: Column) -> dict[int, Decimal]:
    """account_id -> signed balance (debit - credit) for an actual column."""
    f = LineFilter(**{**flt.__dict__})
    if col.site_ids:
        f.site_ids = col.site_ids
    if col.cost_centre_ids:
        f.cost_centre_ids = col.cost_centre_ids
    bal = balances_by_account(db, f, date_from=col.date_from, date_to=col.date_to)
    return {aid: dr - cr for aid, (dr, cr) in bal.items()}


def _budget_values(db: Session, flt: LineFilter, col: Column) -> dict[int, Decimal]:
    from backend.budgeting.service import budget_by_account
    return budget_by_account(db, flt.company_id, col.budget_version_id, col.date_from, col.date_to,
                             site_ids=col.site_ids or flt.site_ids, cost_centre_ids=col.cost_centre_ids or flt.cost_centre_ids)


# ------------------------------------------------------------------ profit and loss
def profit_and_loss(db: Session, company_id: int, actor: Actor | None, columns: list[Column], *,
                    detail: str = "account", flt: LineFilter | None = None, title: str = "Profit and Loss Statement",
                    subtitle: str = "") -> dict:
    flt = flt or LineFilter.build(company_id, actor)
    flt.exclude_sources = tuple(set(flt.exclude_sources) | {"CLOSING"})
    chart = ChartCache(db)
    col_vals: list[dict[int, Decimal]] = []
    for col in columns:
        if col.kind == "actual":
            raw = _column_values(db, flt, col)
            # natural P&L sign: income positive, expenses positive
            vals = {}
            for aid, v in raw.items():
                a = chart.accounts[aid]
                if a.pl_section:
                    vals[aid] = -v if a.pl_section in INCOME_SECTIONS else v
            col_vals.append(vals)
        elif col.kind == "budget":
            col_vals.append(_budget_values(db, flt, col))
        else:
            col_vals.append({})
    pl_accounts = sorted([a for a in chart.accounts.values() if a.is_postable and a.pl_section], key=lambda a: a.code)
    out_rows: list[dict] = []
    section_totals: list[dict[str, Decimal]] = [defaultdict(lambda: ZERO) for _ in columns]

    def vals_for(accs: list[Account]) -> list[Decimal]:
        return [sum((cv.get(a.id, ZERO) for a in accs), ZERO) for cv in col_vals]

    def emit(label, level, style, values, **extra):
        r = {"label": label, "level": level, "style": style, **extra}
        for i, v in enumerate(values):
            r[f"c{i}"] = v
        out_rows.append(r)

    for key, label, sections, kind in PL_LAYOUT:
        if kind == "section":
            accs = [a for a in pl_accounts if a.pl_section in sections]
            emit(label.upper(), 0, "header", [None] * len(columns), section=key)
            groups: dict[str, list[Account]] = defaultdict(list)
            for a in accs:
                groups[a.code[:5]].append(a)
            for gcode in sorted(groups):
                gaccs = groups[gcode]
                gacc = chart.by_code[gcode]
                if detail == "group":
                    emit(gacc.name, 1, "line", vals_for(gaccs), code=gcode, drill={"account_prefix": gcode})
                    continue
                emit(gacc.name, 1, "subheader", [None] * len(columns), code=gcode)
                subs: dict[str, list[Account]] = defaultdict(list)
                for a in gaccs:
                    subs[a.code[:8]].append(a)
                for scode in sorted(subs):
                    saccs = subs[scode]
                    if detail == "subgroup":
                        emit(chart.by_code[scode].name, 2, "line", vals_for(saccs), code=scode,
                             drill={"account_prefix": scode})
                    else:
                        for a in saccs:
                            v = vals_for([a])
                            if any(x for x in v):
                                emit(a.name, 2, "line", v, code=a.code, account_id=a.id, drill={"account_id": a.id})
                emit(f"Total {gacc.name.lower()}", 1, "subtotal", vals_for(gaccs), code=gcode)
            tot = vals_for(accs)
            for i, v in enumerate(tot):
                section_totals[i][key] = v
            emit(f"Total {label.lower()}", 0, "total", tot, section=key)
        else:
            vals = [_totals(st)[key] for st in section_totals]
            emit(label.upper(), 0, "grand", vals, section=key)
            if key in ("GROSS_PROFIT", "EBITDA", "PAT"):
                margins = []
                for i, st in enumerate(section_totals):
                    rev = st.get("REVENUE", ZERO)
                    margins.append((vals[i] / rev * 100).quantize(Decimal("0.1")) if rev else None)
                emit(f"{label} margin %", 0, "pct", margins, section=key + "_MARGIN")
    # variance columns
    for ci, col in enumerate(columns):
        if col.kind in ("variance", "variance_pct") and col.base:
            a_i, b_i = col.base
            for r in out_rows:
                a, b = r.get(f"c{a_i}"), r.get(f"c{b_i}")
                if a is None or b is None or r["style"] == "pct":
                    r[f"c{ci}"] = None
                elif col.kind == "variance":
                    r[f"c{ci}"] = a - b
                else:
                    r[f"c{ci}"] = ((a - b) / abs(b) * 100).quantize(Decimal("0.1")) if b else None
    cols = [{"key": "label", "label": "", "type": "text"}] + [
        {"key": f"c{i}", "label": c.label, "type": "pct" if c.kind == "variance_pct" else "money",
         "date_from": c.date_from.isoformat() if c.date_from else None,
         "date_to": c.date_to.isoformat() if c.date_to else None,
         "site_ids": c.site_ids, "cost_centre_ids": c.cost_centre_ids, "kind": c.kind}
        for i, c in enumerate(columns)]
    summary = [{k: v for k, v in _totals(st).items()} | {s: st.get(s, ZERO) for s in
               ("REVENUE", "COST_OF_SALES", "OPEX", "OTHER_INCOME", "OTHER_EXPENSE", "DEPRECIATION",
                "FINANCE_COST", "TAXATION")} for st in section_totals]
    return {"title": title, "subtitle": subtitle, "company": _company(db, company_id).name, "columns": cols,
            "rows": out_rows, "meta": {"summary": summary}}


def month_ranges(start: date, end: date) -> list[tuple[str, date, date]]:
    out = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        last = date(y, m, calendar.monthrange(y, m)[1])
        out.append((date(y, m, 1).strftime("%b-%Y"), max(start, date(y, m, 1)), min(end, last)))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _shift_year(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def pl_preset(db: Session, company_id: int, actor: Actor | None, preset: str, date_from: date, date_to: date, *,
              flt: LineFilter, detail: str = "account", budget_version_id: int | None = None) -> dict:
    """Presets: period | monthly | ytd | comparative | budget | site | cost_centre."""
    fy = fiscal_year_for(db, company_id, date_to)
    period_label = f"{date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}"
    if preset == "monthly":
        cols = [Column(lbl, a, b) for lbl, a, b in month_ranges(date_from, date_to)]
        cols.append(Column("Total", date_from, date_to))
    elif preset == "ytd":
        cols = [Column("Period", date_from, date_to), Column("Year to date", fy.start_date, date_to)]
    elif preset == "comparative":
        pf, pt = _shift_year(date_from, -1), _shift_year(date_to, -1)
        cols = [Column(f"Current ({date_to.year})", date_from, date_to), Column(f"Prior year ({pt.year})", pf, pt),
                Column("Variance", kind="variance", base=(0, 1)), Column("Var %", kind="variance_pct", base=(0, 1))]
    elif preset == "budget":
        from backend.budgeting.service import active_version_id
        vid = budget_version_id or active_version_id(db, company_id, fy.id)
        cols = [Column("Actual", date_from, date_to), Column("Budget", date_from, date_to, kind="budget", budget_version_id=vid),
                Column("Variance", kind="variance", base=(0, 1)), Column("Var %", kind="variance_pct", base=(0, 1))]
    elif preset == "site":
        sites = db.scalars(select(Site).where(Site.company_id == company_id).order_by(Site.code)).all()
        sites = [s for s in sites if (flt.site_ids is None or s.id in flt.site_ids)
                 and (flt.actor_sites is None or s.id in flt.actor_sites)]
        cols = [Column(s.name, date_from, date_to, site_ids=[s.id]) for s in sites] + [Column("Total", date_from, date_to)]
    elif preset == "cost_centre":
        used = db.scalars(select(JournalLine.cost_centre_id).where(
            JournalLine.company_id == company_id, JournalLine.is_posted.is_(True),
            JournalLine.posting_date.between(date_from, date_to), JournalLine.cost_centre_id.is_not(None)).distinct()).all()
        ccs = db.scalars(select(CostCentre).where(CostCentre.id.in_(used)).order_by(CostCentre.code)).all()
        cols = [Column(f"{c.code} {c.name}", date_from, date_to, cost_centre_ids=[c.id]) for c in ccs] + \
               [Column("Total", date_from, date_to)]
    else:
        cols = [Column(period_label, date_from, date_to)]
    titles = {"monthly": "Monthly Profit and Loss", "ytd": "Profit and Loss - Period and Year to Date",
              "comparative": "Comparative Profit and Loss", "budget": "Budget vs Actual - Profit and Loss",
              "site": "Site-wise Profit and Loss", "cost_centre": "Cost-centre-wise Profit and Loss"}
    return profit_and_loss(db, company_id, actor, cols, detail=detail, flt=flt,
                           title=titles.get(preset, "Profit and Loss Statement"), subtitle=period_label)


# ------------------------------------------------------------------ balance sheet
def _pl_balance(db: Session, flt: LineFilter, chart: ChartCache, *, date_to: date | None = None,
                before: date | None = None) -> Decimal:
    """Credit-positive cumulative P&L (profit) up to a date, including year-end closing lines."""
    f = LineFilter(**{**flt.__dict__})
    f.exclude_sources = ()
    bal = balances_by_account(db, f, date_to=date_to, before=before)
    return -sum(((dr - cr) for aid, (dr, cr) in bal.items() if chart.accounts[aid].pl_section), ZERO)


def balance_sheet(db: Session, company_id: int, actor: Actor | None, as_of_dates: list[date], *,
                  flt: LineFilter | None = None, detail: str = "account") -> dict:
    flt = flt or LineFilter.build(company_id, actor)
    flt.exclude_sources = ()
    chart = ChartCache(db)
    col_bal = []
    extras = []
    for d in as_of_dates:
        bal = balances_by_account(db, flt, date_to=d)
        col_bal.append({aid: dr - cr for aid, (dr, cr) in bal.items()})
        fy = db.scalar(select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.start_date <= d,
                                                FiscalYear.end_date >= d))
        total_pl = _pl_balance(db, flt, chart, date_to=d)
        py = _pl_balance(db, flt, chart, before=fy.start_date) if fy else ZERO
        cy = total_pl - py
        extras.append({"current_year": money(cy), "prior_unclosed": money(py)})
    rows_out: list[dict] = []
    n = len(as_of_dates)

    def emit(label, level, style, values, **extra):
        r = {"label": label, "level": level, "style": style, **extra}
        for i, v in enumerate(values):
            r[f"c{i}"] = v
        rows_out.append(r)

    def sect_values(prefix: str, sign: int) -> list[Decimal]:
        return [sum((v for aid, v in cb.items() if chart.accounts[aid].code.startswith(prefix)), ZERO) * sign
                for cb in col_bal]

    totals = {}
    for cls, label, sign in (("01", "ASSETS", 1), ("02", "LIABILITIES", -1), ("03", "EQUITY", -1)):
        emit(label, 0, "header", [None] * n)
        groups = sorted([a for a in chart.accounts.values() if a.level == 2 and a.code.startswith(cls)],
                        key=lambda a: a.code)
        for g in groups:
            emit(g.name, 1, "subheader", [None] * n, code=g.code)
            subs = sorted([a for a in chart.accounts.values() if a.level == 3 and a.code.startswith(g.code)],
                          key=lambda a: a.code)
            for s in subs:
                if detail == "subgroup":
                    v = sect_values(s.code, sign)
                    if any(v):
                        emit(s.name, 2, "line", v, code=s.code, drill={"account_prefix": s.code})
                    continue
                for a in sorted([a for a in chart.accounts.values() if a.is_postable and a.parent_id == s.id],
                                key=lambda a: a.code):
                    v = [cb.get(a.id, ZERO) * sign for cb in col_bal]
                    if any(v):
                        emit(a.name, 2, "line", v, code=a.code, account_id=a.id, drill={"account_id": a.id},
                             contra=a.is_contra)
            if cls == "03" and g.code == "03-01":
                emit("Unappropriated profit brought forward (not yet closed)", 2, "line",
                     [e["prior_unclosed"] for e in extras], computed=True)
                emit("Profit / (loss) for the current year", 2, "line", [e["current_year"] for e in extras],
                     computed=True)
            gv = sect_values(g.code, sign)
            if cls == "03" and g.code == "03-01":
                gv = [gv[i] + extras[i]["prior_unclosed"] + extras[i]["current_year"] for i in range(n)]
            emit(f"Total {g.name.lower()}", 1, "subtotal", gv, code=g.code)
        tv = sect_values(cls, sign)
        if cls == "03":
            tv = [tv[i] + extras[i]["prior_unclosed"] + extras[i]["current_year"] for i in range(n)]
        totals[cls] = tv
        emit(f"TOTAL {label}", 0, "total", tv)
    le = [totals["02"][i] + totals["03"][i] for i in range(n)]
    emit("TOTAL LIABILITIES AND EQUITY", 0, "grand", le)
    diffs = [money(totals["01"][i] - le[i]) for i in range(n)]
    site_filtered = bool(flt.site_ids or flt.cost_centre_ids or flt.actor_sites is not None)
    cols = [{"key": "label", "label": "", "type": "text"}] + [
        {"key": f"c{i}", "label": f"As at {d.strftime('%d %b %Y')}", "type": "money", "date_to": d.isoformat()}
        for i, d in enumerate(as_of_dates)]
    return {"title": "Statement of Financial Position (Balance Sheet)", "company": _company(db, company_id).name,
            "subtitle": ", ".join(d.strftime("%d %b %Y") for d in as_of_dates), "columns": cols, "rows": rows_out,
            "meta": {"difference": diffs, "balanced": all(d == 0 for d in diffs) if not site_filtered else None,
                     "filtered": site_filtered, "total_assets": totals["01"], "total_liabilities": totals["02"],
                     "total_equity": totals["03"]}}


# ------------------------------------------------------------------ cash flow
def _is_cash(a: Account) -> bool:
    return a.cash_flow_line == "CASH"


def cash_flow(db: Session, company_id: int, actor: Actor | None, date_from: date, date_to: date, *,
              flt: LineFilter | None = None) -> dict:
    """Indirect-method cash flow. Lines sum exactly to the movement in cash and cash equivalents."""
    flt = flt or LineFilter.build(company_id, actor)
    chart = ChartCache(db)
    f_mov = LineFilter(**{**flt.__dict__})
    f_mov.exclude_sources = ("CLOSING", "OPENING")
    mov = {aid: dr - cr for aid, (dr, cr) in balances_by_account(db, f_mov, date_from=date_from, date_to=date_to).items()}
    f_ob = LineFilter(**{**flt.__dict__})
    f_ob.exclude_sources = ()
    ob_lines = select(JournalLine.account_id, func.sum(JournalLine.debit - JournalLine.credit)).where(
        JournalLine.source_module == "OPENING")
    ob_mov = {aid: Decimal(v) for aid, v in db.execute(
        f_ob.apply(ob_lines, date_from=date_from, date_to=date_to).group_by(JournalLine.account_id)).all()}
    lines: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for aid, m in mov.items():
        a = chart.accounts[aid]
        if _is_cash(a):
            continue
        if a.pl_section and a.pl_section != "TAXATION":
            lines["PBT"] += -m
            if a.cf_adjustment:
                lines[a.cf_adjustment] += m
                lines[a.cf_counter_line or "INV_PPE"] += -m
        else:
            lines[a.cash_flow_line or ("OP_ACCRUALS" if a.account_type == AccountType.LIABILITY else "OP_ADVANCES")] += -m
    ob_non_cash = -sum((v for aid, v in ob_mov.items() if not _is_cash(chart.accounts[aid])), ZERO)
    f_cash = LineFilter(**{**flt.__dict__})
    f_cash.exclude_sources = ()
    cash_ids = [a.id for a in chart.accounts.values() if _is_cash(a) and a.is_postable]
    f_cash.account_ids = cash_ids
    open_bal = sum((dr - cr for dr, cr in balances_by_account(db, f_cash, before=date_from).values()), ZERO)
    close_bal = sum((dr - cr for dr, cr in balances_by_account(db, f_cash, date_to=date_to).values()), ZERO)
    out: list[dict] = []
    totals: dict[str, Decimal] = {}
    for section, label in (("OPERATING", "CASH FLOWS FROM OPERATING ACTIVITIES"),
                           ("INVESTING", "CASH FLOWS FROM INVESTING ACTIVITIES"),
                           ("FINANCING", "CASH FLOWS FROM FINANCING ACTIVITIES")):
        out.append({"label": label, "level": 0, "style": "header", "c0": None})
        sec_total = ZERO
        for code, (sec, lbl, _order) in sorted(CASH_FLOW_LINES.items(), key=lambda kv: kv[1][2]):
            if sec != section:
                continue
            v = money(lines.get(code, ZERO))
            if v or code == "PBT":
                out.append({"label": lbl, "level": 1, "style": "line", "c0": v, "code": code})
            if section == "OPERATING" and code == "ADJ_FINANCE":
                out.append({"label": "Operating cash flow before working capital changes", "level": 1,
                            "style": "subtotal", "c0": money(sum(lines.get(k, ZERO) for k in ("PBT", "ADJ_DA", "ADJ_DISPOSAL", "ADJ_FINANCE")))})
            sec_total += v
        totals[section] = money(sec_total)
        out.append({"label": f"Net cash from {section.lower()} activities", "level": 0, "style": "total", "c0": totals[section]})
    net = totals["OPERATING"] + totals["INVESTING"] + totals["FINANCING"]
    if ob_non_cash:
        out.append({"label": "Opening balances migrated in the period", "level": 0, "style": "line", "c0": money(ob_non_cash)})
        net += ob_non_cash
    unclassified = money(lines.get("EXCLUDED", ZERO))
    if unclassified:
        out.append({"label": "Opening balance clearing (should be nil)", "level": 0, "style": "line", "c0": unclassified})
        net += unclassified
    out += [{"label": "NET INCREASE / (DECREASE) IN CASH AND CASH EQUIVALENTS", "level": 0, "style": "grand", "c0": money(net)},
            {"label": "Cash and cash equivalents at beginning of period", "level": 0, "style": "line", "c0": money(open_bal)},
            {"label": "CASH AND CASH EQUIVALENTS AT END OF PERIOD", "level": 0, "style": "grand", "c0": money(close_bal)}]
    diff = money(open_bal + net - close_bal)
    return {"title": "Statement of Cash Flows (indirect method)", "company": _company(db, company_id).name,
            "subtitle": f"{date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}",
            "columns": [{"key": "label", "label": "", "type": "text"}, {"key": "c0", "label": "PKR", "type": "money"}],
            "rows": out, "meta": {"opening_cash": money(open_bal), "closing_cash": money(close_bal),
                                  "net_change": money(net), "difference": diff, "reconciles": diff == 0,
                                  "sections": totals}}


DIRECT_LABELS = [
    ("receipts_customers", "Receipts from customers (box office, F&B, advertising)"),
    ("payments_suppliers", "Payments to suppliers and distributors"),
    ("payments_employees", "Payments to and on behalf of employees"),
    ("taxes", "Taxes paid / (refunded)"),
    ("other_operating", "Other operating receipts / (payments)"),
    ("investing", "Investing activities"),
    ("financing", "Financing activities"),
]


def _direct_category(a: Account) -> str:
    cf = a.cash_flow_line or ""
    if cf.startswith("INV_"):
        return "investing"
    if cf.startswith("FIN_"):
        return "financing"
    if a.pl_section in ("REVENUE", "OTHER_INCOME") or cf == "OP_RECEIVABLES" or a.party_type.value == "CUSTOMER":
        return "receipts_customers"
    if a.code.startswith("06-01") or a.party_type.value == "EMPLOYEE" or a.code in ("02-02-02-0004", "02-02-02-0005"):
        return "payments_employees"
    if a.control_type.value == "TAX" or a.pl_section == "TAXATION" or cf in ("OP_TAX_PAID", "OP_TAXES"):
        return "taxes"
    if a.party_type.value == "SUPPLIER" or a.pl_section in ("COST_OF_SALES", "OPEX") or cf in ("OP_INVENTORY", "OP_ADVANCES", "OP_PAYABLES", "OP_ACCRUALS"):
        return "payments_suppliers"
    return "other_operating"


def cash_flow_direct(db: Session, company_id: int, actor: Actor | None, date_from: date, date_to: date, *,
                     flt: LineFilter | None = None) -> dict:
    """Direct method: each journal's cash movement is classified by its counter-account lines."""
    flt = flt or LineFilter.build(company_id, actor)
    chart = ChartCache(db)
    cash_ids = {a.id for a in chart.accounts.values() if _is_cash(a)}
    f = LineFilter(**{**flt.__dict__})
    f.exclude_sources = ("CLOSING", "OPENING")
    jids = select(JournalLine.journal_id).where(JournalLine.account_id.in_(cash_ids))
    jids = f.apply(jids, date_from=date_from, date_to=date_to).distinct()
    cats: dict[str, Decimal] = defaultdict(lambda: ZERO)
    q = select(JournalLine.account_id, func.sum(JournalLine.debit - JournalLine.credit)).where(
        JournalLine.journal_id.in_(jids), JournalLine.account_id.not_in(cash_ids)).group_by(JournalLine.account_id)
    for aid, net in db.execute(q).all():
        cats[_direct_category(chart.accounts[aid])] += -Decimal(net)
    rows_out = [{"label": lbl, "level": 1, "style": "line", "c0": money(cats.get(k, ZERO)), "code": k}
                for k, lbl in DIRECT_LABELS]
    total = money(sum(cats.values(), ZERO))
    rows_out.append({"label": "NET CASH MOVEMENT", "level": 0, "style": "grand", "c0": total})
    return {"title": "Statement of Cash Flows (direct method)", "company": _company(db, company_id).name,
            "subtitle": f"{date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}",
            "columns": [{"key": "label", "label": "", "type": "text"}, {"key": "c0", "label": "PKR", "type": "money"}],
            "rows": rows_out, "meta": {"net": total}}


def cash_by_account(db: Session, company_id: int, actor: Actor | None, date_from: date, date_to: date) -> dict:
    from backend.banking.models import BankAccount
    accts = db.scalars(select(BankAccount).where(BankAccount.company_id == company_id).order_by(BankAccount.code)).all()
    out = []
    for ba in accts:
        if actor and ba.site_id and not actor.can_site(ba.site_id):
            continue
        base = select(func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0)).where(
            JournalLine.is_posted.is_(True), JournalLine.company_id == company_id, JournalLine.account_id == ba.gl_account_id)
        if ba.site_id:
            base = base.where(JournalLine.site_id == ba.site_id)
        else:
            base = base.where(JournalLine.site_id.is_(None)) if _shared_gl(db, ba) else base
        o_dr, o_cr = db.execute(base.where(JournalLine.posting_date < date_from)).one()
        p_dr, p_cr = db.execute(base.where(JournalLine.posting_date.between(date_from, date_to))).one()
        opening = Decimal(o_dr) - Decimal(o_cr)
        out.append({"label": f"{ba.code} {ba.name}", "level": 1, "style": "line", "c0": money(opening),
                    "c1": money(p_dr), "c2": money(p_cr), "c3": money(opening + Decimal(p_dr) - Decimal(p_cr)),
                    "bank_account_id": ba.id, "drill": {"account_id": ba.gl_account_id, "site_id": ba.site_id}})
    tot = [money(sum((r[f"c{i}"] for r in out), ZERO)) for i in range(4)]
    out.append({"label": "TOTAL", "level": 0, "style": "grand", **{f"c{i}": tot[i] for i in range(4)}})
    return {"title": "Cash and Bank Position by Account", "company": _company(db, company_id).name,
            "subtitle": f"{date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}",
            "columns": [{"key": "label", "label": "Account", "type": "text"},
                        {"key": "c0", "label": "Opening", "type": "money"}, {"key": "c1", "label": "Receipts", "type": "money"},
                        {"key": "c2", "label": "Payments", "type": "money"}, {"key": "c3", "label": "Closing", "type": "money"}],
            "rows": out, "meta": {}}


def _shared_gl(db: Session, ba) -> bool:
    from backend.banking.models import BankAccount
    return (db.scalar(select(func.count()).select_from(BankAccount).where(BankAccount.gl_account_id == ba.gl_account_id)) or 0) > 1


# ------------------------------------------------------------------ trial balance and GL
def trial_balance(db: Session, company_id: int, actor: Actor | None, date_from: date, date_to: date, *,
                  flt: LineFilter | None = None, include_zero: bool = False, exclude_closing: bool = False) -> dict:
    flt = flt or LineFilter.build(company_id, actor)
    if exclude_closing:
        flt.exclude_sources = ("CLOSING",)
    chart = ChartCache(db)
    opening = balances_by_account(db, flt, before=date_from)
    period = balances_by_account(db, flt, date_from=date_from, date_to=date_to)
    rows_out = []
    tot = [ZERO] * 6
    for a in sorted([a for a in chart.accounts.values() if a.is_postable], key=lambda a: a.code):
        o_dr, o_cr = opening.get(a.id, (ZERO, ZERO))
        p_dr, p_cr = period.get(a.id, (ZERO, ZERO))
        o = o_dr - o_cr
        c = o + p_dr - p_cr
        vals = [o if o > 0 else ZERO, -o if o < 0 else ZERO, p_dr, p_cr, c if c > 0 else ZERO, -c if c < 0 else ZERO]
        if not include_zero and not any(vals):
            continue
        abnormal = (a.sign * c) < 0 and not a.is_contra
        rows_out.append({"label": f"{a.code}  {a.name}", "code": a.code, "name": a.name, "account_id": a.id, "level": 1,
                         "style": "line", **{f"c{i}": money(v) for i, v in enumerate(vals)},
                         "abnormal": abnormal, "drill": {"account_id": a.id}})
        tot = [t + v for t, v in zip(tot, vals)]
    rows_out.append({"label": "TOTAL", "level": 0, "style": "grand", **{f"c{i}": money(v) for i, v in enumerate(tot)}})
    cols = [{"key": "label", "label": "Account", "type": "text"}] + [
        {"key": f"c{i}", "label": l, "type": "money"} for i, l in enumerate(
            ["Opening Dr", "Opening Cr", "Period Dr", "Period Cr", "Closing Dr", "Closing Cr"])]
    return {"title": "Trial Balance", "company": _company(db, company_id).name,
            "subtitle": f"{date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}", "columns": cols,
            "rows": rows_out, "meta": {"balanced": money(tot[4]) == money(tot[5]) and money(tot[2]) == money(tot[3]),
                                       "totals": [money(t) for t in tot]}}


def gl_detail(db: Session, company_id: int, actor: Actor | None, date_from: date, date_to: date, *,
              flt: LineFilter, page_no: int = 1, page_size: int = 200) -> dict:
    """Ledger lines with opening and running balance (window function; paginated)."""
    L, J = JournalLine, JournalEntry
    opening = sum(((dr - cr) for dr, cr in balances_by_account(db, flt, before=date_from).values()), ZERO)
    running = func.sum(L.debit - L.credit).over(order_by=(L.posting_date, L.journal_id, L.id))
    base = select(L.id, L.posting_date, L.journal_id, J.number, J.journal_type, J.description.label("jdesc"),
                  L.description, L.reference, L.account_id, L.site_id, L.cost_centre_id, L.supplier_id, L.customer_id,
                  L.debit, L.credit, running.label("running")).join(J, J.id == L.journal_id)
    base = flt.apply(base, date_from=date_from, date_to=date_to)
    sub = base.subquery()
    total = db.scalar(select(func.count()).select_from(sub)) or 0
    page_size = max(1, min(page_size, 1000))
    data = db.execute(select(sub).order_by(sub.c.posting_date, sub.c.journal_id, sub.c.id)
                      .limit(page_size).offset((max(page_no, 1) - 1) * page_size)).all()
    chart = ChartCache(db)
    sites = {s.id: s.code for s in db.scalars(select(Site)).all()}
    ccs = {c.id: c.code for c in db.scalars(select(CostCentre)).all()}
    tot = db.execute(flt.apply(select(func.coalesce(func.sum(L.debit), 0), func.coalesce(func.sum(L.credit), 0)),
                               date_from=date_from, date_to=date_to)).one()
    items = []
    for r in data:
        a = chart.accounts[r.account_id]
        items.append({"line_id": r.id, "date": r.posting_date.isoformat(), "journal_id": r.journal_id, "number": r.number,
                      "journal_type": r.journal_type.value if hasattr(r.journal_type, "value") else r.journal_type,
                      "description": r.description or r.jdesc, "reference": r.reference, "account_code": a.code,
                      "account_name": a.name, "site": sites.get(r.site_id), "cost_centre": ccs.get(r.cost_centre_id),
                      "supplier_id": r.supplier_id, "customer_id": r.customer_id,
                      "debit": money(r.debit), "credit": money(r.credit), "balance": money(opening + Decimal(r.running))})
    return {"opening": money(opening), "period_debit": money(tot[0]), "period_credit": money(tot[1]),
            "closing": money(opening + Decimal(tot[0]) - Decimal(tot[1])), "items": items, "total": total,
            "page": page_no, "page_size": page_size}


def gl_detail_report(db: Session, company_id: int, actor: Actor | None, date_from: date, date_to: date, *,
                     flt: LineFilter, title: str = "General Ledger") -> dict:
    """Export-friendly GL (all lines; streams page by page)."""
    rows_out = []
    pg = 1
    head = None
    while True:
        d = gl_detail(db, company_id, actor, date_from, date_to, flt=flt, page_no=pg, page_size=1000)
        if head is None:
            head = d
            rows_out.append({"label": "Opening balance", "style": "subtotal", "level": 0, "balance": d["opening"]})
        for it in d["items"]:
            rows_out.append({"label": it["date"], "level": 1, "style": "line", **it})
        if pg * 1000 >= d["total"]:
            break
        pg += 1
    rows_out.append({"label": "Closing balance", "style": "grand", "level": 0, "debit": head["period_debit"],
                     "credit": head["period_credit"], "balance": head["closing"]})
    cols = [{"key": "label", "label": "Date", "type": "text"}, {"key": "number", "label": "Journal", "type": "text"},
            {"key": "account_code", "label": "Account", "type": "text"}, {"key": "description", "label": "Description", "type": "text"},
            {"key": "site", "label": "Site", "type": "text"}, {"key": "cost_centre", "label": "CC", "type": "text"},
            {"key": "debit", "label": "Debit", "type": "money"}, {"key": "credit", "label": "Credit", "type": "money"},
            {"key": "balance", "label": "Balance", "type": "money"}]
    return {"title": title, "company": _company(db, company_id).name,
            "subtitle": f"{date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}",
            "columns": cols, "rows": rows_out, "meta": {}}


def monthly_movements(db: Session, company_id: int, actor: Actor | None, date_from: date, date_to: date, *,
                      flt: LineFilter, compare_prior_year: bool = False) -> dict:
    """Monthly / comparative GL: account x month net movement matrix."""
    months = month_ranges(date_from, date_to)
    chart = ChartCache(db)
    data = []
    ranges = [(lbl, a, b) for lbl, a, b in months]
    if compare_prior_year:
        ranges += [(f"PY {lbl}", _shift_year(a, -1), _shift_year(b, -1)) for lbl, a, b in months]
    for lbl, a, b in ranges:
        data.append({aid: dr - cr for aid, (dr, cr) in balances_by_account(db, flt, date_from=a, date_to=b).items()})
    used = sorted({aid for d in data for aid in d}, key=lambda i: chart.accounts[i].code)
    rows_out = []
    for aid in used:
        a = chart.accounts[aid]
        vals = [money(d.get(aid, ZERO)) for d in data]
        rows_out.append({"label": f"{a.code}  {a.name}", "level": 1, "style": "line", "account_id": aid,
                         "drill": {"account_id": aid}, **{f"c{i}": v for i, v in enumerate(vals)},
                         f"c{len(data)}": money(sum(vals[:len(months)], ZERO))})
    cols = [{"key": "label", "label": "Account", "type": "text"}] + [
        {"key": f"c{i}", "label": lbl, "type": "money", "date_from": a.isoformat(), "date_to": b.isoformat()}
        for i, (lbl, a, b) in enumerate(ranges)] + [{"key": f"c{len(ranges)}", "label": "Total", "type": "money"}]
    return {"title": "Monthly General Ledger Movements (net debit / (credit))", "company": _company(db, company_id).name,
            "subtitle": f"{date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}", "columns": cols,
            "rows": rows_out, "meta": {}}


def period_bounds(db: Session, company_id: int, period_id: int) -> tuple[date, date]:
    p = db.get(AccountingPeriod, period_id)
    if p is None or p.company_id != company_id:
        raise NotFound("Period not found")
    return p.start_date, p.end_date


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def prior_month_end(d: date) -> date:
    return date(d.year, d.month, 1) - timedelta(days=1)
