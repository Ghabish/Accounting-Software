# Universal Cinemas / NC Entertainment — Finance System
## Part 1: Analysis of the Generation Chart of Accounts and System Design

Prepared from *Generation Chart of Accounts – Developer Structure v9.2* (29 sheets). The Generation workbook is a **reference only**; the system is built for a multi-site cinema business.

---

## 1. What the uploaded COA contains

The workbook is not just a list of accounts. It is a complete ERP specification for a vertically-integrated **fashion retail and garment manufacturer**:

| Area | Content found |
|---|---|
| **Account string** | `Entity(2) . Cost Centre(6) . Ledger(00-00-00-0000)` + vendor / customer / employee code on sub-ledger ledgers. Codes stored as text. |
| **Natural account coding** | 4 levels: Class (2) → Group (2) → Sub-group (2) → Ledger (4). **8 classes, 23 groups, 61 sub-groups, 327 posting ledgers.** Only level-4 ledgers post. |
| **Classes** | 01 Assets, 02 Liabilities, 03 Equity, 04 Revenue, 05 Cost of Sales, 06 Operating Expenses, 07 Other Income & Expenses, 08 Finance Costs & Taxation. |
| **Assets** | PPE with accumulated depreciation *beside* each cost ledger, CWIP, IFRS 16 right-of-use assets, intangibles, deposits, 19 inventory ledgers (fabric, yarn, WIP, finished goods), receivables, advances, tax refunds, investments, cash and 11 bank ledgers. |
| **Liabilities / Equity** | Long-term financing, lease liabilities, gratuity, deferred tax, 14 AP control ledgers by supplier class + GRNI clearing, accruals, customer liabilities, 13 tax payable ledgers by tax and section, share capital, unappropriated profit. |
| **Revenue / COS** | Sales by channel (stores, e-commerce, marketplaces, exports, wholesale), returns and discounts as contra revenue; materials, processing charges, piece-rate labour, COGS and variances. |
| **Opex** | Expenses *by nature*, function-neutral (employee, premises, utilities, R&M, marketing, selling, distribution, travel, admin, design, D&A). |
| **Tax** | 68 configurable tax rates for tax year 2027 (WHT s.149/152/153/155/233, advance tax s.235/236, sales tax FBR, provincial sales tax PRA/SRB/KPRA/ICT, sales tax withholding), slab tables, effective dates. |
| **Cost centres** | 126 cost centres, 6 digits (section + department + sub), with P&L function, budget owner, city, province, tax authority. Location and department are combined. |
| **ERP attributes per ledger** | Account sub-type, sign multiplier, abnormal-balance control (Block/Alert/Allow), manual-journal permission, open-item management, reconciliation method/frequency/owner, currency, FX revaluation, **cash-flow category (indirect)**, budget control (None/Advisory/Absolute), intercompany flag, year-end treatment, access, zero-at-period-end, auto-reverse accruals, effective dates. |
| **Rules** | Cost-centre rules per ledger (`BS`, `LOC`, `REQ`, `PROD`, `CORP`), control ledgers require a party, register ledgers posted only by their module, 55 validation rules (V01–V55). |
| **Sub-ledgers** | Vendors (455) and customers (15) are codes on control ledgers, not GL accounts; card acquirers are bank-specific receivable ledgers, not customers. |
| **Workflow** | Preparer → Checker → Approver → (Internal Audit) → Poster; segregation of duties; approval bands; reversal instead of edit; gapless numbers at posting; period statuses Open / Soft-close / Closed. |

### Counts by control type (reference chart)
Plain ledgers 222 · Register 57 · Control 22 · Sub-ledger 12 · Bank 12 · AP clearing 2.
Cost-centre rule: BS 115 · REQ 113 · LOC 54 · PROD 26 · CORP 19.

---

## 2. What is retained

These are sound accounting design decisions and are carried into the Universal Cinemas system unchanged in principle:

