<template>
  <div>
    <div class="page-head"><h1>Recurring journals</h1>
      <div class="actions">
        <input v-model="asOf" type="date" style="max-width:170px" />
        <button v-if="session.can('journal.create')" class="btn" @click="run">Generate due journals</button>
        <button v-if="session.can('journal.create')" class="btn primary" @click="openNew">New template</button>
      </div>
    </div>
    <div class="panel"><DataTable :columns="cols" :rows="items" clickable @row="openEdit" /></div>
    <Modal v-if="edit" :title="edit.id ? 'Edit recurring journal' : 'New recurring journal'" width="min(1200px,100%)" @close="edit = null">
      <div class="form-grid">
        <div class="field"><label>Name</label><input v-model="edit.name" /></div>
        <div class="field"><label>Frequency</label><select v-model="edit.frequency"><option>MONTHLY</option><option>QUARTERLY</option><option>YEARLY</option></select></div>
        <div class="field"><label>Next run date</label><input v-model="edit.next_run_date" type="date" /></div>
        <div class="field"><label>End date</label><input v-model="edit.end_date" type="date" /></div>
        <div class="field"><label class="check"><input v-model="edit.auto_submit" type="checkbox" /> Submit for approval automatically</label></div>
        <div class="field wide"><label>Narration</label><input v-model="edit.description" /></div>
      </div>
      <div style="margin-top:1rem"><LineEditor :lines="edit.lines" drcr party /></div>
      <template #footer><button class="btn" @click="edit = null">Cancel</button><button class="btn primary" @click="save">Save</button></template>
    </Modal>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { today } from '../format.js'
import { session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import LineEditor from '../components/LineEditor.vue'
import Modal from '../components/Modal.vue'
const items = ref([]); const edit = ref(null); const asOf = ref(today())
const cols = [{ key: 'name', label: 'Name' }, { key: 'frequency', label: 'Frequency' }, { key: 'next_run_date', label: 'Next run', type: 'date' },
  { key: 'end_date', label: 'Ends', type: 'date' }, { key: 'auto_submit', label: 'Auto-submit', type: 'bool' }, { key: 'is_active', label: 'Active', type: 'bool' }]
const load = async () => { items.value = await api.get('/recurring-journals') }
const openNew = () => { edit.value = { name: '', description: '', frequency: 'MONTHLY', next_run_date: today(), end_date: '', auto_submit: false, is_active: true, lines: [{}, {}] } }
const openEdit = (r) => { edit.value = { ...r, end_date: r.end_date || '', lines: r.lines.map((l) => ({ ...l, debit: Number(l.debit) || '', credit: Number(l.credit) || '' })) } }
async function save() {
  const e = edit.value
  const body = { ...e, end_date: e.end_date || null, lines: e.lines.filter((l) => l.account_id).map((l) => ({ account_id: l.account_id, site_id: l.site_id || null,
    cost_centre_id: l.cost_centre_id || null, supplier_id: l.supplier_id || null, customer_id: l.customer_id || null, description: l.description, debit: l.debit || 0, credit: l.credit || 0 })) }
  try { if (e.id) await api.put(`/recurring-journals/${e.id}`, body); else await api.post('/recurring-journals', body); toast('Saved'); edit.value = null; load() } catch (err) { showError(err) }
}
async function run() { try { const r = await api.post('/recurring-journals/run', { as_of: asOf.value }); toast(`${r.created.length} journal(s) generated`); load() } catch (e) { showError(e) } }
onMounted(load)
</script>
