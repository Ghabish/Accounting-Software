<template>
  <div>
    <div class="page-head">
      <h1>{{ cfg.title }}</h1>
      <div class="actions">
        <button class="btn" :disabled="!report" @click="exp('xlsx')">Excel</button>
        <button class="btn" :disabled="!report" @click="exp('pdf')">PDF</button>
        <button class="btn hide-sm" :disabled="!report" @click="exp('csv')">CSV</button>
      </div>
    </div>
    <div class="panel no-print">
      <form class="filters" @submit.prevent="load">
        <div v-for="f in cfg.filters" :key="f.key" class="field">
          <label>{{ f.label }}</label>
          <Picker v-if="f.type === 'picker'" v-model="params[f.key]" :options="opts[f.key] || []" />
          <select v-else-if="f.type === 'select'" v-model="params[f.key]">
            <option v-for="o in f.options" :key="o[0]" :value="o[0]">{{ o[1] }}</option>
          </select>
          <label v-else-if="f.type === 'checkbox'" class="check"><input v-model="params[f.key]" type="checkbox" /> yes</label>
          <input v-else v-model="params[f.key]" :type="f.type || 'text'" />
        </div>
        <div class="field" style="flex:0 0 auto"><button class="btn primary" type="submit">Run report</button></div>
      </form>
    </div>
    <div v-if="loading" class="panel empty">Calculating from the general ledger…</div>
    <div v-else-if="report" class="panel">
      <div class="row" style="margin-bottom:.6rem"><strong>{{ report.title }}</strong><span class="muted">{{ report.subtitle }}</span></div>
      <ReportView :report="report" @drill="drill" />
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, showError } from '../api.js'
import { fyStart, monthEnd, monthStart, today } from '../format.js'
import { opt, refs } from '../refs.js'
import Picker from '../components/Picker.vue'
import ReportView from '../components/ReportView.vue'

const props = defineProps({ rkey: String })
const route = useRoute()
const router = useRouter()
const SITE = { key: 'site_ids', label: 'Site', type: 'picker', load: async () => (await refs.sites()).map(opt.coded) }
const CC = { key: 'cost_centre_ids', label: 'Cost centre', type: 'picker', load: async () => (await refs.costCentres()).map(opt.coded) }
const RANGE = [{ key: 'date_from', label: 'From', type: 'date' }, { key: 'date_to', label: 'To', type: 'date' }]
const ASOF = [{ key: 'as_of', label: 'As at', type: 'date' }]
const CONFIG = {
  'trial-balance': { title: 'Trial balance', ep: '/reports/trial-balance', filters: [...RANGE, SITE, CC, { key: 'include_zero', label: 'Include zero', type: 'checkbox' }] },
  'profit-loss': { title: 'Profit & loss', ep: '/reports/profit-loss', filters: [...RANGE,
    { key: 'preset', label: 'Layout', type: 'select', options: [['period', 'Single period'], ['monthly', 'Monthly'], ['ytd', 'Period and YTD'], ['comparative', 'vs prior year'], ['budget', 'Budget vs actual'], ['site', 'Site-wise'], ['cost_centre', 'Cost-centre-wise']] },
    { key: 'detail', label: 'Detail', type: 'select', options: [['account', 'Accounts'], ['subgroup', 'Sub-groups'], ['group', 'Groups']] }, SITE, CC] },
  'balance-sheet': { title: 'Balance sheet', ep: '/reports/balance-sheet', filters: [...ASOF,
    { key: 'compare', label: 'Compare with', type: 'select', options: [['', 'None'], ['prior_month', 'Prior month end'], ['prior_year', 'Same date last year'], ['fy_start', 'Start of year']] },
    { key: 'detail', label: 'Detail', type: 'select', options: [['account', 'Accounts'], ['subgroup', 'Sub-groups']] }, SITE] },
  'cash-flow': { title: 'Cash flow statement', ep: '/reports/cash-flow', filters: [...RANGE,
    { key: 'method', label: 'Method', type: 'select', options: [['indirect', 'Indirect'], ['direct', 'Direct']] }, SITE] },
  'cash-flow-monthly': { title: 'Monthly cash flow', ep: '/reports/cash-flow-monthly', filters: [...RANGE] },
  'gl-monthly': { title: 'Monthly GL movements', ep: '/reports/gl-monthly', filters: [...RANGE, { key: 'account_prefix', label: 'Account code starts with' }, SITE, { key: 'compare_prior_year', label: 'Compare prior year', type: 'checkbox' }] },
  'journal-listing': { title: 'Journal listing', ep: '/reports/journal-listing', filters: [...RANGE, { key: 'journal_type', label: 'Type' }, { key: 'status', label: 'Status', type: 'select', options: [['', 'All'], ['POSTED', 'Posted'], ['DRAFT', 'Draft'], ['SUBMITTED', 'Submitted'], ['APPROVED', 'Approved'], ['REVERSED', 'Reversed']] }] },
  'cash-position': { title: 'Daily cash position', ep: '/banking/cash-position', filters: [{ key: 'on_date', label: 'Date', type: 'date' }] },
  'ap-aging': { title: 'Accounts payable aging', ep: '/ap/aging', filters: [...ASOF] },
  'ar-aging': { title: 'Accounts receivable aging', ep: '/ar/aging', filters: [...ASOF] },
  'ap-reconciliation': { title: 'AP sub-ledger to GL', ep: '/ap/reconciliation', filters: [...ASOF] },
  'ar-reconciliation': { title: 'AR sub-ledger to GL', ep: '/ar/reconciliation', filters: [...ASOF] },
  subledger: { title: 'Sub-ledger reconciliation status', ep: '/reports/subledger-reconciliation', filters: [...ASOF] },
  'supplier-statement': { title: 'Supplier statement', ep: (p) => `/ap/suppliers/${p.supplier_id}/statement`, filters: [{ key: 'supplier_id', label: 'Supplier', type: 'picker', load: async () => (await refs.suppliers()).map(opt.coded) }, ...RANGE] },
  'customer-statement': { title: 'Customer statement', ep: (p) => `/ar/customers/${p.customer_id}/statement`, filters: [{ key: 'customer_id', label: 'Customer', type: 'picker', load: async () => (await refs.customers()).map(opt.coded) }, ...RANGE] },
  'tax-summary': { title: 'Tax summary', ep: '/tax/reports/summary', filters: [...RANGE] },
  'tax-transactions': { title: 'Tax transactions', ep: '/tax/reports/transactions', filters: [...RANGE, { key: 'direction', label: 'Direction', type: 'select', options: [['', 'All'], ['OUTPUT', 'Output'], ['INPUT', 'Input'], ['WITHHELD', 'Withheld from suppliers'], ['SUFFERED', 'Deducted from us']] }] },
  'tax-reconciliation': { title: 'Tax accounts reconciliation', ep: '/tax/reports/reconciliation', filters: [...RANGE] },
  'fa-register': { title: 'Fixed asset register', ep: '/assets/reports/register', filters: [...ASOF, { ...SITE, key: 'site_id' }] },
  'fa-reconciliation': { title: 'Fixed assets to GL', ep: '/assets/reports/reconciliation', filters: [...ASOF] },
  'budget-variance': { title: 'Budget vs actual', ep: '/budgets/reports/variance', filters: [...RANGE, SITE, CC] },
  'cinema-revenue': { title: 'Cinema revenue analysis', ep: '/cinema/reports/revenue', filters: [...RANGE,
    { key: 'group_by', label: 'Group by', type: 'select', options: [['site', 'Cinema'], ['screen', 'Screen'], ['film', 'Film'], ['show', 'Show'], ['distributor', 'Distributor'], ['revenue_type', 'Revenue type'], ['payment_method', 'Payment method'], ['date', 'Date']] }, SITE] },
  'collections-reconciliation': { title: 'Revenue & collections reconciliation', ep: '/cinema/reports/collections-reconciliation', filters: [...RANGE] },
  'pos-gl': { title: 'POS revenue to GL', ep: '/cinema/reports/gl-reconciliation', filters: [...RANGE] },
}
const cfg = computed(() => CONFIG[props.rkey] || { title: 'Unknown report', ep: '', filters: [] })
const params = reactive({ date_from: fyStart(), date_to: monthEnd(), as_of: monthEnd(), on_date: today(), preset: 'period', detail: 'account',
  method: 'indirect', group_by: 'site', compare: '', status: '', direction: '', ...route.query })
