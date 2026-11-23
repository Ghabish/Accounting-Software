<template>
  <div class="table-wrap">
    <table class="lines-table">
      <thead><tr>
        <th style="min-width:260px">Account</th><th style="min-width:150px">Site</th><th style="min-width:150px">Cost centre</th>
        <th v-if="party" style="min-width:180px">Party</th><th v-if="dims" style="min-width:170px">Dimension</th>
        <th style="min-width:160px">Description</th>
        <template v-if="drcr"><th class="num">Debit</th><th class="num">Credit</th></template>
        <th v-else class="num">Amount</th>
        <th v-if="taxField" style="min-width:170px">{{ taxLabel }}</th>
        <th></th>
      </tr></thead>
      <tbody>
        <tr v-for="(l, i) in lines" :key="i">
          <td><Picker v-model="l.account_id" :options="accounts" placeholder="Account" @change="onAccount(l, $event)" /></td>
          <td><Picker v-model="l.site_id" :options="sites" placeholder="Site" /></td>
          <td><Picker v-model="l.cost_centre_id" :options="ccs" placeholder="Cost centre" /></td>
          <td v-if="party">
            <Picker v-if="partyType(l) === 'SUPPLIER'" v-model="l.supplier_id" :options="suppliers" placeholder="Supplier" />
            <Picker v-else-if="partyType(l) === 'CUSTOMER'" v-model="l.customer_id" :options="customers" placeholder="Customer" />
            <Picker v-else-if="partyType(l) === 'EMPLOYEE'" v-model="l.employee_id" :options="employees" placeholder="Employee" />
            <span v-else class="muted small">n/a</span>
          </td>
          <td v-if="dims"><Picker v-model="l._dim" :options="dimValues" placeholder="Film / screen…" /></td>
          <td><input v-model="l.description" /></td>
          <template v-if="drcr">
            <td><input v-model="l.debit" type="number" step="0.01" min="0" class="num" style="min-width:120px" /></td>
            <td><input v-model="l.credit" type="number" step="0.01" min="0" class="num" style="min-width:120px" /></td>
          </template>
          <td v-else><input v-model="l.amount" type="number" step="0.01" min="0" class="num" style="min-width:130px" /></td>
          <td v-if="taxField"><Picker v-model="l[taxField]" :options="taxCodes" placeholder="Default" /></td>
          <td><button class="btn sm ghost" title="Remove" @click="lines.splice(i, 1)">✕</button></td>
        </tr>
      </tbody>
      <tfoot>
        <tr>
          <td :colspan="3 + (party ? 1 : 0) + (dims ? 1 : 0) + 1"><button class="btn sm" @click="add">+ Add line</button></td>
          <template v-if="drcr"><td class="num"><strong>{{ fmtMoney(totDr) }}</strong></td><td class="num"><strong>{{ fmtMoney(totCr) }}</strong></td></template>
          <td v-else class="num"><strong>{{ fmtMoney(totAmt) }}</strong></td>
          <td :colspan="taxField ? 2 : 1"><span v-if="drcr" class="badge" :class="balanced ? 'PASS' : 'FAIL'">{{ balanced ? 'Balanced' : `Difference ${fmtMoney(totDr - totCr)}` }}</span></td>
        </tr>
      </tfoot>
    </table>
  </div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { fmtMoney } from '../format.js'
import { opt, refs } from '../refs.js'
import Picker from './Picker.vue'
const props = defineProps({ lines: Array, drcr: Boolean, party: Boolean, dims: Boolean, taxField: String, taxLabel: { type: String, default: 'Tax code' },
  taxFilter: Function, accountFilter: Function })
const accounts = ref([]); const accMap = ref({}); const sites = ref([]); const ccs = ref([]); const suppliers = ref([]); const customers = ref([])
const employees = ref([]); const dimValues = ref([]); const taxCodes = ref([])
const n = (v) => Number(v || 0)
const totDr = computed(() => props.lines.reduce((s, l) => s + n(l.debit), 0))
const totCr = computed(() => props.lines.reduce((s, l) => s + n(l.credit), 0))
const totAmt = computed(() => props.lines.reduce((s, l) => s + n(l.amount), 0))
const balanced = computed(() => Math.abs(totDr.value - totCr.value) < 0.005 && totDr.value > 0)
const partyType = (l) => accMap.value[l.account_id]?.party_type
function add() { props.lines.push({ account_id: null, site_id: props.lines.at(-1)?.site_id ?? null, cost_centre_id: null, description: props.lines.at(-1)?.description ?? '', debit: '', credit: '', amount: '' }) }
function onAccount(l, a) { if (a && a.site_rule === 'NONE') l.site_id = null; if (a && a.cost_centre_rule === 'BS') l.cost_centre_id = null }
onMounted(async () => {
  const accs = await refs.accounts()
  accMap.value = Object.fromEntries(accs.map((a) => [a.id, a]))
  accounts.value = accs.filter((a) => !props.accountFilter || props.accountFilter(a)).map(opt.account)
  sites.value = (await refs.sites()).map(opt.coded)
  ccs.value = (await refs.costCentres()).map(opt.coded)
  if (props.party) {
    suppliers.value = (await refs.suppliers()).map(opt.coded)
    customers.value = (await refs.customers()).map(opt.coded)
    employees.value = (await refs.employees()).map(opt.coded)
  }
  if (props.dims) dimValues.value = (await refs.dimValues()).map(opt.coded)
  if (props.taxField) taxCodes.value = (await refs.taxCodes()).filter((t) => !props.taxFilter || props.taxFilter(t)).map((t) => ({ value: t.id, label: `${t.code} ${t.name}` }))
})
</script>
