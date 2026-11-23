# Database schema

Generated from the SQLAlchemy models (`python -m scripts.export_docs`). PostgreSQL 16 is the production database; migrations live in `migrations/versions`. Money columns are NUMERIC(18,2); rates NUMERIC(9,6).

Integrity triggers (PostgreSQL, installed by migration 0001): posted journal lines immutable; posted journals cannot be deleted or financially altered; a journal can only become POSTED when balanced (deferred constraint trigger); audit log append-only.

## account_dimension_rules

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| account_id | INTEGER | no | → accounts.id |
| dimension_type_id | INTEGER | no | → dimension_types.id |
| rule | VARCHAR(32) | no |  |

Constraints: `ck_account_dimension_rules_dimensionrule`, `uq_account_dimension_rules_account_id_dimension_type_id`

Indexes: `ix_account_dimension_rules_account_id`, `ix_account_dimension_rules_dimension_type_id`

## accounting_periods

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| fiscal_year_id | INTEGER | no | → fiscal_years.id |
| period_no | INTEGER | no |  |
| name | VARCHAR(20) | no |  |
| start_date | DATE | no |  |
| end_date | DATE | no |  |
| status | VARCHAR(32) | no |  |
| status_changed_by_id | INTEGER | yes | → users.id |
| status_changed_at | DATETIME | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_accounting_periods_dates`, `ck_accounting_periods_periodstatus`, `uq_accounting_periods_company_id_start_date`

Indexes: `ix_accounting_periods_company_id`, `ix_accounting_periods_end_date`, `ix_accounting_periods_fiscal_year_id`, `ix_accounting_periods_start_date`

## accounts

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(13) | no |  |
| name | VARCHAR(160) | no |  |
| level | INTEGER | no |  |
| parent_id | INTEGER | yes | → accounts.id |
| account_type | VARCHAR(32) | no |  |
| normal_balance | VARCHAR(1) | no |  |
| is_postable | BOOLEAN | no |  |
| is_contra | BOOLEAN | no |  |
| control_type | VARCHAR(32) | no |  |
| party_type | VARCHAR(32) | no |  |
| party_rule | VARCHAR(32) | no |  |
| site_rule | VARCHAR(32) | no |  |
| cost_centre_rule | VARCHAR(32) | no |  |
| pl_section | VARCHAR(20) | yes |  |
| revenue_stream | VARCHAR(20) | yes |  |
| cash_flow_line | VARCHAR(30) | yes |  |
| cf_adjustment | VARCHAR(30) | yes |  |
| cf_counter_line | VARCHAR(30) | yes |  |
| manual_journal | VARCHAR(32) | no |  |
| abnormal_balance | VARCHAR(32) | no |  |
| reconcile_required | BOOLEAN | no |  |
| budget_control | VARCHAR(32) | no |  |
| is_intercompany | BOOLEAN | no |  |
| zero_at_period_end | BOOLEAN | no |  |
| requires_attachment | BOOLEAN | no |  |
| is_active | BOOLEAN | no |  |
| effective_from | DATE | yes |  |
| effective_to | DATE | yes |  |
| gen_ref | VARCHAR(20) | yes |  |
| description | TEXT | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_accounts_abnormalbalance`, `ck_accounts_accounttype`, `ck_accounts_budgetcontrol`, `ck_accounts_controltype`, `ck_accounts_costcentrerule`, `ck_accounts_manualjournal`, `ck_accounts_party_rule`, `ck_accounts_partytype`, `ck_accounts_site_rule`, `uq_accounts_code`

Indexes: `ix_accounts_parent_id`, `ix_accounts_pl_section`

## ap_allocations

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| invoice_id | INTEGER | no | → ap_documents.id |
| source_type | VARCHAR(20) | no |  |
| payment_id | INTEGER | yes | → ap_payments.id |
| credit_document_id | INTEGER | yes | → ap_documents.id |
| amount | NUMERIC(18, 2) | no |  |
| allocation_date | DATE | no |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| is_active | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_ap_allocations_positive`

Indexes: `ix_ap_allocations_company_id`, `ix_ap_allocations_credit_document_id`, `ix_ap_allocations_invoice_id`, `ix_ap_allocations_journal_id`, `ix_ap_allocations_payment_id`

## ap_document_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| document_id | INTEGER | no | → ap_documents.id |
| line_no | INTEGER | no |  |
| account_id | INTEGER | no | → accounts.id |
| site_id | INTEGER | yes | → sites.id |
| cost_centre_id | INTEGER | yes | → cost_centres.id |
| description | TEXT | yes |  |
| quantity | NUMERIC(18, 3) | no |  |
| unit_price | NUMERIC(18, 2) | no |  |
| amount | NUMERIC(18, 2) | no |  |
| st_tax_code_id | INTEGER | yes | → tax_codes.id |
| st_rate | NUMERIC(9, 6) | yes |  |
| st_amount | NUMERIC(18, 2) | no |  |
| dimensions | JSON | yes |  |
| asset_id | INTEGER | yes | → fixed_assets.id |

Constraints: `ck_ap_document_lines_non_negative`

Indexes: `ix_ap_document_lines_account_id`, `ix_ap_document_lines_cost_centre_id`, `ix_ap_document_lines_document_id`, `ix_ap_document_lines_site_id`, `ix_ap_document_lines_st_tax_code_id`

## ap_documents

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| doc_type | VARCHAR(32) | no |  |
| number | VARCHAR(30) | no |  |
| supplier_id | INTEGER | no | → suppliers.id |
| supplier_invoice_no | VARCHAR(60) | no |  |
| invoice_date | DATE | no |  |
| posting_date | DATE | no |  |
| due_date | DATE | no |  |
| site_id | INTEGER | yes | → sites.id |
| description | TEXT | no |  |
| currency | VARCHAR(3) | no |  |
| subtotal | NUMERIC(18, 2) | no |  |
| tax_total | NUMERIC(18, 2) | no |  |
| total | NUMERIC(18, 2) | no |  |
| amount_settled | NUMERIC(18, 2) | no |  |
| payment_status | VARCHAR(32) | no |  |
| status | VARCHAR(32) | no |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| related_document_id | INTEGER | yes | → ap_documents.id |
| is_opening | BOOLEAN | no |  |
| source_type | VARCHAR(40) | yes |  |
| source_id | INTEGER | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_ap_documents_apdoctype`, `ck_ap_documents_docstatus`, `ck_ap_documents_paymentstatus`, `ck_ap_documents_total_non_negative`, `uq_ap_documents_company_id_number`

Indexes: `ix_ap_documents_company_id`, `ix_ap_documents_due_date`, `ix_ap_documents_journal_id`, `ix_ap_documents_related_document_id`, `ix_ap_documents_site_id`, `ix_ap_documents_status`, `ix_apdoc_supplier`

## ap_payment_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| payment_id | INTEGER | no | → ap_payments.id |
| document_id | INTEGER | yes | → ap_documents.id |
| amount | NUMERIC(18, 2) | no |  |
| wht_tax_code_id | INTEGER | yes | → tax_codes.id |
| wht_rate | NUMERIC(9, 6) | no |  |
| wht_base | NUMERIC(18, 2) | no |  |
| wht_amount | NUMERIC(18, 2) | no |  |
| stw_tax_code_id | INTEGER | yes | → tax_codes.id |
| stw_rate | NUMERIC(9, 6) | no |  |
| stw_amount | NUMERIC(18, 2) | no |  |
| rate_overridden | BOOLEAN | no |  |
| override_reason | TEXT | yes |  |

Constraints: `ck_ap_payment_lines_positive`

Indexes: `ix_ap_payment_lines_document_id`, `ix_ap_payment_lines_payment_id`, `ix_ap_payment_lines_stw_tax_code_id`, `ix_ap_payment_lines_wht_tax_code_id`

