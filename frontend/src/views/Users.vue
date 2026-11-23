<template>
  <div>
    <div class="page-head"><h1>Users</h1><div class="actions"><button class="btn primary" @click="edit = { is_active: true, all_sites: false, role_codes: [], site_ids: [], must_change_password: true }">New user</button></div></div>
    <div class="panel"><DataTable :columns="cols" :rows="users" clickable @row="(u) => (edit = { ...u, password: '', role_codes: [...u.roles], site_ids: [...u.site_ids] })" /></div>
    <Modal v-if="edit" :title="edit.id ? `Edit ${edit.username}` : 'New user'" @close="edit = null">
      <div class="form-grid">
        <div class="field"><label>Username</label><input v-model="edit.username" :disabled="!!edit.id" /></div>
        <div class="field"><label>Full name</label><input v-model="edit.full_name" /></div>
        <div class="field"><label>Email</label><input v-model="edit.email" /></div>
        <div class="field"><label>{{ edit.id ? 'Reset password' : 'Password' }}</label><input v-model="edit.password" type="password" autocomplete="new-password" /></div>
        <label class="check"><input v-model="edit.is_active" type="checkbox" /> Active</label>
        <label class="check"><input v-model="edit.all_sites" type="checkbox" /> Access to all sites</label>
        <label class="check"><input v-model="edit.must_change_password" type="checkbox" /> Must change password</label>
        <div class="field wide"><label>Roles</label><div class="row"><label v-for="r in roles" :key="r.code" class="check"><input v-model="edit.role_codes" type="checkbox" :value="r.code" /> {{ r.name }}</label></div></div>
        <div v-if="!edit.all_sites" class="field wide"><label>Sites</label><div class="row"><label v-for="s in sites" :key="s.id" class="check"><input v-model="edit.site_ids" type="checkbox" :value="s.id" /> {{ s.name }}</label></div></div>
      </div>
      <template #footer><button class="btn" @click="edit = null">Cancel</button><button class="btn primary" @click="save">Save</button></template>
    </Modal>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { refs } from '../refs.js'
import { toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import Modal from '../components/Modal.vue'
const users = ref([]); const roles = ref([]); const sites = ref([]); const edit = ref(null)
const cols = [{ key: 'username', label: 'User' }, { key: 'full_name', label: 'Name' }, { key: 'roles', label: 'Roles', render: (u) => u.roles.join(', ') },
  { key: 'all_sites', label: 'All sites', type: 'bool' }, { key: 'last_login_at', label: 'Last sign-in', type: 'datetime' }, { key: 'is_active', label: 'Active', type: 'bool' }]
const load = async () => { users.value = await api.get('/admin/users') }
async function save() {
  const e = { ...edit.value }
  if (!e.password) delete e.password
  try { if (e.id) await api.patch(`/admin/users/${e.id}`, e); else await api.post('/admin/users', e); toast('Saved'); edit.value = null; load() } catch (err) { showError(err) }
}
onMounted(async () => { load(); roles.value = await refs.roles(); sites.value = await refs.sites() })
</script>