1. **Code format `00-00-00-0000` and the 8 classes** — same statement mapping, same posting-at-level-4 rule.
2. **Contra accounts beside their parent** (accumulated depreciation next to cost; discounts/refunds inside revenue).
3. **Natural accounts are function-neutral**; location and function come from dimensions, never from account names (Generation Rule 1 and 2).
4. **Parties are sub-ledger codes on control accounts** (Rule 3). The GL holds one balance per control account; supplier/customer balances come from the sub-ledger; sub-ledger total must equal the control account (automatic AP/AR-vs-GL reconciliation).
5. **Tax accounts by tax type and section** (Rule 7) — e.g. separate payable ledgers for s.149, s.153(1)(a), (b), (c), s.155, provincial sales tax.
6. **One receivable/clearing ledger per card acquirer**, reconciled to its settlement report (Rule 4).
7. **Per-ledger ERP attributes**: normal balance & sign, abnormal-balance control, manual-journal control, reconciliation flag, cash-flow category, budget control, intercompany flag, zero-at-period-end.
8. **Cost-centre rules** `BS`, `LOC`, `REQ`, `CORP` (the `PROD` rule is dropped — no manufacturing).
9. **Tax rate table** structure: tax code → effective-dated rates by payee type and ATL status, posting ledger, base. The 2027 rates are loaded as *configurable seed data*, never hard-coded.
10. **Workflow and controls**: segregation of duties, approval limits by amount band, reversal-only corrections, gapless numbering at posting, period control, reconciliation sign-off before close, suspense / in-transit accounts must be nil at close.

---

## 3. What is changed for Universal Cinemas

| # | Generation design | Universal Cinemas design | Reason |
|---|---|---|---|
| 1 | Cost centre combines **location + department** (e.g. store cost centres per region). | **Site** and **Cost Centre** are *separate* dimensions, plus unlimited extra dimensions (Screen, Film, Distributor, Campaign, Project …). | Brief §3 requires site-wise and cost-centre-wise reporting independently and unlimited future dimensions. A cinema P&L is read by site *and* by function. |
| 2 | Manufacturing inventory (fabric, yarn, WIP, third-party stock), processing charges, piece-rate labour, production variances, overhead absorption. | **Removed.** Replaced by F&B inventory (food, beverages, snacks, packaging), merchandise, projection spares. | Not a manufacturing business. |
| 3 | Revenue by retail channel (stores, e-commerce, marketplaces, exports, wholesale). | Revenue by **stream**: Ticketing (counter, online, third-party, corporate, booking fees), F&B (food, beverage, combo, café, catering), Advertising (screen, lobby, sponsorship), Other (private screenings, venue hire, breakage, merchandise, parking, management fees). Each ledger carries a `revenue_stream` attribute used by the dashboard filter. | Cinema revenue model. |
| 4 | COS = materials + processing + labour + COGS. | COS = **Film rental (distributor share)**, minimum-guarantee adjustments, VPF/DCP, F&B cost of goods sold & wastage, advertising revenue share, third-party ticketing commission. | Film hire is the largest cinema cost and must sit in gross margin. |
| 5 | No distributor concept. | **Film distributors** are suppliers (AP class `DISTRIBUTOR`, control ledger `02-02-01-0001`), **accrued film rental** `02-02-02-0006`, **advances / minimum guarantees** `01-02-03-0005`, WHT on non-resident royalties `02-02-03-0013`. Distributor settlement module computes share by film × site × week. | Brief §3 "Film/distributor settlements". |
| 6 | Customers: couriers (COD), marketplaces, gateways, BNPL. | Customers: payment gateways, mobile wallets, third-party ticketing platforms, advertising clients, corporate/event clients. Walk-in moviegoers are **not** customers — POS sales post to cash / card clearing / gateway. | Cinema collection model. |
| 7 | Card receivable ledgers for named Generation banks. | Two generic acquirer ledgers + gateway + wallet ledgers, renameable. | Universal Cinemas' banks are not known — no invented bank data. |
| 8 | Tax payable ledgers for manufacturer. | Added **output sales tax on services (PRA)** for F&B/advertising, **entertainment duty/tax on tickets** (configurable, may be nil/exempt), **WHT non-resident s.152** for foreign film rights. | Cinema tax profile (to be confirmed by tax advisor — see §10). |
| 9 | No deferred revenue for advance sales. | `02-02-02-0012` **Advance ticket sales – shows not yet screened**; `02-02-02-0013` gift cards/vouchers/loyalty. | IFRS 15: revenue when the show is screened. |
| 10 | Cost centres for manufacturing sections. | New 6-digit cost-centre tree for cinema functions (§6). Format section(2)+department(2)+sub(2) retained. | |
| 11 | P&L function derived from cost-centre section (admin / selling / factory overhead). | Management P&L follows the brief: Revenue → COS → **Gross Profit** → Opex → **EBITDA** → D&A → **EBIT** → Finance cost → **PBT** → Tax → **PAT**. Each ledger has a `pl_section`; cost-centre `function` (Site operations / Head office / Company level) gives the secondary analysis and site contribution. | Brief §13. |
| 12 | Reserves ledger "Current year profit". | Dropped — current-year result is computed from the GL in the balance sheet; year-end close posts to Unappropriated profit. Added **Opening balance clearing** `03-01-03-0001` (must net to nil). | Prevents a manually-maintained profit figure disconnected from the GL. |
| 13 | Intercompany via "due from/to related parties". | Separate **Intercompany** sub-group with partner-company tagging on every intercompany line and an intercompany reconciliation report; investments in group companies; management-fee income/expense. | NC Entertainment group structure. |
| 14 | Shop cash expenses replace petty cash. | Explicit **petty cash** (imprest) per site, cash-in-hand box office and F&B, cash-in-transit (must be nil at close), funds in transit between banks. | Cinema cash handling. |

