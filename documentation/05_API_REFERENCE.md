# API reference

Base path `/api`. Authenticate with `POST /api/auth/login` and send `Authorization: Bearer <token>`. Interactive documentation (OpenAPI / Swagger) is served at `/api/docs` and `/api/redoc`. Errors return `{"error": code, "message": text, "details": [...]}` with HTTP 401 / 403 / 404 / 409 / 422.

Report endpoints accept `format=json|xlsx|csv|pdf`. List endpoints accept `page` and `page_size`.

## accounts payable

| Method | Path | Summary |
|---|---|---|
| GET | `/api/ap/aging` | Aging |
| POST | `/api/ap/allocations` | Allocate |
| GET | `/api/ap/documents` | List Docs |
| POST | `/api/ap/documents` | Create Doc |
| GET | `/api/ap/documents/{doc_id}` | Get Doc |
| PUT | `/api/ap/documents/{doc_id}` | Update Doc |
| POST | `/api/ap/documents/{doc_id}/reverse` | Reverse Doc |
| POST | `/api/ap/documents/{doc_id}/{action}` | Act Doc |
| GET | `/api/ap/open-items` | Open Items |
| GET | `/api/ap/payments` | List Payments |
| POST | `/api/ap/payments` | Create Payment |
| POST | `/api/ap/payments/preview` | Preview Payment |
| GET | `/api/ap/payments/{pay_id}` | Get Payment |
| PUT | `/api/ap/payments/{pay_id}` | Update Payment |
| POST | `/api/ap/payments/{pay_id}/apply-advance` | Apply Adv |
| POST | `/api/ap/payments/{pay_id}/reverse` | Reverse Payment |
| POST | `/api/ap/payments/{pay_id}/{action}` | Act Payment |
| GET | `/api/ap/reconciliation` | Reconciliation |
| GET | `/api/ap/supplier-categories` | Categories |
| GET | `/api/ap/suppliers` | List Suppliers |
| POST | `/api/ap/suppliers` | Create Suppliers |
| GET | `/api/ap/suppliers/{item_id}` | Get Suppliers |
| PATCH | `/api/ap/suppliers/{item_id}` | Update Suppliers |
| GET | `/api/ap/suppliers/{supplier_id}/statement` | Statement |

## accounts receivable

| Method | Path | Summary |
|---|---|---|
| GET | `/api/ar/aging` | Aging |
| POST | `/api/ar/allocations` | Allocate |
| GET | `/api/ar/customer-categories` | Categories |
| GET | `/api/ar/customers` | List Customers |
| POST | `/api/ar/customers` | Create Customers |
| GET | `/api/ar/customers/{customer_id}/statement` | Statement |
| GET | `/api/ar/customers/{item_id}` | Get Customers |
| PATCH | `/api/ar/customers/{item_id}` | Update Customers |
| GET | `/api/ar/documents` | List Docs |
| POST | `/api/ar/documents` | Create Doc |
| GET | `/api/ar/documents/{doc_id}` | Get Doc |
| PUT | `/api/ar/documents/{doc_id}` | Update Doc |
| POST | `/api/ar/documents/{doc_id}/reverse` | Reverse Doc |
| POST | `/api/ar/documents/{doc_id}/{action}` | Act Doc |
| GET | `/api/ar/open-items` | Open Items |
| GET | `/api/ar/receipts` | List Receipts |
| POST | `/api/ar/receipts` | Create Receipt |
| GET | `/api/ar/receipts/{rec_id}` | Get Receipt |
| PUT | `/api/ar/receipts/{rec_id}` | Update Receipt |
| POST | `/api/ar/receipts/{rec_id}/apply-advance` | Apply Adv |
| POST | `/api/ar/receipts/{rec_id}/reverse` | Reverse Receipt |
| POST | `/api/ar/receipts/{rec_id}/{action}` | Act Receipt |
| GET | `/api/ar/reconciliation` | Reconciliation |

## admin

