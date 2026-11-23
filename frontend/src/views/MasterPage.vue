<template>
  <div>
    <div class="page-head"><h1>{{ cfg.title }}</h1>
      <div class="actions"><button v-if="session.can(cfg.perm)" class="btn primary" @click="openNew">New</button></div>
    </div>
    <div class="panel">
      <form class="filters" @submit.prevent="load(1)">
        <div class="field"><label>Search</label><input v-model="q" /></div>
        <div class="field"><label>Status</label><select v-model="active"><option value="">All</option><option value="true">Active</option><option value="false">Inactive</option></select></div>
        <div class="field" style="flex:0 0 auto"><button class="btn">Filter</button></div>
      </form>
      <DataTable :columns="cfg.columns" :rows="rows" :total="total" :page="page" :page-size="100" clickable @row="openEdit" @page="load">
        <template v-if="cfg.links" #actions="{ row }"><router-link v-for="l in cfg.links" :key="l.label" class="btn sm" :to="l.to(row)">{{ l.label }}</router-link></template>
      </DataTable>
    </div>
    <Modal v-if="edit" :title="edit.id ? `Edit ${cfg.title.toLowerCase()}` : `New ${cfg.title.toLowerCase()}`" @close="edit = null">
      <EntityForm :fields="cfg.fields" :model="edit" :editing="!!edit.id" />
      <template #footer><button class="btn" @click="edit = null">Cancel</button><button v-if="session.can(cfg.perm)" class="btn primary" @click="save">Save</button></template>
    </Modal>
  </div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, showError } from '../api.js'
import { MASTERS } from '../masters.js'
import { lookups, session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import EntityForm from '../components/EntityForm.vue'
import Modal from '../components/Modal.vue'
const props = defineProps({ entity: String })
const route = useRoute()
const cfg = computed(() => MASTERS[props.entity])
const rows = ref([]); const total = ref(0); const page = ref(1); const q = ref(route.query.q || ''); const active = ref(''); const edit = ref(null)
async function load(p = 1) {
  try { const r = await api.get(cfg.value.ep, { q: q.value, active: active.value, page: p, page_size: 100 }); rows.value = r.items; total.value = r.total; page.value = p } catch (e) { showError(e) }
}
const openNew = () => { edit.value = { ...(cfg.value.defaults || {}) } }
const openEdit = (r) => { edit.value = { ...r } }
async function save() {
  const e = edit.value
  const body = {}
  for (const f of cfg.value.fields) {
    if (e.id && (f.readonlyEdit || f.createOnly)) continue
    let v = e[f.key]
    if (v === '' && f.type !== 'checkbox') v = null
    if (v !== undefined) body[f.key] = v
  }
  try {
    if (e.id) await api.patch(`${cfg.value.ep}/${e.id}`, body); else await api.post(cfg.value.ep, body)
    toast('Saved'); edit.value = null; if (cfg.value.refKey) lookups.invalidate(cfg.value.refKey); load(page.value)
  } catch (err) { showError(err) }
}
onMounted(load)
</script>