const opts = reactive({})
const report = ref(null)
const loading = ref(false)
const ep = () => (typeof cfg.value.ep === 'function' ? cfg.value.ep(params) : cfg.value.ep)
const query = () => { const q = {}; for (const f of cfg.value.filters) if (params[f.key] !== undefined && params[f.key] !== '' && params[f.key] !== null) q[f.key] = params[f.key]; return q }
async function load() {
  if (cfg.value.filters.some((f) => f.type === 'picker' && /statement/.test(props.rkey) && !params[f.key])) return
  loading.value = true
  try { report.value = await api.get(ep(), query()) } catch (e) { showError(e) } finally { loading.value = false }
}
const exp = (fmt) => api.download(ep(), { ...query(), format: fmt }).catch(showError)
function drill(r, col) {
  if (r.journal_id && !r.drill) return router.push(`/journals/${r.journal_id}`)
  const d = r.drill || {}
  if (d.supplier_id) return router.push({ path: '/reports/supplier-statement', query: { supplier_id: d.supplier_id, date_from: params.date_from || fyStart(), date_to: params.as_of || params.date_to } })
  if (d.customer_id) return router.push({ path: '/reports/customer-statement', query: { customer_id: d.customer_id, date_from: params.date_from || fyStart(), date_to: params.as_of || params.date_to } })
  if (d.tax_code_id) return router.push({ path: '/reports/tax-transactions', query: { tax_code_id: d.tax_code_id, date_from: params.date_from, date_to: params.date_to } })
  if (d.account_id || d.account_prefix) {
    const q = { date_from: col?.date_from || params.date_from || fyStart(), date_to: col?.date_to || params.date_to || params.as_of }
    if (!col?.date_from && params.as_of && !params.date_from) q.date_from = fyStart(new Date(params.as_of))
    if (d.account_id) q.account_ids = d.account_id
    if (d.account_prefix) q.account_prefix = d.account_prefix
    const site = col?.site_ids?.[0] || d.site_id || params.site_ids
    if (site) q.site_ids = site
    const cc = col?.cost_centre_ids?.[0] || params.cost_centre_ids
    if (cc) q.cost_centre_ids = cc
    return router.push({ path: '/ledger', query: q })
  }
}
onMounted(async () => {
  for (const f of cfg.value.filters) if (f.type === 'picker') opts[f.key] = await f.load()
  load()
})
</script>
