<template>
  <div>
    <div class="page-head"><h1>Collections &amp; settlements</h1>
      <div class="actions"><router-link class="btn" to="/reports/collections-reconciliation">Reconciliation report</router-link></div></div>
    <div v-if="session.can('cinema.settle')" class="panel">
      <h2>Record an acquirer / gateway / wallet settlement</h2>
      <div class="form-grid">
        <div class="field"><label>Payment method</label><Picker v-model="s.payment_method_id" :options="pms" /></div>
        <div class="field"><label>Credited to bank</label><Picker v-model="s.bank_account_id" :options="banks" /></div>
        <div class="field"><label>Settlement date</label><input v-model="s.settlement_date" type="date" /></div>
        <div class="field"><label>Gross settled</label><input v-model="s.gross_amount" type="number" step="0.01" /></div>
        <div class="field"><label>Charges (MDR)</label><input v-model="s.fee_amount" type="number" step="0.01" /></div>
        <div class="field"><label>Tax deducted</label><input v-model="s.tax_deducted" type="number" step="0.01" /></div>
        <div class="field"><label>Settlement reference</label><input v-model="s.reference" /></div>
      </div>
      <p class="small">Net to bank: <strong>{{ fmtMoney(Number(s.gross_amount || 0) - Number(s.fee_amount || 0) - Number(s.tax_deducted || 0)) }}</strong> · allocated to the oldest open collections of the method.</p>
      <button class="btn primary" @click="settle">Post settlement</button>
    </div>
    <div class="panel">
      <div class="row"><h3>Expected collections</h3><span class="spacer"></span>
        <select v-model="status" style="max-width:200px" @change="load"><option value="OPEN,PARTIAL">Open</option><option value="">All</option><option value="SETTLED">Settled</option></select></div>
      <DataTable :columns="cols" :rows="rows" />
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtMoney, today } from '../format.js'
import { opt, refs } from '../refs.js'
import { session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import Picker from '../components/Picker.vue'
const s = reactive({ payment_method_id: null, bank_account_id: null, settlement_date: today(), gross_amount: '', fee_amount: '', tax_deducted: '', reference: '' })
const pms = ref([]); const banks = ref([]); const rows = ref([]); const status = ref('OPEN,PARTIAL'); let pmName = {}
const cols = [{ key: 'business_date', label: 'Business date', type: 'date' }, { key: 'site_id', label: 'Site' }, { key: 'payment_method_id', label: 'Method', render: (r) => pmName[r.payment_method_id] },
  { key: 'expected_amount', label: 'Expected', type: 'money' }, { key: 'settled_gross', label: 'Settled', type: 'money' }, { key: 'fee_amount', label: 'Charges', type: 'money' },
  { key: 'net_received', label: 'Net received', type: 'money' }, { key: 'difference', label: 'Outstanding', type: 'money' }, { key: 'status', label: 'Status', type: 'status' }]
const load = async () => { rows.value = await api.get('/cinema/collections', { status: status.value }) }
async function settle() {
  try { await api.post('/cinema/settlements', { ...s, fee_amount: s.fee_amount || 0, tax_deducted: s.tax_deducted || 0 }); toast('Settlement posted'); load() } catch (e) { showError(e) }
}
onMounted(async () => {
  const p = await refs.paymentMethods()
  pmName = Object.fromEntries(p.map((x) => [x.id, x.name]))
  pms.value = p.filter((x) => !['CASH', 'VOUCHER'].includes(x.method_type)).map(opt.coded)
  banks.value = (await refs.bankAccounts()).filter((b) => b.kind === 'BANK').map(opt.coded)
  load()
})
</script>
