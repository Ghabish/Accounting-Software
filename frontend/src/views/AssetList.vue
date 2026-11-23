<template>
  <div>
    <div class="page-head"><h1>Fixed asset register</h1>
      <div class="actions"><button v-if="session.can('asset.manage')" class="btn primary" @click="openNew">New asset</button></div></div>
    <div class="panel">
      <form class="filters" @submit.prevent="load(1)">
        <div class="field"><label>Search</label><input v-model="q" placeholder="Code, name, tag" /></div>
        <div class="field"><label>Status</label><select v-model="status"><option value="">All</option><option>DRAFT</option><option>ACTIVE</option><option>FULLY_DEPRECIATED</option><option>DISPOSED</option></select></div>
        <div class="field" style="flex:0 0 auto"><button class="btn">Filter</button></div>
      </form>
      <DataTable :columns="cols" :rows="rows" :total="total" :page="page" :page-size="100" :row-link="(r) => `/assets/${r.id}`" @page="load" />
    </div>
    <Modal v-if="edit" title="New fixed asset" @close="edit = null">
      <EntityForm :fields="fields" :model="edit" />
      <template #footer><button class="btn" @click="edit = null">Cancel</button><button class="btn primary" @click="save">Create</button></template>
    </Modal>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, showError } from '../api.js'
import { today } from '../format.js'
import { opt, refs } from '../refs.js'
import { session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import EntityForm from '../components/EntityForm.vue'
import Modal from '../components/Modal.vue'
const router = useRouter()
const rows = ref([]); const total = ref(0); const page = ref(1); const q = ref(''); const status = ref(''); const edit = ref(null)
const cols = [{ key: 'code', label: 'Code' }, { key: 'name', label: 'Name' }, { key: 'capitalisation_date', label: 'Capitalised', type: 'date' }, { key: 'useful_life_months', label: 'Life (m)', type: 'int' },
  { key: 'cost', label: 'Cost', type: 'money' }, { key: 'accumulated_depreciation', label: 'Acc. dep.', type: 'money' }, { key: 'net_book_value', label: 'NBV', type: 'money' }, { key: 'status', label: 'Status', type: 'status' }]
const fields = [{ key: 'name', label: 'Description', required: true, wide: true },
  { key: 'category_id', label: 'Category', type: 'picker', required: true, load: async () => (await refs.assetCategories()).map(opt.coded) },
  { key: 'site_id', label: 'Site', type: 'picker', required: true, load: async () => (await refs.sites()).map(opt.coded) },
  { key: 'cost_centre_id', label: 'Cost centre', type: 'picker', required: true, load: async () => (await refs.costCentres()).map(opt.coded) },
  { key: 'supplier_id', label: 'Supplier', type: 'picker', load: async () => (await refs.suppliers()).map(opt.coded) },
  { key: 'purchase_date', label: 'Purchase date', type: 'date', required: true }, { key: 'capitalisation_date', label: 'Capitalisation date', type: 'date' },
  { key: 'cost', label: 'Cost', type: 'number', required: true }, { key: 'residual_value', label: 'Residual value', type: 'number' },
  { key: 'useful_life_months', label: 'Useful life (months, blank = category default)', type: 'number' },
  { key: 'method', label: 'Method', type: 'select', options: ['STRAIGHT_LINE', 'REDUCING_BALANCE'] }, { key: 'reducing_rate', label: 'Reducing balance rate', type: 'number', step: '0.01' },
  { key: 'serial_no', label: 'Serial no.' }, { key: 'tag_no', label: 'Tag / barcode' }]
async function load(p = 1) { try { const r = await api.get('/assets', { q: q.value, status: status.value, page: p }); rows.value = r.items; total.value = r.total; page.value = p } catch (e) { showError(e) } }
const openNew = () => { edit.value = { purchase_date: today(), method: 'STRAIGHT_LINE', residual_value: 0 } }
async function save() {
  const b = { ...edit.value }
  for (const k of Object.keys(b)) if (b[k] === '') b[k] = null
  try { const a = await api.post('/assets', b); toast('Asset created - capitalise it next'); router.push(`/assets/${a.id}`) } catch (e) { showError(e) }
}
onMounted(load)
</script>
