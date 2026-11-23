<template>
  <div>
    <div class="page-head"><h1>Workflow settings</h1></div>
    <div class="panel">
      <div class="table-wrap"><table><thead><tr><th>Document</th><th>Check stage</th><th>Segregation of duties</th><th>Auto-post on approval</th><th>Attachment required</th></tr></thead>
        <tbody><tr v-for="w in items" :key="w.id"><td>{{ w.name }}</td>
          <td v-for="k in keys" :key="k"><input v-model="w[k]" type="checkbox" @change="save(w, k)" /></td></tr></tbody></table></div>
      <p class="small muted">Segregation of duties prevents the preparer from checking, approving or posting their own documents (and the checker from approving).</p>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { toast } from '../store.js'
const items = ref([]); const keys = ['require_check', 'segregation_of_duties', 'auto_post_on_approval', 'require_attachment']
const load = async () => { items.value = await api.get('/admin/workflows') }
async function save(w, k) { try { await api.patch(`/admin/workflows/${w.id}`, { [k]: w[k] }); toast('Saved') } catch (e) { showError(e); load() } }
onMounted(load)
</script>
