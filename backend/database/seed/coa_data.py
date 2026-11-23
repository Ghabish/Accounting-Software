"""Universal Cinemas / NC Entertainment - Chart of Accounts definition (v1.0).

Single source of truth for the seeded chart.  ``build_chart()`` returns one dict
per account (levels 1-4) with every attribute the accounting engine uses.  The
CSV in ``configuration/coa_universal_cinemas.csv`` and the markdown in
``documentation/CHART_OF_ACCOUNTS.md`` are generated from this module by
``scripts/export_coa.py``; edit here, then regenerate.

Design (see documentation/01_ANALYSIS_AND_DESIGN.md):
  * Code format 00-00-00-0000 (class, group, sub-group, ledger) retained from the
    Generation reference chart.  Only level-4 ledgers accept postings.
  * Account classes 01-08 retained (assets ... finance costs and taxation).
  * Location is NOT in the account: it is the Site dimension.  Function is the
    Cost Centre dimension.  Film / screen / distributor are extra dimensions.
  * Vendors and customers are party codes on control ledgers, not GL accounts.
  * ``gen_ref`` records the Generation ledger an account was adapted from
    ("NEW" = cinema-specific, not in the reference chart).
"""
from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# Level 1-3 headings
# --------------------------------------------------------------------------
CLASSES = {
    "01": "ASSETS",
    "02": "LIABILITIES",
    "03": "EQUITY",
    "04": "REVENUE",
    "05": "COST OF SALES",
    "06": "OPERATING EXPENSES",
    "07": "OTHER INCOME AND OTHER EXPENSES",
    "08": "FINANCE COSTS AND TAXATION",
}

GROUPS = {
    "01-01": "Non-Current Assets",
    "01-02": "Current Assets",
    "02-01": "Non-Current Liabilities",
    "02-02": "Current Liabilities",
    "03-01": "Share Capital and Reserves",
    "04-01": "Ticketing Revenue",
    "04-02": "Food and Beverage Revenue",
    "04-03": "Advertising and Sponsorship Revenue",
    "04-04": "Other Operating Revenue",
    "05-01": "Film Costs",
    "05-02": "Food and Beverage Cost",
    "05-03": "Other Direct Costs",
    "06-01": "Employee Costs",
    "06-02": "Premises and Occupancy",
    "06-03": "Repairs and Maintenance - Equipment",
    "06-04": "Selling and Marketing",
    "06-05": "Travel and Vehicles",
    "06-06": "Office and General Administration",
    "06-07": "Depreciation and Amortisation",
    "07-01": "Other Income",
    "07-02": "Other Expenses",
    "08-01": "Finance Costs",
    "08-02": "Taxation",
}

# Sub-group: (name, defaults) - defaults apply to every ledger in the sub-group
# Keys: control, party, party_rule, site, cc, cf, pl, stream, manual, abnormal,
#       recon, budget, ic, zero
BS = dict(site="OPT", cc="BS")
LOC = dict(site="REQ", cc="LOC")

