"""Generate clearly-labelled DEMO transactions so the dashboards and reports have content.

    python -m scripts.load_demo_data

Everything created here is synthetic ([DEMO] masters, round illustrative amounts). It is NOT
Universal Cinemas data. Remove it before go-live by recreating the database (see BACKUP_RESTORE.md).
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from backend.accounting import service as jsvc
from backend.accounting.engine import LineInput
from backend.ap import service as ap
from backend.ap.models import Supplier
from backend.authentication.models import User
from backend.banking.models import BankAccount
from backend.cinema import service as cinema
from backend.cinema.models import Film, PaymentMethod, Screen
from backend.core.actor import actor_for
from backend.database import models  # noqa: F401
from backend.database.seed.seed import acc
from backend.database.session import SessionLocal, get_engine
from backend.masters.models import CostCentre, Site
from backend.workflow import engine as wf

D = Decimal
random.seed(7)


def main(start: date = date(2026, 10, 1), days: int = 53) -> None:
    get_engine()
    with SessionLocal() as db:
        cfo = actor_for(db.scalar(select(User).where(User.username == "cfo")))
        fm = actor_for(db.scalar(select(User).where(User.username == "fm")))
        apu = actor_for(db.scalar(select(User).where(User.username == "ap")))
        acct = actor_for(db.scalar(select(User).where(User.username == "accountant")))
        sites = {s.code: s for s in db.scalars(select(Site))}
        cc = {c.code: c.id for c in db.scalars(select(CostCentre))}
        films = db.scalars(select(Film)).all()
        pm = {p.code: p for p in db.scalars(select(PaymentMethod))}
        bank = db.scalar(select(BankAccount).where(BankAccount.code == "BNK-OPS"))
        col = db.scalar(select(BankAccount).where(BankAccount.code == "BNK-COL"))
        # opening capital (demo)
        je, _ = jsvc.create_manual(db, fm, 1, transaction_date=date(2026, 7, 1), description="[DEMO] Share capital injected",
                                   lines=[LineInput(account_id=acc(db, "01-02-07-0006").id, debit=D("150000000")),
                                          LineInput(account_id=acc(db, "03-01-01-0001").id, credit=D("150000000"))])
        sp = jsvc.spec(db, je)
        for a, u in (("submit", fm), ("check", acct), ("approve", cfo)):
            wf.transition(db, je, sp, a, u)
        wf.transition(db, je, sp, "post", cfo)
        db.commit()
        price = {"101": 1200, "102": 900, "103": 1000}
        for i in range(days):
            day = start + timedelta(days=i)
            weekend = day.weekday() >= 4
            for scode in ("101", "102", "103"):
                site = sites[scode]
                screens = db.scalars(select(Screen).where(Screen.site_id == site.id)).all()
                rows, fnb = [], []
                for sc in screens:
                    film = films[(sc.id + i) % len(films)]
                    if film.release_date > day:
                        film = films[0]
                    tickets = int(sc.seats * random.uniform(0.25, 0.75 if weekend else 0.45))
                    for rt, pmc, share in (("TKT-COUNTER", "CASH", 0.35), ("TKT-COUNTER", "CARD-A", 0.25), ("TKT-ONLINE", "GATEWAY", 0.30), ("TKT-ONLINE", "WALLET", 0.10)):
                        t = int(tickets * share)
                        if t:
                            rows.append({"site_code": scode, "business_date": day, "screen_code": sc.code, "film_code": film.code,
                                         "show_date": day, "show_time": "19:30", "revenue_type_code": rt, "payment_method_code": pmc,
                                         "tickets_sold": t, "gross_amount": D(t * price[scode]), "discount_amount": D(int(t * price[scode] * 0.03)),
                                         "complimentary_tickets": 1 if rt == "TKT-COUNTER" and pmc == "CASH" else 0,
                                         "source_ref": f"DEMO-{scode}-{day:%Y%m%d}-{sc.code}-{rt}-{pmc}"})
                adm = sum(r["tickets_sold"] for r in rows)
                for rt, share in (("FNB-COMBO", 0.45), ("FNB-BEV", 0.25), ("FNB-FOOD", 0.30)):
                    for pmc, ps in (("CASH", 0.5), ("CARD-A", 0.5)):
                        fnb.append({"site_code": scode, "business_date": day, "revenue_type_code": rt, "payment_method_code": pmc,
                                    "quantity": int(adm * share * ps), "gross_amount": D(int(adm * 450 * share * ps))})
                cinema.import_box_office(db, cfo, 1, rows)
                cinema.import_fnb(db, cfo, 1, fnb)
                cinema.day_close(db, cfo, 1, site.id, day)
                db.commit()
            if day.weekday() == 0:  # weekly card / gateway settlements
                for code in ("CARD-A", "GATEWAY", "WALLET"):
                    open_amt = sum((b.expected_amount - b.settled_gross) for b in db.scalars(
                        select(cinema.CollectionBatch).where(cinema.CollectionBatch.payment_method_id == pm[code].id,
                                                             cinema.CollectionBatch.status.in_(["OPEN", "PARTIAL"]),
                                                             cinema.CollectionBatch.business_date < day))) or D("0")
                    if open_amt > 0:
                        cinema.settle(db, cfo, 1, payment_method_id=pm[code].id, bank_account_id=col.id, settlement_date=day,
                                      gross_amount=open_amt, fee_amount=(open_amt * pm[code].fee_pct).quantize(D("0.01")),
                                      reference=f"DEMO-{code}-{day:%Y%m%d}", batch_ids=None)
                db.commit()
        # monthly operating costs via AP (demo)
        sup = {s.code: s for s in db.scalars(select(Supplier))}
        bills = [("V00004", "06-02-01-0003", "010101", 2_500_000, "CAM and service charges"), ("V00005", "06-02-02-0001", "010101", 1_800_000, "Electricity"),
                 ("V00006", "06-03-01-0001", "050102", 450_000, "Projection maintenance"), ("V00007", "06-04-01-0001", "040101", 900_000, "Digital campaign")]
        for scode in ("101", "102", "103"):
            for vcode, account, ccode, amount, desc in bills:
                doc, _ = ap.save_document(db, apu, 1, {"supplier_id": sup[vcode].id, "supplier_invoice_no": f"DEMO-{vcode}-{scode}-OCT",
                                                       "invoice_date": date(2026, 10, 28), "site_id": sites[scode].id,
                                                       "description": f"[DEMO] {desc} October",
                                                       "lines": [{"account_id": acc(db, account).id, "cost_centre_id": cc[ccode],
                                                                  "amount": D(amount) * (D("1") if scode == "101" else D("0.7"))}]})
                s = ap.doc_spec(db, doc)
                wf.transition(db, doc, s, "submit", apu)
                wf.transition(db, doc, s, "approve", cfo)
        db.commit()
    print(f"Demo transactions loaded ({start} + {days} days).")


if __name__ == "__main__":
    main()
