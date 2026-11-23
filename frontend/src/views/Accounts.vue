<template>
  <div>
    <div class="page-head"><h1>Chart of accounts</h1>
      <div class="actions"><button v-if="session.can('coa.manage')" class="btn primary" @click="openNew()">New account</button></div>
    </div>
    <div class="panel">
      <div class="filters">
        <div class="field" style="max-width:400px;flex:2"><label>Search code or name</label><input v-model="q" /></div>
        <label class="check"><input v-model="postableOnly" type="checkbox" /> Posting accounts only</label>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Code</th><th>Name</th><th class="hide-sm">Type</th><th class="hide-sm">Control</th><th class="hide-sm">Site</th><th class="hide-sm">CC rule</th><th class="hide-sm">P&amp;L / CF</th><th>Status</th><th></th></tr></thead>
          <tbody>
            <tr v-for="a in shown" :key="a.id" :class="a.level < 4 ? (a.level === 1 ? 'st-header' : 'st-subheader') : ''">
              <td class="nowrap">{{ a.code }}</td>
              <td :style="{ paddingLeft: `${(a.level - 1) * 14 + 8}px` }">{{ a.name }} <span v-if="a.is_contra" class="badge">contra</span></td>
              <td class="hide-sm small">{{ a.account_type }} <span class="muted">{{ a.level === 4 ? a.normal_balance : '' }}</span></td>
              <td class="hide-sm small">{{ a.level === 4 ? a.control_type : '' }}<span v-if="a.party_type !== 'NONE' && a.level === 4" class="muted"> · {{ a.party_type }} {{ a.party_rule }}</span></td>
              <td class="hide-sm small">{{ a.level === 4 ? a.site_rule : '' }}</td>
              <td class="hide-sm small">{{ a.level === 4 ? a.cost_centre_rule : '' }}</td>
              <td class="hide-sm small">{{ a.pl_section || a.cash_flow_line }}</td>
              <td><span class="badge" :class="a.is_active ? 'ACTIVE' : 'CLOSED'">{{ a.is_active ? 'Active' : 'Inactive' }}</span></td>
              <td class="nowrap">
                <router-link v-if="a.level === 4" class="btn sm" :to="{ path: '/ledger', query: { account_ids: a.id } }">Ledger</router-link>
                <button v-if="session.can('coa.manage')" class="btn sm" @click="openEdit(a)">Edit</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <Modal v-if="edit" :title="edit.id ? `Edit ${edit.code}` : 'New account'" @close="edit = null">
      <EntityForm :fields="fields" :model="edit" :editing="!!edit.id" />
      <template #footer><button class="btn" @click="edit = null">Cancel</button><button class="btn primary" @click="save">Save</button></template>
    </Modal>
  </div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { lookups, session, toast } from '../store.js'
import EntityForm from '../components/EntityForm.vue'
import Modal from '../components/Modal.vue'
const all = ref([])
const q = ref('')
const postableOnly = ref(false)
const edit = ref(null)
const shown = computed(() => {
  const t = q.value.trim().toLowerCase()
  return all.value.filter((a) => (!postableOnly.value || a.level === 4) && (!t || a.code.startsWith(t) || a.name.toLowerCase().includes(t)))
})
const R = ['REQ', 'OPT', 'NONE']
const fields = [
  { key: 'parent_code', label: 'Parent (group / sub-group) code', required: true, createOnly: true, placeholder: 'e.g. 06-06-06', help: 'The next free code in the parent is assigned automatically' },
  { key: 'name', label: 'Account name', required: true, wide: true },
  { key: 'is_contra', label: 'Contra account', type: 'checkbox', createOnly: true },
  { key: 'control_type', label: 'Control type', type: 'select', options: ['NONE', 'AP_CONTROL', 'AR_CONTROL', 'BANK', 'CASH', 'CLEARING', 'TAX', 'REGISTER'] },
  { key: 'party_type', label: 'Party type', type: 'select', options: ['NONE', 'SUPPLIER', 'CUSTOMER', 'EMPLOYEE'] },
  { key: 'party_rule', label: 'Party code on line', type: 'select', options: R },
  { key: 'site_rule', label: 'Site', type: 'select', options: R },
  { key: 'cost_centre_rule', label: 'Cost centre rule', type: 'select', options: ['BS', 'LOC', 'REQ', 'CORP'] },
  { key: 'pl_section', label: 'P&L section', type: 'select', options: ['REVENUE', 'COST_OF_SALES', 'OPEX', 'DEPRECIATION', 'OTHER_INCOME', 'OTHER_EXPENSE', 'FINANCE_COST', 'TAXATION'] },
  { key: 'revenue_stream', label: 'Revenue stream', type: 'select', options: ['TICKETING', 'FNB', 'ADVERTISING', 'OTHER'] },
  { key: 'cash_flow_line', label: 'Cash flow line' },
  { key: 'manual_journal', label: 'Manual journals', type: 'select', options: ['ALLOWED', 'RESTRICTED', 'NOT_ALLOWED'] },
  { key: 'abnormal_balance', label: 'Abnormal balance', type: 'select', options: ['BLOCK', 'ALERT', 'ALLOW'] },
  { key: 'budget_control', label: 'Budget control', type: 'select', options: ['NONE', 'ADVISORY', 'ABSOLUTE'] },
  { key: 'reconcile_required', label: 'Reconciliation required', type: 'checkbox' },
  { key: 'zero_at_period_end', label: 'Must be nil at period end', type: 'checkbox' },
  { key: 'is_intercompany', label: 'Intercompany', type: 'checkbox' },
  { key: 'requires_attachment', label: 'Attachment required', type: 'checkbox' },
  { key: 'is_active', label: 'Active', type: 'checkbox', editOnly: true },
  { key: 'description', label: 'Description / posting guidance', type: 'textarea' },
]
async function load() { all.value = await api.get('/accounts') }
function openNew() { edit.value = { control_type: 'NONE', party_type: 'NONE', party_rule: 'NONE', site_rule: 'OPT', manual_journal: 'ALLOWED', abnormal_balance: 'ALERT', budget_control: 'NONE' } }
function openEdit(a) { edit.value = { ...a } }
async function save() {
  const e = edit.value
  try {
    if (e.id) {
      const body = {}
      for (const f of fields) if (!f.createOnly && f.key in e) body[f.key] = e[f.key]
      await api.patch(`/accounts/${e.id}`, body)
    } else await api.post('/accounts', e)
    toast('Account saved'); edit.value = null; lookups.invalidate('accounts'); load()
  } catch (err) { showError(err) }
}
onMounted(load)
</script>