SUBGROUPS: dict[str, tuple[str, dict[str, Any]]] = {
    "01-01-01": ("Property, Plant and Equipment", dict(LOC, control="REGISTER", cf="INV_PPE", manual="RESTRICTED", abnormal="BLOCK", recon=True, budget="ABSOLUTE")),
    "01-01-02": ("Capital Work in Progress", dict(LOC, control="REGISTER", cf="INV_PPE", manual="RESTRICTED", recon=True, budget="ABSOLUTE")),
    "01-01-03": ("Right-of-Use Assets", dict(LOC, control="REGISTER", cf="FIN_LEASE", manual="RESTRICTED", recon=True)),
    "01-01-04": ("Intangible Assets", dict(BS, control="REGISTER", cf="INV_INTANGIBLES", manual="RESTRICTED", recon=True, budget="ABSOLUTE")),
    "01-01-05": ("Long-Term Deposits and Investments", dict(LOC, cf="INV_DEPOSITS", recon=True)),
    "01-02-01": ("Inventories", dict(LOC, control="REGISTER", cf="OP_INVENTORY", manual="RESTRICTED", abnormal="BLOCK", recon=True)),
    "01-02-02": ("Trade Receivables", dict(BS, cf="OP_RECEIVABLES", recon=True)),
    "01-02-03": ("Advances, Deposits, Prepayments and Other Receivables", dict(BS, cf="OP_ADVANCES")),
    "01-02-04": ("Intercompany Receivables", dict(BS, cf="OP_RELATED", ic=True, recon=True)),
    "01-02-05": ("Tax Refunds Due from Government", dict(BS, control="TAX", cf="OP_TAXES", recon=True)),
    "01-02-06": ("Short-Term Investments", dict(BS, control="REGISTER", cf="INV_INVESTMENTS", recon=True)),
    "01-02-07": ("Cash and Bank Balances", dict(BS, control="BANK", cf="CASH", recon=True, abnormal="ALERT")),
    "02-01-01": ("Long-Term Financing", dict(BS, cf="FIN_BORROWINGS", recon=True, manual="RESTRICTED")),
    "02-01-02": ("Lease Liabilities", dict(LOC, control="REGISTER", cf="FIN_LEASE", manual="RESTRICTED", recon=True)),
    "02-01-03": ("Deferred Liabilities", dict(BS, cf="OP_PROVISIONS", manual="RESTRICTED")),
    "02-01-04": ("Long-Term Deposits Received", dict(BS, cf="OP_PAYABLES")),
    "02-02-01": ("Trade and Other Payables - Suppliers", dict(BS, control="AP_CONTROL", party="SUPPLIER", party_rule="REQ", cf="OP_PAYABLES", recon=True)),
    "02-02-02": ("Accrued and Other Liabilities", dict(BS, cf="OP_ACCRUALS")),
    "02-02-03": ("Taxes and Duties Payable", dict(BS, control="TAX", cf="OP_TAXES", recon=True)),
    "02-02-04": ("Short-Term Borrowings", dict(BS, cf="FIN_SHORT_TERM", recon=True, manual="RESTRICTED")),
    "03-01-01": ("Share Capital", dict(BS, control="REGISTER", cf="FIN_EQUITY", manual="RESTRICTED")),
    "03-01-02": ("Reserves", dict(BS, cf="FIN_EQUITY", manual="NOT_ALLOWED")),
    "03-01-03": ("Opening Balance Clearing", dict(BS, control="CLEARING", cf="EXCLUDED", manual="NOT_ALLOWED", zero=True, recon=True)),
    "04-01-01": ("Box Office Sales", dict(site="REQ", cc="REQ", pl="REVENUE", stream="TICKETING", cf="PBT")),
    "04-01-02": ("Ticketing Deductions", dict(site="REQ", cc="REQ", pl="REVENUE", stream="TICKETING", cf="PBT")),
    "04-02-01": ("Concession Sales", dict(site="REQ", cc="REQ", pl="REVENUE", stream="FNB", cf="PBT")),
    "04-02-02": ("Food and Beverage Deductions", dict(site="REQ", cc="REQ", pl="REVENUE", stream="FNB", cf="PBT")),
    "04-03-01": ("Advertising and Sponsorship", dict(site="REQ", cc="REQ", pl="REVENUE", stream="ADVERTISING", cf="PBT")),
    "04-04-01": ("Other Revenue", dict(site="REQ", cc="REQ", pl="REVENUE", stream="OTHER", cf="PBT")),
    "05-01-01": ("Film Rental and Content Costs", dict(site="REQ", cc="REQ", pl="COST_OF_SALES", stream="TICKETING", cf="PBT", budget="ADVISORY")),
    "05-02-01": ("Food and Beverage Cost of Goods Sold", dict(site="REQ", cc="REQ", pl="COST_OF_SALES", stream="FNB", cf="PBT", budget="ADVISORY")),
    "05-03-01": ("Revenue Direct Costs", dict(site="REQ", cc="REQ", pl="COST_OF_SALES", cf="PBT", budget="ADVISORY")),
    "06-01-01": ("Salaries and Wages", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-01-02": ("Retirement Benefits and Statutory Contributions", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-01-03": ("Staff Welfare", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-01-04": ("Recruitment and Training", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-02-01": ("Rent and Service Charges", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-02-02": ("Utilities", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-02-03": ("Premises Upkeep", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-03-01": ("Repairs and Maintenance", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-04-01": ("Advertising and Media", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-04-02": ("Selling and Collection Costs", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-05-01": ("Travel", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-05-02": ("Vehicle Running", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-06-01": ("Communication", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-06-02": ("Office Running", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-06-03": ("IT, Ticketing and Software", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-06-04": ("Legal and Professional", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-06-05": ("Licences, Fees, Subscriptions and Insurance", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-06-06": ("Other Administrative Expenses", dict(site="REQ", cc="REQ", pl="OPEX", cf="PBT", budget="ADVISORY")),
    "06-07-01": ("Depreciation - Owned Assets", dict(site="REQ", cc="REQ", pl="DEPRECIATION", cf="PBT", cf_adj="ADJ_DA", cf_counter="INV_PPE", manual="RESTRICTED")),
    "06-07-02": ("Depreciation - Right-of-Use Assets", dict(site="REQ", cc="REQ", pl="DEPRECIATION", cf="PBT", cf_adj="ADJ_DA", cf_counter="FIN_LEASE", manual="RESTRICTED")),
    "06-07-03": ("Amortisation and Impairment", dict(site="REQ", cc="REQ", pl="DEPRECIATION", cf="PBT", cf_adj="ADJ_DA", cf_counter="INV_INTANGIBLES", manual="RESTRICTED")),
    "07-01-01": ("Income from Financial Assets", dict(site="OPT", cc="CORP", pl="OTHER_INCOME", cf="PBT")),
    "07-01-02": ("Other Income", dict(site="OPT", cc="CORP", pl="OTHER_INCOME", cf="PBT")),
    "07-02-01": ("Other Losses and Charges", dict(site="OPT", cc="CORP", pl="OTHER_EXPENSE", cf="PBT")),
    "08-01-01": ("Finance Costs", dict(site="OPT", cc="CORP", pl="FINANCE_COST", cf="PBT")),
    "08-02-01": ("Taxation", dict(site="OPT", cc="CORP", pl="TAXATION", cf="OP_TAX_PAID", manual="RESTRICTED")),
}

# --------------------------------------------------------------------------
# Level 4 ledgers: (code, name, gen_ref, overrides)
# --------------------------------------------------------------------------
C = dict(contra=True)  # contra account (normal balance opposite to its class)

LEDGERS: list[tuple[str, str, str, dict[str, Any]]] = [
    # ---- 01-01-01 PPE
    ("01-01-01-0001", "Freehold land - cost", "01-01-01-0001", {}),
    ("01-01-01-0002", "Buildings - cost", "01-01-01-0002", {}),
    ("01-01-01-0003", "Accumulated depreciation - buildings", "01-01-01-0005", C),
    ("01-01-01-0004", "Leasehold improvements and cinema fit-out - cost", "01-01-01-0008", {}),
    ("01-01-01-0005", "Accumulated depreciation - leasehold improvements and fit-out", "01-01-01-0009", C),
    ("01-01-01-0006", "Projection and digital cinema equipment - cost", "NEW", dict(description="Digital projectors, servers, screens, 3D systems")),
    ("01-01-01-0007", "Accumulated depreciation - projection equipment", "NEW", C),
    ("01-01-01-0008", "Sound and audio systems - cost", "NEW", {}),
    ("01-01-01-0009", "Accumulated depreciation - sound and audio systems", "NEW", C),
    ("01-01-01-0010", "Cinema seating and auditorium fixtures - cost", "NEW", {}),
    ("01-01-01-0011", "Accumulated depreciation - seating and auditorium fixtures", "NEW", C),
    ("01-01-01-0012", "Kitchen and F&B equipment - cost", "NEW", {}),
    ("01-01-01-0013", "Accumulated depreciation - kitchen and F&B equipment", "NEW", C),
    ("01-01-01-0014", "Electrical installations, HVAC and generators - cost", "01-01-01-0012", {}),
    ("01-01-01-0015", "Accumulated depreciation - electrical, HVAC and generators", "01-01-01-0013", C),
    ("01-01-01-0016", "Furniture and office equipment - cost", "01-01-01-0014", {}),
    ("01-01-01-0017", "Accumulated depreciation - furniture and office equipment", "01-01-01-0016", C),
    ("01-01-01-0018", "Computers, POS and IT equipment - cost", "01-01-01-0018", {}),
    ("01-01-01-0019", "Accumulated depreciation - computers, POS and IT equipment", "01-01-01-0019", C),
    ("01-01-01-0020", "Vehicles - cost", "01-01-01-0020", {}),
    ("01-01-01-0021", "Accumulated depreciation - vehicles", "01-01-01-0021", C),
    # ---- 01-01-02 CWIP
    ("01-01-02-0001", "CWIP - cinema construction and fit-out", "01-01-02-0002", {}),
    ("01-01-02-0002", "CWIP - equipment pending installation", "01-01-02-0003", {}),
    ("01-01-02-0003", "Advances to capital suppliers", "01-01-02-0004", dict(site="OPT", party="SUPPLIER", party_rule="REQ")),
    # ---- 01-01-03 ROU
    ("01-01-03-0001", "Right-of-use assets - cinema premises (cost)", "01-01-03-0001", {}),
    ("01-01-03-0002", "Accumulated depreciation - right-of-use premises", "01-01-03-0002", C),
    ("01-01-03-0003", "Right-of-use assets - vehicles (cost)", "01-01-03-0003", dict(site="OPT")),
    ("01-01-03-0004", "Accumulated depreciation - right-of-use vehicles", "01-01-03-0004", dict(C, site="OPT")),
    # ---- 01-01-04 Intangibles
    ("01-01-04-0001", "Software, ERP and ticketing systems - cost", "01-01-04-0001", {}),
    ("01-01-04-0002", "Accumulated amortisation - software", "01-01-04-0002", C),
    ("01-01-04-0003", "Trademarks and brand - cost", "01-01-04-0003", {}),
    ("01-01-04-0004", "Accumulated amortisation - trademarks", "01-01-04-0004", C),
    # ---- 01-01-05 Deposits / investments
    ("01-01-05-0001", "Security deposits - cinema premises leases", "01-01-05-0001", dict(party="SUPPLIER", party_rule="OPT")),
    ("01-01-05-0002", "Security deposits - utilities", "01-01-05-0002", dict(party="SUPPLIER", party_rule="OPT")),
    ("01-01-05-0003", "Security deposits - others", "01-01-05-0003", dict(site="OPT", cc="BS")),
    ("01-01-05-0004", "Long-term investments in group companies", "NEW", dict(site="OPT", cc="BS", ic=True, cf="INV_INVESTMENTS", manual="RESTRICTED")),
    # ---- 01-02-01 Inventories
    ("01-02-01-0001", "F&B stock - food ingredients", "NEW", {}),
    ("01-02-01-0002", "F&B stock - beverages", "NEW", {}),
    ("01-02-01-0003", "F&B stock - packaged snacks and confectionery", "NEW", {}),
    ("01-02-01-0004", "F&B packaging and disposables - stock", "01-02-01-0007", {}),
    ("01-02-01-0005", "Merchandise and promotional items - stock", "NEW", {}),
    ("01-02-01-0006", "Projection spares and technical stores", "01-02-01-0016", {}),
    ("01-02-01-0007", "General stores and consumables", "01-02-01-0018", {}),
    ("01-02-01-0008", "Provision for slow-moving and obsolete stock", "01-02-01-0019", dict(C, site="OPT", cc="BS", control="NONE", abnormal="ALLOW")),
    # ---- 01-02-02 Trade receivables
    ("01-02-02-0001", "Card settlements receivable - acquirer bank A", "01-02-02-0001", dict(control="CLEARING", recon=True, description="Debited at POS day close with card sales; credited by the acquirer settlement")),
    ("01-02-02-0002", "Card settlements receivable - acquirer bank B", "01-02-02-0002", dict(control="CLEARING", recon=True)),
    ("01-02-02-0003", "Online payment gateway receivable", "01-02-02-0007", dict(control="AR_CONTROL", party="CUSTOMER", party_rule="REQ")),
    ("01-02-02-0004", "Mobile wallet receivable", "NEW", dict(control="AR_CONTROL", party="CUSTOMER", party_rule="REQ", description="JazzCash / Easypaisa and similar wallets")),
    ("01-02-02-0005", "Third-party ticketing platform receivable", "01-02-02-0009", dict(control="AR_CONTROL", party="CUSTOMER", party_rule="REQ")),
    ("01-02-02-0006", "Trade receivables - advertising customers", "01-02-02-0011", dict(control="AR_CONTROL", party="CUSTOMER", party_rule="REQ")),
    ("01-02-02-0007", "Trade receivables - corporate bookings and events", "NEW", dict(control="AR_CONTROL", party="CUSTOMER", party_rule="REQ")),
    ("01-02-02-0008", "Trade receivables - other customers", "01-02-02-0011", dict(control="AR_CONTROL", party="CUSTOMER", party_rule="REQ")),
    ("01-02-02-0009", "Allowance for expected credit losses", "01-02-02-0012", dict(C, recon=False, abnormal="ALLOW")),
    # ---- 01-02-03 Advances etc
    ("01-02-03-0001", "Salary advances and loans to employees", "01-02-03-0001", dict(party="EMPLOYEE", party_rule="REQ")),
    ("01-02-03-0002", "Advances against expenses (employees)", "01-02-03-0002", dict(party="EMPLOYEE", party_rule="REQ")),
    ("01-02-03-0003", "Advances to suppliers - goods", "01-02-03-0003", dict(control="AP_CONTROL", party="SUPPLIER", party_rule="REQ", recon=True)),
    ("01-02-03-0004", "Advances to suppliers - services", "01-02-03-0004", dict(control="AP_CONTROL", party="SUPPLIER", party_rule="REQ", recon=True)),
    ("01-02-03-0005", "Advances to film distributors (minimum guarantees)", "NEW", dict(control="AP_CONTROL", party="SUPPLIER", party_rule="REQ", recon=True)),
    ("01-02-03-0006", "Prepaid rent", "01-02-03-0005", dict(site="REQ", cc="LOC", party="SUPPLIER", party_rule="OPT")),
    ("01-02-03-0007", "Prepaid insurance", "01-02-03-0006", {}),
    ("01-02-03-0008", "Other prepayments", "01-02-03-0007", {}),
    ("01-02-03-0009", "Bank guarantees and margin deposits", "01-02-03-0008", {}),
    ("01-02-03-0010", "Insurance claims receivable", "01-02-03-0009", {}),
    ("01-02-03-0011", "Other receivables", "01-02-03-0011", {}),
    # ---- 01-02-04 Intercompany
    ("01-02-04-0001", "Due from group companies (intercompany)", "01-02-03-0010", {}),
    ("01-02-04-0002", "Due from other related parties", "01-02-03-0010", dict(ic=False)),
    # ---- 01-02-05 Tax refunds
    ("01-02-05-0001", "Advance income tax", "01-02-04-0001", dict(cf="OP_TAX_PAID")),
    ("01-02-05-0002", "Tax deducted at source - utility bills", "01-02-04-0002", dict(cf="OP_TAX_PAID")),
    ("01-02-05-0003", "Tax deducted at source - profit on deposits", "01-02-04-0003", dict(cf="OP_TAX_PAID")),
    ("01-02-05-0004", "Tax deducted at source - banking transactions", "01-02-04-0004", dict(cf="OP_TAX_PAID")),
    ("01-02-05-0005", "Tax deducted at source - motor vehicles", "01-02-04-0005", dict(cf="OP_TAX_PAID")),
    ("01-02-05-0006", "Tax deducted by customers, gateways and platforms", "01-02-04-0006", dict(cf="OP_TAX_PAID", party="CUSTOMER", party_rule="OPT")),
    ("01-02-05-0007", "Input sales tax - FBR", "01-02-04-0008", {}),
    ("01-02-05-0008", "Input sales tax on services - PRA", "01-02-04-0010", {}),
    ("01-02-05-0009", "Input sales tax on services - other provinces", "01-02-04-0010", {}),
    ("01-02-05-0010", "Sales tax refundable and carried forward", "01-02-04-0009", {}),
    # ---- 01-02-06 Short-term investments
    ("01-02-06-0001", "Investments in mutual funds and T-bills", "01-02-05-0001", {}),
    # ---- 01-02-07 Cash and bank
    ("01-02-07-0001", "Cash in hand - head office", "01-02-06-0001", dict(control="CASH", site="REQ", cc="LOC", abnormal="BLOCK")),
    ("01-02-07-0002", "Cash in hand - box office", "01-02-06-0002", dict(control="CASH", site="REQ", cc="LOC", abnormal="BLOCK")),
    ("01-02-07-0003", "Cash in hand - F&B counters", "NEW", dict(control="CASH", site="REQ", cc="LOC", abnormal="BLOCK")),
    ("01-02-07-0004", "Petty cash", "NEW", dict(control="CASH", site="REQ", cc="LOC", abnormal="BLOCK", description="Imprest float per site")),
    ("01-02-07-0005", "Cash in transit", "01-02-06-0003", dict(control="CLEARING", site="REQ", cc="LOC", zero=True, description="Cash lifted from site, not yet credited by the bank; must be nil at period end")),
    ("01-02-07-0006", "Bank - operating current account", "01-02-06-0005", dict(description="Sample bank ledger - rename to the actual bank and account number")),
    ("01-02-07-0007", "Bank - collections account", "NEW", dict(description="Card, gateway and cash deposit collections (sample)")),
    ("01-02-07-0008", "Bank - payroll account", "NEW", dict(description="Sample")),
    ("01-02-07-0009", "Bank - savings and deposit account", "01-02-06-0013", dict(description="Sample")),
    ("01-02-07-0010", "Funds in transit between bank accounts", "NEW", dict(control="CLEARING", zero=True, description="Inter-bank transfers in transit; must be nil at period end")),
    # ---- 02-01 Non-current liabilities
    ("02-01-01-0001", "Long-term loans from banks", "02-01-01-0001", {}),
    ("02-01-01-0002", "Loans from directors and sponsors", "02-01-01-0002", {}),
    ("02-01-02-0001", "Lease liabilities - cinema premises", "02-01-02-0001", {}),
    ("02-01-02-0002", "Lease liabilities - vehicles", "02-01-02-0002", dict(site="OPT", cc="BS")),
    ("02-01-03-0001", "Staff gratuity obligation", "02-01-03-0001", {}),
    ("02-01-03-0002", "Deferred taxation - net", "02-01-03-0002", dict(cf="OP_TAX_PAID")),
    ("02-01-04-0001", "Security deposits received", "02-01-04-0001", dict(party="CUSTOMER", party_rule="OPT")),
    # ---- 02-02-01 Payables (AP control)
    ("02-02-01-0001", "Film distributors payable", "NEW", dict(description="Distributor share (film rental) due under distribution agreements")),
    ("02-02-01-0002", "Trade creditors - F&B suppliers", "NEW", {}),
    ("02-02-01-0003", "Trade creditors - landlords (rent and CAM)", "02-02-01-0008", {}),
    ("02-02-01-0004", "Trade creditors - utilities and telecom", "02-02-01-0009", {}),
    ("02-02-01-0005", "Trade creditors - maintenance and technical services", "02-02-01-0011", {}),
    ("02-02-01-0006", "Trade creditors - marketing, media and agencies", "02-02-01-0006", {}),
    ("02-02-01-0007", "Trade creditors - IT, software and ticketing systems", "02-02-01-0010", {}),
    ("02-02-01-0008", "Trade creditors - capital and fit-out contractors", "02-02-01-0012", {}),
    ("02-02-01-0009", "Trade creditors - professional services", "02-02-01-0013", {}),
    ("02-02-01-0010", "Trade creditors - general services and supplies", "02-02-01-0011", {}),
    ("02-02-01-0011", "Trade creditors - imports", "02-02-01-0014", {}),
    ("02-02-01-0012", "AP clearing - goods and services received not invoiced", "02-02-01-0015", dict(control="CLEARING", party_rule="OPT")),
    # ---- 02-02-02 Accrued
    ("02-02-02-0001", "Salaries and wages payable", "02-02-02-0001", dict(party="EMPLOYEE", party_rule="OPT")),
    ("02-02-02-0002", "Bonus payable", "02-02-02-0004", dict(party="EMPLOYEE", party_rule="OPT")),
    ("02-02-02-0003", "Final settlements payable", "02-02-02-0005", dict(party="EMPLOYEE", party_rule="OPT")),
    ("02-02-02-0004", "EOBI payable", "02-02-02-0006", {}),
    ("02-02-02-0005", "Social security payable (PESSI / SESSI)", "02-02-02-0007", {}),
    ("02-02-02-0006", "Accrued film rental", "NEW", dict(site="REQ", cc="LOC", recon=True, description="Distributor share accrued at day close; cleared by the distributor settlement invoice")),
    ("02-02-02-0007", "Accrued utilities", "02-02-02-0009", dict(site="REQ", cc="LOC")),
    ("02-02-02-0008", "Accrued rent and CAM", "02-02-02-0010", dict(site="REQ", cc="LOC", party="SUPPLIER", party_rule="OPT")),
    ("02-02-02-0009", "Accrued audit and professional fees", "02-02-02-0011", {}),
    ("02-02-02-0010", "Accrued expenses - others", "02-02-02-0012", {}),
    ("02-02-02-0011", "Accrued markup on borrowings", "02-02-02-0013", dict(cf="FIN_FINANCE_COST")),
    ("02-02-02-0012", "Advance ticket sales - shows not yet screened", "02-02-02-0014", dict(site="REQ", cc="LOC", description="Deferred revenue: tickets sold for future show dates")),
    ("02-02-02-0013", "Gift cards, vouchers and loyalty liability", "02-02-02-0015", {}),
    ("02-02-02-0014", "Customer advances - bookings, events and advertising", "02-02-02-0014", dict(control="AR_CONTROL", party="CUSTOMER", party_rule="REQ", recon=True)),
    ("02-02-02-0015", "Unidentified receipts", "02-02-02-0017", dict(recon=True)),
    ("02-02-02-0016", "Due to group companies (intercompany)", "02-02-02-0018", dict(ic=True, recon=True, cf="OP_RELATED")),
    ("02-02-02-0017", "Workers' Profit Participation Fund payable", "02-02-02-0019", {}),
    ("02-02-02-0018", "Workers' Welfare Fund payable", "02-02-02-0020", {}),
    ("02-02-02-0019", "Retention money and contractor deposits", "02-02-02-0021", dict(party="SUPPLIER", party_rule="OPT")),
    ("02-02-02-0020", "Other payables", "02-02-02-0022", {}),
    ("02-02-02-0021", "Suspense account", "02-02-02-0023", dict(zero=True, recon=True, manual="RESTRICTED")),
    # ---- 02-02-03 Taxes payable
    ("02-02-03-0001", "Output sales tax payable - FBR", "02-02-03-0001", {}),
    ("02-02-03-0002", "Output sales tax on services payable - PRA", "NEW", dict(description="Provincial sales tax on F&B (restaurant) and advertising services")),
    ("02-02-03-0003", "Output sales tax on services payable - other provinces", "NEW", {}),
    ("02-02-03-0004", "Entertainment duty / tax on cinema tickets payable", "NEW", dict(description="Provincial levy on admissions where applicable; rate configured in Tax module (may be nil or exempt)")),
    ("02-02-03-0005", "Sales tax withheld payable - FBR", "02-02-03-0003", dict(party="SUPPLIER", party_rule="OPT")),
    ("02-02-03-0006", "Sales tax on services withheld payable - PRA", "02-02-03-0004", dict(party="SUPPLIER", party_rule="OPT")),
    ("02-02-03-0007", "Sales tax on services withheld payable - other provinces", "02-02-03-0005", dict(party="SUPPLIER", party_rule="OPT")),
    ("02-02-03-0008", "Income tax withheld - salaries (s.149)", "02-02-03-0007", dict(party="EMPLOYEE", party_rule="OPT")),
    ("02-02-03-0009", "Income tax withheld - rent (s.155)", "02-02-03-0008", dict(party="SUPPLIER", party_rule="OPT")),
    ("02-02-03-0010", "Income tax withheld - supply of goods (s.153(1)(a))", "02-02-03-0009", dict(party="SUPPLIER", party_rule="OPT")),
    ("02-02-03-0011", "Income tax withheld - services (s.153(1)(b))", "02-02-03-0010", dict(party="SUPPLIER", party_rule="OPT")),
    ("02-02-03-0012", "Income tax withheld - contracts (s.153(1)(c))", "02-02-03-0011", dict(party="SUPPLIER", party_rule="OPT")),
    ("02-02-03-0013", "Income tax withheld - non-residents (s.152)", "NEW", dict(party="SUPPLIER", party_rule="OPT", description="Royalties / film rights paid to foreign distributors")),
    ("02-02-03-0014", "Income tax withheld - other sections", "02-02-03-0012", dict(party="SUPPLIER", party_rule="OPT")),
    ("02-02-03-0015", "Provision for taxation", "02-02-03-0013", dict(cf="OP_TAX_PAID", manual="RESTRICTED")),
    # ---- 02-02-04 Short-term borrowings
    ("02-02-04-0001", "Running finance and short-term borrowings", "02-02-04-0001", {}),
    ("02-02-04-0002", "Current portion of long-term financing", "NEW", dict(cf="FIN_BORROWINGS")),
    # ---- 03 Equity
    ("03-01-01-0001", "Issued, subscribed and paid-up share capital", "03-01-01-0001", {}),
    ("03-01-01-0002", "Share deposit money", "03-01-01-0002", dict(control="NONE")),
    ("03-01-02-0001", "Unappropriated profit / (accumulated loss)", "03-01-02-0001", dict(description="Year-end close and opening balance only (no manual journals)")),
    ("03-01-02-0002", "Dividends and distributions", "NEW", dict(manual="RESTRICTED", description="Dividends declared in the year; closed to unappropriated profit at year end")),
    ("03-01-03-0001", "Opening balance clearing", "NEW", dict(description="Contra for migrated opening balances (GL, AP, AR, bank, assets); must net to nil after cut-over")),
    # ---- 04 Revenue
    ("04-01-01-0001", "Ticket sales - box office counter", "04-01-01-0001", {}),
    ("04-01-01-0002", "Ticket sales - online (website and app)", "04-01-01-0002", {}),
    ("04-01-01-0003", "Ticket sales - third-party platforms", "04-01-01-0003", {}),
    ("04-01-01-0004", "Ticket sales - corporate and group bookings", "04-01-01-0005", {}),
    ("04-01-01-0005", "Booking and convenience fees", "04-01-01-0006", {}),
    ("04-01-02-0001", "Ticket discounts and promotions", "04-01-02-0003", C),
    ("04-01-02-0002", "Ticket refunds and cancellations", "04-01-02-0001", C),
    ("04-02-01-0001", "Food sales", "NEW", {}),
    ("04-02-01-0002", "Beverage sales", "NEW", {}),
    ("04-02-01-0003", "Combo and meal-deal sales", "NEW", {}),
    ("04-02-01-0004", "Cafe and restaurant sales", "NEW", {}),
    ("04-02-01-0005", "Other F&B revenue (event catering)", "NEW", {}),
    ("04-02-02-0001", "F&B discounts and promotions", "04-01-02-0003", C),
    ("04-02-02-0002", "F&B refunds and voids", "04-01-02-0001", C),
    ("04-03-01-0001", "Screen advertising (on-screen and pre-show)", "NEW", {}),
    ("04-03-01-0002", "Lobby and ambient advertising", "NEW", {}),
    ("04-03-01-0003", "Sponsorship and promotional income", "NEW", {}),
    ("04-03-01-0004", "Other advertising income", "NEW", {}),
    ("04-04-01-0001", "Private screenings and event hire", "NEW", {}),
    ("04-04-01-0002", "Auditorium and venue rental", "NEW", {}),
    ("04-04-01-0003", "Gift card and voucher breakage income", "04-01-01-0007", {}),
    ("04-04-01-0004", "Merchandise sales", "NEW", {}),
    ("04-04-01-0005", "Parking and other site income", "NEW", {}),
    ("04-04-01-0006", "Management fee income - group companies", "NEW", dict(ic=True)),
    # ---- 05 Cost of sales
    ("05-01-01-0001", "Film rental - distributor share", "NEW", dict(description="Distributor share of net box office per the distribution agreement")),
    ("05-01-01-0002", "Film rental - minimum guarantee shortfall and adjustments", "NEW", {}),
    ("05-01-01-0003", "Virtual print fees, DCP and KDM delivery", "NEW", {}),
    ("05-01-01-0004", "Film licensing, censor and certification fees", "NEW", {}),
    ("05-02-01-0001", "Cost of food consumed", "NEW", {}),
    ("05-02-01-0002", "Cost of beverages consumed", "NEW", {}),
    ("05-02-01-0003", "Cost of packaged snacks and confectionery sold", "NEW", {}),
    ("05-02-01-0004", "F&B packaging and disposables consumed", "NEW", {}),
    ("05-02-01-0005", "F&B wastage and spoilage", "05-04-01-0005", {}),
    ("05-02-01-0006", "F&B inventory count differences", "05-04-01-0003", {}),
    ("05-03-01-0001", "Advertising revenue share and agency commission", "06-04-04-0004", dict(stream="ADVERTISING")),
    ("05-03-01-0002", "Third-party ticketing platform commission", "06-04-04-0003", dict(stream="TICKETING")),
    ("05-03-01-0003", "Merchandise cost of sales", "05-04-01-0001", dict(stream="OTHER")),
    ("05-03-01-0004", "Event and private screening direct costs", "NEW", dict(stream="OTHER")),
    # ---- 06-01 Employee
    ("06-01-01-0001", "Salaries and allowances", "06-01-01-0001", {}),
    ("06-01-01-0002", "Overtime", "06-01-01-0002", {}),
    ("06-01-01-0003", "Bonus and Eid bonus", "06-01-01-0003", {}),
    ("06-01-01-0004", "Directors' remuneration", "06-01-01-0004", {}),
    ("06-01-01-0005", "Final settlements and leave encashment", "06-01-01-0005", {}),
    ("06-01-01-0006", "Contract and part-time staff (ushers, crew)", "NEW", {}),
    ("06-01-01-0007", "Staff commissions and incentives", "06-01-01-0007", {}),
    ("06-01-02-0001", "Gratuity expense", "06-01-02-0001", {}),
    ("06-01-02-0002", "EOBI - employer contribution", "06-01-02-0002", {}),
    ("06-01-02-0003", "Social security - employer contribution", "06-01-02-0003", {}),
    ("06-01-03-0001", "Staff meals and refreshments", "06-01-03-0001", {}),
    ("06-01-03-0002", "Staff uniforms", "NEW", {}),
    ("06-01-03-0003", "Medical and health", "06-01-03-0003", {}),
    ("06-01-03-0004", "Staff welfare and events", "06-01-03-0002", {}),
    ("06-01-04-0001", "Recruitment and job advertising", "06-01-04-0001", {}),
    ("06-01-04-0002", "Training and development", "06-01-04-0002", {}),
    # ---- 06-02 Premises
    ("06-02-01-0001", "Rent - short-term and low-value leases", "06-02-01-0001", {}),
    ("06-02-01-0002", "Variable rent (revenue share)", "06-02-01-0002", {}),
    ("06-02-01-0003", "CAM and service charges", "06-02-01-0003", {}),
    ("06-02-01-0004", "Property tax and rates", "06-02-01-0004", {}),
    ("06-02-02-0001", "Electricity", "06-02-02-0001", {}),
    ("06-02-02-0002", "Gas", "06-02-02-0002", {}),
    ("06-02-02-0003", "Generator fuel", "06-02-02-0004", {}),
    ("06-02-02-0004", "Water and sanitation", "06-02-02-0005", {}),
    ("06-02-03-0001", "Repairs and maintenance - premises", "06-02-03-0001", {}),
    ("06-02-03-0002", "Cleaning and housekeeping", "06-02-03-0002", {}),
    ("06-02-03-0003", "Security services", "06-02-03-0003", {}),
    ("06-02-03-0004", "Pest control and fumigation", "NEW", {}),
    # ---- 06-03 R&M equipment
    ("06-03-01-0001", "Projection and sound equipment maintenance", "NEW", {}),
    ("06-03-01-0002", "HVAC and generator maintenance", "06-03-01-0002", {}),
    ("06-03-01-0003", "Kitchen and F&B equipment repairs", "06-03-01-0003", {}),
    ("06-03-01-0004", "IT and POS hardware repairs", "06-07-02-0002", {}),
    ("06-03-01-0005", "Small tools and low-value equipment", "06-03-01-0004", {}),
    ("06-03-01-0006", "Annual maintenance contracts", "NEW", {}),
    # ---- 06-04 Selling and marketing
    ("06-04-01-0001", "Digital advertising", "06-04-01-0001", {}),
    ("06-04-01-0002", "Print, outdoor and in-mall advertising", "06-04-01-0002", {}),
    ("06-04-01-0003", "Film promotions, premieres and launches", "06-04-02-0003", {}),
    ("06-04-01-0004", "SMS, CRM and loyalty marketing", "06-04-01-0004", {}),
    ("06-04-01-0005", "Influencers and PR", "06-04-01-0005", {}),
    ("06-04-02-0001", "Card and payment gateway charges", "06-04-04-0002", {}),
    ("06-04-02-0002", "Mobile wallet charges", "NEW", {}),
    ("06-04-02-0003", "Cash handling and cash-in-transit services", "06-04-04-0008", {}),
    ("06-04-02-0004", "Cash over / (short) - box office and F&B", "NEW", dict(description="Day-close cash differences")),
    ("06-04-02-0005", "Ticket stock and printing", "NEW", {}),
    # ---- 06-05 Travel
    ("06-05-01-0001", "Local travel and conveyance", "06-06-01-0001", {}),
    ("06-05-01-0002", "Domestic travel - air, rail and lodging", "06-06-01-0002", {}),
    ("06-05-01-0003", "Foreign travel", "06-06-01-0003", {}),
    ("06-05-02-0001", "Vehicle fuel", "06-06-02-0001", {}),
    ("06-05-02-0002", "Vehicle repairs and maintenance", "06-06-02-0002", {}),
    ("06-05-02-0003", "Vehicle token tax, registration and tracking", "06-06-02-0003", {}),
    # ---- 06-06 Admin
    ("06-06-01-0001", "Telephone and internet", "06-07-01-0001", {}),
    ("06-06-01-0002", "Mobile phones", "06-07-01-0002", {}),
    ("06-06-01-0003", "Postage and courier", "06-07-01-0004", {}),
    ("06-06-02-0001", "Printing and stationery", "06-07-02-0001", {}),
    ("06-06-02-0002", "Computer consumables", "06-07-02-0002", {}),
    ("06-06-03-0001", "Software subscriptions and licences", "06-07-03-0001", {}),
    ("06-06-03-0002", "Ticketing and POS system charges", "06-07-03-0003", {}),
    ("06-06-03-0003", "IT support and outsourced IT services", "06-07-03-0002", {}),
    ("06-06-03-0004", "FBR / PRA POS integration charges", "06-07-03-0003", {}),
    ("06-06-04-0001", "Statutory audit fee", "06-07-04-0001", {}),
    ("06-06-04-0002", "Internal audit and advisory", "06-07-04-0002", {}),
    ("06-06-04-0003", "Legal fees", "06-07-04-0003", {}),
    ("06-06-04-0004", "Tax advisory and compliance fees", "06-07-04-0004", {}),
    ("06-06-04-0005", "Other professional and consultancy fees", "06-07-04-0006", {}),
    ("06-06-05-0001", "Cinema licences, permits and NOCs", "NEW", {}),
    ("06-06-05-0002", "Memberships and subscriptions", "06-07-05-0001", {}),
    ("06-06-05-0003", "Government fees and stamp duty", "06-07-05-0002", {}),
    ("06-06-05-0004", "Insurance - property and equipment", "06-07-05-0003", {}),
    ("06-06-05-0005", "Insurance - vehicles", "06-07-05-0004", {}),
    ("06-06-05-0006", "Insurance - public liability and other", "06-07-05-0005", {}),
    ("06-06-06-0001", "Business entertainment", "06-07-06-0001", {}),
    ("06-06-06-0002", "Donations and sponsorships", "06-07-06-0002", dict(cc="CORP", site="OPT")),
    ("06-06-06-0003", "Miscellaneous expenses", "06-07-06-0003", {}),
    ("06-06-06-0004", "Management fee - group companies", "NEW", dict(ic=True)),
    # ---- 06-07 D&A
    ("06-07-01-0001", "Depreciation - buildings", "06-09-01-0001", {}),
    ("06-07-01-0002", "Depreciation - leasehold improvements and fit-out", "06-09-01-0002", {}),
    ("06-07-01-0003", "Depreciation - projection equipment", "NEW", {}),
    ("06-07-01-0004", "Depreciation - sound and audio systems", "NEW", {}),
    ("06-07-01-0005", "Depreciation - seating and auditorium fixtures", "NEW", {}),
    ("06-07-01-0006", "Depreciation - kitchen and F&B equipment", "NEW", {}),
    ("06-07-01-0007", "Depreciation - electrical, HVAC and generators", "06-09-01-0004", {}),
    ("06-07-01-0008", "Depreciation - furniture and office equipment", "06-09-01-0005", {}),
    ("06-07-01-0009", "Depreciation - computers, POS and IT equipment", "06-09-01-0006", {}),
    ("06-07-01-0010", "Depreciation - vehicles", "06-09-01-0007", {}),
    ("06-07-02-0001", "Depreciation - right-of-use premises", "06-09-02-0001", {}),
    ("06-07-02-0002", "Depreciation - right-of-use vehicles", "06-09-02-0002", {}),
    ("06-07-03-0001", "Amortisation - intangible assets", "06-09-03-0001", {}),
    ("06-07-03-0002", "Impairment losses", "06-09-03-0002", dict(cf_counter="INV_PPE")),
    # ---- 07 Other income / expenses
    ("07-01-01-0001", "Profit on bank deposits", "07-01-01-0001", {}),
    ("07-01-01-0002", "Income from mutual funds and T-bills", "07-01-01-0002", {}),
    ("07-01-02-0001", "Gain on disposal of fixed assets", "07-01-02-0001", dict(cf_adj="ADJ_DISPOSAL", cf_counter="INV_PPE")),
    ("07-01-02-0002", "Scrap sales", "07-01-02-0002", dict(cc="REQ", site="REQ")),
    ("07-01-02-0003", "Insurance claim income", "07-01-02-0003", {}),
    ("07-01-02-0004", "Exchange gain", "07-01-02-0004", {}),
    ("07-01-02-0005", "Liabilities written back and other income", "07-01-02-0005", {}),
    ("07-02-01-0001", "Loss on disposal and write-off of fixed assets", "07-02-01-0001", dict(cf_adj="ADJ_DISPOSAL", cf_counter="INV_PPE")),
    ("07-02-01-0002", "Exchange loss", "07-02-01-0002", {}),
    ("07-02-01-0003", "Expected credit losses and bad debts", "07-02-01-0004", {}),
    ("07-02-01-0004", "Workers' Profit Participation Fund", "07-02-01-0005", {}),
    ("07-02-01-0005", "Workers' Welfare Fund", "07-02-01-0006", {}),
    # ---- 08
    ("08-01-01-0001", "Markup / profit on borrowings", "08-01-01-0001", dict(cf_adj="ADJ_FINANCE", cf_counter="FIN_FINANCE_COST")),
    ("08-01-01-0002", "Interest on lease liabilities", "08-01-01-0002", dict(cf_adj="ADJ_FINANCE", cf_counter="FIN_LEASE", cc="REQ", site="REQ")),
    ("08-01-01-0003", "Bank charges and commission", "08-01-01-0003", {}),
    ("08-01-01-0004", "Guarantee and facility charges", "08-01-01-0004", {}),
    ("08-02-01-0001", "Current tax", "08-02-01-0001", {}),
    ("08-02-01-0002", "Prior year tax", "08-02-01-0002", {}),
    ("08-02-01-0003", "Deferred tax", "08-02-01-0003", {}),
    ("08-02-01-0004", "Levies - minimum and final taxes", "08-02-01-0004", {}),
]

# Cash flow line catalogue: code -> (section, label, order)
CASH_FLOW_LINES: dict[str, tuple[str, str, int]] = {
    "PBT": ("OPERATING", "Profit / (loss) before taxation", 10),
    "ADJ_DA": ("OPERATING", "Depreciation, amortisation and impairment", 20),
    "ADJ_DISPOSAL": ("OPERATING", "(Gain) / loss on disposal of fixed assets", 21),
    "ADJ_FINANCE": ("OPERATING", "Finance costs", 22),
    "OP_RECEIVABLES": ("OPERATING", "(Increase) / decrease in trade receivables", 30),
    "OP_INVENTORY": ("OPERATING", "(Increase) / decrease in inventories", 31),
    "OP_ADVANCES": ("OPERATING", "(Increase) / decrease in advances, deposits and prepayments", 32),
    "OP_TAXES": ("OPERATING", "Increase / (decrease) in sales tax and withholding tax balances", 33),
    "OP_RELATED": ("OPERATING", "Net movement in related party balances", 34),
    "OP_PAYABLES": ("OPERATING", "Increase / (decrease) in trade and other payables", 35),
    "OP_ACCRUALS": ("OPERATING", "Increase / (decrease) in accrued and other liabilities", 36),
    "OP_PROVISIONS": ("OPERATING", "Increase / (decrease) in gratuity and other provisions", 37),
    "OP_TAX_PAID": ("OPERATING", "Income tax paid", 40),
    "INV_PPE": ("INVESTING", "Capital expenditure on property, plant and equipment (net of disposals)", 50),
    "INV_INTANGIBLES": ("INVESTING", "Investment in intangible assets", 51),
    "INV_DEPOSITS": ("INVESTING", "Long-term deposits (net)", 52),
    "INV_INVESTMENTS": ("INVESTING", "Investments (net)", 53),
    "FIN_BORROWINGS": ("FINANCING", "Long-term financing (net)", 60),
    "FIN_SHORT_TERM": ("FINANCING", "Short-term borrowings (net)", 61),
    "FIN_LEASE": ("FINANCING", "Lease rentals paid", 62),
    "FIN_FINANCE_COST": ("FINANCING", "Finance costs paid", 63),
    "FIN_EQUITY": ("FINANCING", "Share capital, share deposit money and dividends", 64),
    "CASH": ("CASH", "Cash and cash equivalents", 90),
    "EXCLUDED": ("EXCLUDED", "Excluded from cash flow (migration clearing)", 99),
}

PL_SECTIONS = ["REVENUE", "COST_OF_SALES", "OPEX", "DEPRECIATION", "OTHER_INCOME",
               "OTHER_EXPENSE", "FINANCE_COST", "TAXATION"]


def _account_type(code: str) -> str:
    cls = code[:2]
    if cls == "01":
        return "ASSET"
    if cls == "02":
        return "LIABILITY"
    if cls == "03":
        return "EQUITY"
    if cls == "04" or code.startswith("07-01"):
        return "INCOME"
    return "EXPENSE"


def _normal(atype: str, contra: bool) -> str:
    base = "D" if atype in ("ASSET", "EXPENSE") else "C"
    if contra:
        return "C" if base == "D" else "D"
    return base


def build_chart() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code, name in CLASSES.items():
        rows.append(dict(code=code, name=name, level=1, parent_code=None,
                         account_type=_account_type(code if code != "07" else "07-02"),
                         is_postable=False))
    for code, name in GROUPS.items():
        rows.append(dict(code=code, name=name, level=2, parent_code=code[:2],
                         account_type=_account_type(code), is_postable=False))
    for code, (name, _d) in SUBGROUPS.items():
        rows.append(dict(code=code, name=name, level=3, parent_code=code[:5],
                         account_type=_account_type(code), is_postable=False))
    seen: set[str] = set()
    for code, name, gen_ref, ov in LEDGERS:
        if code in seen:
            raise ValueError(f"duplicate account code {code}")
        seen.add(code)
        parent = code[:8]
        d = dict(SUBGROUPS[parent][1])
        d.update(ov)
        atype = _account_type(code)
        contra = bool(d.get("contra"))
        control = d.get("control", "NONE")
        party = d.get("party", "NONE")
        party_rule = d.get("party_rule", "NONE" if party == "NONE" else "OPT")
        rows.append(dict(
            code=code, name=name, level=4, parent_code=parent,
            account_type=atype, is_postable=True,
            normal_balance=_normal(atype, contra), is_contra=contra,
            control_type=control, party_type=party, party_rule=party_rule,
            site_rule=d.get("site", "OPT"), cost_centre_rule=d.get("cc", "BS"),
            pl_section=d.get("pl"), revenue_stream=d.get("stream"),
            cash_flow_line=d.get("cf"), cf_adjustment=d.get("cf_adj"),
            cf_counter_line=d.get("cf_counter"),
            manual_journal=d.get("manual", "ALLOWED"),
            abnormal_balance=d.get("abnormal", "ALERT" if not contra else "ALLOW"),
            reconcile_required=bool(d.get("recon", False)),
            budget_control=d.get("budget", "NONE"),
            is_intercompany=bool(d.get("ic", False)),
            zero_at_period_end=bool(d.get("zero", False)),
            gen_ref=gen_ref, description=d.get("description", ""),
        ))
    return rows


if __name__ == "__main__":  # pragma: no cover
    chart = build_chart()
    print(len([r for r in chart if r["level"] == 4]), "ledgers")
