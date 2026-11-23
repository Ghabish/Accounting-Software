<template>
  <div>
    <div class="page-head"><h1>Tax deposits (CPR / PSID)</h1>
      <div class="actions"><button class="btn" @click="api.download('/tax/reports/working-papers', { date_from: d.date_from, date_to: d.date_to, format: 'xlsx' }).catch(showError)">Tax return working papers (Excel)</button></div></div>
    <div class="panel">
      <p class="small muted">Pays the selected withheld / output tax to the authority from a bank account and stamps the CPR number on every covered tax transaction.</p>
      <div class="form-grid">
        <div class="field wide"><label>Tax codes</label>
          <div class="row"><label v-for="t in codes" :key="t.id" class="check"><input v-model="d.tax_code_ids" type="checkbox" :value="t.id" /> {{ t.code }}</label></div></div>
        <div class="field"><label>Transactions from</label><input v-model="d.date_from" type="date" /></div>
        <div class="field"><label>Transactions to</label><input v-model="d.date_to" type="date" /></div>
        <div class="field"><label>Paid from</label><Picker v-model="d.bank_account_id" :options="banks" /></div>
        <div class="field"><label>Deposit date</label><input v-model="d.deposit_date" type="date" /></div>
        <div class="field"><label>CPR / PSID number</label><input v-model="d.cpr_number" /></div>
      </div>
      <button class="btn primary" style="margin-top:.75rem" @click="deposit">Record deposit</button>
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, showError } from '../api.js'
import { monthEnd, monthStart, today } from '../format.js'
import { opt, refs } from '../refs.js'
import { toast } from '../store.js'
import Picker from '../components/Picker.vue'
const d = reactive({ tax_code_ids: [], date_from: monthStart(), date_to: monthEnd(), bank_account_id: null, deposit_date: today(), cpr_number: '' })
const codes = ref([]); const banks = ref([])
async function deposit() { try { const r = await api.post('/tax/deposits', d); toast(`Deposit posted (${r.number}) for ${r.amount}`) } catch (e) { showError(e) } }
onMounted(async () => {
  codes.value = (await refs.taxCodes()).filter((t) => ['WHT_DEDUCTED', 'ST_WITHHELD', 'SALES_TAX_OUTPUT', 'PST_OUTPUT', 'ENTERTAINMENT_DUTY'].includes(t.tax_type))
  banks.value = (await refs.bankAccounts()).filter((b) => b.kind === 'BANK').map(opt.coded)
})
</script>
