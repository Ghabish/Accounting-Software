# Universal Cinemas Finance

Accounting and finance system for **Universal Cinemas / NC Entertainment**: a double-entry general ledger with
site, cost-centre and unlimited analysis dimensions; AP, AR, cash & bank, bank reconciliation, Pakistan tax
framework, fixed assets, budgeting, cinema revenue accounting (POS day close, collections, distributor
settlements), month-end and year-end close, financial statements, CFO dashboard and reporting pack.

* **Backend**: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16
* **Front end**: Vue 3 single-page app (pre-built in `frontend/dist`), responsive for desktop, tablet and phone, installable as a PWA
* **Reports**: Excel (openpyxl), PDF (ReportLab), CSV — every figure derived from the posted ledger

## Quick start (development)
```bash
pip install -r requirements-dev.txt
export UCF_DATABASE_URL=postgresql+psycopg://user:pass@localhost/ucfin
alembic upgrade head
python -m scripts.seed --demo          # reference data + [DEMO] masters and users
python -m scripts.load_demo_data       # optional synthetic transactions (Oct-Nov 2026)
uvicorn backend.main:app --reload      # http://localhost:8000  ·  API docs: /api/docs
pytest -q                              # 91 tests (set UCF_TEST_DATABASE_URL to run on PostgreSQL)
```
Production deployment (Windows Server, Linux, Docker / cloud): `documentation/02_SETUP_AND_DEPLOYMENT.md`.

## Repository layout
```
backend/
  api/            HTTP routers, request schemas, dependencies (auth, company, permissions)
  accounting/     chart, periods, journal engine (validation, posting, reversal), manual & recurring journals, immutability guards
  workflow/       configurable approval workflow, approval limits, history
  authentication/ users, roles, permissions, password hashing, JWT
  masters/        companies, sites, cost centres, dimensions, employees, settings
  ap/ ar/         sub-ledgers: documents, payments / receipts, allocations, aging, statements, reconciliation
  banking/        bank & cash accounts, vouchers, transfers, cash position, bank reconciliation
  tax/            tax codes, effective-dated rates, slabs, tax engine, transactions, deposits, reports
  assets/         fixed asset register, depreciation, transfer, disposal, impairment
  budgeting/      budgets, versions, budget control, variance
  cinema/         screens, films & distributor terms, POS import, day close, settlements, distributor settlements, KPIs
  closing/        month-end checklist, period close / reopen, year-end close
  reporting/      trial balance, GL, P&L, balance sheet, cash flow, dashboard, CFO pack, Excel / PDF / CSV export
  imports/        CSV / Excel imports, opening balances
  database/       SQLAlchemy base, session, seed data (chart of accounts in seed/coa_data.py)
frontend/         Vue 3 source (src/) and production build (dist/)
migrations/       Alembic migrations + PostgreSQL integrity triggers
tests/            automated tests incl. the 24-step end-to-end validation
configuration/    .env template, chart of accounts CSV
documentation/    analysis & design, setup, workflows, user manual, API, security, backup, testing, COA, schema
scripts/          seed, demo data, documentation export, backup scripts
```

## Documentation
| Document | |
|---|---|
| [01 Analysis & design](documentation/01_ANALYSIS_AND_DESIGN.md) | COA analysis, retained / changed, COA, sites, cost centres, DB architecture, workflow, roadmap |
| [02 Setup & deployment](documentation/02_SETUP_AND_DEPLOYMENT.md) | Windows, Linux, Docker, cloud, first sign-in, upgrades |
| [03 Accounting workflows](documentation/03_ACCOUNTING_WORKFLOWS.md) | controls, workflow, standard entries, month-end, opening balances, cash flow method |
| [04 User manual](documentation/04_USER_MANUAL.md) | day-to-day use by role |
| [05 API reference](documentation/05_API_REFERENCE.md) | endpoints (live OpenAPI at `/api/docs`) |
| [06 Security](documentation/06_SECURITY.md) | authentication, authorisation, integrity, hardening |
| [07 Backup & restore](documentation/07_BACKUP_RESTORE.md) | nightly backup, restore, restore test |
| [08 Testing & validation](documentation/08_TESTING_AND_VALIDATION.md) | test suite, 24-step E2E results, volume test, known limitations |
| [Chart of accounts](documentation/CHART_OF_ACCOUNTS.md) · [CSV](configuration/coa_universal_cinemas.csv) | 295 ledgers with all attributes |
| [Database schema](documentation/DATABASE_SCHEMA.md) | tables, columns, keys, constraints, indexes |

Sample / demo data is labelled `[DEMO]` and is never loaded into production (see 07_BACKUP_RESTORE.md).
No real Universal Cinemas financial figures are included.