### Documented assumptions (Finance to confirm)
* **A1** Fiscal year 1 July – 30 June (Pakistan standard, as in the reference workbook).
* **A2** Functional currency PKR; foreign-currency fields exist on documents but FX revaluation is not automated in v1.
* **A3** EBITDA = Gross profit − Operating expenses (excluding D&A) + Other income − Other expenses. Configurable through each ledger's `pl_section`.
* **A4** Complimentary tickets are recorded as **statistics** (quantity and face value) and do not create GL entries; discounts and refunds are contra-revenue ledgers.
* **A5** Ticket and F&B prices are **tax-inclusive** at POS; the day-close splits net revenue and output tax using the configured tax code for each revenue type.
* **A6** Film rental is accrued at day close as `distributor % × net box office (gross less taxes)`; a weekly/periodic settlement turns the accrual into a distributor AP invoice. Terms (% by week, minimum guarantee) are configured per film agreement.
* **A7** Tax rates are seeded from the reference workbook (tax year 2027) for codes relevant to a cinema, and **marked "to confirm"**. Cinema-specific rates (entertainment duty, provincial sales tax on F&B) are seeded at the rates in the reference workbook where one exists, otherwise at 0% and flagged.
* **A8** Bank account names/numbers in the seed are placeholders ("Bank – operating current account"); no real Universal Cinemas bank data is invented.
* **A9** Site cities: Emporium = Lahore, The Grand = Multan, Buch Villas = Multan (to confirm), Head Office = Lahore (to confirm).

---

## 4. Proposed Universal Cinemas COA structure

Full listing: [`CHART_OF_ACCOUNTS.md`](CHART_OF_ACCOUNTS.md) and [`configuration/coa_universal_cinemas.csv`](../configuration/coa_universal_cinemas.csv) (generated from `backend/database/seed/coa_data.py`).

**8 classes · 23 groups · 58 sub-groups · 295 posting ledgers** (227 adapted from Generation, 68 new cinema-specific).

