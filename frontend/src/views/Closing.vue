<template>
  <div>
    <div class="page-head"><h1>Periods &amp; month-end close</h1></div>
    <div class="panel">
      <DataTable :columns="cols" :rows="periods">
        <template #actions="{ row }">
          <router-link class="btn sm" :to="`/closing/${row.id}`">Checklist</router-link>
          <button v-if="row.status === 'OPEN' && session.can('period.manage')" class="btn sm" @click="setStatus(row, 'SOFT_CLOSED')">Soft close</button>
          <button v-if="row.status === 'SOFT_CLOSED' && session.can('period.manage')" class="btn sm" @click="setStatus(row, 'OPEN')">Re-open</button>
          <button v-if="row.status === 'CLOSED' && session.can('period.reopen')" class="btn sm danger" @click="reopen(row)">Reopen</button>
          <button v-if="row.status === 'CLOSED' && session.can('period.lock')" class="btn sm" @click="lock(row)">Lock</button>
        </template>
      </DataTable>
    </div>
    <div v-if="session.can('period.close')" class="panel">
      <h2>Year-end close</h2>
      <p class="small muted">Closes income and expense accounts and dividends to unappropriated profit at 30 June. Periods 1 to 11 must be closed first.</p>
      <div class="row"><select v-model="fy" style="max-width:220px"><option v-for="f in fys" :key="f.id" :value="f.id">{{ f.code }} ({{ f.status }})</option></select>
        <button class="btn danger" @click="yearEnd">Post year-end close</button></div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { lookups, session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
const periods = ref([]); const fys = ref([]); const fy = ref(null)
const cols = [{ key: 'name', label: 'Period' }, { key: 'start_date', label: 'From', type: 'date' }, { key: 'end_date', label: 'To', type: 'date' }, { key: 'status', label: 'Status', type: 'status' }, { key: 'status_changed_at', label: 'Changed', type: 'datetime' }]
const load = async () => { periods.value = await api.get('/periods'); fys.value = await api.get('/fiscal-years'); fy.value = fy.value || fys.value[0]?.id; lookups.invalidate('periods') }
async function setStatus(p, status) { try { await api.post(`/periods/${p.id}/status`, { status }); toast('Updated'); load() } catch (e) { showError(e) } }
async function reopen(p) { const reason = prompt('Reason for reopening (recorded in the audit trail)?'); if (!reason) return; try { await api.post(`/closing/${p.id}/reopen`, { reason }); toast('Period reopened'); load() } catch (e) { showError(e) } }
async function lock(p) { const reason = prompt('Locking is permanent. Reason?'); if (!reason) return; try { await api.post(`/periods/${p.id}/status`, { status: 'LOCKED', reason }); toast('Locked'); load() } catch (e) { showError(e) } }
async function yearEnd() { if (!confirm('Post the year-end close journal?')) return; try { const r = await api.post('/closing/year-end', { fiscal_year_id: fy.value }); toast(`Year-end journal ${r.number} posted`); load() } catch (e) { showError(e) } }
onMounted(load)
</script>
