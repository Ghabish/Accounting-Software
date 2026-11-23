<template>
  <div>
    <div class="page-head"><h1>Audit trail</h1></div>
    <div class="panel">
      <form class="filters" @submit.prevent="load(1)">
        <div class="field"><label>Action contains</label><input v-model="f.action" placeholder="e.g. journal.post" /></div>
        <div class="field"><label>Entity type</label><input v-model="f.entity_type" placeholder="journal, period…" /></div>
        <div class="field"><label>Entity id</label><input v-model="f.entity_id" /></div>
        <div class="field"><label>From</label><input v-model="f.date_from" type="date" /></div>
        <div class="field"><label>To</label><input v-model="f.date_to" type="date" /></div>
        <div class="field" style="flex:0 0 auto"><button class="btn">Search</button></div>
      </form>
      <DataTable :columns="cols" :rows="rows" :total="total" :page="page" :page-size="100" clickable @row="(r) => (sel = r)" @page="load" />
    </div>
    <div v-if="sel" class="panel">
      <h3>Entry #{{ sel.id }}</h3>
      <div class="grid two"><div><strong class="small">Old values</strong><pre class="small">{{ JSON.stringify(sel.old_values, null, 2) }}</pre></div>
        <div><strong class="small">New values</strong><pre class="small">{{ JSON.stringify(sel.new_values, null, 2) }}</pre></div></div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, showError } from '../api.js'
import DataTable from '../components/DataTable.vue'
const f = reactive({ action: '', entity_type: '', entity_id: '', date_from: '', date_to: '' })
const rows = ref([]); const total = ref(0); const page = ref(1); const sel = ref(null)
const cols = [{ key: 'ts', label: 'When', type: 'datetime' }, { key: 'username', label: 'User' }, { key: 'action', label: 'Action' }, { key: 'entity_type', label: 'Entity' },
  { key: 'entity_id', label: 'Id' }, { key: 'ip_address', label: 'IP' }, { key: 'notes', label: 'Notes' }]
async function load(p = 1) { try { const r = await api.get('/admin/audit', { ...f, page: p, page_size: 100 }); rows.value = r.items; total.value = r.total; page.value = p } catch (e) { showError(e) } }
onMounted(load)
</script>