```
01 ASSETS
   01-01 Non-Current Assets
         01-01-01 Property, Plant and Equipment   (projection, sound, seating, kitchen, fit-out, HVAC, IT/POS …; acc. dep. beside cost)
         01-01-02 Capital Work in Progress
         01-01-03 Right-of-Use Assets             (IFRS 16 cinema premises)
         01-01-04 Intangible Assets               (ERP, ticketing systems, brand)
         01-01-05 Long-Term Deposits and Investments
   01-02 Current Assets
         01-02-01 Inventories                     (F&B food, beverages, snacks, packaging, merchandise, spares)
         01-02-02 Trade Receivables               (card acquirers, gateway, wallets, platforms, advertising, corporate)
         01-02-03 Advances, Deposits, Prepayments (incl. distributor minimum guarantees)
         01-02-04 Intercompany Receivables
         01-02-05 Tax Refunds Due from Government (input tax FBR / PRA, WHT suffered)
         01-02-06 Short-Term Investments
         01-02-07 Cash and Bank Balances          (HO cash, box office, F&B counters, petty cash, banks, in-transit)
02 LIABILITIES
   02-01 Non-Current: Long-term financing · Lease liabilities · Deferred liabilities · Deposits received
   02-02 Current:     Payables – suppliers (AP control incl. Film distributors payable) · Accrued & other
                      (accrued film rental, advance ticket sales, gift cards, customer advances, suspense)
                      · Taxes & duties payable · Short-term borrowings
03 EQUITY          Share capital · Reserves · Opening balance clearing
04 REVENUE         04-01 Ticketing · 04-02 Food & Beverage · 04-03 Advertising & Sponsorship · 04-04 Other
05 COST OF SALES   05-01 Film costs · 05-02 F&B cost · 05-03 Other direct costs
06 OPERATING EXP.  Employee · Premises & occupancy · R&M equipment · Selling & marketing · Travel & vehicles ·
                   Office & general admin · Depreciation & amortisation
07 OTHER INCOME AND OTHER EXPENSES
08 FINANCE COSTS AND TAXATION
```

### Account string
```
Company(2) . Site(3) . Cost Centre(6) . Account(00-00-00-0000) [. Party] [. Extra dimensions…]
01        . 101    . 010201         . 04-01-01-0002            → Online ticket sales, Emporium, Ticketing
```

### Per-ledger attributes (drive validation and reporting)
| Attribute | Values | Use |
|---|---|---|
| `normal_balance`, `is_contra` | D / C | Reporting sign, abnormal-balance detection |
| `control_type` | NONE, AP_CONTROL, AR_CONTROL, BANK, CASH, CLEARING, TAX, REGISTER | Who may post; reconciliations |
| `party_type` / `party_rule` | SUPPLIER, CUSTOMER, EMPLOYEE / REQ, OPT, NONE | Sub-ledger enforcement |
| `site_rule` | REQ, OPT, NONE | Site dimension enforcement |
| `cost_centre_rule` | BS (none), LOC (optional), REQ (mandatory, not company-level), CORP (must be 090101) | Cost-centre enforcement |
| `pl_section` | REVENUE, COST_OF_SALES, OPEX, DEPRECIATION, OTHER_INCOME, OTHER_EXPENSE, FINANCE_COST, TAXATION | P&L structure, EBITDA |
| `revenue_stream` | TICKETING, FNB, ADVERTISING, OTHER | Dashboard / management filters |
| `cash_flow_line`, `cf_adjustment`, `cf_counter_line` | see CF catalogue | Indirect cash-flow statement |
| `manual_journal` | ALLOWED, RESTRICTED, NOT_ALLOWED | Manual JV control |
| `abnormal_balance` | BLOCK, ALERT, ALLOW | Block postings leaving cash/stock negative |
| `reconcile_required`, `zero_at_period_end` | bool | Month-end checklist |
| `budget_control` | NONE, ADVISORY, ABSOLUTE | Budget checks on AP invoices / journals |
| `is_intercompany` | bool | Partner company mandatory, IC reconciliation |

---

## 5. Proposed site structure

Sites are an **unlimited master** (`sites` table) belonging to a company.

| Code | Site | Type | City | Province / PST authority |
|---|---|---|---|---|
| 001 | Head Office | HEAD_OFFICE | Lahore | Punjab / PRA |
| 101 | Emporium Lahore | CINEMA | Lahore | Punjab / PRA |
| 102 | Buch Villas | CINEMA | Multan *(confirm)* | Punjab / PRA |
| 103 | The Grand Multan | CINEMA | Multan | Punjab / PRA |
| 1xx | *Future cinemas* | CINEMA | — | — |

Attributes: company, code, name, type (CINEMA / HEAD_OFFICE / WAREHOUSE / OTHER), city, province, provincial tax authority, POS code, opening date, active flag. Each cinema site has **screens** (halls) with seat counts (cinema module). Users are granted access per site; queries and reports are filtered to authorised sites.

---

## 6. Proposed cost-centre structure

6-digit hierarchy (section 2 + department 2 + sub 2), retained from Generation, now *function only*:

