<template>
  <div>
    <div class="page-head"><h1>{{ id ? 'Edit voucher' : 'New cash / bank voucher' }}</h1></div>
    <div class="panel">
      <div class="form-grid">
        <div class="field"><label>Type</label><select v-model="v.direction"><option value="PAYMENT">Payment</option><option value="RECEIPT">Receipt</option></select></div>
        <div class="field" style="grid-column: span 2"><label>Bank / cash account <span class="req">*</span></label><Picker v-model="v.bank_account_id" :options="banks" /></div>
        <div class="field"><label>Date</label><input v-model="v.voucher_date" type="date" /></div>
        <div class="field"><label>Payee / payer</label><input v-model="v.counterparty" /></div>
        <div class="field"><label>Cheque no.</label><input v-model="v.cheque_no" /></div>
        <div class="field wide"><label>Description</label><input v-model="v.description" /></div>
      </div>
      <p class="small muted">Supplier and customer settlements go through AP payments and AR receipts so that sub-ledgers stay reconciled.</p>
    </div>
    <div class="panel"><LineEditor :lines="v.lines" party tax-field="tax_code_id" tax-label="Withholding / tax deducted"
      :account-filter="(a) => !['AP_CONTROL', 'AR_CONTROL'].includes(a.control_type) && a.cash_flow_line !== 'CASH'"
      :tax-filter="(t) => ['WHT_DEDUCTED', 'WHT_SUFFERED', 'ADVANCE_TAX'].includes(t.tax_type)" /></div>
    <div class="row"><span class="spacer"></span><button class="btn" @click="$router.back()">Cancel</button><button class="btn primary" @click="save">Save draft</button></div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, showError } from '../api.js'
import { today } from '../format.js'
import { opt, refs } from '../refs.js'
import { toast } from '../store.js'
import LineEditor from '../components/LineEditor.vue'
import Picker from '../components/Picker.vue'
const route = useRoute(); const router = useRouter(); const id = route.params.id
const v = reactive({ direction: 'PAYMENT', bank_account_id: null, voucher_date: today(), counterparty: '', cheque_no: '', description: '',
  lines: [{ account_id: null, site_id: null, cost_centre_id: null, description: '', amount: '' }] })
const banks = ref([])
async function save() {
  const body = { ...v, lines: v.lines.filter((l) => l.account_id).map((l) => ({ account_id: l.account_id, site_id: l.site_id, cost_centre_id: l.cost_centre_id,
    supplier_id: l.supplier_id || null, customer_id: l.customer_id || null, employee_id: l.employee_id || null, description: l.description, amount: l.amount,
    tax_code_id: l.tax_code_id || null })) }
  try { const x = id ? await api.put(`/banking/vouchers/${id}`, body) : await api.post('/banking/vouchers', body); toast(`Saved ${x.number}`); router.push(`/bank/vouchers/${x.id}`) } catch (e) { showError(e) }
}
onMounted(async () => {
  banks.value = (await refs.bankAccounts()).map(opt.coded)
  if (id) {
    const x = await api.get(`/banking/vouchers/${id}`)
    Object.assign(v, { direction: ['BPV', 'CPV'].includes(x.voucher_type) ? 'PAYMENT' : 'RECEIPT', bank_account_id: x.bank_account_id, voucher_date: x.voucher_date,
      counterparty: x.counterparty || '', cheque_no: x.cheque_no || '', description: x.description,
      lines: x.lines.map((l) => ({ ...l, amount: Number(l.amount) })) })
  }
})
</script>
