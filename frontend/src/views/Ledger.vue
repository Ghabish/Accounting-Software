<template>
  <div>
    <div class="page-head"><h1>General ledger</h1>
      <div class="actions"><button class="btn" @click="exp('xlsx')">Excel</button><button class="btn" @click="exp('pdf')">PDF</button></div>
    </div>
    <div class="panel no-print">
      <form class="filters" @submit.prevent="load(1)">
        <div class="field" style="max-width:380px;flex:2 1 300px"><label>Account</label><Picker v-model="f.account_ids" :options="accounts" placeholder="All accounts" /></div>
        <div class="field"><label>Code starts with</label><input v-model="f.account_prefix" placeholder="e.g. 04-01" /></div>
        <div class="field"><label>From</label><input v-model="f.date_from" type="date" /></div>
        <div class="field"><label>To</label><input v-model="f.date_to" type="date" /></div>
        <div class="field"><label>Site</label><Picker v-model="f.site_ids" :options="sites" /></div>
        <div class="field"><label>Cost centre</label><Picker v-model="f.cost_centre_ids" :options="ccs" /></div>
        <div class="field"><label>Dimension (film, screen…)</label><Picker v-model="f.dimension_value_ids" :options="dims" /></div>
        <div class="field" style="flex:0 0 auto"><button class="btn primary">Show</button></div>
      </form>
    </div>
    <div v-if="data" class="panel">
      <div class="grid kpis" style="margin-bottom:.8rem">
        <div class="kpi"><div class="label">Opening</div><div class="value">{{ fmtMoney(data.opening) }}</div></div>
        <div class="kpi"><div class="label">Debits</div><div class="value">{{ fmtMoney(data.period_debit) }}</div></div>
        <div class="kpi"><div class="label">Credits</div><div class="value">{{ fmtMoney(data.period_credit) }}</div></div>
        <div class="kpi"><div class="label">Closing</div><div class="value">{{ fmtMoney(data.closing) }}</div></div>
      </div>
      <DataTable :columns="cols" :rows="data.items" :total="data.total" :page="data.page" :page-size="data.page_size"
                 :row-link="(r) => `/journals/${r.journal_id}`" @page="load" />
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, showError } from '../api.js'
import { fmtMoney, fyStart, monthEnd } from '../format.js'
import { opt, refs } from '../refs.js'
import DataTable from '../components/DataTable.vue'
import Picker from '../components/Picker.vue'
const route = useRoute()
const num = (v) => (v === undefined || v === null || v === '' ? null : Number(v))
const f = reactive({ date_from: route.query.date_from || fyStart(), date_to: route.query.date_to || monthEnd(), account_ids: num(route.query.account_ids),
  account_prefix: route.query.account_prefix || '', site_ids: num(route.query.site_ids), cost_centre_ids: num(route.query.cost_centre_ids),
  dimension_value_ids: num(route.query.dimension_value_ids) })
const data = ref(null)
const accounts = ref([]); const sites = ref([]); const ccs = ref([]); const dims = ref([])
const cols = [{ key: 'date', label: 'Date', type: 'date' }, { key: 'number', label: 'Journal' }, { key: 'account_code', label: 'Account' },
  { key: 'description', label: 'Description' }, { key: 'reference', label: 'Reference' }, { key: 'site', label: 'Site' }, { key: 'cost_centre', label: 'CC' },
  { key: 'debit', label: 'Debit', type: 'money' }, { key: 'credit', label: 'Credit', type: 'money' }, { key: 'balance', label: 'Balance', type: 'money' }]
async function load(page = 1) { try { data.value = await api.get('/reports/gl', { ...f, page, page_size: 200 }) } catch (e) { showError(e) } }
const exp = (fmt) => api.download('/reports/gl', { ...f, format: fmt }).catch(showError)
onMounted(async () => {
  load()
  accounts.value = (await refs.accounts()).map(opt.account)
  sites.value = (await refs.sites()).map(opt.coded)
  ccs.value = (await refs.costCentres()).map(opt.coded)
  dims.value = (await refs.dimValues()).map(opt.coded)
})
</script>