| Section | Function | Cost centres |
|---|---|---|
| 00 Company | Not P&L | 000000 Balance sheet – no cost centre |
| 01 Cinema Operations | Site operations | 010101 Cinema Operations – General · 010201 Ticketing / Box Office · 010301 Projection & Screen Operations · 010401 Front of House & Ushering |
| 02 Food & Beverage | Site operations | 020101 Concessions Counter · 020102 Café / Restaurant · 020201 Kitchen & F&B Stores |
| 03 Advertising | Site operations | 030101 Screen Advertising · 030102 Lobby & Ambient Advertising · 030201 Sponsorship & Promotions |
| 04 Marketing & Content | Head office | 040101 Marketing & Brand · 040102 Digital & Online Sales · 040201 Film Programming & Distribution · 040202 Production / Content |
| 05 Facilities | Site operations | 050101 Maintenance – Building & MEP · 050102 Maintenance – Projection & Sound · 050201 Security · 050301 Housekeeping |
| 06 Corporate Services | Head office | 060101 CEO Office / Directors · 060201 Finance & Accounts · 060301 Human Resources · 060401 IT · 060501 Administration · 060601 Legal & Compliance · 060701 Internal Audit |
| 09 Company Level | Below operating profit | 090101 Corporate – company level (finance cost, tax, other income) |

Unlimited cost centres; parent/child via section and department codes stored as a tree (`parent_id`). Each has a budget owner and a `function`.

---

## 7. Proposed database architecture

PostgreSQL 16 (SQLite supported for development/tests), SQLAlchemy 2 ORM, Alembic migrations. All money is `NUMERIC(18,2)`; all codes stored as text.

```
organisation   companies · sites · cost_centres · dimension_types · dimension_values
security       users · roles · permissions · role_permissions · user_roles · user_site_access
audit          audit_log (append-only; DB trigger blocks UPDATE/DELETE) · attachments
accounting     accounts · fiscal_years · accounting_periods · number_sequences
               journal_entries · journal_lines · journal_line_dimensions · recurring_journals(+lines)
workflow       workflow_definitions · approval_limits · workflow_history
tax            tax_codes · tax_rates (effective-dated, payee type, ATL) · tax_slabs · tax_transactions
ap             supplier_categories · suppliers · ap_documents(+lines) · ap_payments(+allocations)
ar             customer_categories · customers · ar_documents(+lines) · ar_receipts(+allocations)
banking        bank_accounts · cash_bank_vouchers(+lines) · bank_transfers
               bank_statements · bank_statement_lines · bank_matches · bank_reconciliations
assets         asset_categories · fixed_assets · depreciation_runs(+lines) · asset_transactions
budgeting      budgets · budget_versions · budget_lines
cinema         screens · films · film_agreements · shows · payment_methods · box_office_sales
               fnb_sales · day_closes · collection_batches · distributor_settlements
closing        period_checklist_items · period_close_log
```

**Integrity controls in the database (defence in depth):**
* `journal_lines`: `CHECK (debit >= 0 AND credit >= 0 AND (debit = 0 OR credit = 0) AND debit + credit > 0)`.
* PostgreSQL **constraint trigger**: a journal cannot be set to `POSTED` unless Σdebit = Σcredit.
* PostgreSQL **trigger**: lines and financial columns of posted journals cannot be updated or deleted; posted journals cannot be deleted.
* `audit_log` is append-only (trigger).
* Foreign keys everywhere (`ON DELETE RESTRICT`), unique constraints (account code, supplier invoice number per supplier, posting number per type/year, system-journal source key → no duplicate posting).
* Posting runs in one DB transaction with `SELECT … FOR UPDATE` on the journal and the accounting period (no posting while a period is being closed; no double posting).
* Indexes for reporting: `(company_id, account_id, posting_date)`, `(site_id)`, `(cost_centre_id)`, `(period_id)`, `(party_type, party_id)` on posted lines — reports aggregate in SQL; nothing loads the full GL into memory; lists are paginated.

---

## 8. Proposed accounting workflow

```
          ┌──────────┐ submit ┌───────────┐ check* ┌─────────┐ approve ┌──────────┐ post ┌────────┐
 create → │  DRAFT   │──────▶│ SUBMITTED │──────▶│ CHECKED │───────▶│ APPROVED │────▶│ POSTED │──▶ reverse → REVERSED
          └──────────┘◀──────└───────────┘◀──────└─────────┘◀───────└──────────┘     └────────┘    (+ new reversal journal)
               ▲  reject (reason mandatory, earlier approvals cleared)        * check stage configurable per document type
               └── cancel (never-posted drafts only; number not reused)
```

