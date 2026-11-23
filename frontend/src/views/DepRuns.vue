<template>
  <div>
    <div class="page-head"><h1>Depreciation runs</h1></div>
    <div v-if="session.can('asset.depreciate')" class="panel">
      <div class="filters"><div class="field"><label>Period</label><select v-model="period"><option v-for="p in periods" :key="p.id" :value="p.id">{{ p.name }} ({{ p.status }})</option></select></div>
        <div class="field" style="flex:0 0 auto"><button class="btn primary" @click="compute">Calculate</button></div></div>
      <p class="small muted">Straight-line from the month of capitalisation; remaining NBV is spread over the remaining life after impairments. The run is posted by a second user.</p>
    </div>
    <div class="panel"><DataTable :columns="cols" :rows="runs" clickable @row="open" /></div>
    <div v-if="run" class="panel">
      <div class="row"><h3>Run #{{ run.id }} - {{ fmtMoney(run.total) }}</h3><span class="spacer"></span>
        <button v-if="run.status === 'DRAFT'" class="btn ok" @click="post">Post run</button>
        <button v-if="run.status === 'POSTED'" class="btn danger" @click="reverse">Reverse run</button></div>
      <DataTable :columns="lineCols" :rows="run.lines" />
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtMoney } from '../format.js'
import { refs } from '../refs.js'
import { session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
const periods = ref([]); const period = ref(null); const runs = ref([]); const run = ref(null)
const cols = [{ key: 'id', label: 'Run' }, { key: 'run_date', label: 'Period end', type: 'date' }, { key: 'line_count', label: 'Assets', type: 'int' }, { key: 'total', label: 'Total', type: 'money' }, { key: 'status', label: 'Status', type: 'status' }]
const lineCols = [{ key: 'asset_code', label: 'Asset' }, { key: 'amount', label: 'Depreciation', type: 'money' }, { key: 'nbv_before', label: 'NBV before', type: 'money' }, { key: 'nbv_after', label: 'NBV after', type: 'money' }]
const load = async () => { runs.value = await api.get('/assets/runs/list') }
const open = async (r) => { run.value = await api.get(`/assets/runs/${r.id}`) }
async function compute() { try { const r = await api.post('/assets/runs', { period_id: period.value }); toast('Calculated'); await load(); open(r) } catch (e) { showError(e) } }
async function post() { try { await api.post(`/assets/runs/${run.value.id}/post`); toast('Posted'); load(); open(run.value) } catch (e) { showError(e) } }
async function reverse() { const reason = prompt('Reason?'); if (!reason) return; try { await api.post(`/assets/runs/${run.value.id}/reverse`, { reason }); toast('Reversed'); load(); open(run.value) } catch (e) { showError(e) } }
onMounted(async () => { periods.value = await refs.periods(); period.value = periods.value.find((p) => p.status === 'OPEN')?.id; load() })
</script>
