<template>
  <div>
    <div class="page-head"><h1>Imports &amp; opening balances</h1></div>
    <div class="panel">
      <h2>Opening balances</h2>
      <p class="small muted">Load the audited trial balance at cut-over: GL balances first (control and fixed-asset register accounts excluded), then supplier and customer open items, then fixed assets (Asset register → capitalise as opening). Every load posts against <em>03-01-03-0001 Opening balance clearing</em>, which must be nil when complete.</p>
      <div class="filters"><div class="field"><label>Cut-over date</label><input v-model="cutover" type="date" /></div>
        <div class="field" style="flex:0 0 auto"><button class="btn" @click="status">Check opening status</button></div></div>
      <div v-if="st" class="grid kpis">
        <div class="kpi"><div class="label">Assets</div><div class="value">{{ fmtMoney(st.assets) }}</div></div>
        <div class="kpi"><div class="label">Liabilities</div><div class="value">{{ fmtMoney(st.liabilities) }}</div></div>
        <div class="kpi"><div class="label">Equity</div><div class="value">{{ fmtMoney(st.equity_incl_clearing) }}</div></div>
        <div class="kpi" :class="{ neg: !st.clearing_is_nil }"><div class="label">Clearing balance</div><div class="value">{{ fmtMoney(st.clearing_balance, { zero: '0.00' }) }}</div></div>
        <div class="kpi"><div class="label">Accounting equation</div><div class="value"><span class="badge" :class="st.equation_holds ? 'PASS' : 'FAIL'">{{ st.equation_holds ? 'Holds' : 'Fails' }}</span></div></div>
      </div>
    </div>
    <div class="grid two">
      <div v-for="k in kinds" :key="k.key" class="panel stack">
        <h3>{{ k.title }}</h3><p class="small muted">{{ k.help }}</p>
        <div class="row"><input :ref="(el) => (inputs[k.key] = el)" type="file" accept=".csv,.xlsx" style="max-width:300px" />
          <button class="btn primary" @click="run(k)">Import</button>
          <a href="#" class="small" @click.prevent="api.download(`/imports/templates/${k.key}`, null, `${k.key}.csv`)">Template</a></div>
        <div v-if="res[k.key]" class="alert ok">{{ JSON.stringify(res[k.key]) }}</div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { reactive, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtMoney, fyStart } from '../format.js'
import { lookups, toast } from '../store.js'
const cutover = ref(fyStart()); const st = ref(null); const inputs = reactive({}); const res = reactive({})
const kinds = [
  { key: 'gl-opening', title: 'GL opening balances', help: 'account_code, site_code, cost_centre_code, debit, credit, description', opening: true },
  { key: 'supplier-opening', title: 'Supplier open items', help: 'supplier_code, invoice_no, invoice_date, due_date, amount, doc_type', opening: true },
  { key: 'customer-opening', title: 'Customer open items', help: 'customer_code, invoice_no, invoice_date, due_date, amount, doc_type', opening: true },
  { key: 'suppliers', title: 'Supplier master', help: 'Creates suppliers with tax codes defaulted from the category' },
  { key: 'customers', title: 'Customer master', help: 'Creates customers' },
  { key: 'accounts', title: 'Chart of accounts additions', help: 'parent_code, name (codes assigned automatically)' },
  { key: 'journals', title: 'Journal entries', help: 'Grouped by journal_ref; created as drafts for approval' },
]
async function status() { try { st.value = await api.get('/imports/opening/status', { cutover_date: cutover.value }) } catch (e) { showError(e) } }
async function run(k) {
  const f = inputs[k.key]?.files?.[0]
  if (!f) return
  const fd = new FormData(); fd.append('file', f); if (k.opening) fd.append('cutover_date', cutover.value)
  try { res[k.key] = await api.upload(`/imports/${k.key}`, fd); toast('Imported'); lookups.clear(); if (k.opening) status() } catch (e) { showError(e) }
}
</script>