* **Configurable per document type** (`workflow_definitions`): check stage on/off, segregation of duties, auto-post on approval.
* **Approval limits** (`approval_limits`) by document type × role or user × site × maximum amount. The approver must hold a limit ≥ document total.
* **Segregation of duties**: preparer ≠ checker ≠ approver (even CFO cannot self-approve).
* **No GL effect until POSTED.** Posting assigns a gapless number per journal type and fiscal year.
* **Posted = immutable.** Corrections only by reversal (new journal, same workflow, linked to original).
* **Every action** writes `workflow_history` and `audit_log` (user, time, IP, old/new values).

### Standard cinema entries (generated automatically)
| Event | Debit | Credit |
|---|---|---|
| Box office day close | Cash box office / Card clearing (acquirer) / Gateway (customer) / Wallet / Corporate AR | Ticket sales (by channel, film & screen dims) · Entertainment duty payable · Output tax |
| Day-close refunds & discounts | Ticket refunds / discounts (contra revenue) | (netted in collections) |
| Film rental accrual (day close) | Film rental – distributor share (film, distributor dims) | Accrued film rental |
| Distributor settlement | Accrued film rental (± MG adjustment) | Film distributors payable (distributor party) |
| F&B day close | Cash F&B / card clearing … | Food / Beverage / Combo sales · Output tax on services (PRA) |
| Card settlement | Bank (net) · Card charges · Tax deducted at source | Card settlements receivable – acquirer |
| Cash banking | Cash in transit → Bank | Cash in hand → Cash in transit |
| Supplier invoice | Expense / asset (site, cost centre) · Input tax | AP control (supplier) |
| Supplier payment | AP control (allocated) | Bank (net) · WHT payable (by section) · Sales tax withheld |
| Advertising invoice | Trade receivables – advertising (customer) | Advertising revenue · Output tax on services |
| Customer receipt | Bank · Tax deducted by customer | AR control (allocated) |
| Depreciation run | Depreciation expense (site, cost centre) | Accumulated depreciation |

---

## 9. Development roadmap (as executed)

| Phase | Scope | Exit test |
|---|---|---|
| 1 | Architecture, DB schema, COA, sites, cost centres, dimensions, users/roles/permissions, periods, audit | Schema migrates on PostgreSQL; seed loads; auth & RBAC tests |
| 2 | Journal engine, validations, workflow, reversal, recurring, GL, TB, account statement, P&L, BS, CF, exports | Debit = credit, posting, reversal, TB, statements tests |
| 3 | AP, AR, cash & bank, transfers, cash position | Invoice / payment / WHT / balance / allocation tests |
| 4 | Tax engine & reports, fixed assets & depreciation, budgeting, bank reconciliation, sub-ledger-to-GL reconciliations | Tax calc, FA run, budget variance, bank rec tests |
| 5 | Cinema revenue (screens, films, shows, box office & F&B day close, collections reconciliation, distributor settlement), management reports, CFO dashboard, month-end close, opening balances, imports, reporting pack | Day-close posting, KPI and close tests |
| 6 | Responsive web front-end (desktop / tablet / phone, installable PWA), security hardening, Docker & Windows/Linux deployment, documentation, **24-step end-to-end validation** | E2E suite green on PostgreSQL |

## 10. Items for management confirmation
1. Cinema tax treatment: entertainment duty / provincial tax on admissions (Punjab), sales tax on F&B (PRA restaurant rate, card-payment reduced rate), advertising services, WHT on film rentals to local vs foreign distributors. Seeded as configurable codes flagged *to confirm*.
2. Distributor terms: share % by week, minimum guarantees, settlement frequency.
3. Approval-limit bands (seeded from the reference workbook bands: 250k / 2.5m / 25m PKR).
4. Bank, acquirer and gateway names and account numbers.
5. Whether advance ticket sales for future shows are deferred (system supports it: ledger 02-02-02-0012).
6. Cut-over date and opening balance source (audited TB).
