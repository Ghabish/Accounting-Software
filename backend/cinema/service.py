"""Cinema operations accounting.

Day close for one site and business date turns imported POS sales into:
  DCL journal  Dr cash / card clearing / gateway / wallet / platform (collections)
               Dr discounts and refunds (contra revenue)
               Cr revenue by stream (site, cost centre, SCREEN / FILM / DISTRIBUTOR dimensions)
               Cr output taxes (tax-inclusive POS prices are split with the configured tax codes)
               Cr advance ticket sales (tickets sold for future show dates - IFRS 15 deferral)
               +/- cash over / short against the declared cash count
  FRA journal  Dr film rental (distributor share of net box office by week since release)
               Cr accrued film rental
  Collection batches - expected settlement per payment method, cleared by settlements.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.accounting import engine
from backend.accounting.engine import LineInput
from backend.accounting.models import Account, JournalEntry, JournalType, SourceModule
from backend.ap.models import APDocType, Supplier
from backend.audit.service import record
from backend.banking.models import BankAccount, BankMatch
from backend.cinema.models import (
    BoxOfficeSale, CollectionAllocation, CollectionBatch, CollectionSettlement, DayClose, DistributorSettlement,
    DistributorSettlementLine, Film, FilmTerm, FnBSale, PaymentMethod, RevenueType, SalesImportBatch, Screen, Show,
)
from backend.core.actor import Actor
from backend.core.exceptions import Conflict, NotFound, ValidationFailed
from backend.core.money import ZERO, D, money
from backend.masters.models import CostCentre, DimensionType, DimensionValue, Site
from backend.tax import engine as tax
from backend.tax.models import TaxCode

ADVANCE_TICKETS = "02-02-02-0012"
FILM_RENTAL = "05-01-01-0001"
FILM_RENTAL_ADJ = "05-01-01-0002"
ACCRUED_FILM_RENTAL = "02-02-02-0006"
CASH_OVER_SHORT = "06-04-02-0004"
FNB_CASH = "01-02-07-0003"


def _acc(db: Session, code: str) -> int:
    return db.scalar(select(Account.id).where(Account.code == code))


def _cc(db: Session, company_id: int, code: str) -> int:
    return db.scalar(select(CostCentre.id).where(CostCentre.company_id == company_id, CostCentre.code == code))


def _dim_type(db: Session, code: str) -> DimensionType:
    return db.scalar(select(DimensionType).where(DimensionType.code == code))


# ------------------------------------------------------------------ masters
def ensure_dimension(db: Session, type_code: str, code: str, name: str, site_id: int | None = None) -> int:
    dt = _dim_type(db, type_code)
    dv = db.scalar(select(DimensionValue).where(DimensionValue.dimension_type_id == dt.id, DimensionValue.code == code))
    if dv is None:
        dv = DimensionValue(dimension_type_id=dt.id, code=code, name=name, site_id=site_id)
        db.add(dv)
        db.flush()
    elif dv.name != name:
        dv.name = name
    return dv.id


def validate_screen(db: Session, actor: Actor, obj: Screen, data: dict) -> None:
    site = db.get(Site, data.get("site_id") or obj.site_id)
    if site is None:
        raise ValidationFailed("Site not found")
    actor.require_site(site.id)
    code = data.get("code") or obj.code
    data["dimension_value_id"] = ensure_dimension(db, "SCREEN", f"{site.code}-{code}",
                                                  f"{site.name} {data.get('name') or obj.name}", site.id)


def validate_film(db: Session, actor: Actor, obj: Film, data: dict) -> None:
    dist = db.get(Supplier, data.get("distributor_id") or obj.distributor_id)
    if dist is None:
        raise ValidationFailed("Distributor (supplier) not found")
    code = data.get("code") or obj.code
    data["dimension_value_id"] = ensure_dimension(db, "FILM", code, data.get("title") or obj.title)
    ensure_dimension(db, "DISTRIBUTOR", dist.code, dist.name)


def set_film_terms(db: Session, actor: Actor, film_id: int, terms: list[dict]) -> Film:
    actor.require("cinema.manage")
    film = db.get(Film, film_id)
    if film is None:
        raise NotFound("Film not found")
    film.terms = [FilmTerm(site_id=t.get("site_id"), week_from=t["week_from"], week_to=t["week_to"],
                           share_pct=D(t["share_pct"]), minimum_guarantee=t.get("minimum_guarantee")) for t in terms]
    db.flush()
    record(db, actor, "film.terms", "film", film.id, None, {"terms": [{k: str(v) for k, v in t.items()} for t in terms]})
    return film


def share_pct(film: Film, site_id: int, on_date: date) -> Decimal:
    week = max((on_date - film.release_date).days // 7 + 1, 1)
    specific = [t for t in film.terms if t.site_id == site_id and t.week_from <= week <= t.week_to]
    general = [t for t in film.terms if t.site_id is None and t.week_from <= week <= t.week_to]
    term = (specific or general or [None])[0]
    if term is None:
        raise ValidationFailed(f"No distributor terms for film {film.code} in week {week}", code="no_film_terms")
    return term.share_pct


# ------------------------------------------------------------------ sales import
def _closed(db: Session, site_id: int, business_date: date) -> bool:
    return db.scalar(select(DayClose.id).where(DayClose.site_id == site_id, DayClose.business_date == business_date,
                                               DayClose.status == "POSTED")) is not None


def import_box_office(db: Session, actor: Actor, company_id: int, rows: list[dict], filename: str | None = None) -> SalesImportBatch:
    actor.require("cinema.import")
    sites = {s.code: s for s in db.scalars(select(Site).where(Site.company_id == company_id))}
    rtypes = {r.code: r for r in db.scalars(select(RevenueType))}
    pms = {p.code: p for p in db.scalars(select(PaymentMethod))}
    films = {f.code: f for f in db.scalars(select(Film))}
    batch = SalesImportBatch(kind="BOX_OFFICE", filename=filename, created_by_id=actor.id)
    db.add(batch)
    db.flush()
    errors = []
    created = []
    for i, r in enumerate(rows, start=1):
        p = f"Row {i}: "
        site = sites.get(str(r.get("site_code")))
        film = films.get(str(r.get("film_code")))
        rt = rtypes.get(str(r.get("revenue_type_code")))
        pm = pms.get(str(r.get("payment_method_code")))
        if not site or not film or not rt or not pm:
            errors.append(p + "unknown site, film, revenue type or payment method code")
            continue
        if rt.stream != "TICKETING":
            errors.append(p + f"revenue type {rt.code} is not a ticketing type")
            continue
        if not actor.can_site(site.id):
            errors.append(p + f"not authorised for site {site.code}")
            continue
        bdate = r["business_date"] if isinstance(r["business_date"], date) else date.fromisoformat(str(r["business_date"])[:10])
        if _closed(db, site.id, bdate):
            errors.append(p + f"{site.code} {bdate} is already day-closed")
            continue
        screen = db.scalar(select(Screen).where(Screen.site_id == site.id, Screen.code == str(r.get("screen_code"))))
        if screen is None:
            errors.append(p + "unknown screen code for the site")
            continue
        show = None
        if r.get("show_date"):
            sdate = r["show_date"] if isinstance(r["show_date"], date) else date.fromisoformat(str(r["show_date"])[:10])
            from datetime import datetime, time
            st = r.get("show_time") or "00:00"
            hh, mm = (int(x) for x in str(st)[:5].split(":"))
            show_dt = datetime.combine(sdate, time(hh, mm))
            show = db.scalar(select(Show).where(Show.screen_id == screen.id, Show.show_time == show_dt))
            if show is None:
                show = Show(site_id=site.id, screen_id=screen.id, film_id=film.id, business_date=sdate, show_time=show_dt,
                            capacity=screen.seats, created_by_id=actor.id)
                db.add(show)
                db.flush()
        ref = r.get("source_ref")
        if ref and db.scalar(select(BoxOfficeSale.id).where(BoxOfficeSale.source_ref == str(ref), BoxOfficeSale.site_id == site.id)):
            errors.append(p + f"duplicate POS reference {ref}")
            continue
        try:
            vals = {k: money(r.get(k) or 0) for k in ("gross_amount", "discount_amount", "refund_amount", "complimentary_value")}
        except ValueError:
            errors.append(p + "invalid amount")
            continue
        if any(v < 0 for v in vals.values()):
            errors.append(p + "negative amounts are not allowed")
            continue
        created.append(BoxOfficeSale(company_id=company_id, site_id=site.id, business_date=bdate, show_id=show.id if show else None,
                                     screen_id=screen.id, film_id=film.id, revenue_type_id=rt.id, payment_method_id=pm.id,
                                     tickets_sold=int(r.get("tickets_sold") or 0), complimentary_tickets=int(r.get("complimentary_tickets") or 0),
                                     refund_tickets=int(r.get("refund_tickets") or 0), import_batch_id=batch.id,
                                     source_ref=str(ref) if ref else None, created_by_id=actor.id, **vals))
    if errors:
        raise ValidationFailed("Box office import rejected - nothing was imported", code="import_failed", details=errors[:200])
    db.add_all(created)
    batch.row_count = len(created)
    db.flush()
    record(db, actor, "cinema.import_box_office", "sales_import_batch", batch.id, None, {"rows": len(created), "file": filename})
    return batch


def import_fnb(db: Session, actor: Actor, company_id: int, rows: list[dict], filename: str | None = None) -> SalesImportBatch:
    actor.require("cinema.import")
    sites = {s.code: s for s in db.scalars(select(Site).where(Site.company_id == company_id))}
    rtypes = {r.code: r for r in db.scalars(select(RevenueType))}
    pms = {p.code: p for p in db.scalars(select(PaymentMethod))}
    batch = SalesImportBatch(kind="FNB", filename=filename, created_by_id=actor.id)
    db.add(batch)
    db.flush()
    errors, created = [], []
    for i, r in enumerate(rows, start=1):
        p = f"Row {i}: "
        site, rt, pm = sites.get(str(r.get("site_code"))), rtypes.get(str(r.get("revenue_type_code"))), pms.get(str(r.get("payment_method_code")))
        if not site or not rt or not pm or rt.stream != "FNB":
            errors.append(p + "unknown site / payment method or not an F&B revenue type")
            continue
        if not actor.can_site(site.id):
            errors.append(p + f"not authorised for site {site.code}")
            continue
        bdate = r["business_date"] if isinstance(r["business_date"], date) else date.fromisoformat(str(r["business_date"])[:10])
        if _closed(db, site.id, bdate):
            errors.append(p + f"{site.code} {bdate} is already day-closed")
            continue
        vals = {k: money(r.get(k) or 0) for k in ("gross_amount", "discount_amount", "refund_amount")}
        if any(v < 0 for v in vals.values()):
            errors.append(p + "negative amounts are not allowed")
            continue
        created.append(FnBSale(company_id=company_id, site_id=site.id, business_date=bdate, revenue_type_id=rt.id,
                               payment_method_id=pm.id, quantity=int(r.get("quantity") or 0), import_batch_id=batch.id,
                               source_ref=r.get("source_ref"), created_by_id=actor.id, **vals))
    if errors:
        raise ValidationFailed("F&B import rejected - nothing was imported", code="import_failed", details=errors[:200])
    db.add_all(created)
    batch.row_count = len(created)
    db.flush()
    record(db, actor, "cinema.import_fnb", "sales_import_batch", batch.id, None, {"rows": len(created)})
    return batch


# ------------------------------------------------------------------ day close
class _Lines:
    """Accumulates signed amounts per posting key and emits net one-sided journal lines."""

    def __init__(self):
        self.amounts: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
        self.meta: dict[tuple, dict] = {}

    def add(self, account_id: int, amount: Decimal, *, site_id=None, cc_id=None, customer_id=None, dims=None,
            tax_code_id=None, description=None):
        key = (account_id, site_id, cc_id, customer_id, tuple(sorted((dims or {}).items())), tax_code_id)
        self.amounts[key] += amount  # positive = debit
        self.meta.setdefault(key, {"description": description})

    def lines(self) -> list[LineInput]:
        out = []
        for key, amt in self.amounts.items():
            amt = money(amt)
            if amt == 0:
                continue
            aid, sid, cid, cus, dims, tcid = key
            out.append(LineInput(account_id=aid, debit=amt if amt > 0 else ZERO, credit=-amt if amt < 0 else ZERO,
                                 site_id=sid, cost_centre_id=cid, customer_id=cus, dimensions=dict(dims),
                                 tax_code_id=tcid, description=self.meta[key]["description"]))
        return out


def _tax_ids(rt: RevenueType) -> list[int]:
    return [int(x) for x in (rt.tax_code_ids or "").split(",") if x.strip()]


def _split(db: Session, amount: Decimal, rt: RevenueType, on_date: date, site_id: int):
    if not amount:
        return ZERO, []
    return tax.split_inclusive(db, amount, _tax_ids(rt), on_date, site_id)


def _film_dims(db: Session, row: BoxOfficeSale, cache: dict) -> dict[int, int]:
    if row.film_id not in cache:
        film = db.get(Film, row.film_id)
        dist = db.get(Supplier, film.distributor_id)
        dt_film, dt_dist = _dim_type(db, "FILM"), _dim_type(db, "DISTRIBUTOR")
        d = {}
        if film.dimension_value_id:
            d[dt_film.id] = film.dimension_value_id
        d[dt_dist.id] = ensure_dimension(db, "DISTRIBUTOR", dist.code, dist.name)
        cache[row.film_id] = d
    screen = db.get(Screen, row.screen_id)
    out = dict(cache[row.film_id])
    if screen.dimension_value_id:
        out[_dim_type(db, "SCREEN").id] = screen.dimension_value_id
    return out


def preview_day_close(db: Session, company_id: int, site_id: int, business_date: date) -> dict:
    bo = db.scalars(select(BoxOfficeSale).where(BoxOfficeSale.site_id == site_id, BoxOfficeSale.business_date == business_date,
                                                BoxOfficeSale.day_close_id.is_(None))).all()
    fnb = db.scalars(select(FnBSale).where(FnBSale.site_id == site_id, FnBSale.business_date == business_date,
                                           FnBSale.day_close_id.is_(None))).all()
    pms = {p.id: p for p in db.scalars(select(PaymentMethod))}
    by_pm: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for r in list(bo) + list(fnb):
        by_pm[pms[r.payment_method_id].code] += r.net_collected
    return {"box_office_rows": len(bo), "fnb_rows": len(fnb), "tickets": sum(r.tickets_sold for r in bo),
            "ticket_gross": money(sum((r.gross_amount for r in bo), ZERO)), "fnb_gross": money(sum((r.gross_amount for r in fnb), ZERO)),
            "collections": {k: money(v) for k, v in by_pm.items()}, "already_closed": _closed(db, site_id, business_date)}


def day_close(db: Session, actor: Actor, company_id: int, site_id: int, business_date: date, *,
              cash_declared: Decimal | None = None, notes: str | None = None) -> DayClose:
    actor.require("cinema.day_close")
    actor.require_site(site_id)
    site = db.get(Site, site_id)
    if site is None or site.company_id != company_id:
        raise NotFound("Site not found")
    if _closed(db, site_id, business_date):
        raise Conflict(f"{site.name} {business_date} is already day-closed", code="already_closed")
    bo = db.scalars(select(BoxOfficeSale).where(BoxOfficeSale.site_id == site_id, BoxOfficeSale.business_date == business_date,
                                                BoxOfficeSale.day_close_id.is_(None)).with_for_update()).all()
    fnb = db.scalars(select(FnBSale).where(FnBSale.site_id == site_id, FnBSale.business_date == business_date,
                                           FnBSale.day_close_id.is_(None)).with_for_update()).all()
    release = db.scalars(select(BoxOfficeSale).join(Show, Show.id == BoxOfficeSale.show_id).where(
        BoxOfficeSale.site_id == site_id, BoxOfficeSale.is_deferred.is_(True), BoxOfficeSale.released_day_close_id.is_(None),
        BoxOfficeSale.day_close_id.is_not(None), Show.business_date == business_date).with_for_update()).all()
    if not bo and not fnb and not release:
        raise ValidationFailed("No sales imported for this site and date")
    rtypes = {r.id: r for r in db.scalars(select(RevenueType))}
    pms = {p.id: p for p in db.scalars(select(PaymentMethod))}
    shows = {}
    adv_acc, fnb_cash = _acc(db, ADVANCE_TICKETS), _acc(db, FNB_CASH)
    L, F = _Lines(), _Lines()
    film_cache: dict = {}
    batches: dict[int, Decimal] = defaultdict(lambda: ZERO)
    tax_totals: dict[int, list] = defaultdict(lambda: [ZERO, ZERO])  # tax code -> [base, tax]
    cash_expected = ZERO
    totals = defaultdict(lambda: ZERO)
    film_rental_total = ZERO
    film_cc = _cc(db, company_id, "040201")

    def collect(pm: PaymentMethod, amount: Decimal, stream: str):
        nonlocal cash_expected
        acc_id = fnb_cash if (pm.method_type == "CASH" and stream == "FNB") else pm.clearing_account_id
        acc = db.get(Account, acc_id)
        cus = pm.customer_id if acc.party_type.value == "CUSTOMER" else None
        if acc.party_rule.value == "REQ" and not cus:
            raise ValidationFailed(f"Payment method {pm.code} needs a customer configured for its clearing account")
        L.add(acc_id, amount, site_id=site_id if acc.site_rule.value != "NONE" else None, customer_id=cus,
              description=f"{pm.name} collections {business_date}")
        if pm.method_type == "CASH":
            cash_expected += amount
        elif pm.method_type not in ("VOUCHER",):
            batches[pm.id] += amount

    def revenue(rt: RevenueType, r, net_g, net_d, net_r, dims, credit_account=None):
        if credit_account:  # deferred: hold the net amount in advance ticket sales
            L.add(credit_account, -(net_g - net_d - net_r), site_id=site_id, description=f"Advance ticket sales {business_date}")
            return
        L.add(rt.revenue_account_id, -net_g, site_id=site_id, cc_id=rt.cost_centre_id, dims=dims, description=rt.name)
        if net_d:
            L.add(rt.discount_account_id or rt.revenue_account_id, net_d, site_id=site_id, cc_id=rt.cost_centre_id, dims=dims,
                  description=f"{rt.name} - discounts")
        if net_r:
            L.add(rt.refund_account_id or rt.revenue_account_id, net_r, site_id=site_id, cc_id=rt.cost_centre_id, dims=dims,
                  description=f"{rt.name} - refunds")

    def film_rental(r: BoxOfficeSale, rt: RevenueType, dims: dict, on_date: date):
        nonlocal film_rental_total
        if not rt.applies_film_rental or not r.net_revenue:
            return
        film = db.get(Film, r.film_id)
        amt = money(r.net_revenue * share_pct(film, site_id, on_date))
        r.film_rental_amount = amt
        film_rental_total += amt
        F.add(_acc(db, FILM_RENTAL), amt, site_id=site_id, cc_id=film_cc, dims=dims, description=f"Film rental {film.title}")
        F.add(_acc(db, ACCRUED_FILM_RENTAL), -amt, site_id=site_id, description=f"Accrued film rental {film.title}")

    def taxes(calcs_g, calcs_d, calcs_r):
        for sign, calcs in ((1, calcs_g), (-1, calcs_d), (-1, calcs_r)):
            for c in calcs:
                tax_totals[c.tax_code.id][0] += sign * c.base
                tax_totals[c.tax_code.id][1] += sign * c.amount

    for r in bo:
        rt, pm = rtypes[r.revenue_type_id], pms[r.payment_method_id]
        net_g, cg = _split(db, r.gross_amount, rt, business_date, site_id)
        net_d, cd = _split(db, r.discount_amount, rt, business_date, site_id)
        net_r, cr = _split(db, r.refund_amount, rt, business_date, site_id)
        r.net_revenue = money(net_g - net_d - net_r)
        r.tax_amount = money(r.net_collected - r.net_revenue)
        dims = _film_dims(db, r, film_cache)
        show = shows.setdefault(r.show_id, db.get(Show, r.show_id)) if r.show_id else None
        r.is_deferred = bool(show and show.business_date > business_date)
        revenue(rt, r, net_g, net_d, net_r, dims, adv_acc if r.is_deferred else None)
        if r.is_deferred:
            totals["deferred"] += r.net_revenue
        else:
            film_rental(r, rt, dims, business_date)
            totals["ticket_net"] += r.net_revenue
        taxes(cg, cd, cr)
        collect(pm, r.net_collected, "TICKETING")
        totals["ticket_gross"] += r.gross_amount
    for r in release:  # advance sales whose show is today
        rt = rtypes[r.revenue_type_id]
        sale_date = r.business_date
        net_g, _ = _split(db, r.gross_amount, rt, sale_date, site_id)
        net_d, _ = _split(db, r.discount_amount, rt, sale_date, site_id)
        net_r, _ = _split(db, r.refund_amount, rt, sale_date, site_id)
        dims = _film_dims(db, r, film_cache)
        L.add(adv_acc, r.net_revenue, site_id=site_id, description=f"Release advance ticket sales {business_date}")
        revenue(rt, r, net_g, net_d, net_r, dims)
        film_rental(r, rt, dims, business_date)
        totals["released"] += r.net_revenue
        totals["ticket_net"] += r.net_revenue
    for r in fnb:
        rt, pm = rtypes[r.revenue_type_id], pms[r.payment_method_id]
        net_g, cg = _split(db, r.gross_amount, rt, business_date, site_id)
        net_d, cd = _split(db, r.discount_amount, rt, business_date, site_id)
        net_r, cr = _split(db, r.refund_amount, rt, business_date, site_id)
        r.net_revenue = money(net_g - net_d - net_r)
        r.tax_amount = money(r.net_collected - r.net_revenue)
        revenue(rt, r, net_g, net_d, net_r, {})
        taxes(cg, cd, cr)
        collect(pm, r.net_collected, "FNB")
        totals["fnb_gross"] += r.gross_amount
        totals["fnb_net"] += r.net_revenue
    for tcid, (base, amt) in tax_totals.items():
        tc = db.get(TaxCode, tcid)
        L.add(tc.account_id, -amt, tax_code_id=tc.id, description=f"{tc.name} {business_date}")
    over_short = ZERO
    if cash_declared is not None:
        over_short = money(D(cash_declared) - cash_expected)
        if over_short:
            bo_cash = next((p.clearing_account_id for p in pms.values() if p.method_type == "CASH"), None)
            L.add(bo_cash, over_short, site_id=site_id, description="Cash count difference")
            L.add(_acc(db, CASH_OVER_SHORT), -over_short, site_id=site_id, cc_id=_cc(db, company_id, "010201"),
                  description="Cash over / (short)")
    dc = DayClose(company_id=company_id, site_id=site_id, business_date=business_date, status="POSTED",
                  ticket_gross=money(totals["ticket_gross"]), ticket_net_revenue=money(totals["ticket_net"]),
                  fnb_gross=money(totals["fnb_gross"]), fnb_net_revenue=money(totals["fnb_net"]),
                  tax_total=money(sum((v[1] for v in tax_totals.values()), ZERO)), film_rental=money(film_rental_total),
                  cash_expected=money(cash_expected), cash_declared=money(cash_declared) if cash_declared is not None else None,
                  cash_over_short=over_short, deferred_amount=money(totals["deferred"]), released_amount=money(totals["released"]),
                  notes=notes, created_by_id=actor.id)
    db.add(dc)
    db.flush()
    seq = db.scalar(select(func.count()).select_from(DayClose).where(DayClose.site_id == site_id,
                                                                     DayClose.business_date == business_date))
    je = engine.create_and_post(db, actor, company_id=company_id, journal_type=JournalType.DCL, transaction_date=business_date,
                                description=f"Day close {site.name} {business_date.isoformat()}", lines=L.lines(),
                                reference=f"DC-{site.code}-{business_date.isoformat()}", source_module=SourceModule.CINEMA,
                                source_type="day_close", source_id=dc.id, source_key=f"DCL-{site_id}-{business_date}-{seq}")
    dc.journal_id = je.id
    for tcid, (base, amt) in tax_totals.items():
        if amt:
            tc = db.get(TaxCode, tcid)
            tax.record(db, company_id=company_id, calc=tax.TaxCalc(tc, D("0"), money(base), money(amt), None), journal=je,
                       journal_line=tax.line_for(je, tc.account_id, tc.id), source_type="day_close", source_id=dc.id,
                       transaction_date=business_date, site_id=site_id, document_ref=f"DC-{site.code}-{business_date}")
    if F.amounts:
        fje = engine.create_and_post(db, actor, company_id=company_id, journal_type=JournalType.FRA, transaction_date=business_date,
                                     description=f"Film rental accrual {site.name} {business_date.isoformat()}", lines=F.lines(),
                                     source_module=SourceModule.CINEMA, source_type="day_close_film_rental", source_id=dc.id,
                                     source_key=f"FRA-{site_id}-{business_date}-{seq}")
        dc.film_rental_journal_id = fje.id
    for r in list(bo) + list(fnb):
        r.day_close_id = dc.id
    for r in release:
        r.released_day_close_id = dc.id
    for pm_id, amt in batches.items():
        if amt:
            db.add(CollectionBatch(company_id=company_id, site_id=site_id, business_date=business_date, payment_method_id=pm_id,
                                   day_close_id=dc.id, expected_amount=money(amt)))
    db.flush()
    record(db, actor, "cinema.day_close", "day_close", dc.id, None,
           {"site": site.code, "date": business_date.isoformat(), "journal": je.number, "film_rental": str(dc.film_rental)})
    return dc


def reverse_day_close(db: Session, actor: Actor, dc_id: int, reason: str) -> DayClose:
    actor.require("cinema.day_close")
    dc = db.scalar(select(DayClose).where(DayClose.id == dc_id).with_for_update())
    if dc is None or dc.status != "POSTED":
        raise Conflict("Only posted day closes can be reversed")
    actor.require_site(dc.site_id)
    batches = db.scalars(select(CollectionBatch).where(CollectionBatch.day_close_id == dc.id)).all()
    if any(b.settled_gross for b in batches):
        raise Conflict("Collections from this day have been settled; reverse the settlements first")
    if db.scalar(select(func.count()).select_from(BoxOfficeSale).where(
            BoxOfficeSale.day_close_id == dc.id, BoxOfficeSale.distributor_settlement_id.is_not(None))):
        raise Conflict("Film rental from this day has been settled with the distributor")
    if db.scalar(select(func.count()).select_from(BoxOfficeSale).where(BoxOfficeSale.day_close_id == dc.id,
                                                                        BoxOfficeSale.is_deferred.is_(True),
                                                                        BoxOfficeSale.released_day_close_id.is_not(None))):
        raise Conflict("Advance sales from this day were already recognised; reverse the later day close first")
    rev = engine.create_reversal(db, dc.journal_id, actor, dc.business_date, reason, post=True)
    tax.reverse_for_journal(db, dc.journal_id, rev)
    if dc.film_rental_journal_id:
        engine.create_reversal(db, dc.film_rental_journal_id, actor, dc.business_date, reason, post=True)
    for b in batches:
        db.delete(b)
    for r in db.scalars(select(BoxOfficeSale).where(BoxOfficeSale.day_close_id == dc.id)).all():
        r.day_close_id, r.net_revenue, r.tax_amount, r.film_rental_amount, r.is_deferred = None, ZERO, ZERO, ZERO, False
    for r in db.scalars(select(BoxOfficeSale).where(BoxOfficeSale.released_day_close_id == dc.id)).all():
        r.released_day_close_id, r.film_rental_amount = None, ZERO
    for r in db.scalars(select(FnBSale).where(FnBSale.day_close_id == dc.id)).all():
        r.day_close_id, r.net_revenue, r.tax_amount = None, ZERO, ZERO
    dc.status = "REVERSED"
    record(db, actor, "cinema.day_close_reverse", "day_close", dc.id, None, {"reason": reason})
    return dc


# ------------------------------------------------------------------ collections
def settle(db: Session, actor: Actor, company_id: int, *, payment_method_id: int, bank_account_id: int, settlement_date: date,
           gross_amount: Decimal, fee_amount: Decimal = ZERO, tax_deducted: Decimal = ZERO, reference: str | None = None,
           batch_ids: list[int] | None = None) -> CollectionSettlement:
    """Acquirer / gateway / wallet settlement: Dr bank (net), Dr fees, Dr tax deducted; Cr clearing (allocated FIFO)."""
    actor.require("cinema.settle")
    pm = db.get(PaymentMethod, payment_method_id)
    ba = db.get(BankAccount, bank_account_id)
    if pm is None or ba is None:
        raise NotFound("Payment method or bank account not found")
    gross, fee, wht = money(gross_amount), money(fee_amount), money(tax_deducted)
    net = gross - fee - wht
    if gross <= 0 or net < 0:
        raise ValidationFailed("Settlement amounts are invalid")
    q = select(CollectionBatch).where(CollectionBatch.company_id == company_id, CollectionBatch.payment_method_id == pm.id,
                                      CollectionBatch.status.in_(["OPEN", "PARTIAL"]))
    if batch_ids:
        q = q.where(CollectionBatch.id.in_(batch_ids))
    open_batches = db.scalars(q.order_by(CollectionBatch.business_date, CollectionBatch.id).with_for_update()).all()
    remaining = gross
    allocs: list[tuple[CollectionBatch, Decimal]] = []
    for b in open_batches:
        if remaining <= 0:
            break
        take = min(b.expected_amount - b.settled_gross, remaining)
        if take > 0:
            allocs.append((b, take))
            remaining -= take
    if remaining > 0:
        raise ValidationFailed(f"Settlement exceeds open collections for {pm.name} by {remaining:,.2f}", code="over_settlement")
    clearing = db.get(Account, pm.clearing_account_id)
    cus = pm.customer_id if clearing.party_type.value == "CUSTOMER" else None
    lines = [LineInput(account_id=ba.gl_account_id, debit=net, site_id=ba.site_id, description=f"{pm.name} settlement {reference or ''}",
                       reference=reference)] if net else []
    fee_left, wht_left = fee, wht
    wht_code = db.scalar(select(TaxCode).where(TaxCode.code == "WHT-SUFF-STL"))
    tkt_cc = _cc(db, company_id, "010201")
    for i, (b, amt) in enumerate(allocs):
        last = i == len(allocs) - 1
        f_share = fee_left if last else money(fee * amt / gross)
        w_share = wht_left if last else money(wht * amt / gross)
        fee_left -= f_share
        wht_left -= w_share
        lines.append(LineInput(account_id=clearing.id, credit=amt, site_id=b.site_id if clearing.site_rule.value != "NONE" else None,
                               customer_id=cus, description=f"{pm.name} {b.business_date}", reference=reference))
        if f_share:
            lines.append(LineInput(account_id=pm.fee_account_id or _acc(db, "06-04-02-0001"), debit=f_share, site_id=b.site_id,
                                   cost_centre_id=tkt_cc, description=f"{pm.name} charges {b.business_date}"))
        if w_share:
            lines.append(LineInput(account_id=wht_code.account_id, debit=w_share, tax_code_id=wht_code.id,
                                   customer_id=cus if db.get(Account, wht_code.account_id).party_type.value == "CUSTOMER" else None,
                                   description=f"Tax deducted on {pm.name} settlement"))
        b.settled_gross = money(b.settled_gross + amt)
        b.fee_amount = money(b.fee_amount + f_share)
        b.tax_deducted = money(b.tax_deducted + w_share)
        b.net_received = money(b.net_received + amt - f_share - w_share)
        b.status = "SETTLED" if b.settled_gross == b.expected_amount else "PARTIAL"
    je = engine.create_and_post(db, actor, company_id=company_id, journal_type=JournalType.STL, transaction_date=settlement_date,
                                description=f"{pm.name} settlement {reference or ''}".strip(), lines=lines, reference=reference,
                                source_module=SourceModule.CINEMA, source_type="collection_settlement")
    s = CollectionSettlement(company_id=company_id, payment_method_id=pm.id, bank_account_id=ba.id, settlement_date=settlement_date,
                             gross_amount=gross, fee_amount=fee, tax_deducted=wht, net_amount=net, reference=reference,
                             journal_id=je.id, created_by_id=actor.id)
    s.allocations = [CollectionAllocation(batch_id=b.id, amount=a) for b, a in allocs]
    db.add(s)
    db.flush()
    if wht:
        tax.record(db, company_id=company_id, calc=tax.TaxCalc(wht_code, (wht / gross).quantize(D("0.000001")), gross, wht, None),
                   journal=je, journal_line=tax.line_for(je, wht_code.account_id), source_type="collection_settlement",
                   source_id=s.id, transaction_date=settlement_date, document_ref=reference)
    record(db, actor, "cinema.settlement", "collection_settlement", s.id, None, {"gross": str(gross), "net": str(net)})
    return s


def revenue_reconciliation(db: Session, company_id: int, date_from: date, date_to: date, actor: Actor | None = None) -> dict:
    """Sales -> expected collection -> actual settlement -> bank receipt (matched) -> accounting entry."""
    pms = {p.id: p for p in db.scalars(select(PaymentMethod))}
    sites = {s.id: s for s in db.scalars(select(Site))}
    rows_out = []
    q = select(CollectionBatch).where(CollectionBatch.company_id == company_id,
                                      CollectionBatch.business_date.between(date_from, date_to))
    tot = defaultdict(lambda: ZERO)
    for b in db.scalars(q.order_by(CollectionBatch.business_date, CollectionBatch.site_id)).all():
        if actor and not actor.can_site(b.site_id):
            continue
        dc = db.get(DayClose, b.day_close_id)
        settlements = db.scalars(select(CollectionSettlement).join(CollectionAllocation).where(CollectionAllocation.batch_id == b.id)).all()
        bank_ok = None
        stl_numbers = []
        for s in settlements:
            je = db.get(JournalEntry, s.journal_id)
            stl_numbers.append(je.number)
            ba = db.get(BankAccount, s.bank_account_id)
            bank_line = next((l for l in je.lines if l.account_id == ba.gl_account_id), None)
            matched = bank_line is not None and db.scalar(select(BankMatch.id).where(BankMatch.journal_line_id == bank_line.id,
                                                                                     BankMatch.is_active.is_(True))) is not None
            bank_ok = matched if bank_ok is None else (bank_ok and matched)
        diff = b.expected_amount - b.settled_gross
        rows_out.append({"label": b.business_date.isoformat(), "site": sites[b.site_id].name, "method": pms[b.payment_method_id].name,
                         "expected": b.expected_amount, "settled": b.settled_gross, "fees": b.fee_amount, "tax": b.tax_deducted,
                         "net": b.net_received, "difference": diff, "status": b.status,
                         "bank": "-" if bank_ok is None else ("Matched" if bank_ok else "Not matched"),
                         "day_close_journal": db.scalar(select(JournalEntry.number).where(JournalEntry.id == dc.journal_id)),
                         "settlement_journals": ", ".join(stl_numbers), "level": 1, "style": "line", "batch_id": b.id})
        for k in ("expected", "settled", "fees", "tax", "net", "difference"):
            tot[k] += rows_out[-1][k]
    for dc in db.scalars(select(DayClose).where(DayClose.company_id == company_id, DayClose.status == "POSTED",
                                                DayClose.business_date.between(date_from, date_to))).all():
        if dc.cash_declared is None and not dc.cash_expected:
            continue
        if actor and not actor.can_site(dc.site_id):
            continue
        rows_out.append({"label": dc.business_date.isoformat(), "site": sites[dc.site_id].name, "method": "Cash (counted)",
                         "expected": dc.cash_expected, "settled": dc.cash_declared if dc.cash_declared is not None else dc.cash_expected,
                         "difference": -dc.cash_over_short, "status": "OVER/SHORT" if dc.cash_over_short else "AGREED",
                         "day_close_journal": db.scalar(select(JournalEntry.number).where(JournalEntry.id == dc.journal_id)),
                         "level": 1, "style": "line"})
    rows_out.append({"label": "TOTAL (non-cash)", "level": 0, "style": "grand", **{k: money(v) for k, v in tot.items()}})
    cols = [("label", "Business date", "text"), ("site", "Site", "text"), ("method", "Payment method", "text"),
            ("expected", "Sales / expected", "money"), ("settled", "Settled (gross)", "money"), ("fees", "Charges", "money"),
            ("tax", "Tax deducted", "money"), ("net", "Bank receipt (net)", "money"), ("difference", "Difference", "money"),
            ("status", "Status", "text"), ("bank", "Bank statement", "text"), ("day_close_journal", "Day-close journal", "text"),
            ("settlement_journals", "Settlement journal(s)", "text")]
    return {"title": "Revenue and Collections Reconciliation", "subtitle": f"{date_from} to {date_to}",
            "columns": [{"key": k, "label": l, "type": t} for k, l, t in cols], "rows": rows_out,
            "meta": {"open_difference": money(tot["difference"])}}


# ------------------------------------------------------------------ distributor settlements
def prepare_distributor_settlement(db: Session, actor: Actor, company_id: int, distributor_id: int, period_from: date,
                                   period_to: date, reference: str | None = None, adjustment: Decimal = ZERO,
                                   notes: str | None = None) -> DistributorSettlement:
    actor.require("cinema.settle")
    dist = db.get(Supplier, distributor_id)
    if dist is None:
        raise NotFound("Distributor not found")
    film_ids = db.scalars(select(Film.id).where(Film.distributor_id == dist.id)).all()
    rows = db.scalars(select(BoxOfficeSale).where(BoxOfficeSale.film_id.in_(film_ids or [0]),
                                                  BoxOfficeSale.distributor_settlement_id.is_(None),
                                                  BoxOfficeSale.film_rental_amount != 0).with_for_update()).all()
    picked = []
    for r in rows:
        rec_dc = db.get(DayClose, r.released_day_close_id if r.is_deferred else r.day_close_id) if (r.released_day_close_id or r.day_close_id) else None
        if rec_dc and rec_dc.status == "POSTED" and period_from <= rec_dc.business_date <= period_to:
            picked.append(r)
    if not picked:
        raise ValidationFailed("No unsettled film rental for this distributor and period")
    s = DistributorSettlement(company_id=company_id, distributor_id=dist.id, period_from=period_from, period_to=period_to,
                              reference=reference, adjustment=money(adjustment), notes=notes, created_by_id=actor.id)
    groups: dict[tuple, list] = defaultdict(lambda: [0, ZERO, ZERO])
    for r in picked:
        g = groups[(r.film_id, r.site_id)]
        g[0] += r.tickets_sold
        g[1] += r.net_revenue
        g[2] += r.film_rental_amount
    s.lines = [DistributorSettlementLine(film_id=f, site_id=si, tickets=v[0], net_box_office=money(v[1]), accrued_amount=money(v[2]))
               for (f, si), v in groups.items()]
    s.net_box_office = money(sum((v[1] for v in groups.values()), ZERO))
    s.accrued_amount = money(sum((v[2] for v in groups.values()), ZERO))
    s.total = s.accrued_amount + s.adjustment
    db.add(s)
    db.flush()
    for r in picked:
        r.distributor_settlement_id = s.id
    record(db, actor, "cinema.distributor_settlement", "distributor_settlement", s.id, None,
           {"distributor": dist.code, "accrued": str(s.accrued_amount)})
    return s


def invoice_distributor_settlement(db: Session, actor: Actor, settlement_id: int, invoice_no: str, invoice_date: date):
    """Create the distributor's AP invoice (clears the accrual); it then follows the AP approval workflow."""
    from backend.ap import service as ap
    s = db.get(DistributorSettlement, settlement_id)
    if s is None or s.status != "DRAFT":
        raise Conflict("Settlement is not in draft")
    per_site: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for l in s.lines:
        per_site[l.site_id] += l.accrued_amount
    lines = [{"account_id": _acc(db, ACCRUED_FILM_RENTAL), "site_id": sid, "amount": amt, "st_tax_code_id": None,
              "description": f"Film rental {s.period_from} to {s.period_to}"} for sid, amt in per_site.items() if amt]
    if s.adjustment:
        if s.adjustment < 0:
            raise ValidationFailed("Negative adjustments are recorded as a supplier credit note")
        lines.append({"account_id": _acc(db, FILM_RENTAL_ADJ), "site_id": next(iter(per_site)), "st_tax_code_id": None,
                      "cost_centre_id": _cc(db, s.company_id, "040201"), "amount": s.adjustment,
                      "description": "Minimum guarantee / settlement adjustment"})
    doc, _w = ap.save_document(db, actor, s.company_id, {"doc_type": APDocType.INVOICE.value, "supplier_id": s.distributor_id,
                                                          "supplier_invoice_no": invoice_no, "invoice_date": invoice_date,
                                                          "description": f"Distributor settlement {s.period_from} to {s.period_to}",
                                                          "lines": lines})
    doc.source_type, doc.source_id = "distributor_settlement", s.id
    s.ap_document_id = doc.id
    s.status = "INVOICED"
    db.flush()
    return doc