## ap_payments

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| number | VARCHAR(30) | no |  |
| supplier_id | INTEGER | no | → suppliers.id |
| payment_date | DATE | no |  |
| bank_account_id | INTEGER | no | → bank_accounts.id |
| payment_method | VARCHAR(20) | no |  |
| cheque_no | VARCHAR(30) | yes |  |
| reference | VARCHAR(120) | yes |  |
| description | TEXT | no |  |
| is_advance | BOOLEAN | no |  |
| site_id | INTEGER | yes | → sites.id |
| gross_amount | NUMERIC(18, 2) | no |  |
| wht_amount | NUMERIC(18, 2) | no |  |
| stw_amount | NUMERIC(18, 2) | no |  |
| net_amount | NUMERIC(18, 2) | no |  |
| advance_unapplied | NUMERIC(18, 2) | no |  |
| status | VARCHAR(32) | no |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_ap_payments_docstatus`, `ck_ap_payments_net_non_negative`, `uq_ap_payments_company_id_number`

Indexes: `ix_ap_payments_bank_account_id`, `ix_ap_payments_company_id`, `ix_ap_payments_journal_id`, `ix_ap_payments_site_id`, `ix_ap_payments_status`, `ix_ap_payments_supplier_id`

## approval_limits

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| doc_type | VARCHAR(30) | no |  |
| role_id | INTEGER | yes | → roles.id |
| user_id | INTEGER | yes | → users.id |
| site_id | INTEGER | yes | → sites.id |
| max_amount | NUMERIC(18, 2) | yes |  |
| is_active | BOOLEAN | no |  |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Indexes: `ix_approval_limits_doc_type`, `ix_approval_limits_role_id`, `ix_approval_limits_site_id`, `ix_approval_limits_user_id`

## ar_allocations

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| invoice_id | INTEGER | no | → ar_documents.id |
| source_type | VARCHAR(20) | no |  |
| receipt_id | INTEGER | yes | → ar_receipts.id |
| credit_document_id | INTEGER | yes | → ar_documents.id |
| amount | NUMERIC(18, 2) | no |  |
| allocation_date | DATE | no |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| is_active | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_ar_allocations_positive`

Indexes: `ix_ar_allocations_company_id`, `ix_ar_allocations_credit_document_id`, `ix_ar_allocations_invoice_id`, `ix_ar_allocations_journal_id`, `ix_ar_allocations_receipt_id`

## ar_document_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| document_id | INTEGER | no | → ar_documents.id |
| line_no | INTEGER | no |  |
| account_id | INTEGER | no | → accounts.id |
| site_id | INTEGER | yes | → sites.id |
| cost_centre_id | INTEGER | yes | → cost_centres.id |
| description | TEXT | yes |  |
| quantity | NUMERIC(18, 3) | no |  |
| unit_price | NUMERIC(18, 2) | no |  |
| amount | NUMERIC(18, 2) | no |  |
| tax_code_id | INTEGER | yes | → tax_codes.id |
| tax_rate | NUMERIC(9, 6) | yes |  |
| tax_amount | NUMERIC(18, 2) | no |  |
| dimensions | JSON | yes |  |

Constraints: `ck_ar_document_lines_non_negative`

Indexes: `ix_ar_document_lines_account_id`, `ix_ar_document_lines_cost_centre_id`, `ix_ar_document_lines_document_id`, `ix_ar_document_lines_site_id`, `ix_ar_document_lines_tax_code_id`

## ar_documents

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| doc_type | VARCHAR(32) | no |  |
| number | VARCHAR(30) | no |  |
| customer_id | INTEGER | no | → customers.id |
| customer_reference | VARCHAR(60) | yes |  |
| invoice_date | DATE | no |  |
| posting_date | DATE | no |  |
| due_date | DATE | no |  |
| site_id | INTEGER | yes | → sites.id |
| description | TEXT | no |  |
| currency | VARCHAR(3) | no |  |
| subtotal | NUMERIC(18, 2) | no |  |
| tax_total | NUMERIC(18, 2) | no |  |
| total | NUMERIC(18, 2) | no |  |
| amount_settled | NUMERIC(18, 2) | no |  |
| payment_status | VARCHAR(32) | no |  |
| status | VARCHAR(32) | no |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| related_document_id | INTEGER | yes | → ar_documents.id |
| is_opening | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_ar_documents_ardoctype`, `ck_ar_documents_docstatus`, `ck_ar_documents_paymentstatus`, `ck_ar_documents_total_non_negative`, `uq_ar_documents_company_id_number`

Indexes: `ix_ar_documents_company_id`, `ix_ar_documents_due_date`, `ix_ar_documents_journal_id`, `ix_ar_documents_related_document_id`, `ix_ar_documents_site_id`, `ix_ar_documents_status`, `ix_ardoc_customer`

## ar_receipt_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| receipt_id | INTEGER | no | → ar_receipts.id |
| document_id | INTEGER | no | → ar_documents.id |
| amount | NUMERIC(18, 2) | no |  |

Constraints: `ck_ar_receipt_lines_positive`

Indexes: `ix_ar_receipt_lines_document_id`, `ix_ar_receipt_lines_receipt_id`

## ar_receipts

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| number | VARCHAR(30) | no |  |
| customer_id | INTEGER | no | → customers.id |
| receipt_date | DATE | no |  |
| bank_account_id | INTEGER | no | → bank_accounts.id |
| receipt_method | VARCHAR(20) | no |  |
| reference | VARCHAR(120) | yes |  |
| description | TEXT | no |  |
| is_advance | BOOLEAN | no |  |
| site_id | INTEGER | yes | → sites.id |
| amount_received | NUMERIC(18, 2) | no |  |
| tax_deducted | NUMERIC(18, 2) | no |  |
| wht_tax_code_id | INTEGER | yes | → tax_codes.id |
| gross_amount | NUMERIC(18, 2) | no |  |
| unapplied_amount | NUMERIC(18, 2) | no |  |
| status | VARCHAR(32) | no |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_ar_receipts_docstatus`, `ck_ar_receipts_non_negative`, `uq_ar_receipts_company_id_number`

Indexes: `ix_ar_receipts_bank_account_id`, `ix_ar_receipts_company_id`, `ix_ar_receipts_customer_id`, `ix_ar_receipts_journal_id`, `ix_ar_receipts_site_id`, `ix_ar_receipts_status`, `ix_ar_receipts_wht_tax_code_id`

