<template>
  <div>
    <div class="page-head"><h1>{{ id ? 'Edit receipt' : 'New customer receipt' }}</h1></div>
    <div class="panel">
      <div class="form-grid">
        <div class="field" style="grid-column: span 2"><label>Customer <span class="req">*</span></label><Picker v-model="r.customer_id" :options="customers" @change="loadOpen" /></div>
        <div class="field"><label>Date</label><input v-model="r.receipt_date" type="date" /></div>
        <div class="field"><label>Bank / cash account <span class="req">*</span></label><Picker v-model="r.bank_account_id" :options="banks" /></div>
        <div class="field"><label>Amount received in bank</label><input v-model="r.amount_received" type="number" step="0.01" /></div>
        <div class="field"><label>Tax deducted by customer</label><input v-model="r.tax_deducted" type="number" step="0.01" /></div>
        <div class="field"><label>Reference</label><input v-model="r.reference" /></div>
        <div class="field wide"><label>Description</label><input v-model="r.description" /></div>
      </div>
    </div>
    <div class="panel">
      <h3>Allocate to open invoices (unallocated amount is held as a customer advance)</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Invoice</th><th>Due</th><th class="num">Outstanding</th><th class="num">Allocate</th></tr></thead>
        <tbody>
          <tr v-if="!open.length"><td colspan="4" class="empty">No open invoices</td></tr>
          <tr v-for="o in open" :key="o.document_id"><td>{{ o.number }}</td><td>{{ fmtDate(o.due_date) }}</td><td class="num">{{ fmtMoney(o.open) }}</td>
            <td><input v-model="o.amount" type="number" step="0.01" class="num" /></td></tr>
        </tbody>
      </table></div>
      <p class="small">Gross receipt {{ fmtMoney(gross) }} · allocated {{ fmtMoney(allocated) }} · advance {{ fmtMoney(gross - allocated) }}</p>
    </div>
    <div class="row"><span class="spacer"></span><button class="btn" @click="$router.back()">Cancel</button><button class="btn primary" @click="save">Save draft</button></div>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, showError } from '../api.js'
import { fmtDate, fmtMoney, today } from '../format.js'
import { opt, refs } from '../refs.js'
import { toast } from '../store.js'
import Picker from '../components/Picker.vue'
const route = useRoute(); const router = useRouter(); const id = route.params.id
const r = reactive({ customer_id: null, receipt_date: today(), bank_account_id: null, amount_received: '', tax_deducted: '', reference: '', description: '' })
const open = ref([]); const customers = ref([]); const banks = ref([])
const gross = computed(() => Number(r.amount_received || 0) + Number(r.tax_deducted || 0))
const allocated = computed(() => open.value.reduce((s, o) => s + Number(o.amount || 0), 0))
async function loadOpen() {
  if (!r.customer_id) return
  open.value = (await api.get('/ar/open-items', { as_of: '2999-12-31', customer_id: r.customer_id })).filter((i) => i.document_id && Number(i.open) > 0).map((i) => ({ ...i, amount: '' }))
}
async function save() {
  const body = { ...r, amount_received: r.amount_received || 0, tax_deducted: r.tax_deducted || 0,
    lines: open.value.filter((o) => Number(o.amount) > 0).map((o) => ({ document_id: o.document_id, amount: o.amount })) }
  try { const x = id ? await api.put(`/ar/receipts/${id}`, body) : await api.post('/ar/receipts', body); toast(`Saved ${x.number}`); router.push(`/ar/receipts/${x.id}`) } catch (e) { showError(e) }
}
onMounted(async () => {
  customers.value = (await refs.customers()).map(opt.coded)
  banks.value = (await refs.bankAccounts()).map(opt.coded)
})
</script>
