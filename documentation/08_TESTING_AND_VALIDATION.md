# Testing, validation and known limitations

## Automated test suite
```bash
pip install -r requirements-dev.txt
# against PostgreSQL (recommended - builds the schema through the real Alembic migrations and triggers)
UCF_TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost/ucfin_test pytest -q
# quick run on SQLite
pytest -q
```
**91 tests, all passing on PostgreSQL 16 and on SQLite** (each test module gets a freshly migrated and seeded database).

| Module | Tests | What is proven |
|---|---|---|
| `test_phase1_foundation` | 10 | chart hierarchy and contra balances, login / lockout, RBAC, account coding rules and attribute inheritance, sites and cost centres, site-scoped users, period status authority, audit log |
| `test_phase2_gl` | 17 | unbalanced and invalid journals rejected (site / cost-centre / CORP / party / restricted rules), 3-level workflow with segregation of duties and limits, posting numbers, immutability (ORM + DB trigger), abnormal-balance block, reversal, auto-reversing accruals, trial balance, P&L structure (site-wise, monthly), balance sheet balances, cash flow reconciles (indirect and direct), running balances, Excel / PDF / CSV exports, closed-period block, recurring journals |
| `test_phase3_ap_ar_bank` | 13 | AP invoice with input tax, duplicate invoice block, WHT + sales-tax withholding at payment, partial payments taxed on amount paid, rate-override authority, advances and application, credit-note allocation, AP aging / statement / reconciliation, AR invoice with output tax, receipts with tax deducted by customer, customer advances, vouchers with site restriction, AP-control protection, petty-cash block, transfers via transit, daily cash position |
| `test_phase4_tax_fa_budget_bankrec` | 8 | rate selection by payee type / ATL / date, slab tax, effective-dated rate changes, tax summary, tax-to-GL reconciliation, CPR deposits, working papers; fixed-asset capitalisation from AP, catch-up depreciation, impairment, transfer, disposal gain / loss, FA-to-GL reconciliation; budget versions, approval SoD, variance, revisions with history, advisory budget warnings; bank statement import, auto-match, adjustments, completion and history; sub-ledger summary |
| `test_phase5_cinema_close` | 8 | POS import validation and site authority, day close (tax-inclusive split, discounts, refunds, film rental by week, cash over / short), advance-sale deferral and release, card / gateway settlements, collections and POS-to-GL reconciliation, distributor settlement → AP invoice (no double settlement), cinema KPIs (ATP, SPH), film-dimension drill-down, CFO dashboard and revenue-stream filter, CFO pack PDF / Excel, sequential month-end close, closed-period block, CFO-only reasoned reopen recorded in the audit trail |
| `test_phase5_opening_yearend` | 4 | import templates, GL / supplier / customer / fixed-asset opening balances with clearing nil and accounting equation, master and journal imports with permissions, year-end close to retained earnings |
| `test_security` | 6 | security headers, production secret / database guard, site scoping of ledgers, P&L and journals, read-only auditor, token revocation on password change, upload type / name / deletion controls |
| `test_e2e_validation` | 25 | the 24-step final validation below |

## Final validation (brief section 45) — PASSED
`tests/test_e2e_validation.py`, run on PostgreSQL:

