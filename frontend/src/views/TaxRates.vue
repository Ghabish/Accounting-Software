<template>
  <div v-if="code">
    <div class="page-head"><h1>{{ code.code }} - {{ code.name }}</h1></div>
    <div v-if="code.needs_confirmation" class="alert warn">Rate seeded from the reference workbook - to be confirmed by the tax advisor. {{ code.notes }}</div>
    <div class="panel"><h3>Effective-dated rates</h3><DataTable :columns="cols" :rows="code.rates" /></div>
    <div v-if="session.can('tax.manage')" class="panel">
      <h2>Add a new rate</h2>
      <p class="small muted">The current open-ended rate for the same payee type / ATL status is closed the day before the new effective date. History is kept.</p>
      <div class="form-grid">
        <div class="field"><label>Name</label><input v-model="r.name" placeholder="e.g. WHT 7% Specified Services" /></div>
        <div class="field"><label>Payee type</label><select v-model="r.payee_type"><option>ALL</option><option>COMPANY</option><option>INDIVIDUAL</option><option>AOP</option><option>NON_RESIDENT</option></select></div>
        <div class="field"><label>ATL status</label><select v-model="r.atl_status"><option>ALL</option><option>ATL</option><option>NON_ATL</option></select></div>
        <div class="field"><label>Rate (fraction)</label><input v-model="r.rate" type="number" step="0.0001" min="0" max="1" /></div>
        <div class="field"><label>Effective from</label><input v-model="r.effective_from" type="date" /></div>
        <div class="field"><label>Source / law reference</label><input v-model="r.source_ref" /></div>
      </div>
      <button class="btn primary" style="margin-top:.75rem" @click="add">Add rate</button>
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, showError } from '../api.js'
import { lookups, session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
const props = defineProps({ id: [String, Number] })
const code = ref(null)
const r = reactive({ name: '', payee_type: 'ALL', atl_status: 'ALL', rate: '', effective_from: '', source_ref: '' })
const cols = [{ key: 'name', label: 'Name' }, { key: 'payee_type', label: 'Payee' }, { key: 'atl_status', label: 'ATL' }, { key: 'rate', label: 'Rate', render: (x) => `${(Number(x.rate) * 100).toFixed(3)}%` },
  { key: 'effective_from', label: 'From', type: 'date' }, { key: 'effective_to', label: 'To', type: 'date' }, { key: 'source_ref', label: 'Source' }]
const load = async () => { code.value = await api.get(`/tax/codes/${props.id}`) }
async function add() { try { await api.post('/tax/rates', { ...r, tax_code_id: Number(props.id) }); toast('Rate added'); lookups.invalidate('taxCodes'); load() } catch (e) { showError(e) } }
onMounted(load)
</script>
