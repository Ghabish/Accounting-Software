"""Create the schema (if needed) and load reference data.

    python -m scripts.seed                 # production: reference data + company + admin user
    python -m scripts.seed --demo          # + clearly-labelled [DEMO] masters and demo users

Production databases should be created with Alembic first:  alembic upgrade head
"""
from __future__ import annotations

import argparse
import os

from backend.database import models  # noqa: F401
from backend.database.base import Base
from backend.database.seed.seed import DEMO_PASSWORD, seed_all
from backend.database.session import SessionLocal, get_engine


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="load [DEMO] masters and demo users")
    ap.add_argument("--create-schema", action="store_true", help="create tables without Alembic (development only)")
    args = ap.parse_args()
    eng = get_engine()
    if args.create_schema:
        Base.metadata.create_all(eng)
        from migrations.triggers import install_triggers
        with eng.begin() as c:
            install_triggers(c)
    with SessionLocal() as db:
        from backend.config import get_settings
        result = seed_all(db, demo=args.demo, admin_password=get_settings().admin_password or os.environ.get("UCF_ADMIN_PASSWORD"))
        db.commit()
    print(f"Seeded company {result['company_id']}; {result['accounts_created']} accounts created.")
    if result["admin_password"]:
        print(f"Initial administrator: admin / {result['admin_password']}  (change it at first sign-in)")
    if args.demo:
        print(f"Demo users (cfo, fm, accountant, ap, ar, cashier.emp, manager.emp, auditor) password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
