<template>
  <div>
    <div class="page-head"><h1>Distributor settlements</h1></div>
    <div v-if="session.can('cinema.settle')" class="panel">
      <h2>Prepare settlement from accrued film rental</h2>
      <div class="form-grid">
        <div class="field" style="grid-column: span 2"><label>Distributor</label><Picker v-model="f.distributor_id" :options="dists" /></div>
        <div class="field"><label>From</label><input v-model="f.period_from" type="date" /></div>
        <div class="field"><label>To</label><input v-model="f.period_to" type="date" /></div>
        <div class="field"><label>Reference</label><input v-model="f.reference" /></div>
        <div class="field"><label>Adjustment (e.g. MG shortfall)</label><input v-model="f.adjustment" type="number" step="0.01" /></div>
      </div>
      <button class="btn primary" style="margin-top:.75rem" @click="prepare">Prepare</button>
    </div>
    <div v-for="s in list" :key="s.id" class="panel">
      <div class="row"><strong>Settlement #{{ s.id }}</strong><span class="muted">{{ distName[s.distributor_id] }} · {{ fmtDate(s.period_from) }} – {{ fmtDate(s.period_to) }}</span>
        <span class="badge" :class="s.status === 'INVOICED' ? 'POSTED' : 'DRAFT'">{{ s.status }}</span><span class="spacer"></span>
        <strong>{{ fmtMoney(s.total) }}</strong>
        <router-link v-if="s.ap_document_id" class="btn sm" :to="`/ap/documents/${s.ap_document_id}`">AP invoice</router-link>
        <template v-if="s.status === 'DRAFT' && session.can('ap_invoice.create')">
          <input v-model="inv[s.id]" placeholder="Distributor invoice no." style="max-width:200px" />
          <button class="btn sm primary" @click="invoice(s)">Create AP invoice</button>
        </template>
      </div>
      <DataTable :columns="lineCols" :rows="s.lines" />
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtDate, fmtMoney, monthEnd, monthStart, today } from '../format.js'
import { opt, refs } from '../refs.js'
import { session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import Picker from '../components/Picker.vue'
const f = reactive({ distributor_id: null, period_from: monthStart(), period_to: monthEnd(), reference: '', adjustment: '' })
const dists = ref([]); const list = ref([]); const inv = reactive({}); let distName = {}
const lineCols = [{ key: 'film_id', label: 'Film' }, { key: 'site_id', label: 'Site' }, { key: 'tickets', label: 'Tickets', type: 'int' },
  { key: 'net_box_office', label: 'Net box office', type: 'money' }, { key: 'accrued_amount', label: 'Distributor share', type: 'money' }]
const load = async () => { list.value = await api.get('/cinema/distributor-settlements') }
async function prepare() { try { await api.post('/cinema/distributor-settlements', { ...f, adjustment: f.adjustment || 0 }); toast('Prepared'); load() } catch (e) { showError(e) } }
async function invoice(s) {
  try { const r = await api.post(`/cinema/distributor-settlements/${s.id}/invoice`, { invoice_no: inv[s.id], invoice_date: today() }); toast(`AP invoice ${r.number} created - submit it for approval`); load() } catch (e) { showError(e) }
}
onMounted(async () => {
  const sups = await refs.suppliers()
  distName = Object.fromEntries(sups.map((s) => [s.id, s.name]))
  dists.value = sups.map(opt.coded)
  load()
})
</script>