## asset_categories

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(20) | no |  |
| name | VARCHAR(120) | no |  |
| cost_account_id | INTEGER | no | → accounts.id |
| accum_dep_account_id | INTEGER | yes | → accounts.id |
| dep_expense_account_id | INTEGER | yes | → accounts.id |
| gain_account_id | INTEGER | no | → accounts.id |
| loss_account_id | INTEGER | no | → accounts.id |
| impairment_account_id | INTEGER | yes | → accounts.id |
| default_useful_life_months | INTEGER | no |  |
| default_method | VARCHAR(32) | no |  |
| default_residual_pct | NUMERIC(9, 6) | no |  |
| is_depreciable | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_asset_categories_depreciationmethod`, `uq_asset_categories_code`

Indexes: `ix_asset_categories_accum_dep_account_id`, `ix_asset_categories_cost_account_id`, `ix_asset_categories_dep_expense_account_id`, `ix_asset_categories_gain_account_id`, `ix_asset_categories_impairment_account_id`, `ix_asset_categories_loss_account_id`

## asset_transactions

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| asset_id | INTEGER | no | → fixed_assets.id |
| txn_type | VARCHAR(20) | no |  |
| txn_date | DATE | no |  |
| from_site_id | INTEGER | yes | → sites.id |
| to_site_id | INTEGER | yes | → sites.id |
| from_cost_centre_id | INTEGER | yes | → cost_centres.id |
| to_cost_centre_id | INTEGER | yes | → cost_centres.id |
| amount | NUMERIC(18, 2) | no |  |
| proceeds | NUMERIC(18, 2) | yes |  |
| gain_loss | NUMERIC(18, 2) | yes |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| notes | TEXT | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Indexes: `ix_asset_transactions_asset_id`, `ix_asset_transactions_from_cost_centre_id`, `ix_asset_transactions_from_site_id`, `ix_asset_transactions_journal_id`, `ix_asset_transactions_to_cost_centre_id`, `ix_asset_transactions_to_site_id`

## attachments

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| entity_type | VARCHAR(60) | no |  |
| entity_id | BIGINT | no |  |
| filename | VARCHAR(255) | no |  |
| content_type | VARCHAR(120) | yes |  |
| size_bytes | INTEGER | no |  |
| sha256 | VARCHAR(64) | no |  |
| storage_path | VARCHAR(500) | no |  |
| description | TEXT | yes |  |
| uploaded_by_id | INTEGER | yes | → users.id |
| uploaded_at | DATETIME | no |  |

Indexes: `ix_attachment_entity`

## audit_log

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | BIGINT | no | PK |
| ts | DATETIME | no |  |
| user_id | INTEGER | yes | → users.id |
| username | VARCHAR(60) | yes |  |
| action | VARCHAR(60) | no |  |
| entity_type | VARCHAR(60) | no |  |
| entity_id | VARCHAR(40) | yes |  |
| old_values | JSON | yes |  |
| new_values | JSON | yes |  |
| ip_address | VARCHAR(64) | yes |  |
| user_agent | VARCHAR(255) | yes |  |
| notes | TEXT | yes |  |

Indexes: `ix_audit_entity`, `ix_audit_log_action`, `ix_audit_log_ts`, `ix_audit_log_user_id`

## bank_accounts

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| code | VARCHAR(20) | no |  |
| name | VARCHAR(120) | no |  |
| kind | VARCHAR(32) | no |  |
| bank_name | VARCHAR(120) | yes |  |
| branch | VARCHAR(120) | yes |  |
| account_number | VARCHAR(40) | yes |  |
| iban | VARCHAR(34) | yes |  |
| currency | VARCHAR(3) | no |  |
| gl_account_id | INTEGER | no | → accounts.id |
| site_id | INTEGER | yes | → sites.id |
| imprest_amount | NUMERIC(18, 2) | yes |  |
| is_default_payment | BOOLEAN | no |  |
| is_active | BOOLEAN | no |  |
| is_sample | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_bank_accounts_bankaccountkind`, `uq_bank_accounts_company_id_code`, `uq_bank_accounts_gl_account_id_site_id`

Indexes: `ix_bank_accounts_company_id`, `ix_bank_accounts_gl_account_id`, `ix_bank_accounts_site_id`

## bank_matches

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | BIGINT | no | PK |
| statement_line_id | BIGINT | no | → bank_statement_lines.id |
| journal_line_id | BIGINT | no | → journal_lines.id |
| amount | NUMERIC(18, 2) | no |  |
| match_type | VARCHAR(10) | no |  |
| matched_by_id | INTEGER | yes | → users.id |
| matched_at | DATETIME | no |  |
| is_active | BOOLEAN | no |  |
| unmatched_by_id | INTEGER | yes | → users.id |
| unmatched_at | DATETIME | yes |  |
| reconciliation_id | INTEGER | yes | → bank_reconciliations.id |

Constraints: `ck_bank_matches_positive`

Indexes: `ix_bank_matches_reconciliation_id`, `ix_bank_matches_statement_line_id`, `ix_bankmatch_jl`

## bank_reconciliations

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| bank_account_id | INTEGER | no | → bank_accounts.id |
| statement_id | INTEGER | yes | → bank_statements.id |
| as_of_date | DATE | no |  |
| statement_balance | NUMERIC(18, 2) | no |  |
| gl_balance | NUMERIC(18, 2) | no |  |
| outstanding_payments | NUMERIC(18, 2) | no |  |
| deposits_in_transit | NUMERIC(18, 2) | no |  |
| unmatched_statement_debits | NUMERIC(18, 2) | no |  |
| unmatched_statement_credits | NUMERIC(18, 2) | no |  |
| difference | NUMERIC(18, 2) | no |  |
| status | VARCHAR(12) | no |  |
| completed_by_id | INTEGER | yes | → users.id |
| completed_at | DATETIME | yes |  |
| notes | TEXT | yes |  |
| detail | JSON | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Indexes: `ix_bank_reconciliations_bank_account_id`, `ix_bank_reconciliations_statement_id`

## bank_statement_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | BIGINT | no | PK |
| statement_id | INTEGER | no | → bank_statements.id |
| line_no | INTEGER | no |  |
| txn_date | DATE | no |  |
| value_date | DATE | yes |  |
| description | TEXT | yes |  |
| reference | VARCHAR(120) | yes |  |
| debit | NUMERIC(18, 2) | no |  |
| credit | NUMERIC(18, 2) | no |  |
| balance | NUMERIC(18, 2) | yes |  |
| matched_amount | NUMERIC(18, 2) | no |  |
| status | VARCHAR(12) | no |  |

Constraints: `ck_bank_statement_lines_one_side`

Indexes: `ix_bank_statement_lines_statement_id`

## bank_statements

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| bank_account_id | INTEGER | no | → bank_accounts.id |
| date_from | DATE | no |  |
| date_to | DATE | no |  |
| opening_balance | NUMERIC(18, 2) | no |  |
| closing_balance | NUMERIC(18, 2) | no |  |
| filename | VARCHAR(255) | yes |  |
| status | VARCHAR(12) | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Indexes: `ix_bank_statements_bank_account_id`

## bank_transfers

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| number | VARCHAR(30) | no |  |
| from_account_id | INTEGER | no | → bank_accounts.id |
| to_account_id | INTEGER | no | → bank_accounts.id |
| transfer_date | DATE | no |  |
| amount | NUMERIC(18, 2) | no |  |
| charges | NUMERIC(18, 2) | no |  |
| via_transit | BOOLEAN | no |  |
| received_date | DATE | yes |  |
| reference | VARCHAR(120) | yes |  |
| description | TEXT | no |  |
| status | VARCHAR(32) | no |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| receive_journal_id | INTEGER | yes | → journal_entries.id |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_bank_transfers_different_accounts`, `ck_bank_transfers_docstatus`, `ck_bank_transfers_positive`, `uq_bank_transfers_company_id_number`

Indexes: `ix_bank_transfers_company_id`, `ix_bank_transfers_from_account_id`, `ix_bank_transfers_journal_id`, `ix_bank_transfers_receive_journal_id`, `ix_bank_transfers_status`, `ix_bank_transfers_to_account_id`

## box_office_sales

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | BIGINT | no | PK |
| company_id | INTEGER | no | → companies.id |
| site_id | INTEGER | no | → sites.id |
| business_date | DATE | no |  |
| show_id | INTEGER | yes | → shows.id |
| screen_id | INTEGER | no | → screens.id |
| film_id | INTEGER | no | → films.id |
| revenue_type_id | INTEGER | no | → revenue_types.id |
| payment_method_id | INTEGER | no | → payment_methods.id |
| tickets_sold | INTEGER | no |  |
| complimentary_tickets | INTEGER | no |  |
| complimentary_value | NUMERIC(18, 2) | no |  |
| refund_tickets | INTEGER | no |  |
| gross_amount | NUMERIC(18, 2) | no |  |
| discount_amount | NUMERIC(18, 2) | no |  |
| refund_amount | NUMERIC(18, 2) | no |  |
| import_batch_id | INTEGER | yes | → sales_import_batches.id |
| day_close_id | INTEGER | yes | → day_closes.id |
| source_ref | VARCHAR(80) | yes |  |
| net_revenue | NUMERIC(18, 2) | no |  |
| tax_amount | NUMERIC(18, 2) | no |  |
| film_rental_amount | NUMERIC(18, 2) | no |  |
| is_deferred | BOOLEAN | no |  |
| released_day_close_id | INTEGER | yes | → day_closes.id |
| distributor_settlement_id | INTEGER | yes | → distributor_settlements.id |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_box_office_sales_non_negative`