| # | Step | Result |
|---|---|---|
| 1 | Create a site | `104 [E2E] Packages Mall Lahore` created |
| 2 | Create a cost centre | `050103` created (section 05 derived) |
| 3 | Create a GL account | `06-03-01-0007` — next free code; inherits P&L section, cash-flow line, site and cost-centre rules |
| 4 | Create a supplier | code assigned; tax codes defaulted from the category |
| 5 | Enter supplier invoice | draft, due date from terms |
| 6 | Apply tax | PST 16% = 16,000; total 116,000 |
| 7 | Approve and post | approval refused before submission; submit → approve posts; AP control credited 116,000 |
| 8 | Make a payment | WHT 14% = 14,000, PST withheld 20% = 3,200, net 98,800; check + approval |
| 9 | Verify AP balance | invoice PAID, supplier statement closes at 0 |
| 10 | Verify GL | expense 100,000 at the new site and cost centre; input tax, WHT and PST-withheld payables, bank |
| 11 | Enter customer revenue | advertising invoice 580,000 (PST 80,000) + POS box office and F&B day close |
| 12 | Receive payment | 545,000 received + 35,000 tax deducted; invoice PAID |
| 13 | Reconcile the bank | CSV statement imported, all ledger items auto-matched, bank charge adjusted, difference 0, completed |
| 14 | Post depreciation | projector capitalised from its AP invoice; August run 10,000 posted by a second user |
| 15 | Trial balance | balanced |
| 16 | Monthly P&L | revenue 650,000; COS = film rental; opex 100,000; D&A 10,000; finance cost 750; EBITDA / PAT verified |
| 17 | Balance sheet | balanced; current-year profit equals P&L |
| 18 | Cash flow | reconciles; closing cash equals balance-sheet cash |
| 19 | Tax report | output 84,800; input 167,200; withheld 17,200; suffered 35,000; tax ledgers reconciled |
| 20 | Accounting equation | assets = liabilities + equity (difference 0) |
| 21 | Close the month | July and August closed through the checklist |
| 22 | Invalid posting into closed period | blocked (`period_closed`); nothing reached the GL |
| 23 | Audit trail | entries for postings, approvals, checks, period close, bank reconciliation, day close, account creation, depreciation and sign-ins, with user, time and IP; auditor cannot create |
| 24 | AP / AR / bank / fixed assets / tax reconcile to GL | all reconciled |

The E2E run found one real defect during development — accounts created through the API did not inherit
their sub-group's reporting attributes, so a new expense ledger was missing from the P&L. It was fixed and a
regression assertion was added.

## Browser verification
A Playwright run signed in as the CFO and opened every screen (≈75 routes) at desktop (1440×900) and phone
(iPhone 13) sizes: no JavaScript errors, no error toasts, no horizontal page overflow on phones. The only
finding was intended behaviour (the CFO role has no user-administration permission, so that URL returns 403;
the menu hides it and the router now redirects with a message).

## Volume test (1,000,000 posted ledger lines, PostgreSQL 16, single small container)
| Report | Time |
|---|---|
| Trial balance, full year | 0.15 s |
| P&L, full year | 0.11 s |
| P&L, monthly (13 columns) | 0.70 s |
| P&L, site-wise | 0.28 s |
| Balance sheet with comparative | 0.39 s |
| Cash flow (indirect), full year | 0.27 s |
| GL detail with running balance, page 1 / page 2,000 of 500,000 rows | 0.59 s / 0.90 s |
| CFO dashboard (month) | 1.71 s |
All statements still balanced / reconciled. Reports aggregate in SQL over indexed, denormalised posted lines;
nothing loads the ledger into memory; lists and ledgers are paginated.

## Known limitations (not built in this version)
These are outside what was implemented and are stated plainly rather than presented as working features:
1. **Inventory / F&B stock module** (recipes, stock movements, automatic F&B COGS). Inventory ledgers exist; F&B cost is posted via supplier invoices or journals; stock count is a manual month-end sign-off.
2. **Payroll / HR**. Salary costs are posted by journal or voucher; the employee master is minimal; the s.149 salary slab table is seeded for a future payroll module.
3. **Procurement** (purchase orders, GRN, three-way matching, advances limited to PO). AP invoices are non-PO.
4. **IFRS 16 lease engine** (lease schedules, ROU amortisation, interest). Ledgers and cash-flow mapping exist; entries by journal.
5. **Foreign currency** revaluation and FX documents. Fields exist; v1 operates in PKR.
6. **Intercompany** partner tagging and validation exist; an automated intercompany matching report and consolidation eliminations are not built.
7. **Tax e-filing formats** (FBR / PRA upload files). Excel working papers and registers are provided.
8. **Direct POS / ticketing connectors**. Sales arrive by CSV / Excel upload or the JSON API.
9. **E-mail notifications** for pending approvals (pending items are visible in each module by status).
10. **Separate pre-audit (Internal Audit) approval stage** and a second-approver workflow for supplier bank-detail changes (changes are fully audited).
11. **Budget import from Excel** (budgets are entered in the grid or through the bulk API) and a **company switcher** in the UI (the data model and API are multi-company).
12. **Asynchronous report jobs / materialised balances**. Not needed at the tested volume; recommended beyond ~50 million lines.
13. **Tax rates** are seeded from the Generation workbook (tax year 2027); cinema-specific items are flagged *to confirm* — entertainment duty on admissions (seeded 0%), PRA sales tax on F&B, WHT on film distributors.
