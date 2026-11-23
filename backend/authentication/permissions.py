"""Permission catalogue and default role definitions."""
from __future__ import annotations

WORKFLOW_DOCS = {
    "journal": "Journal vouchers",
    "ap_invoice": "AP invoices, credit and debit notes",
    "ap_payment": "Supplier payments",
    "ar_invoice": "AR invoices, credit and debit notes",
    "ar_receipt": "Customer receipts",
    "cash_voucher": "Cash / bank vouchers",
    "bank_transfer": "Bank and cash transfers",
}
WORKFLOW_ACTIONS = ["view", "create", "check", "approve", "post", "reverse"]

PERMISSIONS: dict[str, str] = {}
for _doc, _label in WORKFLOW_DOCS.items():
    for _act in WORKFLOW_ACTIONS:
        PERMISSIONS[f"{_doc}.{_act}"] = f"{_label}: {_act}"

PERMISSIONS.update({
    "journal.restricted": "Post to restricted accounts (control, register, tax provision)",
    "coa.view": "View chart of accounts",
    "coa.manage": "Create and edit accounts",
    "masters.view": "View sites, cost centres, dimensions",
    "masters.manage": "Maintain sites, cost centres, dimensions, employees",
    "period.view": "View accounting periods",
    "period.manage": "Open / soft-close periods",
    "period.close": "Close periods and run month-end",
    "period.reopen": "Reopen closed periods",
    "period.lock": "Lock periods permanently",
    "period.post_soft_closed": "Post into soft-closed periods",
    "supplier.view": "View suppliers", "supplier.manage": "Maintain suppliers",
    "customer.view": "View customers", "customer.manage": "Maintain customers",
    "bank.view": "View bank and cash accounts", "bank.manage": "Maintain bank and cash accounts",
    "bank.reconcile": "Import statements and reconcile banks",
    "tax.view": "View tax codes and transactions", "tax.manage": "Maintain tax codes and rates",
    "tax.override": "Override default tax rates on transactions",
    "asset.view": "View fixed assets", "asset.manage": "Maintain fixed assets",
    "asset.depreciate": "Run and post depreciation", "asset.dispose": "Transfer, dispose and impair assets",
    "budget.view": "View budgets", "budget.manage": "Prepare budgets", "budget.approve": "Approve budgets",
    "cinema.view": "View cinema operations", "cinema.manage": "Maintain screens, films, shows, mappings",
    "cinema.import": "Import box office and F&B sales", "cinema.day_close": "Post day close",
    "cinema.settle": "Collections and distributor settlements",
    "report.view": "Financial reports", "report.cfo": "CFO dashboard and reporting pack",
    "report.export": "Export reports",
    "audit.view": "View audit trail",
    "import.run": "Run data imports", "opening.manage": "Load opening balances",
    "admin.users": "Manage users", "admin.roles": "Manage roles and approval limits",
    "admin.settings": "System settings and workflow configuration",
})


def _all_view() -> set[str]:
    return {p for p in PERMISSIONS if p.endswith(".view")}


def _doc(prefix: str, *acts: str) -> set[str]:
    return {f"{prefix}.{a}" for a in acts}


ALL = set(PERMISSIONS)
FINANCE_MANAGER = ALL - {"admin.users", "admin.roles", "period.reopen", "period.lock"}
ROLES: dict[str, tuple[str, set[str], bool]] = {
    # code: (name, permissions, all_sites default)
    "CFO": ("Chief Financial Officer", ALL - {"admin.users"}, True),
    "FINANCE_MANAGER": ("Finance Manager", FINANCE_MANAGER, True),
    "ACCOUNTANT": ("Accountant", _all_view() - {"audit.view"} | _doc("journal", "create", "check") | {
        "asset.manage", "asset.depreciate", "report.view", "report.export", "budget.manage", "bank.reconcile",
        "cinema.day_close", "cinema.settle", "import.run"}, True),
    "AP_OFFICER": ("AP Officer", {"supplier.view", "supplier.manage", "tax.view", "coa.view", "masters.view",
                                  "bank.view", "period.view", "report.view", "asset.view", "cinema.view"}
                   | _doc("ap_invoice", "view", "create") | _doc("ap_payment", "view", "create"), True),
    "AR_OFFICER": ("AR Officer", {"customer.view", "customer.manage", "tax.view", "coa.view", "masters.view",
                                  "bank.view", "period.view", "report.view", "cinema.view"}
                   | _doc("ar_invoice", "view", "create") | _doc("ar_receipt", "view", "create"), True),
    "CASHIER": ("Cashier", {"bank.view", "coa.view", "masters.view", "cinema.view", "cinema.import", "period.view"}
                | _doc("cash_voucher", "view", "create") | _doc("bank_transfer", "view", "create"), False),
    "SITE_MANAGER": ("Site Manager", {"cinema.view", "cinema.import", "cinema.day_close", "coa.view", "masters.view",
                                      "report.view", "bank.view", "period.view", "budget.view"}
                     | _doc("cash_voucher", "view", "create", "check"), False),
    "AUDITOR": ("Auditor (read-only)", _all_view() | {"report.view", "report.cfo", "report.export"}, True),
    "ADMIN": ("System Administrator", {"admin.users", "admin.roles", "admin.settings", "masters.view",
                                        "coa.view", "audit.view"}, True),
}
