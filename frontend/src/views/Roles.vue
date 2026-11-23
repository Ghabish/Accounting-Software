<template>
  <div>
    <div class="page-head"><h1>Roles &amp; permissions</h1></div>
    <div class="grid two">
      <div class="panel"><DataTable :columns="[{ key: 'code', label: 'Code' }, { key: 'name', label: 'Role' }, { key: 'permissions', label: 'Permissions', render: (r) => r.permissions.length }]" :rows="roles" clickable @row="pick" /></div>
      <div v-if="sel" class="panel">
        <div class="row"><h2>{{ sel.name }}</h2><span class="spacer"></span><button class="btn primary" @click="save">Save permissions</button></div>
        <div v-for="(perms, mod) in grouped" :key="mod" style="margin-bottom:.6rem"><h3>{{ mod }}</h3>
          <div class="row"><label v-for="p in perms" :key="p.code" class="check small" :title="p.description"><input v-model="chosen" type="checkbox" :value="p.code" /> {{ p.code.split('.')[1] }}</label></div></div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { lookups, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
const roles = ref([]); const perms = ref([]); const sel = ref(null); const chosen = ref([])
const grouped = computed(() => perms.value.reduce((g, p) => { (g[p.module] = g[p.module] || []).push(p); return g }, {}))
const load = async () => { roles.value = await api.get('/admin/roles'); perms.value = await api.get('/admin/permissions') }
const pick = (r) => { sel.value = r; chosen.value = [...r.permissions] }
async function save() { try { await api.put(`/admin/roles/${sel.value.id}/permissions`, { permissions: chosen.value }); toast('Saved'); lookups.invalidate('roles'); load() } catch (e) { showError(e) } }
onMounted(load)
</script>
