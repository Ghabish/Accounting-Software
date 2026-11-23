"""Reference data for Universal Cinemas (sites, cost centres, tax, categories, mappings).

Everything here is configuration, maintained afterwards through the UI / API.
Items marked ``needs_confirmation`` must be confirmed by Finance / the tax advisor.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal as Dec

TAX_EFFECTIVE = date(2026, 7, 1)  # tax year 2027 (Finance Act 2026) per the reference workbook

COMPANY = dict(code="01", name="Universal Cinemas", legal_name="NC Entertainment (Pvt) Ltd (to confirm)",
               base_currency="PKR", fiscal_year_start_month=7)

SITES = [
    # code, name, type, city, province, authority, pos_code
    ("001", "Head Office", "HEAD_OFFICE", "Lahore", "Punjab", "PRA", None),
    ("101", "Emporium Lahore", "CINEMA", "Lahore", "Punjab", "PRA", "EMP"),
    ("102", "Buch Villas", "CINEMA", "Multan", "Punjab", "PRA", "BUCH"),
    ("103", "The Grand Multan", "CINEMA", "Multan", "Punjab", "PRA", "GRAND"),
]

# code, name, section_code, section_name, function, budget_owner
COST_CENTRES = [
    ("000000", "Balance sheet - no cost centre", "00", "COMPANY", "NOT_PL", "CFO"),
    ("010101", "Cinema Operations - General", "01", "CINEMA OPERATIONS", "SITE_OPERATIONS", "Cinema Manager"),
    ("010201", "Ticketing / Box Office", "01", "CINEMA OPERATIONS", "SITE_OPERATIONS", "Cinema Manager"),
    ("010301", "Projection & Screen Operations", "01", "CINEMA OPERATIONS", "SITE_OPERATIONS", "Technical Manager"),
    ("010401", "Front of House & Ushering", "01", "CINEMA OPERATIONS", "SITE_OPERATIONS", "Cinema Manager"),
    ("020101", "F&B - Concessions Counter", "02", "FOOD & BEVERAGE", "SITE_OPERATIONS", "F&B Manager"),
    ("020102", "F&B - Cafe / Restaurant", "02", "FOOD & BEVERAGE", "SITE_OPERATIONS", "F&B Manager"),
    ("020201", "F&B - Kitchen & Stores", "02", "FOOD & BEVERAGE", "SITE_OPERATIONS", "F&B Manager"),
    ("030101", "Screen Advertising", "03", "ADVERTISING & SPONSORSHIP", "SITE_OPERATIONS", "Head of Advertising Sales"),
    ("030102", "Lobby & Ambient Advertising", "03", "ADVERTISING & SPONSORSHIP", "SITE_OPERATIONS", "Head of Advertising Sales"),
    ("030201", "Sponsorship & Promotions", "03", "ADVERTISING & SPONSORSHIP", "SITE_OPERATIONS", "Head of Advertising Sales"),
    ("040101", "Marketing & Brand", "04", "MARKETING & CONTENT", "HEAD_OFFICE", "Head of Marketing"),
    ("040102", "Digital & Online Sales", "04", "MARKETING & CONTENT", "HEAD_OFFICE", "Head of Marketing"),
    ("040201", "Film Programming & Distribution", "04", "MARKETING & CONTENT", "HEAD_OFFICE", "Head of Programming"),
    ("040202", "Production / Content", "04", "MARKETING & CONTENT", "HEAD_OFFICE", "Head of Content"),
    ("050101", "Maintenance - Building & MEP", "05", "FACILITIES", "SITE_OPERATIONS", "Facilities Manager"),
    ("050102", "Maintenance - Projection & Sound", "05", "FACILITIES", "SITE_OPERATIONS", "Technical Manager"),
    ("050201", "Security", "05", "FACILITIES", "SITE_OPERATIONS", "Facilities Manager"),
    ("050301", "Housekeeping", "05", "FACILITIES", "SITE_OPERATIONS", "Facilities Manager"),
    ("060101", "CEO Office / Directors", "06", "CORPORATE SERVICES", "HEAD_OFFICE", "CEO"),
    ("060201", "Finance & Accounts", "06", "CORPORATE SERVICES", "HEAD_OFFICE", "CFO"),
    ("060301", "Human Resources", "06", "CORPORATE SERVICES", "HEAD_OFFICE", "Head of HR"),
    ("060401", "Information Technology", "06", "CORPORATE SERVICES", "HEAD_OFFICE", "Head of IT"),
    ("060501", "Administration", "06", "CORPORATE SERVICES", "HEAD_OFFICE", "Admin Manager"),
    ("060601", "Legal & Compliance", "06", "CORPORATE SERVICES", "HEAD_OFFICE", "Company Secretary"),
    ("060701", "Internal Audit", "06", "CORPORATE SERVICES", "HEAD_OFFICE", "Head of Internal Audit"),
    ("090101", "Corporate - company level", "09", "COMPANY LEVEL", "COMPANY_LEVEL", "CFO"),
]

DIMENSION_TYPES = [
    ("SCREEN", "Screen / Hall", True), ("FILM", "Film", True), ("DISTRIBUTOR", "Distributor", True),
    ("CAMPAIGN", "Marketing campaign", False), ("PROJECT", "Project", False), ("DEPARTMENT", "Department", False),
    ("BUSINESS_LINE", "Business line", False), ("PRODUCT", "Product", False),
]

# --------------------------------------------------------------------- tax
# code, name, type, authority, section, base, account, recoverable, needs_conf, notes
TAX_CODES = [
    ("ST-OUT-18", "Output sales tax 18% (goods) - FBR", "SALES_TAX_OUTPUT", "FBR", "STA 1990 s.3", "NET_AMOUNT", "02-02-03-0001", True, False, "Merchandise and goods sold"),
    ("PST-OUT-FNB", "PRA sales tax on F&B / restaurant services", "PST_OUTPUT", "PRA", "Punjab Sales Tax on Services Act 2012", "NET_AMOUNT", "02-02-03-0002", True, True, "Confirm standard vs reduced (card payment) rate for cinema F&B"),
    ("PST-OUT-ADV", "PRA sales tax on advertising services", "PST_OUTPUT", "PRA", "Punjab Sales Tax on Services Act 2012", "NET_AMOUNT", "02-02-03-0002", True, True, "Advertising and sponsorship invoices"),
    ("ENT-TKT-PB", "Entertainment duty / tax on cinema admissions - Punjab", "ENTERTAINMENT_DUTY", "PRA", "Provincial levy on admissions", "NET_AMOUNT", "02-02-03-0004", True, True, "Seeded at 0% - tax advisor to confirm current treatment of cinema tickets"),
    ("ST-IN-18", "Input sales tax 18% - FBR (adjustable)", "SALES_TAX_INPUT", "FBR", "STA 1990 s.3", "NET_AMOUNT", "01-02-05-0007", True, False, None),
    ("ST-IN-INAD", "Sales tax 18% - inadmissible (not adjustable)", "SALES_TAX_INPUT", "FBR", "STA 1990 s.8 / s.73", "NET_AMOUNT", "01-02-05-0007", False, False, "Charged to the expense line, not input tax"),
    ("ST-IN-EXEMPT", "Sales tax 0% - exempt / unregistered supplier", "SALES_TAX_INPUT", "FBR", "STA 1990", "NET_AMOUNT", "01-02-05-0007", True, False, None),
    ("PST-IN-PRA", "Input PST 16% - PRA", "PST_INPUT", "PRA", "Punjab Sales Tax on Services Act 2012", "NET_AMOUNT", "01-02-05-0008", True, False, None),
    ("PST-IN-TEL", "Input PST 19.5% telecom - PRA", "PST_INPUT", "PRA", "Punjab Sales Tax on Services Act 2012", "NET_AMOUNT", "01-02-05-0008", True, False, None),
    ("PST-IN-SRB", "Input PST 15% - SRB", "PST_INPUT", "SRB", "Sindh Sales Tax on Services Act 2011", "NET_AMOUNT", "01-02-05-0009", True, False, None),
    ("WHT-153A", "WHT supply of goods s.153(1)(a)", "WHT_DEDUCTED", "FBR", "ITO 2001 s.153(1)(a)", "NET_AMOUNT", "02-02-03-0010", True, False, None),
    ("WHT-153B-S", "WHT specified services s.153(1)(b)", "WHT_DEDUCTED", "FBR", "ITO 2001 s.153(1)(b)", "NET_AMOUNT", "02-02-03-0011", True, False, "Transport, security, advertising (non-media) and other specified services"),
    ("WHT-153B", "WHT other services s.153(1)(b)", "WHT_DEDUCTED", "FBR", "ITO 2001 s.153(1)(b)", "NET_AMOUNT", "02-02-03-0011", True, False, None),
    ("WHT-153B-IT", "WHT IT services s.153(1)(b)", "WHT_DEDUCTED", "FBR", "ITO 2001 s.153(1)(b)", "NET_AMOUNT", "02-02-03-0011", True, False, None),
    ("WHT-153B-P", "WHT professional services s.153(1)(b)", "WHT_DEDUCTED", "FBR", "ITO 2001 s.153(1)(b)", "NET_AMOUNT", "02-02-03-0011", True, False, None),
    ("WHT-153B-M", "WHT media advertising s.153(1)(b)", "WHT_DEDUCTED", "FBR", "ITO 2001 s.153(1)(b)", "NET_AMOUNT", "02-02-03-0011", True, False, None),
    ("WHT-153C", "WHT contracts s.153(1)(c)", "WHT_DEDUCTED", "FBR", "ITO 2001 s.153(1)(c)", "NET_AMOUNT", "02-02-03-0012", True, False, None),
    ("WHT-155", "WHT rent of immovable property s.155", "WHT_DEDUCTED", "FBR", "ITO 2001 s.155", "GROSS_AMOUNT", "02-02-03-0009", True, False, "Individuals / AOPs on the annual slab"),
    ("WHT-152", "WHT non-resident royalties / film rights s.152", "WHT_DEDUCTED", "FBR", "ITO 2001 s.152(1)", "GROSS_AMOUNT", "02-02-03-0013", True, True, "Confirm treatment of payments to foreign film distributors (treaty rates)"),
    ("WHT-233", "WHT commission s.233", "WHT_DEDUCTED", "FBR", "ITO 2001 s.233", "NET_AMOUNT", "02-02-03-0014", True, False, None),
    ("WHT-FILM", "WHT local film distributors", "WHT_DEDUCTED", "FBR", "ITO 2001 s.153(1)(b) (to confirm)", "NET_AMOUNT", "02-02-03-0011", True, True, "Rate for local distributors' share to be confirmed by tax advisor"),
    ("WHT-149", "WHT salaries s.149 (annual slab)", "WHT_DEDUCTED", "FBR", "ITO 2001 s.149", "GROSS_AMOUNT", "02-02-03-0008", True, False, "Computed per employee by payroll (future module)"),
    ("WHT-NIL", "WHT not applicable", "WHT_DEDUCTED", "FBR", None, "NET_AMOUNT", "02-02-03-0014", True, False, "Utilities, government fees"),
    ("STW-FBR", "Sales tax withholding - FBR (fraction of ST)", "ST_WITHHELD", "FBR", "STA 1990 Eleventh Schedule", "SALES_TAX_AMOUNT", "02-02-03-0005", True, False, None),
    ("STW-PRA", "Sales tax withholding - PRA (fraction of PST)", "ST_WITHHELD", "PRA", "Punjab ST on Services (Withholding) Rules", "SALES_TAX_AMOUNT", "02-02-03-0006", True, False, None),
    ("STW-NIL", "Sales tax withholding not applicable", "ST_WITHHELD", "FBR", None, "SALES_TAX_AMOUNT", "02-02-03-0005", True, False, None),
    ("WHT-SUFF-CUS", "Income tax deducted by customers", "WHT_SUFFERED", "FBR", "ITO 2001 s.153 (suffered)", "GROSS_AMOUNT", "01-02-05-0006", True, False, "Amount entered from the customer's certificate"),
    ("WHT-SUFF-STL", "Tax deducted by acquirers / gateways on settlement", "WHT_SUFFERED", "FBR", "ITO 2001 (suffered)", "GROSS_AMOUNT", "01-02-05-0006", True, True, None),
    ("ADV-235", "Advance tax on electricity bills s.235", "ADVANCE_TAX", "FBR", "ITO 2001 s.235", "GROSS_AMOUNT", "01-02-05-0002", True, False, "Amount as shown on the bill"),
]

# tax_code, rate name, payee_type, atl, rate
TAX_RATES = [
    ("ST-OUT-18", "ST 18% output", "ALL", "ALL", "0.18"),
    ("PST-OUT-FNB", "PST 16% PRA F&B", "ALL", "ALL", "0.16"),
    ("PST-OUT-ADV", "PST 16% PRA advertising", "ALL", "ALL", "0.16"),
    ("ENT-TKT-PB", "Entertainment duty 0% (to confirm)", "ALL", "ALL", "0"),
    ("ST-IN-18", "ST 18% goods purchase", "ALL", "ALL", "0.18"),
    ("ST-IN-INAD", "ST 18% inadmissible", "ALL", "ALL", "0.18"),
    ("ST-IN-EXEMPT", "ST 0% exempt", "ALL", "ALL", "0"),
    ("PST-IN-PRA", "PST 16% PRA", "ALL", "ALL", "0.16"),
    ("PST-IN-TEL", "PST 19.5% telecom PRA", "ALL", "ALL", "0.195"),
    ("PST-IN-SRB", "PST 15% SRB", "ALL", "ALL", "0.15"),
    ("WHT-153A", "WHT 5% Goods Company", "COMPANY", "ATL", "0.05"),
    ("WHT-153A", "WHT 10% Goods Company Non-ATL", "COMPANY", "NON_ATL", "0.10"),
    ("WHT-153A", "WHT 5.5% Goods Individual", "INDIVIDUAL", "ATL", "0.055"),
    ("WHT-153A", "WHT 11% Goods Individual Non-ATL", "INDIVIDUAL", "NON_ATL", "0.11"),
    ("WHT-153A", "WHT 5.5% Goods AOP", "AOP", "ATL", "0.055"),
    ("WHT-153A", "WHT 11% Goods AOP Non-ATL", "AOP", "NON_ATL", "0.11"),
    ("WHT-153B-S", "WHT 7% Specified Services", "ALL", "ATL", "0.07"),
    ("WHT-153B-S", "WHT 14% Specified Services Non-ATL", "ALL", "NON_ATL", "0.14"),
    ("WHT-153B", "WHT 14% Services", "ALL", "ATL", "0.14"),
    ("WHT-153B", "WHT 28% Services Non-ATL", "ALL", "NON_ATL", "0.28"),
    ("WHT-153B-IT", "WHT 4% IT Services", "ALL", "ATL", "0.04"),
    ("WHT-153B-IT", "WHT 8% IT Services Non-ATL", "ALL", "NON_ATL", "0.08"),
    ("WHT-153B-P", "WHT 15% Professional", "ALL", "ATL", "0.15"),
    ("WHT-153B-P", "WHT 30% Professional Non-ATL", "ALL", "NON_ATL", "0.30"),
    ("WHT-153B-M", "WHT 1.5% Media", "ALL", "ATL", "0.015"),
    ("WHT-153B-M", "WHT 3% Media Non-ATL", "ALL", "NON_ATL", "0.03"),
    ("WHT-153C", "WHT 7.5% Contracts Company", "COMPANY", "ATL", "0.075"),
    ("WHT-153C", "WHT 15% Contracts Company Non-ATL", "COMPANY", "NON_ATL", "0.15"),
    ("WHT-153C", "WHT 8% Contracts Individual", "INDIVIDUAL", "ATL", "0.08"),
    ("WHT-153C", "WHT 16% Contracts Individual Non-ATL", "INDIVIDUAL", "NON_ATL", "0.16"),
    ("WHT-153C", "WHT 8% Contracts AOP", "AOP", "ATL", "0.08"),
    ("WHT-153C", "WHT 16% Contracts AOP Non-ATL", "AOP", "NON_ATL", "0.16"),
    ("WHT-155", "WHT 15% Rent Company", "COMPANY", "ATL", "0.15"),
    ("WHT-155", "WHT 30% Rent Company Non-ATL", "COMPANY", "NON_ATL", "0.30"),
    ("WHT-152", "WHT 15% Non-Resident", "NON_RESIDENT", "ALL", "0.15"),
    ("WHT-233", "WHT 12% Commission", "ALL", "ATL", "0.12"),
    ("WHT-233", "WHT 24% Commission Non-ATL", "ALL", "NON_ATL", "0.24"),
    ("WHT-FILM", "WHT local distributor (to confirm)", "ALL", "ATL", "0.07"),
    ("WHT-FILM", "WHT local distributor Non-ATL (to confirm)", "ALL", "NON_ATL", "0.14"),
    ("WHT-NIL", "WHT 0% not applicable", "ALL", "ALL", "0"),
    ("STW-FBR", "STW 20% of ST (one-fifth)", "ALL", "ATL", "0.20"),
    ("STW-FBR", "STW 20% of ST", "ALL", "NON_ATL", "0.20"),
    ("STW-PRA", "STW 20% of PST (one-fifth)", "ALL", "ALL", "0.20"),
    ("STW-NIL", "STW 0% not applicable", "ALL", "ALL", "0"),
    ("WHT-SUFF-CUS", "Tax deducted by customer (entered)", "ALL", "ALL", "0"),
    ("WHT-SUFF-STL", "Tax deducted on settlement (entered)", "ALL", "ALL", "0"),
    ("ADV-235", "Advance tax electricity (as billed)", "ALL", "ALL", "0"),
]

# Rent slab s.155 individuals / AOPs (tax year 2027, from the reference workbook)
RENT_SLABS = [
    (Dec("0"), Dec("300000"), Dec("0"), Dec("0")),
    (Dec("300001"), Dec("600000"), Dec("0"), Dec("0.05")),
    (Dec("600001"), Dec("2000000"), Dec("15000"), Dec("0.10")),
    (Dec("2000001"), None, Dec("155000"), Dec("0.25")),
]

SALARY_SLABS = [
    (Dec("0"), Dec("600000"), Dec("0"), Dec("0")),
    (Dec("600001"), Dec("1200000"), Dec("0"), Dec("0.01")),
    (Dec("1200001"), Dec("2200000"), Dec("6000"), Dec("0.11")),
    (Dec("2200001"), Dec("3200000"), Dec("116000"), Dec("0.20")),
    (Dec("3200001"), Dec("4100000"), Dec("316000"), Dec("0.25")),
    (Dec("4100001"), Dec("5600000"), Dec("541000"), Dec("0.29")),
    (Dec("5600001"), Dec("7000000"), Dec("976000"), Dec("0.32")),
    (Dec("7000001"), None, Dec("1424000"), Dec("0.35")),
]

# --------------------------------------------------------------------- AP / AR categories
# code, name, AP control, advance, default expense, WHT, ST, STW
SUPPLIER_CATEGORIES = [
    ("DISTRIBUTOR", "Film distributors", "02-02-01-0001", "01-02-03-0005", "02-02-02-0006", "WHT-FILM", "ST-IN-EXEMPT", "STW-NIL"),
    ("FNB", "F&B suppliers", "02-02-01-0002", "01-02-03-0003", "01-02-01-0001", "WHT-153A", "ST-IN-18", "STW-FBR"),
    ("LANDLORD", "Landlords (rent and CAM)", "02-02-01-0003", "01-02-03-0004", "06-02-01-0003", "WHT-155", "PST-IN-PRA", "STW-PRA"),
    ("UTILITIES", "Utilities and telecom", "02-02-01-0004", "01-02-03-0004", "06-02-02-0001", "WHT-NIL", "ST-IN-18", "STW-NIL"),
    ("MAINTENANCE", "Maintenance and technical services", "02-02-01-0005", "01-02-03-0004", "06-03-01-0001", "WHT-153B", "PST-IN-PRA", "STW-PRA"),
    ("MARKETING", "Marketing, media and agencies", "02-02-01-0006", "01-02-03-0004", "06-04-01-0001", "WHT-153B-S", "PST-IN-PRA", "STW-PRA"),
    ("IT", "IT, software and ticketing systems", "02-02-01-0007", "01-02-03-0004", "06-06-03-0001", "WHT-153B-IT", "PST-IN-PRA", "STW-PRA"),
    ("CAPEX", "Capital and fit-out contractors", "02-02-01-0008", "01-01-02-0003", "01-01-02-0001", "WHT-153C", "ST-IN-18", "STW-FBR"),
    ("PROFESSIONAL", "Professional services", "02-02-01-0009", "01-02-03-0004", "06-06-04-0005", "WHT-153B-P", "PST-IN-PRA", "STW-PRA"),
    ("GENERAL", "General services and supplies", "02-02-01-0010", "01-02-03-0004", "06-06-06-0003", "WHT-153B", "PST-IN-PRA", "STW-PRA"),
    ("IMPORT", "Foreign suppliers", "02-02-01-0011", "01-02-03-0003", "01-02-01-0006", "WHT-152", "ST-IN-EXEMPT", "STW-NIL"),
]

# code, name, AR control, advance, default revenue, output tax
CUSTOMER_CATEGORIES = [
    ("ADVERTISING", "Advertising customers", "01-02-02-0006", "02-02-02-0014", "04-03-01-0001", "PST-OUT-ADV"),
    ("CORPORATE", "Corporate bookings and events", "01-02-02-0007", "02-02-02-0014", "04-01-01-0004", None),
    ("GATEWAY", "Payment gateways", "01-02-02-0003", None, None, None),
    ("WALLET", "Mobile wallets", "01-02-02-0004", None, None, None),
    ("PLATFORM", "Third-party ticketing platforms", "01-02-02-0005", None, None, None),
    ("OTHER", "Other customers", "01-02-02-0008", "02-02-02-0014", "04-04-01-0005", None),
]

# code, name, cost, accum dep, dep expense, life months
ASSET_CATEGORIES = [
    ("LAND", "Freehold land", "01-01-01-0001", None, None, 0),
    ("BLDG", "Buildings", "01-01-01-0002", "01-01-01-0003", "06-07-01-0001", 240),
    ("FITOUT", "Leasehold improvements and cinema fit-out", "01-01-01-0004", "01-01-01-0005", "06-07-01-0002", 120),
    ("PROJ", "Projection and digital cinema equipment", "01-01-01-0006", "01-01-01-0007", "06-07-01-0003", 84),
    ("SOUND", "Sound and audio systems", "01-01-01-0008", "01-01-01-0009", "06-07-01-0004", 84),
    ("SEAT", "Cinema seating and auditorium fixtures", "01-01-01-0010", "01-01-01-0011", "06-07-01-0005", 120),
    ("KITCHEN", "Kitchen and F&B equipment", "01-01-01-0012", "01-01-01-0013", "06-07-01-0006", 60),
    ("ELEC", "Electrical, HVAC and generators", "01-01-01-0014", "01-01-01-0015", "06-07-01-0007", 120),
    ("FURN", "Furniture and office equipment", "01-01-01-0016", "01-01-01-0017", "06-07-01-0008", 60),
    ("IT", "Computers, POS and IT equipment", "01-01-01-0018", "01-01-01-0019", "06-07-01-0009", 36),
    ("VEH", "Vehicles", "01-01-01-0020", "01-01-01-0021", "06-07-01-0010", 60),
    ("SOFT", "Software, ERP and ticketing systems", "01-01-04-0001", "01-01-04-0002", "06-07-03-0001", 60),
]

# code, name, kind, gl account, site code, bank name (placeholders only)
BANK_ACCOUNTS = [
    ("BNK-OPS", "Bank - operating current account", "BANK", "01-02-07-0006", None, "Bank (to configure)"),
    ("BNK-COL", "Bank - collections account", "BANK", "01-02-07-0007", None, "Bank (to configure)"),
    ("BNK-PAY", "Bank - payroll account", "BANK", "01-02-07-0008", None, "Bank (to configure)"),
    ("CASH-HO", "Cash in hand - Head Office", "CASH", "01-02-07-0001", "001", None),
    ("CASH-BO-101", "Box office cash - Emporium", "CASH", "01-02-07-0002", "101", None),
    ("CASH-BO-102", "Box office cash - Buch Villas", "CASH", "01-02-07-0002", "102", None),
    ("CASH-BO-103", "Box office cash - The Grand", "CASH", "01-02-07-0002", "103", None),
    ("CASH-FB-101", "F&B cash - Emporium", "CASH", "01-02-07-0003", "101", None),
    ("CASH-FB-102", "F&B cash - Buch Villas", "CASH", "01-02-07-0003", "102", None),
    ("CASH-FB-103", "F&B cash - The Grand", "CASH", "01-02-07-0003", "103", None),
    ("PETTY-001", "Petty cash - Head Office", "PETTY_CASH", "01-02-07-0004", "001", None),
    ("PETTY-101", "Petty cash - Emporium", "PETTY_CASH", "01-02-07-0004", "101", None),
    ("PETTY-102", "Petty cash - Buch Villas", "PETTY_CASH", "01-02-07-0004", "102", None),
    ("PETTY-103", "Petty cash - The Grand", "PETTY_CASH", "01-02-07-0004", "103", None),
]

# Workflow definitions: doc_type, name, require_check, auto_post_on_approval
WORKFLOWS = [
    ("JOURNAL", "Journal voucher", True, False),
    ("AP_INVOICE", "AP invoice / credit / debit note", False, True),
    ("AP_PAYMENT", "Supplier payment", True, True),
    ("AR_INVOICE", "AR invoice / credit / debit note", False, True),
    ("AR_RECEIPT", "Customer receipt", False, True),
    ("CASH_VOUCHER", "Cash / bank voucher", False, True),
    ("BANK_TRANSFER", "Bank / cash transfer", False, True),
]

# Approval limits (PKR) - bands proposed in the reference workbook; CFO to confirm
APPROVAL_LIMITS = {
    "FINANCE_MANAGER": Dec("2500000"),
    "CFO": None,  # unlimited
}

# Payment methods: code, name, type, clearing account, customer code (for AR-control clearings), fee %
PAYMENT_METHODS = [
    ("CASH", "Cash", "CASH", None, None, "0"),
    ("CARD-A", "Card - acquirer bank A", "CARD", "01-02-02-0001", None, "0.02"),
    ("CARD-B", "Card - acquirer bank B", "CARD", "01-02-02-0002", None, "0.02"),
    ("GATEWAY", "Online payment gateway", "GATEWAY", "01-02-02-0003", "C00901", "0.025"),
    ("WALLET", "Mobile wallet", "WALLET", "01-02-02-0004", "C00902", "0.015"),
    ("PLATFORM", "Third-party ticketing platform", "PLATFORM", "01-02-02-0005", "C00903", "0"),
    ("CORPORATE", "Corporate credit", "CORPORATE", "01-02-02-0007", None, "0"),
    ("VOUCHER", "Gift card / voucher redemption", "VOUCHER", "02-02-02-0013", None, "0"),
]

# Revenue types: code, name, stream, revenue acc, discount acc, refund acc, cost centre, tax codes, film rental
REVENUE_TYPES = [
    ("TKT-COUNTER", "Tickets - box office counter", "TICKETING", "04-01-01-0001", "04-01-02-0001", "04-01-02-0002", "010201", ["ENT-TKT-PB"], True),
    ("TKT-ONLINE", "Tickets - website and app", "TICKETING", "04-01-01-0002", "04-01-02-0001", "04-01-02-0002", "040102", ["ENT-TKT-PB"], True),
    ("TKT-PLATFORM", "Tickets - third-party platform", "TICKETING", "04-01-01-0003", "04-01-02-0001", "04-01-02-0002", "040102", ["ENT-TKT-PB"], True),
    ("TKT-CORPORATE", "Tickets - corporate / group", "TICKETING", "04-01-01-0004", "04-01-02-0001", "04-01-02-0002", "010201", ["ENT-TKT-PB"], True),
    ("BOOKING-FEE", "Booking and convenience fees", "TICKETING", "04-01-01-0005", None, "04-01-02-0002", "040102", [], False),
    ("FNB-FOOD", "F&B - food", "FNB", "04-02-01-0001", "04-02-02-0001", "04-02-02-0002", "020101", ["PST-OUT-FNB"], False),
    ("FNB-BEV", "F&B - beverages", "FNB", "04-02-01-0002", "04-02-02-0001", "04-02-02-0002", "020101", ["PST-OUT-FNB"], False),
    ("FNB-COMBO", "F&B - combos and meal deals", "FNB", "04-02-01-0003", "04-02-02-0001", "04-02-02-0002", "020101", ["PST-OUT-FNB"], False),
    ("FNB-CAFE", "F&B - cafe / restaurant", "FNB", "04-02-01-0004", "04-02-02-0001", "04-02-02-0002", "020102", ["PST-OUT-FNB"], False),
]
