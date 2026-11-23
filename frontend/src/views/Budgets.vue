<template>
  <div>
    <div class="page-head"><h1>Budgets</h1>
      <div class="actions"><button v-if="session.can('budget.manage')" class="btn primary" @click="creating = true">New budget</button></div></div>
    <div class="panel">
      <DataTable :columns="[{ key: 'name', label: 'Budget' }, { key: 'fiscal_year_id', label: 'FY' }, { key: 'versions', label: 'Versions', render: (b) => b.versions.map((v) => `${v.label} (${v.status})`).join(' · ') }]"
                 :rows="budgets" clickable @row="selectBudget" />
    </div>
    <div v-if="budget" class="panel">
      <div class="row"><h2>{{ budget.name }}</h2>
        <select v-model="versionId" style="max-width:260px" @change="loadLines"><option v-for="v in budget.versions" :key="v.id" :value="v.id">{{ v.label }} - {{ v.status }}</option></select>
        <span class="spacer"></span>
        <button v-if="version?.status === 'DRAFT' && session.can('budget.approve')" class="btn ok" @click="approve">Approve version</button>
        <button v-if="version?.status !== 'DRAFT' && session.can('budget.manage')" class="btn" @click="revise">Create revision</button>
      </div>
      <p class="small muted">Enter monthly amounts by account, site and cost centre. Revenue and costs are entered as positive figures. Approved versions are locked; revisions keep the full history.</p>
      <div class="filters">
        <div class="field" style="max-width:360px;flex:2"><label>Account</label><Picker v-model="g.account_id" :options="accounts" /></div>
        <div class="field"><label>Site</label><Picker v-model="g.site_id" :options="sites" /></div>
        <div class="field"><label>Cost centre</label><Picker v-model="g.cost_centre_id" :options="ccs" /></div>
        <div class="field"><label>Same amount each month</label><input v-model="g.fill" type="number" @change="fillAll" /></div>
      </div>
      <div class="table-wrap"><table><thead><tr><th v-for="p in periods" :key="p.id" class="num">{{ p.name }}</th><th class="num">Total</th></tr></thead>
        <tbody><tr><td v-for="p in periods" :key="p.id"><input v-model="g.amounts[p.id]" type="number" class="num" style="min-width:95px" :disabled="version?.status !== 'DRAFT'" /></td>
          <td class="num"><strong>{{ fmtMoney(Object.values(g.amounts).reduce((s, v) => s + Number(v || 0), 0)) }}</strong></td></tr></tbody></table></div>
      <div class="row" style="margin-top:.6rem"><span class="spacer"></span><button class="btn primary" :disabled="version?.status !== 'DRAFT'" @click="saveRow">Save budget line</button></div>
      <h3 style="margin-top:1rem">Lines in this version</h3>
      <DataTable :columns="lineCols" :rows="lineSummary" clickable @row="editRow" />
    </div>
    <Modal v-if="creating" title="New budget" width="min(520px,100%)" @close="creating = false">
      <div class="form-grid"><div class="field"><label>Fiscal year</label><select v-model="nb.fiscal_year_id"><option v-for="f in fys" :key="f.id" :value="f.id">{{ f.code }}</option></select></div>
        <div class="field"><label>Name</label><input v-model="nb.name" /></div></div>
      <template #footer><button class="btn primary" @click="create">Create</button></template>
    </Modal>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtMoney } from '../format.js'
import { opt, refs } from '../refs.js'
import { session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import Modal from '../components/Modal.vue'
import Picker from '../components/Picker.vue'
const budgets = ref([]); const budget = ref(null); const versionId = ref(null); const lines = ref([]); const creating = ref(false)
const fys = ref([]); const nb = reactive({ fiscal_year_id: null, name: '' }); const accounts = ref([]); const sites = ref([]); const ccs = ref([]); const allPeriods = ref([])
const g = reactive({ account_id: null, site_id: null, cost_centre_id: null, fill: '', amounts: {} })
const version = computed(() => budget.value?.versions.find((v) => v.id === versionId.value))
const periods = computed(() => allPeriods.value.filter((p) => p.fiscal_year_id === budget.value?.fiscal_year_id))
const accName = ref({})
const lineSummary = computed(() => {
  const m = {}
  for (const l of lines.value) {
    const k = `${l.account_id}|${l.site_id}|${l.cost_centre_id}`
    m[k] = m[k] || { key: k, account_id: l.account_id, site_id: l.site_id, cost_centre_id: l.cost_centre_id, total: 0 }
    m[k].total += Number(l.amount)
  }
  return Object.values(m)
})
const lineCols = [{ key: 'account_id', label: 'Account', render: (r) => accName.value[r.account_id] }, { key: 'site_id', label: 'Site' }, { key: 'cost_centre_id', label: 'CC' }, { key: 'total', label: 'Annual total', type: 'money' }]
async function load() { budgets.value = await api.get('/budgets') }
async function selectBudget(b) { budget.value = b; versionId.value = b.versions.at(-1).id; loadLines() }
async function loadLines() { lines.value = await api.get(`/budgets/versions/${versionId.value}/lines`) }
function fillAll() { for (const p of periods.value) g.amounts[p.id] = g.fill }
function editRow(r) {
  Object.assign(g, { account_id: r.account_id, site_id: r.site_id, cost_centre_id: r.cost_centre_id, amounts: {} })
  for (const l of lines.value) if (`${l.account_id}|${l.site_id}|${l.cost_centre_id}` === r.key) g.amounts[l.period_id] = Number(l.amount)
}
async function saveRow() {
  const body = periods.value.filter((p) => g.amounts[p.id] !== undefined && g.amounts[p.id] !== '').map((p) => ({ account_id: g.account_id, site_id: g.site_id, cost_centre_id: g.cost_centre_id, period_id: p.id, amount: g.amounts[p.id] }))
  try { await api.put(`/budgets/versions/${versionId.value}/lines`, body); toast('Saved'); loadLines() } catch (e) { showError(e) }
}
async function approve() { try { await api.post(`/budgets/versions/${versionId.value}/approve`); toast('Approved'); await load(); selectBudget(budgets.value.find((b) => b.id === budget.value.id)) } catch (e) { showError(e) } }
async function revise() { const reason = prompt('Reason for the revision?'); if (!reason) return; try { await api.post(`/budgets/${budget.value.id}/revise`, { reason }); toast('Revision created'); await load(); selectBudget(budgets.value.find((b) => b.id === budget.value.id)) } catch (e) { showError(e) } }
async function create() { try { await api.post('/budgets', nb); creating.value = false; load() } catch (e) { showError(e) } }
onMounted(async () => {
  load()
  fys.value = await refs.fiscalYears(); nb.fiscal_year_id = fys.value[0]?.id
  allPeriods.value = await refs.periods()
  const accs = await refs.accounts()
  accName.value = Object.fromEntries(accs.map((a) => [a.id, `${a.code} ${a.name}`]))
  accounts.value = accs.filter((a) => a.pl_section).map(opt.account)
  sites.value = (await refs.sites()).map(opt.coded); ccs.value = (await refs.costCentres()).map(opt.coded)
})
</script>