Indexes: `ix_bos_site_date`, `ix_box_office_sales_company_id`, `ix_box_office_sales_day_close_id`, `ix_box_office_sales_distributor_settlement_id`, `ix_box_office_sales_film_id`, `ix_box_office_sales_import_batch_id`, `ix_box_office_sales_payment_method_id`, `ix_box_office_sales_released_day_close_id`, `ix_box_office_sales_revenue_type_id`, `ix_box_office_sales_screen_id`, `ix_box_office_sales_show_id`, `ix_box_office_sales_source_ref`

## budget_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| version_id | INTEGER | no | → budget_versions.id |
| account_id | INTEGER | no | → accounts.id |
| site_id | INTEGER | yes | → sites.id |
| cost_centre_id | INTEGER | yes | → cost_centres.id |
| dimension_value_id | INTEGER | yes | → dimension_values.id |
| period_id | INTEGER | no | → accounting_periods.id |
| amount | NUMERIC(18, 2) | no |  |

Constraints: `uq_budget_line_key`

Indexes: `ix_budget_line_lookup`

## budget_versions

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| budget_id | INTEGER | no | → budgets.id |
| version_no | INTEGER | no |  |
| label | VARCHAR(60) | no |  |
| status | VARCHAR(12) | no |  |
| reason | TEXT | yes |  |
| approved_by_id | INTEGER | yes | → users.id |
| approved_at | DATETIME | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_budget_versions_budget_id_version_no`

Indexes: `ix_budget_versions_budget_id`

## budgets

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| fiscal_year_id | INTEGER | no | → fiscal_years.id |
| name | VARCHAR(120) | no |  |
| description | TEXT | yes |  |
| active_version_id | INTEGER | yes | → budget_versions.id |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_budgets_company_id_fiscal_year_id_name`

Indexes: `ix_budgets_company_id`, `ix_budgets_fiscal_year_id`

## cash_bank_voucher_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| voucher_id | INTEGER | no | → cash_bank_vouchers.id |
| line_no | INTEGER | no |  |
| account_id | INTEGER | no | → accounts.id |
| site_id | INTEGER | yes | → sites.id |
| cost_centre_id | INTEGER | yes | → cost_centres.id |
| supplier_id | INTEGER | yes | → suppliers.id |
| customer_id | INTEGER | yes | → customers.id |
| employee_id | INTEGER | yes | → employees.id |
| description | TEXT | yes |  |
| amount | NUMERIC(18, 2) | no |  |
| tax_code_id | INTEGER | yes | → tax_codes.id |
| tax_rate | NUMERIC(9, 6) | yes |  |
| tax_amount | NUMERIC(18, 2) | no |  |
| dimensions | JSON | yes |  |

Constraints: `ck_cash_bank_voucher_lines_positive`

Indexes: `ix_cash_bank_voucher_lines_account_id`, `ix_cash_bank_voucher_lines_cost_centre_id`, `ix_cash_bank_voucher_lines_customer_id`, `ix_cash_bank_voucher_lines_employee_id`, `ix_cash_bank_voucher_lines_site_id`, `ix_cash_bank_voucher_lines_supplier_id`, `ix_cash_bank_voucher_lines_tax_code_id`, `ix_cash_bank_voucher_lines_voucher_id`

## cash_bank_vouchers

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| voucher_type | VARCHAR(3) | no |  |
| number | VARCHAR(30) | no |  |
| bank_account_id | INTEGER | no | → bank_accounts.id |
| voucher_date | DATE | no |  |
| counterparty | VARCHAR(200) | yes |  |
| cheque_no | VARCHAR(30) | yes |  |
| reference | VARCHAR(120) | yes |  |
| description | TEXT | no |  |
| gross_total | NUMERIC(18, 2) | no |  |
| tax_total | NUMERIC(18, 2) | no |  |
| net_total | NUMERIC(18, 2) | no |  |
| status | VARCHAR(32) | no |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_cash_bank_vouchers_docstatus`, `uq_cash_bank_vouchers_company_id_number`

Indexes: `ix_cash_bank_vouchers_bank_account_id`, `ix_cash_bank_vouchers_company_id`, `ix_cash_bank_vouchers_journal_id`, `ix_cash_bank_vouchers_status`

## collection_allocations

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| settlement_id | INTEGER | no | → collection_settlements.id |
| batch_id | INTEGER | no | → collection_batches.id |
| amount | NUMERIC(18, 2) | no |  |

Indexes: `ix_collection_allocations_batch_id`, `ix_collection_allocations_settlement_id`

## collection_batches

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| site_id | INTEGER | no | → sites.id |
| business_date | DATE | no |  |
| payment_method_id | INTEGER | no | → payment_methods.id |
| day_close_id | INTEGER | no | → day_closes.id |
| expected_amount | NUMERIC(18, 2) | no |  |
| settled_gross | NUMERIC(18, 2) | no |  |
| fee_amount | NUMERIC(18, 2) | no |  |
| tax_deducted | NUMERIC(18, 2) | no |  |
| net_received | NUMERIC(18, 2) | no |  |
| status | VARCHAR(12) | no |  |

Constraints: `uq_collection_batches_day_close_id_payment_method_id`

Indexes: `ix_collection_batches_business_date`, `ix_collection_batches_company_id`, `ix_collection_batches_day_close_id`, `ix_collection_batches_payment_method_id`, `ix_collection_batches_site_id`

## collection_settlements

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| payment_method_id | INTEGER | no | → payment_methods.id |
| bank_account_id | INTEGER | no | → bank_accounts.id |
| settlement_date | DATE | no |  |
| gross_amount | NUMERIC(18, 2) | no |  |
| fee_amount | NUMERIC(18, 2) | no |  |
| tax_deducted | NUMERIC(18, 2) | no |  |
| net_amount | NUMERIC(18, 2) | no |  |
| reference | VARCHAR(120) | yes |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| status | VARCHAR(12) | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Indexes: `ix_collection_settlements_bank_account_id`, `ix_collection_settlements_company_id`, `ix_collection_settlements_journal_id`, `ix_collection_settlements_payment_method_id`

## companies

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(4) | no |  |
| name | VARCHAR(200) | no |  |
| legal_name | VARCHAR(200) | yes |  |
| ntn | VARCHAR(20) | yes |  |
| strn | VARCHAR(20) | yes |  |
| address | TEXT | yes |  |
| base_currency | VARCHAR(3) | no |  |
| fiscal_year_start_month | INTEGER | no |  |
| is_active | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_companies_code`

## cost_centres

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| code | VARCHAR(10) | no |  |
| name | VARCHAR(120) | no |  |
| parent_id | INTEGER | yes | → cost_centres.id |
| section_code | VARCHAR(2) | yes |  |
| section_name | VARCHAR(80) | yes |  |
| function | VARCHAR(32) | no |  |
| budget_owner | VARCHAR(120) | yes |  |
| is_postable | BOOLEAN | no |  |
| is_active | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_cost_centres_costcentrefunction`, `uq_cost_centres_company_id_code`

Indexes: `ix_cost_centres_company_id`, `ix_cost_centres_parent_id`

## customer_categories

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(20) | no |  |
| name | VARCHAR(120) | no |  |
| ar_control_account_id | INTEGER | no | → accounts.id |
| advance_account_id | INTEGER | yes | → accounts.id |
| default_revenue_account_id | INTEGER | yes | → accounts.id |
| default_output_tax_code_id | INTEGER | yes | → tax_codes.id |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_customer_categories_code`

