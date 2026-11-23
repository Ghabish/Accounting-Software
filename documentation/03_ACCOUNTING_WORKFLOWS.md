# Accounting workflows and controls

## 1. Principles
* **The GL is the single source of truth.** P&L, balance sheet, cash flow, dashboards and the CFO pack are
  computed from posted journal lines at request time. AP/AR aging comes from the sub-ledgers, which are
  reconciled to the GL automatically.
* **Double entry is enforced three times**: in the posting engine (`backend/accounting/engine.py`), by
  database CHECK constraints on every line, and by a PostgreSQL deferred constraint trigger that refuses to
  mark a journal POSTED unless debits equal credits.
* **Posted = immutable.** ORM guards and PostgreSQL triggers block any update or delete of posted lines and
  of a posted journal's financial fields. Corrections are made by reversal journals linked to the original.
* **No GL effect until posted.** Drafts, submitted and approved documents do not affect any report.

## 2. Document workflow
```
DRAFT ─submit─▶ SUBMITTED ─check*─▶ CHECKED ─approve─▶ APPROVED ─post─▶ POSTED ─reverse─▶ REVERSED
  ▲                │                    │                  │
  └──── reject (reason required, approvals cleared) ───────┘          * check stage configurable
  └─ cancel (drafts only)
```
| Document | Check stage (default) | Auto-post on approval (default) |
|---|---|---|
| Journal voucher | yes | no — posted by Finance Controller |
| AP invoice / credit / debit note | no | yes |
| Supplier payment | yes | yes |
| AR invoice / credit / debit note | no | yes |
| Customer receipt | no | yes |
| Cash / bank voucher | no | yes |
| Bank / cash transfer | no | yes |

Configured in **Administration → Workflow settings**. Rules applied by `backend/workflow/engine.py`:
* Segregation of duties: the preparer cannot check, approve or post; the checker cannot approve.
  Applies to every role including CFO.
* Approval limits (**Administration → Approval limits**) by document type × role or user × site × amount.
  Seeded bands: Finance Manager PKR 2,500,000; CFO unlimited.
* Any edit after submission returns the document to DRAFT and clears earlier approvals.
* Every action is written to the workflow history and the audit trail (user, time, IP, comment).

## 3. Validation on every journal line
| Rule | Behaviour |
|---|---|
| Balance | Σ debit = Σ credit > 0; each line one-sided and positive |
| Accounts | level-4 ledgers only; active and within effective dates |
| Site rule | REQ → mandatory, NONE → not allowed; user must be authorised for the site |
| Cost-centre rule | BS → none; LOC → optional (not company level); REQ → mandatory operating cost centre (company-level 090101 refused); CORP → must be 090101 |
| Party | control ledgers require the supplier / customer / employee code of the right type; party must be active |
| Intercompany | partner company mandatory on intercompany ledgers |
| Extra dimensions | per-account REQ / OPT / NONE rules; value must belong to the dimension and be active |
| Manual journals | NOT_ALLOWED ledgers refused; RESTRICTED and AP/AR control ledgers need `journal.restricted` |
| Period | posting date in an OPEN period; SOFT_CLOSED needs `period.post_soft_closed`; CLOSED/LOCKED refused |
| Abnormal balance | BLOCK ledgers (cash in hand, inventories, PPE cost) cannot be driven to the wrong side |
| Duplicates | duplicate system postings blocked by a unique source key; similar manual journals and supplier invoices produce warnings; same supplier + document number is blocked |
| Numbering | gapless per journal type and fiscal year, assigned at posting inside the transaction (e.g. `JV-2627-000001`) |

## 4. Standard entries
### Cinema day close (site × business date)
POS exports (box office per show / revenue type / payment method; F&B per category / payment method) are
imported, then **Day close** posts:

| | Debit | Credit |
|---|---|---|
| Collections | Box-office cash / F&B cash / card clearing (per acquirer) / gateway / wallet / platform receivable | |
| Ticket revenue | Discounts, refunds (contra revenue) | Ticket sales by channel — with SCREEN, FILM and DISTRIBUTOR dimensions |
| Advance sales | | Advance ticket sales (shows on a later date) — released to revenue on the show date |
| F&B revenue | | Food / beverage / combo / café sales |
| Output tax | | PST on F&B (PRA), entertainment duty (configurable; seeded 0% pending confirmation) — prices are tax-inclusive and split using the tax codes on the revenue type |
| Cash count | Cash over / short | Cash in hand (or reverse) |
| Film rental (separate FRA journal) | Film rental – distributor share | Accrued film rental |

Film rental = distributor share % (by week since release, optionally per site) × net box office after tax.
A collection batch is opened for every non-cash payment method.

### Card / gateway / wallet settlement
Dr Bank (net) · Dr Card / gateway charges · Dr Tax deducted at source — Cr Card clearing / gateway receivable,
allocated to the oldest open batches. The **Revenue & collections reconciliation** shows
sales → expected → settled → charges → bank receipt (and whether it is matched on the bank statement) → journals.

