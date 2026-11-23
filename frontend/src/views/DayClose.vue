<template>
  <div>
    <div class="page-head"><h1>Cinema day close</h1></div>
    <div class="panel">
      <div class="filters">
        <div class="field"><label>Site</label><Picker v-model="f.site_id" :options="sites" :clearable="false" /></div>
        <div class="field"><label>Business date</label><input v-model="f.business_date" type="date" /></div>
        <div class="field" style="flex:0 0 auto"><button class="btn" @click="loadPreview">Preview</button></div>
      </div>
      <div v-if="pv">
        <div v-if="pv.already_closed" class="alert ok">This date is already day-closed.</div>
        <div class="grid kpis">
          <div class="kpi"><div class="label">Box office rows</div><div class="value">{{ pv.box_office_rows }}</div></div>
          <div class="kpi"><div class="label">Tickets</div><div class="value">{{ fmtInt(pv.tickets) }}</div></div>
          <div class="kpi"><div class="label">Ticket gross</div><div class="value">{{ fmtMoney(pv.ticket_gross) }}</div></div>
          <div class="kpi"><div class="label">F&amp;B gross</div><div class="value">{{ fmtMoney(pv.fnb_gross) }}</div></div>
        </div>
        <h3 style="margin-top:1rem">Collections by payment method</h3>
        <table><tbody><tr v-for="(v, k) in pv.collections" :key="k"><td>{{ k }}</td><td class="num">{{ fmtMoney(v) }}</td></tr></tbody></table>
        <div v-if="!pv.already_closed && session.can('cinema.day_close')" class="filters" style="margin-top:1rem">
          <div class="field"><label>Cash counted (box office + F&amp;B)</label><input v-model="f.cash_declared" type="number" step="0.01" /></div>
          <div class="field" style="max-width:420px;flex:2"><label>Notes</label><input v-model="f.notes" /></div>
          <div class="field" style="flex:0 0 auto"><button class="btn primary" :disabled="busy" @click="close">Post day close</button></div>
        </div>
        <p class="small muted">Posting splits tax-inclusive prices into revenue and output tax, defers tickets sold for future shows, accrues the distributor's film rental and records the expected settlement for each card / gateway / wallet.</p>
      </div>
    </div>
    <div class="panel">
      <h3>Recent day closes</h3>
      <DataTable :columns="cols" :rows="list">
        <template #actions="{ row }">
          <router-link v-if="row.journal_id" class="btn sm" :to="`/journals/${row.journal_id}`">Journal</router-link>
          <button v-if="row.status === 'POSTED' && session.can('cinema.day_close')" class="btn sm danger" @click="reverse(row)">Reverse</button>
        </template>
      </DataTable>
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtInt, fmtMoney, today } from '../format.js'
import { opt, refs } from '../refs.js'
import { session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import Picker from '../components/Picker.vue'
const f = reactive({ site_id: null, business_date: today(), cash_declared: '', notes: '' })
const sites = ref([]); const pv = ref(null); const list = ref([]); const busy = ref(false)
const cols = [{ key: 'business_date', label: 'Date', type: 'date' }, { key: 'site_id', label: 'Site' }, { key: 'ticket_net_revenue', label: 'Ticket revenue', type: 'money' },
  { key: 'fnb_net_revenue', label: 'F&B revenue', type: 'money' }, { key: 'tax_total', label: 'Output tax', type: 'money' }, { key: 'film_rental', label: 'Film rental', type: 'money' },
  { key: 'deferred_amount', label: 'Deferred', type: 'money' }, { key: 'cash_over_short', label: 'Cash +/-', type: 'money' }, { key: 'status', label: 'Status', type: 'status' }]
async function loadPreview() { if (!f.site_id) return; try { pv.value = await api.get('/cinema/day-close/preview', { site_id: f.site_id, business_date: f.business_date }) } catch (e) { showError(e) } }
async function loadList() { list.value = (await api.get('/cinema/day-close', { page_size: 30 })).items }
async function close() {
  busy.value = true
  try { await api.post('/cinema/day-close', { ...f, cash_declared: f.cash_declared === '' ? null : f.cash_declared }); toast('Day close posted'); loadPreview(); loadList() } catch (e) { showError(e) } finally { busy.value = false }
}
async function reverse(row) {
  const reason = prompt('Reason for reversing this day close?')
  if (!reason) return
  try { await api.post(`/cinema/day-close/${row.id}/reverse`, { reason }); toast('Day close reversed'); loadList() } catch (e) { showError(e) }
}
onMounted(async () => {
  const s = await refs.sites()
  sites.value = s.filter((x) => x.site_type === 'CINEMA').map(opt.coded)
  f.site_id = sites.value[0]?.value || null
  loadList(); loadPreview()
})
</script>