| Method | Path | Summary |
|---|---|---|
| GET | `/api/admin/approval-limits` | Approval Limits |
| POST | `/api/admin/approval-limits` | Limit Create |
| PATCH | `/api/admin/approval-limits/{limit_id}` | Limit Update |
| GET | `/api/admin/audit` | Audit |
| GET | `/api/admin/permissions` | Permissions |
| GET | `/api/admin/roles` | Roles |
| POST | `/api/admin/roles` | Role Create |
| PUT | `/api/admin/roles/{role_id}/permissions` | Role Perms |
| GET | `/api/admin/users` | Users |
| POST | `/api/admin/users` | User Create |
| PATCH | `/api/admin/users/{user_id}` | User Update |
| GET | `/api/admin/workflow-config` | Workflow Config |
| GET | `/api/admin/workflow-history/{doc_type}/{doc_id}` | Wf History |
| GET | `/api/admin/workflows` | Workflows |
| PATCH | `/api/admin/workflows/{wf_id}` | Workflow Update |

## attachments

| Method | Path | Summary |
|---|---|---|
| GET | `/api/attachments` | List Attachments |
| POST | `/api/attachments` | Upload |
| DELETE | `/api/attachments/{att_id}` | Delete Attachment |
| GET | `/api/attachments/{att_id}/download` | Download |

## auth