Indexes: `ix_customer_categories_advance_account_id`, `ix_customer_categories_ar_control_account_id`, `ix_customer_categories_default_output_tax_code_id`, `ix_customer_categories_default_revenue_account_id`

## customers

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(10) | no |  |
| name | VARCHAR(200) | no |  |
| category_id | INTEGER | no | → customer_categories.id |
| customer_type | VARCHAR(20) | no |  |
| ntn | VARCHAR(20) | yes |  |
| strn | VARCHAR(20) | yes |  |
| cnic | VARCHAR(20) | yes |  |
| address | TEXT | yes |  |
| city | VARCHAR(80) | yes |  |
| phone | VARCHAR(40) | yes |  |
| email | VARCHAR(160) | yes |  |
| contact_person | VARCHAR(120) | yes |  |
| credit_limit | NUMERIC(18, 2) | yes |  |
| payment_terms_days | INTEGER | no |  |
| wht_tax_code_id | INTEGER | yes | → tax_codes.id |
| is_active | BOOLEAN | no |  |
| is_sample | BOOLEAN | no |  |
| notes | TEXT | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_customers_code`

Indexes: `ix_customers_category_id`, `ix_customers_name`, `ix_customers_ntn`, `ix_customers_wht_tax_code_id`

## day_closes

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| site_id | INTEGER | no | → sites.id |
| business_date | DATE | no |  |
| status | VARCHAR(12) | no |  |
| ticket_gross | NUMERIC(18, 2) | no |  |
| ticket_net_revenue | NUMERIC(18, 2) | no |  |
| fnb_gross | NUMERIC(18, 2) | no |  |
| fnb_net_revenue | NUMERIC(18, 2) | no |  |
| tax_total | NUMERIC(18, 2) | no |  |
| film_rental | NUMERIC(18, 2) | no |  |
| cash_expected | NUMERIC(18, 2) | no |  |
| cash_declared | NUMERIC(18, 2) | yes |  |
| cash_over_short | NUMERIC(18, 2) | no |  |
| deferred_amount | NUMERIC(18, 2) | no |  |
| released_amount | NUMERIC(18, 2) | no |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| film_rental_journal_id | INTEGER | yes | → journal_entries.id |
| notes | TEXT | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Indexes: `ix_day_closes_company_id`, `ix_day_closes_film_rental_journal_id`, `ix_day_closes_journal_id`, `ix_dayclose_site_date`

## depreciation_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| run_id | INTEGER | no | → depreciation_runs.id |
| asset_id | INTEGER | no | → fixed_assets.id |
| amount | NUMERIC(18, 2) | no |  |
| site_id | INTEGER | no | → sites.id |
| cost_centre_id | INTEGER | no | → cost_centres.id |
| nbv_before | NUMERIC(18, 2) | no |  |
| nbv_after | NUMERIC(18, 2) | no |  |

Constraints: `uq_depreciation_lines_run_id_asset_id`

Indexes: `ix_depreciation_lines_asset_id`, `ix_depreciation_lines_cost_centre_id`, `ix_depreciation_lines_run_id`, `ix_depreciation_lines_site_id`

## depreciation_runs

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| period_id | INTEGER | no | → accounting_periods.id |
| run_date | DATE | no |  |
| status | VARCHAR(12) | no |  |
| total | NUMERIC(18, 2) | no |  |
| journal_id | INTEGER | yes | → journal_entries.id |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Indexes: `ix_depreciation_runs_company_id`, `ix_depreciation_runs_journal_id`, `ix_depreciation_runs_period_id`

## dimension_types

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(20) | no |  |
| name | VARCHAR(80) | no |  |
| description | TEXT | yes |  |
| is_system | BOOLEAN | no |  |
| is_active | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_dimension_types_code`

## dimension_values

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| dimension_type_id | INTEGER | no | → dimension_types.id |
| code | VARCHAR(40) | no |  |
| name | VARCHAR(200) | no |  |
| parent_id | INTEGER | yes | → dimension_values.id |
| site_id | INTEGER | yes | → sites.id |
| is_active | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_dimension_values_dimension_type_id_code`

Indexes: `ix_dimension_values_dimension_type_id`, `ix_dimension_values_parent_id`, `ix_dimension_values_site_id`

## distributor_settlement_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| settlement_id | INTEGER | no | → distributor_settlements.id |
| film_id | INTEGER | no | → films.id |
| site_id | INTEGER | no | → sites.id |
| tickets | INTEGER | no |  |
| net_box_office | NUMERIC(18, 2) | no |  |
| accrued_amount | NUMERIC(18, 2) | no |  |

Indexes: `ix_distributor_settlement_lines_film_id`, `ix_distributor_settlement_lines_settlement_id`, `ix_distributor_settlement_lines_site_id`

## distributor_settlements

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| reference | VARCHAR(60) | yes |  |
| company_id | INTEGER | no | → companies.id |
| distributor_id | INTEGER | no | → suppliers.id |
| period_from | DATE | no |  |
| period_to | DATE | no |  |
| net_box_office | NUMERIC(18, 2) | no |  |
| accrued_amount | NUMERIC(18, 2) | no |  |
| adjustment | NUMERIC(18, 2) | no |  |
| total | NUMERIC(18, 2) | no |  |
| status | VARCHAR(12) | no |  |
| ap_document_id | INTEGER | yes | → ap_documents.id |
| notes | TEXT | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Indexes: `ix_distributor_settlements_ap_document_id`, `ix_distributor_settlements_company_id`, `ix_distributor_settlements_distributor_id`

## employees

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| code | VARCHAR(20) | no |  |
| name | VARCHAR(120) | no |  |
| cnic | VARCHAR(20) | yes |  |
| site_id | INTEGER | yes | → sites.id |
| cost_centre_id | INTEGER | yes | → cost_centres.id |
| is_active | BOOLEAN | no |  |
| is_sample | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_employees_company_id_code`

Indexes: `ix_employees_company_id`, `ix_employees_cost_centre_id`, `ix_employees_site_id`

## film_terms

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| film_id | INTEGER | no | → films.id |
| site_id | INTEGER | yes | → sites.id |
| week_from | INTEGER | no |  |
| week_to | INTEGER | no |  |
| share_pct | NUMERIC(9, 6) | no |  |
| minimum_guarantee | NUMERIC(18, 2) | yes |  |

Constraints: `ck_film_terms_share_range`, `ck_film_terms_weeks`

Indexes: `ix_film_terms_film_id`, `ix_film_terms_site_id`

## films

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(20) | no |  |
| title | VARCHAR(200) | no |  |
| distributor_id | INTEGER | no | → suppliers.id |
| language | VARCHAR(40) | yes |  |
| rating | VARCHAR(10) | yes |  |
| release_date | DATE | no |  |
| runtime_minutes | INTEGER | yes |  |
| dimension_value_id | INTEGER | yes | → dimension_values.id |
| is_active | BOOLEAN | no |  |
| is_sample | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_films_code`

Indexes: `ix_films_dimension_value_id`, `ix_films_distributor_id`, `ix_films_title`

## fiscal_years

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| code | VARCHAR(20) | no |  |
| start_date | DATE | no |  |
| end_date | DATE | no |  |
| status | VARCHAR(10) | no |  |
| closing_journal_id | INTEGER | yes | → journal_entries.id |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_fiscal_years_company_id_code`

Indexes: `ix_fiscal_years_company_id`

