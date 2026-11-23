# User manual

Open the system's address in a browser (desktop, tablet or phone) and sign in. Five failed attempts lock the
account for 15 minutes. On phones use the ☰ button for the menu; to install, choose *Add to Home screen*.
The menu shows only what your role allows; site-restricted users see only their sites' data.

## Daily tasks by role
| Role | Typical screens |
|---|---|
| Site manager / cashier | Cinema → POS sales import, Day close; Cash & bank → Receipts & payments (petty cash), Transfers (cash banking) |
| AP officer | Payables → Suppliers, Invoices & notes, Payments, AP aging |
| AR officer | Receivables → Customers, Invoices & notes, Receipts |
| Accountant | Journal vouchers, Bank reconciliation, Collections & settlements, Depreciation, Budgets |
| Finance manager | Approvals, month-end checklist, reports |
| CFO | Dashboard, CFO reporting pack, approvals above limits, period reopening |
| Auditor | Read-only access to every report and the audit trail |

## Journals
1. **General ledger → Journal vouchers → New journal.** Enter dates, a full narration and the lines
   (account, site, cost centre, party where the account needs one, an optional dimension such as a film, debit
   or credit). The footer shows whether the journal balances.
2. Tick *Accrual* to have it reversed automatically on the first day of the next period.
3. **Save draft**, attach the supporting document, then **Submit**. A different user checks, another approves,
   and the Finance Controller posts. Rejections come back to you with the reason.
4. To correct a posted journal open it and use **Reverse** (a reversal journal is created for approval).

## Supplier invoices and payments
* **Invoices & notes → New**: choose the supplier, enter their document number (duplicates are refused), date,
  site and lines. Sales tax is calculated from the supplier's tax code (change it per line if needed).
  Submit; the approver's approval posts it.
* **Payments → New payment**: choose the supplier; open invoices are listed. Tick the invoices and amounts.
  Income-tax and sales-tax withholding are calculated automatically from the supplier's tax profile and shown
  before you save. Overriding a rate requires authority and a reason. The default payment bank is used unless
  you choose another. Payments go through check and approval.
* **Advance payment**: tick *Advance*; later open the payment and apply it to the invoice.
* **AP aging** and **supplier statements** drill down to documents and journals.

## Customer invoices and receipts
* **Invoices & notes → New**: revenue account and output tax default from the customer category.
* **Receipts → New receipt**: enter the amount received in the bank and any tax the customer deducted; allocate
  to open invoices. Any unallocated amount is kept as a customer advance and can be applied later.

## Cinema operations
1. **POS sales import**: upload the box office and F&B files (templates provided). If any row is invalid the
   whole file is rejected with the row errors.
2. **Day close**: choose the site and date, check the preview (tickets, gross, collections by payment method),
   enter the cash counted and post. Revenue, output tax, advance sales, film rental and expected settlements are
   posted automatically.
3. **Collections & settlements**: record each acquirer / gateway / wallet settlement (gross, charges, tax
   deducted). Outstanding collections remain visible until settled.
4. **Distributor settlements**: prepare for a distributor and period, enter the distributor's invoice number and
   create the AP invoice. Distributor terms (share % by week) are maintained on each film.
5. **Cinema revenue analysis**: by cinema, screen, film, show, distributor, revenue type, payment method or date —
   tickets, complimentary tickets, discounts, refunds, average ticket price, F&B spend per head, revenue per show
   and occupancy.

## Cash and bank
* **Receipts & payments** for petty cash and other non-supplier items. Payments to suppliers must use AP.
* **Transfers**: tick *Via transit* for cash deposits; record the bank credit with **Receive** when it appears.
* **Daily cash position** for every cash and bank account.
* **Bank reconciliation**: import the statement (CSV / Excel), run **Auto-match**, match remaining items manually
  (one-to-many and partial matches allowed), post bank charges / interest / direct debits with **Adjust**, and
  **Complete** when the difference is zero. Completed reconciliations are kept in the history.

## Reports
Every report has filters, **Excel / PDF / CSV** export and drill-down: click an account in the P&L or balance
sheet to open the ledger for exactly that period / site / cost centre, then click a line to open the journal and
its supporting documents. Reports available: trial balance, P&L (single period, monthly, period + YTD,
vs prior year, budget vs actual, site-wise, cost-centre-wise), balance sheet (with comparatives), cash flow
(indirect, direct, monthly), monthly GL movements, journal listing, daily cash position, AP / AR aging and
statements, sub-ledger reconciliations, tax reports, fixed-asset register, budget variance and cinema analyses.

## Dashboard and CFO pack
The dashboard shows revenue, gross profit, EBITDA and margins, net profit, cash and bank, receivables, payables,
tax, revenue trend by stream, monthly P&L, site performance, revenue mix, budget vs actual, top expenses,
cost-centre spend, AP / AR aging and the year-to-date cash flow — filtered by period, site, cost centre and
revenue stream. **CFO reporting pack** downloads the month's management accounts as PDF or Excel.

## Budgets
Create a budget for the fiscal year, enter monthly amounts by account / site / cost centre (or fill all months),
and have another user approve it. Approved versions are locked; **Create revision** copies the latest version
with a reason, and history is kept. Expense postings above budget raise warnings (advisory accounts) or are
blocked (absolute accounts, e.g. capex).

## Month-end
**Periods & month-end → Checklist**: automatic checks run each time you open it; complete the manual sign-offs
and **Close period**. Reopening needs CFO authority and a reason. The year-end close is on the same screen.

## Masters and administration
Sites, cost centres, dimensions, employees, suppliers, customers, bank accounts, screens, films, payment
methods, revenue types and tax codes are maintained from their menu entries; records are deactivated, never
deleted. Administrators manage users (roles and site access), role permissions, approval limits and workflow
settings. The **Audit trail** shows every action with old and new values, user, time and IP address.