| Method | Path | Summary |
|---|---|---|
| POST | `/api/auth/change-password` | Change Password |
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/logout-all` | Logout All |
| GET | `/api/auth/me` | Me |

## budgeting

| Method | Path | Summary |
|---|---|---|
| GET | `/api/budgets` | List Budgets |
| POST | `/api/budgets` | Create Budget |
| GET | `/api/budgets/reports/variance` | Variance |
| POST | `/api/budgets/versions/{version_id}/approve` | Approve |
| GET | `/api/budgets/versions/{version_id}/lines` | Get Lines |
| PUT | `/api/budgets/versions/{version_id}/lines` | Put Lines |
| POST | `/api/budgets/{budget_id}/revise` | Revise |

## cash and bank

| Method | Path | Summary |
|---|---|---|
| GET | `/api/banking/accounts` | List Bank Accounts |
| POST | `/api/banking/accounts` | Create Bank Accounts |
| GET | `/api/banking/accounts/{bank_account_id}/unreconciled` | Unreconciled |
| GET | `/api/banking/accounts/{item_id}` | Get Bank Accounts |
| PATCH | `/api/banking/accounts/{item_id}` | Update Bank Accounts |
| POST | `/api/banking/adjustments` | Adjustment |
| GET | `/api/banking/cash-position` | Cash Position |
| POST | `/api/banking/matches` | Match |
| DELETE | `/api/banking/matches/{match_id}` | Unmatch |
| GET | `/api/banking/reconciliation` | Reconciliation |
| POST | `/api/banking/reconciliation/complete` | Reconciliation Complete |
| GET | `/api/banking/reconciliations` | Reconciliation History |
| GET | `/api/banking/statements` | Statements |
| POST | `/api/banking/statements` | Statement Create |
| POST | `/api/banking/statements/import` | Statement Import |
| GET | `/api/banking/statements/{statement_id}` | Statement Get |
| POST | `/api/banking/statements/{statement_id}/auto-match` | Auto Match |
| GET | `/api/banking/transfers` | List Transfers |
| POST | `/api/banking/transfers` | Create Transfer |
| GET | `/api/banking/transfers/{tid}` | Get Transfer |
| POST | `/api/banking/transfers/{tid}/receive` | Receive |
| POST | `/api/banking/transfers/{tid}/{action}` | Act Transfer |
| GET | `/api/banking/vouchers` | List Vouchers |
| POST | `/api/banking/vouchers` | Create Voucher |
| GET | `/api/banking/vouchers/{vid}` | Get Voucher |
| PUT | `/api/banking/vouchers/{vid}` | Update Voucher |
| POST | `/api/banking/vouchers/{vid}/reverse` | Reverse Voucher |
| POST | `/api/banking/vouchers/{vid}/{action}` | Act Voucher |

## cfo

| Method | Path | Summary |
|---|---|---|
| GET | `/api/cfo/dashboard` | Dashboard |
| GET | `/api/cfo/pack` | Pack |
| GET | `/api/cfo/ratios` | Get Ratios |

## cinema

| Method | Path | Summary |
|---|---|---|
| GET | `/api/cinema/collections` | Collections |
| GET | `/api/cinema/day-close` | Dc List |
| POST | `/api/cinema/day-close` | Dc Post |
| GET | `/api/cinema/day-close/preview` | Dc Preview |
| POST | `/api/cinema/day-close/{dc_id}/reverse` | Dc Reverse |
| GET | `/api/cinema/distributor-settlements` | Dist List |
| POST | `/api/cinema/distributor-settlements` | Dist Prepare |
| POST | `/api/cinema/distributor-settlements/{sid}/invoice` | Dist Invoice |
| GET | `/api/cinema/films` | List Films |
| POST | `/api/cinema/films` | Create Films |
| PUT | `/api/cinema/films/{film_id}/terms` | Film Terms |
| GET | `/api/cinema/films/{item_id}` | Get Films |
| PATCH | `/api/cinema/films/{item_id}` | Update Films |
| POST | `/api/cinema/imports/box-office` | Import Bo |
| POST | `/api/cinema/imports/fnb` | Import Fnb |
| POST | `/api/cinema/imports/{kind}/file` | Import File |
| GET | `/api/cinema/payment-methods` | List Payment Methods |
| POST | `/api/cinema/payment-methods` | Create Payment Methods |
| GET | `/api/cinema/payment-methods/{item_id}` | Get Payment Methods |
| PATCH | `/api/cinema/payment-methods/{item_id}` | Update Payment Methods |
| GET | `/api/cinema/reports/collections-reconciliation` | Report Collections |
| GET | `/api/cinema/reports/gl-reconciliation` | Report Gl Recon |
| GET | `/api/cinema/reports/kpis` | Report Kpis |
| GET | `/api/cinema/reports/revenue` | Report Revenue |
| GET | `/api/cinema/revenue-types` | List Revenue Types |
| POST | `/api/cinema/revenue-types` | Create Revenue Types |
| GET | `/api/cinema/revenue-types/{item_id}` | Get Revenue Types |
| PATCH | `/api/cinema/revenue-types/{item_id}` | Update Revenue Types |
| GET | `/api/cinema/screens` | List Screens |
| POST | `/api/cinema/screens` | Create Screens |
| GET | `/api/cinema/screens/{item_id}` | Get Screens |
| PATCH | `/api/cinema/screens/{item_id}` | Update Screens |
| GET | `/api/cinema/settlements` | Settlements |
| POST | `/api/cinema/settlements` | Settle |
| GET | `/api/cinema/shows` | Shows |

## closing

| Method | Path | Summary |
|---|---|---|
| POST | `/api/closing/year-end` | Year End |
| GET | `/api/closing/{period_id}/checklist` | Checklist |
| POST | `/api/closing/{period_id}/checklist/{code}` | Sign Off |
| POST | `/api/closing/{period_id}/close` | Close |
| POST | `/api/closing/{period_id}/reopen` | Reopen |

## fixed assets

| Method | Path | Summary |
|---|---|---|
| GET | `/api/assets` | List Assets |
| POST | `/api/assets` | Create |
| GET | `/api/assets/categories` | Categories |
| GET | `/api/assets/reports/reconciliation` | Report Recon |
| GET | `/api/assets/reports/register` | Report Register |
| POST | `/api/assets/runs` | Run Compute |
| GET | `/api/assets/runs/list` | Runs |
| GET | `/api/assets/runs/{run_id}` | Run Get |
| POST | `/api/assets/runs/{run_id}/post` | Run Post |
| POST | `/api/assets/runs/{run_id}/reverse` | Run Reverse |
| GET | `/api/assets/{asset_id}` | Get Asset |
| POST | `/api/assets/{asset_id}/capitalise` | Capitalise |
| POST | `/api/assets/{asset_id}/dispose` | Dispose |
| POST | `/api/assets/{asset_id}/impair` | Impair |
| POST | `/api/assets/{asset_id}/transfer` | Transfer |

## imports

| Method | Path | Summary |
|---|---|---|
| GET | `/api/imports/opening/status` | Opening Status |
| GET | `/api/imports/templates/{name}` | Template |
| POST | `/api/imports/{kind}` | Run Import |

## journals

| Method | Path | Summary |
|---|---|---|
| GET | `/api/journals` | List Journals |
| POST | `/api/journals` | Create |
| GET | `/api/journals/{journal_id}` | Get Journal |
| PUT | `/api/journals/{journal_id}` | Update |
| POST | `/api/journals/{journal_id}/reverse/request` | Reverse |
| POST | `/api/journals/{journal_id}/{action}` | Workflow Action |
| GET | `/api/recurring-journals` | Rec List |
| POST | `/api/recurring-journals` | Rec Create |
| POST | `/api/recurring-journals/run` | Rec Run |
| PUT | `/api/recurring-journals/{rj_id}` | Rec Update |

## masters

| Method | Path | Summary |
|---|---|---|
| GET | `/api/accounts` | Accounts |
| POST | `/api/accounts` | Account Create |
| GET | `/api/accounts/{account_id}` | Account Get |
| PATCH | `/api/accounts/{account_id}` | Account Update |
| PUT | `/api/accounts/{account_id}/dimension-rules` | Account Dim Rules |
| GET | `/api/companies` | Companies |
| GET | `/api/cost-centres` | List Cost Centres |
| POST | `/api/cost-centres` | Create Cost Centres |
| GET | `/api/cost-centres/{item_id}` | Get Cost Centres |
| PATCH | `/api/cost-centres/{item_id}` | Update Cost Centres |
| GET | `/api/dimension-types` | List Dimension Types |
| POST | `/api/dimension-types` | Create Dimension Types |
| GET | `/api/dimension-types/{item_id}` | Get Dimension Types |
| PATCH | `/api/dimension-types/{item_id}` | Update Dimension Types |
| GET | `/api/dimension-values` | List Dimension Values |
| POST | `/api/dimension-values` | Create Dimension Values |
| GET | `/api/dimension-values/{item_id}` | Get Dimension Values |
| PATCH | `/api/dimension-values/{item_id}` | Update Dimension Values |
| GET | `/api/employees` | List Employees |
| POST | `/api/employees` | Create Employees |
| GET | `/api/employees/{item_id}` | Get Employees |
| PATCH | `/api/employees/{item_id}` | Update Employees |
| GET | `/api/fiscal-years` | Fiscal Years |
| POST | `/api/fiscal-years` | Fiscal Year Create |
| GET | `/api/periods` | Periods |
| POST | `/api/periods/{period_id}/status` | Period Status |
| GET | `/api/settings` | Settings List |
| PUT | `/api/settings` | Settings Put |
| GET | `/api/sites` | List Sites |
| POST | `/api/sites` | Create Sites |
| GET | `/api/sites/{item_id}` | Get Sites |
| PATCH | `/api/sites/{item_id}` | Update Sites |

## reports

| Method | Path | Summary |
|---|---|---|
| GET | `/api/reports/account-statement` | Account Statement |
| GET | `/api/reports/balance-sheet` | Balance Sheet |
| GET | `/api/reports/cash-flow` | Cash Flow |
| GET | `/api/reports/cash-flow-monthly` | Cash Flow Monthly |
| GET | `/api/reports/cash-position` | Cash Position |
| GET | `/api/reports/gl` | General Ledger |
| GET | `/api/reports/gl-monthly` | Gl Monthly |
| GET | `/api/reports/journal-listing` | Journal Listing |
| GET | `/api/reports/profit-loss` | Profit Loss |
| GET | `/api/reports/subledger-reconciliation` | Subledger Reconciliation |
| GET | `/api/reports/trial-balance` | Trial Balance |

## system

| Method | Path | Summary |
|---|---|---|
| GET | `/api/health` | Health |

## tax

| Method | Path | Summary |
|---|---|---|
| GET | `/api/tax/codes` | List Tax Codes |
| POST | `/api/tax/codes` | Create Tax Codes |
| GET | `/api/tax/codes/{item_id}` | Get Tax Codes |
| PATCH | `/api/tax/codes/{item_id}` | Update Tax Codes |
| POST | `/api/tax/deposits` | Deposit |
| GET | `/api/tax/rate-lookup` | Rate Lookup |
| POST | `/api/tax/rates` | Add Rate |
| GET | `/api/tax/reports/reconciliation` | Report Recon |
| GET | `/api/tax/reports/summary` | Report Summary |
| GET | `/api/tax/reports/transactions` | Report Listing |
| GET | `/api/tax/reports/working-papers` | Report Working Papers |
| GET | `/api/tax/slab-calc` | Slab Calc |