## fixed_assets

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| code | VARCHAR(20) | no |  |
| name | VARCHAR(200) | no |  |
| description | TEXT | yes |  |
| category_id | INTEGER | no | → asset_categories.id |
| site_id | INTEGER | no | → sites.id |
| cost_centre_id | INTEGER | no | → cost_centres.id |
| supplier_id | INTEGER | yes | → suppliers.id |
| ap_document_id | INTEGER | yes | → ap_documents.id |
| purchase_date | DATE | no |  |
| capitalisation_date | DATE | no |  |
| depreciation_start_date | DATE | no |  |
| cost | NUMERIC(18, 2) | no |  |
| residual_value | NUMERIC(18, 2) | no |  |
| useful_life_months | INTEGER | no |  |
| method | VARCHAR(32) | no |  |
| reducing_rate | NUMERIC(9, 6) | yes |  |
| accumulated_depreciation | NUMERIC(18, 2) | no |  |
| impairment_total | NUMERIC(18, 2) | no |  |
| status | VARCHAR(32) | no |  |
| last_depreciation_date | DATE | yes |  |
| disposal_date | DATE | yes |  |
| disposal_proceeds | NUMERIC(18, 2) | yes |  |
| acquisition_journal_id | INTEGER | yes | → journal_entries.id |
| serial_no | VARCHAR(80) | yes |  |
| tag_no | VARCHAR(80) | yes |  |
| is_opening | BOOLEAN | no |  |
| is_sample | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_fixed_assets_assetstatus`, `ck_fixed_assets_depreciationmethod`, `ck_fixed_assets_life_positive`, `ck_fixed_assets_non_negative`, `uq_fixed_assets_company_id_code`

Indexes: `ix_fixed_assets_acquisition_journal_id`, `ix_fixed_assets_ap_document_id`, `ix_fixed_assets_category_id`, `ix_fixed_assets_company_id`, `ix_fixed_assets_cost_centre_id`, `ix_fixed_assets_site_id`, `ix_fixed_assets_status`, `ix_fixed_assets_supplier_id`

## fnb_sales

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | BIGINT | no | PK |
| company_id | INTEGER | no | → companies.id |
| site_id | INTEGER | no | → sites.id |
| business_date | DATE | no |  |
| revenue_type_id | INTEGER | no | → revenue_types.id |
| payment_method_id | INTEGER | no | → payment_methods.id |
| quantity | INTEGER | no |  |
| gross_amount | NUMERIC(18, 2) | no |  |
| discount_amount | NUMERIC(18, 2) | no |  |
| refund_amount | NUMERIC(18, 2) | no |  |
| import_batch_id | INTEGER | yes | → sales_import_batches.id |
| day_close_id | INTEGER | yes | → day_closes.id |
| source_ref | VARCHAR(80) | yes |  |
| net_revenue | NUMERIC(18, 2) | no |  |
| tax_amount | NUMERIC(18, 2) | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_fnb_sales_non_negative`

Indexes: `ix_fnb_sales_company_id`, `ix_fnb_sales_day_close_id`, `ix_fnb_sales_import_batch_id`, `ix_fnb_sales_payment_method_id`, `ix_fnb_sales_revenue_type_id`, `ix_fnb_sales_source_ref`, `ix_fnb_site_date`

## journal_entries

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| journal_type | VARCHAR(32) | no |  |
| number | VARCHAR(40) | yes |  |
| transaction_date | DATE | no |  |
| posting_date | DATE | no |  |
| period_id | INTEGER | yes | → accounting_periods.id |
| description | TEXT | no |  |
| reference | VARCHAR(120) | yes |  |
| source_module | VARCHAR(32) | no |  |
| source_type | VARCHAR(40) | yes |  |
| source_id | INTEGER | yes |  |
| source_key | VARCHAR(120) | yes |  |
| status | VARCHAR(32) | no |  |
| total_debit | NUMERIC(18, 2) | no |  |
| total_credit | NUMERIC(18, 2) | no |  |
| currency | VARCHAR(3) | no |  |
| is_system | BOOLEAN | no |  |
| is_accrual | BOOLEAN | no |  |
| auto_reverse_date | DATE | yes |  |
| submitted_by_id | INTEGER | yes | → users.id |
| submitted_at | DATETIME | yes |  |
| checked_by_id | INTEGER | yes | → users.id |
| checked_at | DATETIME | yes |  |
| approved_by_id | INTEGER | yes | → users.id |
| approved_at | DATETIME | yes |  |
| posted_by_id | INTEGER | yes | → users.id |
| posted_at | DATETIME | yes |  |
| reversed_by_id | INTEGER | yes | → users.id |
| reversed_at | DATETIME | yes |  |
| reversal_of_id | INTEGER | yes | → journal_entries.id |
| reversal_reason | TEXT | yes |  |
| recurring_journal_id | INTEGER | yes | → recurring_journals.id |
| rejection_reason | TEXT | yes |  |
| version | INTEGER | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_journal_entries_docstatus`, `ck_journal_entries_journaltype`, `ck_journal_entries_sourcemodule`, `ck_journal_entries_totals_non_negative`, `uq_journal_entries_company_id_number`, `uq_journal_entries_source_key`

Indexes: `ix_journal_entries_company_id`, `ix_journal_entries_journal_type`, `ix_journal_entries_period_id`, `ix_journal_entries_recurring_journal_id`, `ix_journal_entries_reference`, `ix_journal_entries_reversal_of_id`, `ix_journal_entries_status`, `ix_journal_status_date`

## journal_line_dimensions

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | BIGINT | no | PK |
| journal_line_id | BIGINT | no | → journal_lines.id |
| dimension_type_id | INTEGER | no | → dimension_types.id |
| dimension_value_id | INTEGER | no | → dimension_values.id |

Constraints: `uq_journal_line_dimensions_journal_line_id_dimension_type_id`

Indexes: `ix_jld_value`, `ix_journal_line_dimensions_journal_line_id`

## journal_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | BIGINT | no | PK |
| journal_id | INTEGER | no | → journal_entries.id |
| line_no | INTEGER | no |  |
| account_id | INTEGER | no | → accounts.id |
| site_id | INTEGER | yes | → sites.id |
| cost_centre_id | INTEGER | yes | → cost_centres.id |
| supplier_id | INTEGER | yes | → suppliers.id |
| customer_id | INTEGER | yes | → customers.id |
| employee_id | INTEGER | yes | → employees.id |
| partner_company_id | INTEGER | yes | → companies.id |
| description | TEXT | yes |  |
| reference | VARCHAR(120) | yes |  |
| debit | NUMERIC(18, 2) | no |  |
| credit | NUMERIC(18, 2) | no |  |
| currency | VARCHAR(3) | no |  |
| fx_rate | NUMERIC(18, 6) | no |  |
| amount_fc | NUMERIC(18, 2) | yes |  |
| tax_code_id | INTEGER | yes | → tax_codes.id |
| tax_base | NUMERIC(18, 2) | yes |  |
| tax_rate | NUMERIC(9, 6) | yes |  |
| company_id | INTEGER | yes | → companies.id |
| posting_date | DATE | yes |  |
| period_id | INTEGER | yes | → accounting_periods.id |
| is_posted | BOOLEAN | no |  |
| source_module | VARCHAR(20) | yes |  |

Constraints: `ck_journal_lines_non_negative`, `ck_journal_lines_non_zero`, `ck_journal_lines_one_party`, `ck_journal_lines_one_side`

Indexes: `ix_jl_cc_account`, `ix_jl_customer`, `ix_jl_posted_account_date`, `ix_jl_posted_period`, `ix_jl_site_account`, `ix_jl_supplier`, `ix_journal_lines_employee_id`, `ix_journal_lines_journal_id`, `ix_journal_lines_partner_company_id`, `ix_journal_lines_tax_code_id`

## number_sequences

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| seq_key | VARCHAR(40) | no |  |
| prefix | VARCHAR(30) | no |  |
| next_value | INTEGER | no |  |
| padding | INTEGER | no |  |

Constraints: `uq_number_sequences_company_id_seq_key`

Indexes: `ix_number_sequences_company_id`

## payment_methods

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(20) | no |  |
| name | VARCHAR(80) | no |  |
| method_type | VARCHAR(20) | no |  |
| clearing_account_id | INTEGER | no | → accounts.id |
| customer_id | INTEGER | yes | → customers.id |
| fee_pct | NUMERIC(9, 6) | no |  |
| fee_account_id | INTEGER | yes | → accounts.id |
| settlement_bank_account_id | INTEGER | yes | → bank_accounts.id |
| settlement_days | INTEGER | no |  |
| is_active | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_payment_methods_code`

