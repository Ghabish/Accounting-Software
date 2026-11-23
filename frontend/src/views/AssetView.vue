<template>
  <div v-if="a">
    <div class="page-head"><h1>{{ a.code }} - {{ a.name }}</h1><span class="badge" :class="a.status">{{ a.status }}</span></div>
    <div class="grid kpis">
      <div class="kpi"><div class="label">Cost</div><div class="value">{{ fmtMoney(a.cost) }}</div></div>
      <div class="kpi"><div class="label">Accumulated depreciation</div><div class="value">{{ fmtMoney(a.accumulated_depreciation) }}</div></div>
      <div class="kpi"><div class="label">Impairment</div><div class="value">{{ fmtMoney(a.impairment_total) }}</div></div>
      <div class="kpi"><div class="label">Net book value</div><div class="value">{{ fmtMoney(a.net_book_value) }}</div></div>
    </div>
    <div class="panel" style="margin-top:1rem"><dl class="facts">
      <div><dt>Capitalised</dt><dd>{{ fmtDate(a.capitalisation_date) }}</dd></div><div><dt>Depreciation from</dt><dd>{{ fmtDate(a.depreciation_start_date) }}</dd></div>
      <div><dt>Life</dt><dd>{{ a.useful_life_months }} months · {{ a.method }}</dd></div><div><dt>Residual</dt><dd>{{ fmtMoney(a.residual_value) }}</dd></div>
      <div><dt>Last depreciated</dt><dd>{{ fmtDate(a.last_depreciation_date) || '-' }}</dd></div><div><dt>Tag / serial</dt><dd>{{ a.tag_no || '-' }} / {{ a.serial_no || '-' }}</dd></div>
    </dl></div>
    <div v-if="a.status === 'DRAFT' && session.can('asset.manage')" class="panel">
      <h2>Capitalise</h2>
      <div class="form-grid">
        <div class="field"><label>Source</label><select v-model="cap.source"><option value="AP_INVOICE">Supplier invoice (already posted)</option><option value="JOURNAL">Transfer from CWIP / other account</option><option value="OPENING">Opening balance (migration)</option></select></div>
        <div v-if="cap.source === 'AP_INVOICE'" class="field"><label>AP invoice line id</label><input v-model="cap.ap_document_line_id" type="number" /></div>
        <div v-if="cap.source === 'JOURNAL'" class="field"><label>Offset account</label><Picker v-model="cap.offset_account_id" :options="accounts" /></div>
        <div v-if="cap.source === 'OPENING'" class="field"><label>Opening accumulated depreciation</label><input v-model="cap.opening_accumulated" type="number" step="0.01" /></div>
      </div>
      <button class="btn primary" style="margin-top:.75rem" @click="act('capitalise', cap)">Capitalise</button>
    </div>
    <div v-if="['ACTIVE', 'FULLY_DEPRECIATED'].includes(a.status) && session.can('asset.dispose')" class="grid three">
      <div class="panel stack"><h3>Transfer</h3>
        <Picker v-model="tr.to_site_id" :options="sites" placeholder="New site" /><Picker v-model="tr.to_cost_centre_id" :options="ccs" placeholder="New cost centre" />
        <input v-model="tr.date" type="date" /><button class="btn" @click="act('transfer', tr)">Transfer</button></div>
      <div class="panel stack"><h3>Impairment</h3>
        <input v-model="im.amount" type="number" step="0.01" placeholder="Amount" /><input v-model="im.reason" placeholder="Reason" /><input v-model="im.date" type="date" />
        <button class="btn" @click="act('impair', im)">Post impairment</button></div>
      <div class="panel stack"><h3>Disposal</h3>
        <input v-model="dp.proceeds" type="number" step="0.01" placeholder="Proceeds" /><Picker v-model="dp.bank_account_id" :options="banks" placeholder="Proceeds received in" />
        <input v-model="dp.date" type="date" /><button class="btn danger" @click="act('dispose', dp)">Dispose</button></div>
    </div>
    <div class="panel"><h3>Asset history</h3><DataTable :columns="cols" :rows="a.transactions" :row-link="(r) => r.journal_id ? `/journals/${r.journal_id}` : null" /></div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtDate, fmtMoney, today } from '../format.js'
import { opt, refs } from '../refs.js'
import { session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import Picker from '../components/Picker.vue'
const props = defineProps({ id: [String, Number] })
const a = ref(null); const accounts = ref([]); const sites = ref([]); const ccs = ref([]); const banks = ref([])
const cap = reactive({ source: 'AP_INVOICE', ap_document_line_id: '', offset_account_id: null, opening_accumulated: '' })
const tr = reactive({ to_site_id: null, to_cost_centre_id: null, date: today() }); const im = reactive({ amount: '', reason: '', date: today() })
const dp = reactive({ proceeds: '', bank_account_id: null, date: today() })
const cols = [{ key: 'txn_date', label: 'Date', type: 'date' }, { key: 'txn_type', label: 'Transaction' }, { key: 'amount', label: 'Amount', type: 'money' },
  { key: 'proceeds', label: 'Proceeds', type: 'money' }, { key: 'gain_loss', label: 'Gain / (loss)', type: 'money' }, { key: 'notes', label: 'Notes' }]
const load = async () => { a.value = await api.get(`/assets/${props.id}`) }
async function act(action, body) {
  const b = { ...body }
  for (const k of Object.keys(b)) if (b[k] === '') b[k] = null
  try { await api.post(`/assets/${props.id}/${action}`, b); toast('Done'); load() } catch (e) { showError(e) }
}
onMounted(async () => {
  load()
  accounts.value = (await refs.accounts()).map(opt.account)
  sites.value = (await refs.sites()).map(opt.coded); ccs.value = (await refs.costCentres()).map(opt.coded); banks.value = (await refs.bankAccounts()).map(opt.coded)
})
</script>
