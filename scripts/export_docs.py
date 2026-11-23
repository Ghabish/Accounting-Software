"""Regenerate reference documents from the code: chart of accounts (CSV + Markdown), database schema, API reference.

    python -m scripts.export_docs
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from backend.database.seed.coa_data import CASH_FLOW_LINES, build_chart

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "documentation"
COLS = ["code", "name", "level", "parent_code", "account_type", "normal_balance", "is_contra", "control_type", "party_type",
        "party_rule", "site_rule", "cost_centre_rule", "pl_section", "revenue_stream", "cash_flow_line", "cf_adjustment",
        "cf_counter_line", "manual_journal", "abnormal_balance", "reconcile_required", "budget_control", "is_intercompany",
        "zero_at_period_end", "gen_ref", "description"]


def export_coa() -> None:
    rows = build_chart()
    with open(ROOT / "configuration" / "coa_universal_cinemas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    ledgers = [r for r in rows if r["level"] == 4]
    new = sum(1 for r in ledgers if r["gen_ref"] == "NEW")
    out = ["# Universal Cinemas - Chart of Accounts", "",
           f"Generated from `backend/database/seed/coa_data.py`. **{len(ledgers)} posting ledgers** "
           f"({len(ledgers) - new} adapted from the Generation reference chart, {new} new cinema-specific). "
           "Only level-4 ledgers accept postings. CSV: `configuration/coa_universal_cinemas.csv`.", "",
           "Legend - **NB** normal balance · **Site** site rule (REQ / OPT / NONE) · **CC** cost-centre rule (BS none, LOC optional, "
           "REQ mandatory operating cost centre, CORP company level 090101) · **Party** sub-ledger code on the line · "
           "**MJ** manual journals · **Ref** Generation ledger it was adapted from (NEW = cinema-specific).", ""]
    for r in rows:
        if r["level"] == 1:
            out += ["", f"## {r['code']} {r['name']}", ""]
        elif r["level"] == 2:
            out += ["", f"### {r['code']} {r['name']}", ""]
        elif r["level"] == 3:
            out += ["", f"**{r['code']} {r['name']}**", "",
                    "| Code | Ledger | NB | Control | Party | Site | CC | P&L / CF line | MJ | Ref |",
                    "|---|---|---|---|---|---|---|---|---|---|"]
        else:
            party = f"{r['party_type']} {r['party_rule']}" if r["party_type"] != "NONE" else ""
            line = r["pl_section"] or CASH_FLOW_LINES.get(r["cash_flow_line"] or "", ("", r["cash_flow_line"] or "", 0))[1]
            out.append(f"| {r['code']} | {r['name']}{' *(contra)*' if r['is_contra'] else ''} | {r['normal_balance']} | {r['control_type']} | "
                       f"{party} | {r['site_rule']} | {r['cost_centre_rule']} | {line} | {r['manual_journal']} | {r['gen_ref']} |")
    out += ["", "## Cash-flow line catalogue (indirect method)", "", "| Code | Section | Line |", "|---|---|---|"]
    for k, (sec, lbl, _o) in sorted(CASH_FLOW_LINES.items(), key=lambda kv: kv[1][2]):
        out.append(f"| {k} | {sec} | {lbl} |")
    (DOCS / "CHART_OF_ACCOUNTS.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def export_schema() -> None:
    from backend.database import models  # noqa: F401
    from backend.database.base import Base
    out = ["# Database schema", "", "Generated from the SQLAlchemy models (`python -m scripts.export_docs`). PostgreSQL 16 is the "
           "production database; migrations live in `migrations/versions`. Money columns are NUMERIC(18,2); rates NUMERIC(9,6).", "",
           "Integrity triggers (PostgreSQL, installed by migration 0001): posted journal lines immutable; posted journals cannot be "
           "deleted or financially altered; a journal can only become POSTED when balanced (deferred constraint trigger); audit log append-only.", ""]
    groups = defaultdict(list)
    for t in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
        groups[t.name].append(t)
    for name, (t,) in groups.items():
        out += [f"## {name}", "", "| Column | Type | Null | Key / reference |", "|---|---|---|---|"]
        for c in t.columns:
            ref = ", ".join(f"→ {fk.column.table.name}.{fk.column.name}" for fk in c.foreign_keys)
            key = "PK" if c.primary_key else ""
            out.append(f"| {c.name} | {c.type} | {'yes' if c.nullable else 'no'} | {' '.join(x for x in (key, ref) if x)} |")
        cons = [f"`{getattr(k, 'name', '')}`" for k in t.constraints if k.__class__.__name__ in ("UniqueConstraint", "CheckConstraint") and getattr(k, "name", None)]
        if cons:
            out += ["", "Constraints: " + ", ".join(sorted(set(cons)))]
        idx = [f"`{i.name}`" for i in t.indexes]
        if idx:
            out += ["", "Indexes: " + ", ".join(sorted(idx))]
        out.append("")
    (DOCS / "DATABASE_SCHEMA.md").write_text("\n".join(out), encoding="utf-8")


def export_api() -> None:
    import os
    os.environ.setdefault("UCF_FRONTEND_DIST", "/nonexistent")
    from backend.main import create_app
    spec = create_app().openapi()
    out = ["# API reference", "", "Base path `/api`. Authenticate with `POST /api/auth/login` and send `Authorization: Bearer <token>`. "
           "Interactive documentation (OpenAPI / Swagger) is served at `/api/docs` and `/api/redoc`. Errors return "
           "`{\"error\": code, \"message\": text, \"details\": [...]}` with HTTP 401 / 403 / 404 / 409 / 422.", "",
           "Report endpoints accept `format=json|xlsx|csv|pdf`. List endpoints accept `page` and `page_size`.", ""]
    by_tag = defaultdict(list)
    for path, methods in spec["paths"].items():
        for m, op in methods.items():
            by_tag[(op.get("tags") or ["other"])[0]].append((path, m.upper(), op.get("summary", "")))
    for tag in sorted(by_tag):
        out += [f"## {tag}", "", "| Method | Path | Summary |", "|---|---|---|"]
        for path, m, summ in sorted(by_tag[tag]):
            out.append(f"| {m} | `{path}` | {summ} |")
        out.append("")
    (DOCS / "05_API_REFERENCE.md").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    export_coa()
    export_schema()
    export_api()
    print("Documentation regenerated.")
