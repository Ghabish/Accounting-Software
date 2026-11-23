import { createRouter, createWebHashHistory } from 'vue-router'
import { session, toast } from './store.js'
import { NAV } from './nav.js'

const PERM_BY_PATH = Object.fromEntries(NAV.flatMap((g) => g.items.map((i) => [i.to, i.perm])))

const v = (name) => () => import(`./views/${name}.vue`)

const routes = [
  { path: '/login', component: v('Login'), meta: { public: true } },
  { path: '/', component: v('Dashboard') },
  { path: '/profile', component: v('Profile') },
  { path: '/accounts', component: v('Accounts') },
  { path: '/journals', component: v('DocList'), props: { kind: 'journal' } },
  { path: '/journals/new', component: v('JournalEdit') },
  { path: '/journals/:id/edit', component: v('JournalEdit') },
  { path: '/journals/:id', component: v('DocView'), props: (r) => ({ kind: 'journal', id: r.params.id }) },
  { path: '/recurring', component: v('Recurring') },
  { path: '/ledger', component: v('Ledger') },
  { path: '/reports/:rkey', component: v('ReportPage'), props: true },
  { path: '/cfo-pack', component: v('CfoPack') },
  { path: '/masters/:entity', component: v('MasterPage'), props: true },
  { path: '/ap/documents', component: v('DocList'), props: { kind: 'ap_doc' } },
  { path: '/ap/documents/new', component: v('SubDocEdit'), props: { side: 'ap' } },
  { path: '/ap/documents/:id/edit', component: v('SubDocEdit'), props: (r) => ({ side: 'ap', id: r.params.id }) },
  { path: '/ap/documents/:id', component: v('DocView'), props: (r) => ({ kind: 'ap_doc', id: r.params.id }) },
  { path: '/ap/payments', component: v('DocList'), props: { kind: 'ap_payment' } },
  { path: '/ap/payments/new', component: v('PaymentEdit') },
  { path: '/ap/payments/:id/edit', component: v('PaymentEdit') },
  { path: '/ap/payments/:id', component: v('DocView'), props: (r) => ({ kind: 'ap_payment', id: r.params.id }) },
  { path: '/ar/documents', component: v('DocList'), props: { kind: 'ar_doc' } },
  { path: '/ar/documents/new', component: v('SubDocEdit'), props: { side: 'ar' } },
  { path: '/ar/documents/:id/edit', component: v('SubDocEdit'), props: (r) => ({ side: 'ar', id: r.params.id }) },
  { path: '/ar/documents/:id', component: v('DocView'), props: (r) => ({ kind: 'ar_doc', id: r.params.id }) },
  { path: '/ar/receipts', component: v('DocList'), props: { kind: 'ar_receipt' } },
  { path: '/ar/receipts/new', component: v('ReceiptEdit') },
  { path: '/ar/receipts/:id/edit', component: v('ReceiptEdit') },
  { path: '/ar/receipts/:id', component: v('DocView'), props: (r) => ({ kind: 'ar_receipt', id: r.params.id }) },
  { path: '/bank/vouchers', component: v('DocList'), props: { kind: 'voucher' } },
  { path: '/bank/vouchers/new', component: v('VoucherEdit') },
  { path: '/bank/vouchers/:id/edit', component: v('VoucherEdit') },
  { path: '/bank/vouchers/:id', component: v('DocView'), props: (r) => ({ kind: 'voucher', id: r.params.id }) },
  { path: '/bank/transfers', component: v('DocList'), props: { kind: 'transfer' } },
  { path: '/bank/transfers/new', component: v('TransferEdit') },
  { path: '/bank/transfers/:id', component: v('DocView'), props: (r) => ({ kind: 'transfer', id: r.params.id }) },
  { path: '/bank/reconciliation', component: v('BankRec') },
  { path: '/cinema/day-close', component: v('DayClose') },
  { path: '/cinema/import', component: v('SalesImport') },
  { path: '/cinema/collections', component: v('Collections') },
  { path: '/cinema/distributors', component: v('Distributors') },
  { path: '/cinema/films/:id/terms', component: v('FilmTerms'), props: true },
  { path: '/tax/codes/:id/rates', component: v('TaxRates'), props: true },
  { path: '/tax/deposits', component: v('TaxDeposits') },
  { path: '/assets', component: v('AssetList') },
  { path: '/assets/runs', component: v('DepRuns') },
  { path: '/assets/:id', component: v('AssetView'), props: true },
  { path: '/budgets', component: v('Budgets') },
  { path: '/closing', component: v('Closing') },
  { path: '/closing/:id', component: v('Checklist'), props: true },
  { path: '/imports', component: v('Imports') },
  { path: '/admin/users', component: v('Users') },
  { path: '/admin/roles', component: v('Roles') },
  { path: '/admin/limits', component: v('Limits') },
  { path: '/admin/workflows', component: v('Workflows') },
  { path: '/admin/audit', component: v('Audit') },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHashHistory(), routes, scrollBehavior: () => ({ top: 0 }) })
router.beforeEach((to) => {
  if (!to.meta.public && !session.token) return { path: '/login', query: { next: to.fullPath } }
  const perm = PERM_BY_PATH[to.path]
  if (perm && session.token && !session.can(perm)) {
    toast('You do not have access to that screen', 'error')
    return to.path === '/' ? { path: '/profile' } : { path: '/' }
  }
})
export default router