Indexes: `ix_payment_methods_clearing_account_id`, `ix_payment_methods_customer_id`, `ix_payment_methods_fee_account_id`, `ix_payment_methods_settlement_bank_account_id`

## period_checklist_items

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| period_id | INTEGER | no | → accounting_periods.id |
| code | VARCHAR(40) | no |  |
| title | VARCHAR(200) | no |  |
| is_auto | BOOLEAN | no |  |
| is_blocking | BOOLEAN | no |  |
| status | VARCHAR(10) | no |  |
| detail | TEXT | yes |  |
| signed_off_by_id | INTEGER | yes | → users.id |
| signed_off_at | DATETIME | yes |  |
| comment | TEXT | yes |  |

Constraints: `uq_period_checklist_items_period_id_code`

Indexes: `ix_period_checklist_items_period_id`

## period_status_log

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| period_id | INTEGER | no | → accounting_periods.id |
| from_status | VARCHAR(20) | no |  |
| to_status | VARCHAR(20) | no |  |
| user_id | INTEGER | yes | → users.id |
| ts | DATETIME | no |  |
| reason | TEXT | yes |  |

Indexes: `ix_period_status_log_period_id`

## permissions

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(80) | no |  |
| module | VARCHAR(40) | no |  |
| description | VARCHAR(200) | no |  |

Constraints: `uq_permissions_code`

## recurring_journal_lines

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| recurring_journal_id | INTEGER | no | → recurring_journals.id |
| line_no | INTEGER | no |  |
| account_id | INTEGER | no | → accounts.id |
| site_id | INTEGER | yes | → sites.id |
| cost_centre_id | INTEGER | yes | → cost_centres.id |
| supplier_id | INTEGER | yes | → suppliers.id |
| customer_id | INTEGER | yes | → customers.id |
| employee_id | INTEGER | yes | → employees.id |
| description | TEXT | yes |  |
| debit | NUMERIC(18, 2) | no |  |
| credit | NUMERIC(18, 2) | no |  |
| dimensions | TEXT | yes |  |

Indexes: `ix_recurring_journal_lines_account_id`, `ix_recurring_journal_lines_cost_centre_id`, `ix_recurring_journal_lines_customer_id`, `ix_recurring_journal_lines_employee_id`, `ix_recurring_journal_lines_recurring_journal_id`, `ix_recurring_journal_lines_site_id`, `ix_recurring_journal_lines_supplier_id`

## recurring_journals

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| name | VARCHAR(120) | no |  |
| description | TEXT | no |  |
| frequency | VARCHAR(10) | no |  |
| next_run_date | DATE | no |  |
| end_date | DATE | yes |  |
| auto_submit | BOOLEAN | no |  |
| is_active | BOOLEAN | no |  |
| last_run_at | DATETIME | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Indexes: `ix_recurring_journals_company_id`

## revenue_types

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(30) | no |  |
| name | VARCHAR(80) | no |  |
| stream | VARCHAR(20) | no |  |
| revenue_account_id | INTEGER | no | → accounts.id |
| discount_account_id | INTEGER | yes | → accounts.id |
| refund_account_id | INTEGER | yes | → accounts.id |
| cost_centre_id | INTEGER | no | → cost_centres.id |
| tax_code_ids | VARCHAR(100) | yes |  |
| applies_film_rental | BOOLEAN | no |  |
| is_active | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_revenue_types_code`

Indexes: `ix_revenue_types_cost_centre_id`, `ix_revenue_types_discount_account_id`, `ix_revenue_types_refund_account_id`, `ix_revenue_types_revenue_account_id`

## role_permissions

| Column | Type | Null | Key / reference |
|---|---|---|---|
| role_id | INTEGER | no | PK → roles.id |
| permission_id | INTEGER | no | PK → permissions.id |

## roles

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(40) | no |  |
| name | VARCHAR(80) | no |  |
| description | TEXT | yes |  |
| is_system | BOOLEAN | no |  |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_roles_code`

## sales_import_batches

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| kind | VARCHAR(12) | no |  |
| filename | VARCHAR(255) | yes |  |
| row_count | INTEGER | no |  |
| status | VARCHAR(12) | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

## screens

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| site_id | INTEGER | no | → sites.id |
| code | VARCHAR(10) | no |  |
| name | VARCHAR(80) | no |  |
| seats | INTEGER | no |  |
| screen_type | VARCHAR(20) | no |  |
| dimension_value_id | INTEGER | yes | → dimension_values.id |
| is_active | BOOLEAN | no |  |
| is_sample | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_screens_site_id_code`

Indexes: `ix_screens_dimension_value_id`, `ix_screens_site_id`

## settings

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | yes | → companies.id |
| key | VARCHAR(80) | no |  |
| value | TEXT | no |  |
| description | TEXT | yes |  |

Constraints: `uq_settings_company_id_key`

## shows

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| site_id | INTEGER | no | → sites.id |
| screen_id | INTEGER | no | → screens.id |
| film_id | INTEGER | no | → films.id |
| business_date | DATE | no |  |
| show_time | DATETIME | no |  |
| capacity | INTEGER | no |  |
| status | VARCHAR(12) | no |  |
| is_sample | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_shows_screen_id_show_time`

Indexes: `ix_show_site_date`, `ix_shows_film_id`, `ix_shows_screen_id`

## sites

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| company_id | INTEGER | no | → companies.id |
| code | VARCHAR(10) | no |  |
| name | VARCHAR(120) | no |  |
| site_type | VARCHAR(32) | no |  |
| city | VARCHAR(80) | yes |  |
| province | VARCHAR(40) | yes |  |
| tax_authority | VARCHAR(20) | yes |  |
| pos_code | VARCHAR(20) | yes |  |
| opening_date | DATE | yes |  |
| is_active | BOOLEAN | no |  |
| notes | TEXT | yes |  |
| is_sample | BOOLEAN | no |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_sites_sitetype`, `uq_sites_company_id_code`

Indexes: `ix_sites_company_id`

## supplier_categories

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(20) | no |  |
| name | VARCHAR(120) | no |  |
| ap_control_account_id | INTEGER | no | → accounts.id |
| advance_account_id | INTEGER | yes | → accounts.id |
| default_expense_account_id | INTEGER | yes | → accounts.id |
| default_wht_tax_code_id | INTEGER | yes | → tax_codes.id |
| default_st_tax_code_id | INTEGER | yes | → tax_codes.id |
| default_stw_tax_code_id | INTEGER | yes | → tax_codes.id |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_supplier_categories_code`

Indexes: `ix_supplier_categories_advance_account_id`, `ix_supplier_categories_ap_control_account_id`, `ix_supplier_categories_default_expense_account_id`, `ix_supplier_categories_default_st_tax_code_id`, `ix_supplier_categories_default_stw_tax_code_id`, `ix_supplier_categories_default_wht_tax_code_id`

