<template>
  <div>
    <div class="page-head"><h1>Approval limits</h1></div>
    <div class="panel">
      <p class="small muted">The approver needs a limit at least equal to the document total. Blank maximum = unlimited. Limits can be set per role or per user and optionally per site.</p>
      <DataTable :columns="cols" :rows="limits" clickable @row="(l) => (edit = { ...l })" />
      <button class="btn primary" style="margin-top:.75rem" @click="edit = { doc_type: 'JOURNAL', role_id: null, user_id: null, site_id: null, max_amount: null, is_active: true }">Add limit</button>
    </div>
    <Modal v-if="edit" title="Approval limit" width="min(600px,100%)" @close="edit = null">
      <div class="form-grid">
        <div class="field"><label>Document type</label><select v-model="edit.doc_type"><option v-for="d in docs" :key="d">{{ d }}</option></select></div>
        <div class="field"><label>Role</label><select v-model="edit.role_id"><option :value="null">—</option><option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option></select></div>
        <div class="field"><label>Site</label><select v-model="edit.site_id"><option :value="null">All sites</option><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.name }}</option></select></div>
        <div class="field"><label>Maximum amount (PKR)</label><input v-model="edit.max_amount" type="number" /></div>
        <label class="check"><input v-model="edit.is_active" type="checkbox" /> Active</label>
      </div>
      <template #footer><button class="btn primary" @click="save">Save</button></template>
    </Modal>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtMoney } from '../format.js'
import { refs } from '../refs.js'
import { toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import Modal from '../components/Modal.vue'
const docs = ['JOURNAL', 'AP_INVOICE', 'AP_PAYMENT', 'AR_INVOICE', 'AR_RECEIPT', 'CASH_VOUCHER', 'BANK_TRANSFER']
const limits = ref([]); const roles = ref([]); const sites = ref([]); const edit = ref(null); let roleName = {}
const cols = [{ key: 'doc_type', label: 'Document' }, { key: 'role_id', label: 'Role', render: (l) => roleName[l.role_id] || (l.user_id ? `User #${l.user_id}` : '') },
  { key: 'site_id', label: 'Site', render: (l) => l.site_id || 'All' }, { key: 'max_amount', label: 'Maximum', render: (l) => (l.max_amount == null ? 'Unlimited' : fmtMoney(l.max_amount)) }, { key: 'is_active', label: 'Active', type: 'bool' }]
const load = async () => { limits.value = await api.get('/admin/approval-limits') }
async function save() {
  const e = { ...edit.value, max_amount: edit.value.max_amount === '' ? null : edit.value.max_amount }
  try { if (e.id) await api.patch(`/admin/approval-limits/${e.id}`, e); else await api.post('/admin/approval-limits', e); toast('Saved'); edit.value = null; load() } catch (err) { showError(err) }
}
onMounted(async () => { roles.value = await refs.roles(); roleName = Object.fromEntries(roles.value.map((r) => [r.id, r.name])); sites.value = await refs.sites(); load() })
</script>