### Distributor settlement
Accrued film rental for a distributor and period is summarised by film and site and turned into an AP
invoice (Dr Accrued film rental [+ MG adjustment] / Cr Film distributors payable). It then follows the AP
approval workflow; payment deducts the distributor's withholding tax.

### Supplier invoice and payment
| | Debit | Credit |
|---|---|---|
| Invoice | Expense / asset (site, cost centre, dimensions) · recoverable input tax (FBR / PRA) — inadmissible tax is added to the cost | AP control of the supplier category (supplier code) |
| Payment | AP control (allocated to invoices) or supplier advance | Bank (net) · income tax withheld (by section) · sales tax withheld |
| Advance application | AP control | Supplier advance |
| Credit / debit note | AP control | Expense · input tax — auto-allocated to the related invoice |

Withholding at payment (as in the reference workbook, V20): income-tax base = amount paid excluding the sales-tax
portion; rate from the supplier's tax code, type (company / individual / AOP / non-resident) and ATL status at
the payment date; valid exemption certificates override; part payments are taxed on the amount paid; tax is not
deducted again when an advance is applied. Rate overrides need `tax.override` and a reason, and are listed in
the tax transaction report. Withholding is rounded to the nearest rupee per line.

### Customer invoice and receipt
Invoice: Dr AR control (customer) / Cr revenue (site, cost centre) · Cr output tax.
Receipt: Dr Bank (amount received) · Dr Tax deducted by customer — Cr AR control (allocated) · Cr customer
advances (unallocated). Advances are applied later (Dr customer advance / Cr AR control).

### Cash and bank
Cash / bank vouchers (BPV, BRV, CPV, CRV) for items that are not supplier or customer settlements
(those must use AP / AR so that sub-ledgers stay reconciled). Transfers: direct (Dr destination / Cr source)
or via *cash in transit* / *funds in transit* with a second "received" step; bank charges on transfers go to
finance cost (090101).

### Fixed assets
Capitalise from a posted AP invoice line (no second posting), from CWIP / another account (FAT journal) or as an
opening balance. Monthly depreciation run (DEP journal): Dr depreciation (asset's site and cost centre) /
Cr accumulated depreciation. Straight-line = (NBV − residual) / remaining months, full month from the month of
capitalisation, with catch-up; reducing balance optional. Transfer between sites moves cost and accumulated
depreciation; disposal posts proceeds and the gain or loss (090101); impairment increases accumulated
depreciation and is spread over the remaining life.

### Tax deposits
**Tax → Tax deposits** pays withheld / output tax for a period from a bank account and stamps the CPR / PSID on
each covered tax transaction (V24).

## 5. Month-end close (Periods & month-end)
Automatic checks (blocking unless noted): no unposted documents · trial balance balanced · every bank account
reconciled to the period end · AP, AR, fixed assets and tax sub-ledgers agree to the GL · depreciation posted ·
suspense, cash-in-transit, funds-in-transit and opening-balance clearing are nil · all imported cinema sales
day-closed · collections settled within 7 days (advisory) · abnormal balances (advisory).
Manual sign-offs: accruals, prepayments, inventory count (advisory), revenue review, cash counts,
intercompany (advisory), CFO review of the trial balance and management accounts.

Periods close in sequence. Statuses: OPEN → SOFT_CLOSED (Finance Manager; posting only with special authority)
→ CLOSED (checklist complete) → LOCKED (permanent). Reopening a CLOSED period needs `period.reopen` (CFO) and a
reason, must be done latest-first, and is recorded in the period log and the audit trail. Waiving a failed
check also needs CFO authority and a reason.

**Year-end close** (after periods 1–11 are closed): closes every income and expense ledger (by site and cost
centre) and the dividends ledger to *Unappropriated profit*, dated 30 June (source CLOSING). P&L reports
exclude closing entries, so the year's result is still reported; the balance sheet moves it into reserves.

## 6. Opening balances
All migrated balances post against **03-01-03-0001 Opening balance clearing**:
1. GL balances (control ledgers and fixed-asset register ledgers are rejected — they come from step 2/3);
   the difference is carried to the clearing account automatically.
2. Supplier and customer open items (each becomes an open document, so aging works from day one).
3. Fixed assets via **capitalise → Opening balance** (cost and accumulated depreciation).
The opening status screen confirms the clearing account is nil and Assets = Liabilities + Equity.

## 7. Reconciliations (Reconciliation status)
AP sub-ledger vs AP control & advance ledgers · AR sub-ledger (+ cinema collection clearing) vs AR control ·
fixed asset register vs cost / accumulated depreciation by category · tax transactions vs tax ledgers
(excluding deposits) · bank statement vs GL. Lines posted to control ledgers outside the module are listed for
investigation. POS revenue (day-closed) vs GL revenue is reconciled per stream.

## 8. Cash-flow statement
Indirect method from GL movements: profit before tax; add back depreciation / amortisation / impairment,
disposal gains and losses, finance costs (with their cash counterpart shown in investing / financing);
working-capital movements by balance-sheet line; tax paid; investing and financing lines from each ledger's
cash-flow category. The statement proves itself: opening cash + net movement = closing cash per balance sheet.
A direct-method view classifies every cash journal by its counter-accounts.
