"""Cinema management reporting. Operational statistics come from day-closed POS sales; revenue values
are the ex-tax amounts posted to the GL at day close, and a reconciliation report proves they agree."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.accounting.models import Account, JournalLine
from backend.cinema.models import BoxOfficeSale, DayClose, Film, FnBSale, PaymentMethod, RevenueType, Screen, Show
from backend.core.actor import Actor
from backend.core.money import ZERO, money
from backend.masters.models import Site

GROUPS = {"site": "Cinema", "screen": "Screen", "film": "Film", "show": "Show", "revenue_type": "Revenue type",
          "payment_method": "Payment method", "date": "Business date", "distributor": "Distributor"}


def _posted_rows(db: Session, model, company_id: int, date_from: date, date_to: date, site_ids, actor: Actor | None):
    q = select(model).join(DayClose, DayClose.id == model.day_close_id).where(
        model.company_id == company_id, DayClose.status == "POSTED", model.business_date.between(date_from, date_to))
    if site_ids:
        q = q.where(model.site_id.in_(site_ids))
    if actor is not None and actor.site_ids is not None:
        q = q.where(model.site_id.in_(actor.site_ids))
    return db.scalars(q).all()


def revenue_analysis(db: Session, company_id: int, date_from: date, date_to: date, group_by: str = "site", *,
                     site_ids: list[int] | None = None, actor: Actor | None = None) -> dict:
    if group_by not in GROUPS:
        group_by = "site"
    bo = _posted_rows(db, BoxOfficeSale, company_id, date_from, date_to, site_ids, actor)
    fnb = _posted_rows(db, FnBSale, company_id, date_from, date_to, site_ids, actor) if group_by in (
        "site", "date", "payment_method", "revenue_type") else []
    sites = {s.id: s for s in db.scalars(select(Site))}
    screens = {s.id: s for s in db.scalars(select(Screen))}
    films = {f.id: f for f in db.scalars(select(Film))}
    rts = {r.id: r for r in db.scalars(select(RevenueType))}
    pms = {p.id: p for p in db.scalars(select(PaymentMethod))}
    from backend.ap.models import Supplier
    sups = {s.id: s for s in db.scalars(select(Supplier))}
    shows = {s.id: s for s in db.scalars(select(Show).where(Show.business_date.between(date_from, date_to)))}

    def key(r, is_fnb=False):
        if group_by == "site":
            return sites[r.site_id].name
        if group_by == "screen":
            return f"{sites[r.site_id].name} - {screens[r.screen_id].name}"
        if group_by == "film":
            return films[r.film_id].title
        if group_by == "distributor":
            return sups[films[r.film_id].distributor_id].name
        if group_by == "show":
            sh = shows.get(r.show_id) if r.show_id else None
            return f"{sh.show_time:%d %b %H:%M} {screens[r.screen_id].name} {films[r.film_id].title}" if sh else "(no show reference)"
        if group_by == "revenue_type":
            return rts[r.revenue_type_id].name
        if group_by == "payment_method":
            return pms[r.payment_method_id].name
        return r.business_date.isoformat()

    agg: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: ZERO))
    show_sets: dict[str, set] = defaultdict(set)
    for r in bo:
        a = agg[key(r)]
        a["tickets"] += r.tickets_sold
        a["comps"] += r.complimentary_tickets
        a["comp_value"] += r.complimentary_value
        a["refund_tickets"] += r.refund_tickets
        a["ticket_gross"] += r.gross_amount
        a["discounts"] += r.discount_amount
        a["refunds"] += r.refund_amount
        a["ticket_net"] += r.net_revenue
        a["tax"] += r.tax_amount
        a["film_rental"] += r.film_rental_amount
        if r.show_id:
            show_sets[key(r)].add(r.show_id)
    for r in fnb:
        a = agg[key(r, True)]
        a["fnb_gross"] += r.gross_amount
        a["fnb_net"] += r.net_revenue
        a["tax"] += r.tax_amount
        a["discounts"] += r.discount_amount
        a["refunds"] += r.refund_amount
    rows_out = []
    total = defaultdict(lambda: ZERO)
    for k in sorted(agg):
        a = agg[k]
        n_shows = len(show_sets.get(k, ()))
        capacity = sum(shows[s].capacity for s in show_sets.get(k, ()) if s in shows)
        row = {"label": k, "level": 1, "style": "line", "tickets": int(a["tickets"]), "comps": int(a["comps"]),
               "ticket_gross": money(a["ticket_gross"]), "discounts": money(a["discounts"]), "refunds": money(a["refunds"]),
               "ticket_net": money(a["ticket_net"]), "fnb_net": money(a["fnb_net"]),
               "total_net": money(a["ticket_net"] + a["fnb_net"]), "film_rental": money(a["film_rental"]),
               "atp": money(a["ticket_net"] / a["tickets"]) if a["tickets"] else None,
               "sph": money(a["fnb_net"] / a["tickets"]) if a["tickets"] and a["fnb_net"] else None,
               "shows": n_shows, "rev_per_show": money(a["ticket_net"] / n_shows) if n_shows else None,
               "occupancy": (Decimal(a["tickets"]) / capacity * 100).quantize(Decimal("0.1")) if capacity else None}
        rows_out.append(row)
        for f in ("tickets", "comps", "ticket_gross", "discounts", "refunds", "ticket_net", "fnb_net", "total_net", "film_rental", "shows"):
            total[f] += row[f]
    tot = {"label": "TOTAL", "level": 0, "style": "grand", **{k: (int(v) if k in ("tickets", "comps", "shows") else money(v)) for k, v in total.items()}}
    if total["tickets"]:
        tot["atp"] = money(total["ticket_net"] / total["tickets"])
        tot["sph"] = money(total["fnb_net"] / total["tickets"]) if total["fnb_net"] else None
    rows_out.append(tot)
    cols = [("label", GROUPS[group_by], "text"), ("tickets", "Tickets sold", "int"), ("comps", "Complimentary", "int"),
            ("ticket_gross", "Ticket gross (incl. tax)", "money"), ("discounts", "Discounts", "money"), ("refunds", "Refunds", "money"),
            ("ticket_net", "Ticket revenue (net)", "money"), ("fnb_net", "F&B revenue (net)", "money"),
            ("total_net", "Total revenue", "money"), ("atp", "Avg ticket price", "money"), ("sph", "F&B spend per head", "money"),
            ("shows", "Shows", "int"), ("rev_per_show", "Revenue per show", "money"), ("occupancy", "Occupancy %", "pct"),
            ("film_rental", "Film rental", "money")]
    return {"title": f"Revenue by {GROUPS[group_by]}", "subtitle": f"{date_from} to {date_to}",
            "columns": [{"key": k, "label": l, "type": t} for k, l, t in cols], "rows": rows_out, "meta": {}}


def kpis(db: Session, company_id: int, date_from: date, date_to: date, *, site_ids=None, actor: Actor | None = None) -> dict:
    rep = revenue_analysis(db, company_id, date_from, date_to, "site", site_ids=site_ids, actor=actor)
    t = rep["rows"][-1]
    n_screens = db.scalar(select(func.count()).select_from(Screen).join(Site, Site.id == Screen.site_id).where(
        Site.company_id == company_id, Screen.is_active.is_(True), *( [Screen.site_id.in_(site_ids)] if site_ids else []))) or 0
    adv = db.scalar(select(func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0)).join(Account, Account.id == JournalLine.account_id).where(
        JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.posting_date.between(date_from, date_to),
        Account.revenue_stream == "ADVERTISING", Account.pl_section == "REVENUE",
        *([JournalLine.site_id.in_(site_ids)] if site_ids else []))) or 0
    tickets = t.get("tickets") or 0
    ticket_net = t.get("ticket_net") or ZERO
    total_net = (t.get("total_net") or ZERO) + Decimal(adv)
    return {"admissions": tickets, "complimentary": t.get("comps") or 0, "ticket_revenue": ticket_net,
            "fnb_revenue": t.get("fnb_net") or ZERO, "advertising_revenue": money(adv), "total_revenue": money(total_net),
            "average_ticket_price": t.get("atp"), "spend_per_head": t.get("sph"), "discounts": t.get("discounts") or ZERO,
            "refunds": t.get("refunds") or ZERO, "film_rental": t.get("film_rental") or ZERO,
            "film_rental_pct": (t["film_rental"] / ticket_net * 100).quantize(Decimal("0.1")) if ticket_net else None,
            "screens": n_screens, "revenue_per_screen": money(total_net / n_screens) if n_screens else None,
            "shows": t.get("shows") or 0, "revenue_per_show": money(ticket_net / t["shows"]) if t.get("shows") else None}


def gl_reconciliation(db: Session, company_id: int, date_from: date, date_to: date) -> dict:
    """Recognised POS revenue (ex-tax) per stream vs GL revenue posted by the cinema module."""
    def recognised_ticket():
        # non-deferred sales recognised on their day close; deferred sales recognised when released
        a = db.scalar(select(func.coalesce(func.sum(BoxOfficeSale.net_revenue), 0)).join(DayClose, DayClose.id == BoxOfficeSale.day_close_id)
                      .where(BoxOfficeSale.company_id == company_id, BoxOfficeSale.is_deferred.is_(False), DayClose.status == "POSTED",
                             DayClose.business_date.between(date_from, date_to))) or 0
        b = db.scalar(select(func.coalesce(func.sum(BoxOfficeSale.net_revenue), 0)).join(DayClose, DayClose.id == BoxOfficeSale.released_day_close_id)
                      .where(BoxOfficeSale.company_id == company_id, DayClose.status == "POSTED",
                             DayClose.business_date.between(date_from, date_to))) or 0
        return Decimal(a) + Decimal(b)
    fnb = Decimal(db.scalar(select(func.coalesce(func.sum(FnBSale.net_revenue), 0)).join(DayClose, DayClose.id == FnBSale.day_close_id)
                            .where(FnBSale.company_id == company_id, DayClose.status == "POSTED",
                                   DayClose.business_date.between(date_from, date_to))) or 0)

    def gl(stream):
        return Decimal(db.scalar(select(func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0)).join(
            Account, Account.id == JournalLine.account_id).where(
            JournalLine.company_id == company_id, JournalLine.is_posted.is_(True), JournalLine.source_module == "CINEMA",
            JournalLine.posting_date.between(date_from, date_to), Account.pl_section == "REVENUE",
            Account.revenue_stream == stream)) or 0)
    tk, gl_tk, gl_fnb = recognised_ticket(), gl("TICKETING"), gl("FNB")
    rows_out = [{"label": "Ticketing", "c0": money(tk), "c1": money(gl_tk), "c2": money(tk - gl_tk), "level": 1, "style": "line"},
                {"label": "Food & beverage", "c0": money(fnb), "c1": money(gl_fnb), "c2": money(fnb - gl_fnb), "level": 1, "style": "line"}]
    ok = money(tk - gl_tk) == 0 and money(fnb - gl_fnb) == 0
    return {"title": "POS Revenue to GL Reconciliation", "subtitle": f"{date_from} to {date_to}",
            "columns": [{"key": "label", "label": "Stream", "type": "text"}, {"key": "c0", "label": "POS (day-closed, ex-tax)", "type": "money"},
                        {"key": "c1", "label": "GL revenue (cinema module)", "type": "money"}, {"key": "c2", "label": "Difference", "type": "money"}],
            "rows": rows_out, "meta": {"reconciled": ok}}