## suppliers

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(10) | no |  |
| name | VARCHAR(200) | no |  |
| beneficiary_name | VARCHAR(200) | yes |  |
| category_id | INTEGER | no | → supplier_categories.id |
| supplier_type | VARCHAR(32) | no |  |
| ntn | VARCHAR(20) | yes |  |
| strn | VARCHAR(20) | yes |  |
| cnic | VARCHAR(20) | yes |  |
| atl_status | VARCHAR(10) | no |  |
| st_registered | BOOLEAN | no |  |
| address | TEXT | yes |  |
| city | VARCHAR(80) | yes |  |
| phone | VARCHAR(40) | yes |  |
| email | VARCHAR(160) | yes |  |
| contact_person | VARCHAR(120) | yes |  |
| bank_name | VARCHAR(120) | yes |  |
| bank_account_title | VARCHAR(160) | yes |  |
| bank_account_no | VARCHAR(40) | yes |  |
| iban | VARCHAR(34) | yes |  |
| payment_terms_days | INTEGER | no |  |
| wht_tax_code_id | INTEGER | yes | → tax_codes.id |
| st_tax_code_id | INTEGER | yes | → tax_codes.id |
| stw_tax_code_id | INTEGER | yes | → tax_codes.id |
| wht_exemption_rate | NUMERIC(9, 6) | yes |  |
| wht_exemption_until | DATE | yes |  |
| payment_hold | BOOLEAN | no |  |
| is_active | BOOLEAN | no |  |
| is_sample | BOOLEAN | no |  |
| notes | TEXT | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_suppliers_suppliertype`, `uq_suppliers_code`

Indexes: `ix_suppliers_category_id`, `ix_suppliers_cnic`, `ix_suppliers_name`, `ix_suppliers_ntn`, `ix_suppliers_st_tax_code_id`, `ix_suppliers_stw_tax_code_id`, `ix_suppliers_wht_tax_code_id`

## tax_codes

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| code | VARCHAR(30) | no |  |
| name | VARCHAR(160) | no |  |
| tax_type | VARCHAR(32) | no |  |
| authority | VARCHAR(20) | no |  |
| law_section | VARCHAR(120) | yes |  |
| base | VARCHAR(32) | no |  |
| account_id | INTEGER | no | → accounts.id |
| is_recoverable | BOOLEAN | no |  |
| is_inclusive_default | BOOLEAN | no |  |
| is_active | BOOLEAN | no |  |
| needs_confirmation | BOOLEAN | no |  |
| notes | TEXT | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `ck_tax_codes_taxbase`, `ck_tax_codes_taxtype`, `uq_tax_codes_code`

Indexes: `ix_tax_codes_account_id`

## tax_rates

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| tax_code_id | INTEGER | no | → tax_codes.id |
| name | VARCHAR(120) | no |  |
| payee_type | VARCHAR(20) | no |  |
| atl_status | VARCHAR(10) | no |  |
| rate | NUMERIC(9, 6) | no |  |
| effective_from | DATE | no |  |
| effective_to | DATE | yes |  |
| site_id | INTEGER | yes | → sites.id |
| transaction_type | VARCHAR(30) | yes |  |
| is_active | BOOLEAN | no |  |
| source_ref | VARCHAR(160) | yes |  |
| created_by_id | INTEGER | yes | → users.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Indexes: `ix_tax_rates_site_id`, `ix_taxrate_lookup`

## tax_slabs

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| tax_code_id | INTEGER | no | → tax_codes.id |
| effective_from | DATE | no |  |
| effective_to | DATE | yes |  |
| amount_from | NUMERIC(18, 2) | no |  |
| amount_to | NUMERIC(18, 2) | yes |  |
| fixed_tax | NUMERIC(18, 2) | no |  |
| rate | NUMERIC(9, 6) | no |  |

Indexes: `ix_tax_slabs_tax_code_id`

## tax_transactions

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | BIGINT | no | PK |
| company_id | INTEGER | no | → companies.id |
| tax_code_id | INTEGER | no | → tax_codes.id |
| tax_rate_id | INTEGER | yes | → tax_rates.id |
| journal_id | INTEGER | no | → journal_entries.id |
| journal_line_id | BIGINT | yes | → journal_lines.id |
| source_type | VARCHAR(40) | no |  |
| source_id | INTEGER | yes |  |
| transaction_date | DATE | no |  |
| period_id | INTEGER | yes | → accounting_periods.id |
| direction | VARCHAR(10) | no |  |
| supplier_id | INTEGER | yes | → suppliers.id |
| customer_id | INTEGER | yes | → customers.id |
| site_id | INTEGER | yes | → sites.id |
| party_ntn | VARCHAR(20) | yes |  |
| party_name | VARCHAR(200) | yes |  |
| document_ref | VARCHAR(120) | yes |  |
| base_amount | NUMERIC(18, 2) | no |  |
| rate | NUMERIC(9, 6) | no |  |
| tax_amount | NUMERIC(18, 2) | no |  |
| rate_overridden | BOOLEAN | no |  |
| override_reason | TEXT | yes |  |
| is_reversal | BOOLEAN | no |  |
| deposited | BOOLEAN | no |  |
| deposit_reference | VARCHAR(60) | yes |  |
| deposit_date | DATE | yes |  |

Indexes: `ix_tax_transactions_company_id`, `ix_tax_transactions_customer_id`, `ix_tax_transactions_journal_id`, `ix_tax_transactions_period_id`, `ix_tax_transactions_site_id`, `ix_tax_transactions_supplier_id`, `ix_tax_transactions_tax_rate_id`, `ix_taxtxn_code_date`

## user_roles

| Column | Type | Null | Key / reference |
|---|---|---|---|
| user_id | INTEGER | no | PK → users.id |
| role_id | INTEGER | no | PK → roles.id |

## user_site_access

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| user_id | INTEGER | no | → users.id |
| site_id | INTEGER | no | → sites.id |

Constraints: `uq_user_site_access_user_id_site_id`

Indexes: `ix_user_site_access_site_id`, `ix_user_site_access_user_id`

## users

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| username | VARCHAR(60) | no |  |
| full_name | VARCHAR(120) | no |  |
| email | VARCHAR(160) | yes |  |
| password_hash | VARCHAR(255) | no |  |
| is_active | BOOLEAN | no |  |
| is_superuser | BOOLEAN | no |  |
| all_sites | BOOLEAN | no |  |
| failed_logins | INTEGER | no |  |
| locked_until | DATETIME | yes |  |
| token_version | INTEGER | no |  |
| must_change_password | BOOLEAN | no |  |
| last_login_at | DATETIME | yes |  |
| default_company_id | INTEGER | yes | → companies.id |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_users_username`

## workflow_definitions

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | INTEGER | no | PK |
| doc_type | VARCHAR(30) | no |  |
| name | VARCHAR(80) | no |  |
| require_check | BOOLEAN | no |  |
| segregation_of_duties | BOOLEAN | no |  |
| auto_post_on_approval | BOOLEAN | no |  |
| require_attachment | BOOLEAN | no |  |
| is_active | BOOLEAN | no |  |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | yes |  |

Constraints: `uq_workflow_definitions_doc_type`

## workflow_history

| Column | Type | Null | Key / reference |
|---|---|---|---|
| id | BIGINT | no | PK |
| doc_type | VARCHAR(30) | no |  |
| doc_id | INTEGER | no |  |
| action | VARCHAR(20) | no |  |
| from_status | VARCHAR(20) | no |  |
| to_status | VARCHAR(20) | no |  |
| user_id | INTEGER | yes | → users.id |
| ts | DATETIME | no |  |
| comment | TEXT | yes |  |

Indexes: `ix_wfh_doc`
