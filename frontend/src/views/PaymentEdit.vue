<template>
  <div>
    <div class="page-head"><h1>{{ id ? 'Edit payment' : 'New supplier payment' }}</h1></div>
    <div class="panel">
      <div class="form-grid">
        <div class="field" style="grid-column: span 2"><label>Supplier <span class="req">*</span></label><Picker v-model="p.supplier_id" :options="suppliers" @change="loadOpen" /></div>
        <div class="field"><label>Payment date</label><input v-model="p.payment_date" type="date" @change="preview" /></div>
        <div class="field"><label>Bank account</label><Picker v-model="p.bank_account_id" :options="banks" placeholder="Default payment bank" /></div>
        <div class="field"><label>Method</label><select v-model="p.payment_method"><option>TRANSFER</option><option>CHEQUE</option><option>ONLINE</option><option>CASH</option></select></div>
        <div class="field"><label>Cheque / transfer no.</label><input v-model="p.cheque_no" /></div>
        <div class="field"><label class="check"><input v-model="p.is_advance" type="checkbox" @change="preview" /> Advance payment (no invoice)</label></div>
        <div v-if="p.is_advance" class="field"><label>Advance amount</label><input v-model="advance" type="number" step="0.01" @change="preview" /></div>
        <div class="field wide"><label>Description</label><input v-model="p.description" /></div>
      </div>
    </div>
    <div v-if="!p.is_advance" class="panel">
      <h3>Open invoices</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Pay</th><th>Invoice</th><th>Supplier ref</th><th>Due</th><th class="num">Outstanding</th><th class="num">Amount to pay</th><th>Rate override</th></tr></thead>
        <tbody>
          <tr v-if="!open.length"><td colspan="7" class="empty">Select a supplier to see open invoices</td></tr>
          <tr v-for="o in open" :key="o.document_id">
            <td><input v-model="o.sel" type="checkbox" @change="o.amount = o.sel ? Number(o.open) : ''; preview()" /></td>
            <td>{{ o.number }}</td><td>{{ o.supplier_invoice_no }}</td><td>{{ fmtDate(o.due_date) }}</td><td class="num">{{ fmtMoney(o.open) }}</td>
            <td><input v-model="o.amount" type="number" step="0.01" class="num" @change="preview" /></td>
            <td class="row" style="flex-wrap:nowrap"><input v-model="o.override_rate" type="number" step="0.0001" placeholder="e.g. 0.05" style="max-width:110px" @change="preview" />
              <input v-if="o.override_rate" v-model="o.override_reason" placeholder="Reason" @change="preview" /></td>
          </tr>
        </tbody>
      </table></div>
    </div>
    <div v-if="calc" class="panel">
      <h3>Tax deduction (calculated from the supplier's tax codes, type and ATL status)</h3>
      <div class="grid kpis">
        <div class="kpi"><div class="label">Gross settled</div><div class="value">{{ fmtMoney(calc.gross) }}</div></div>
        <div class="kpi"><div class="label">Income tax withheld</div><div class="value">{{ fmtMoney(calc.wht) }}</div></div>
        <div class="kpi"><div class="label">Sales tax withheld</div><div class="value">{{ fmtMoney(calc.stw) }}</div></div>
        <div class="kpi"><div class="label">Net to bank</div><div class="value">{{ fmtMoney(calc.net) }}</div></div>
      </div>
    </div>
    <div class="row"><span class="spacer"></span><button class="btn" @click="$router.back()">Cancel</button><button class="btn primary" :disabled="busy" @click="save">Save draft</button></div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, showError } from '../api.js'
import { fmtDate, fmtMoney, today } from '../format.js'
import { opt, refs } from '../refs.js'
import { toast } from '../store.js'
import Picker from '../components/Picker.vue'
const route = useRoute(); const router = useRouter(); const id = route.params.id
const p = reactive({ supplier_id: null, payment_date: today(), bank_account_id: null, payment_method: 'TRANSFER', cheque_no: '', is_advance: false, description: '' })
const advance = ref(''); const open = ref([]); const calc = ref(null); const suppliers = ref([]); const banks = ref([]); const busy = ref(false)
const lines = () => (p.is_advance ? (advance.value ? [{ amount: advance.value }] : []) : open.value.filter((o) => o.sel && Number(o.amount) > 0).map((o) => ({
  document_id: o.document_id, amount: o.amount, override_rate: o.override_rate || null, override_reason: o.override_reason || null })))
async function loadOpen() {
  if (!p.supplier_id) return
  const items = await api.get('/ap/open-items', { as_of: '2999-12-31', supplier_id: p.supplier_id })
  open.value = items.filter((i) => i.doc_type === 'INVOICE' && Number(i.open) > 0).map((i) => ({ ...i, sel: false, amount: '', override_rate: '', override_reason: '' }))
}
async function preview() {
  const l = lines()
  if (!p.supplier_id || !l.length) { calc.value = null; return }
  try { calc.value = await api.post('/ap/payments/preview', { ...p, lines: l }) } catch (e) { showError(e) }
}
async function save() {
  busy.value = true
  try {
    const body = { ...p, bank_account_id: p.bank_account_id || null, lines: lines() }
    const r = id ? await api.put(`/ap/payments/${id}`, body) : await api.post('/ap/payments', body)
    toast(`Saved ${r.number}`); router.push(`/ap/payments/${r.id}`)
  } catch (e) { showError(e) } finally { busy.value = false }
}
onMounted(async () => {
  suppliers.value = (await refs.suppliers()).map(opt.coded)
  banks.value = (await refs.bankAccounts()).map(opt.coded)
  if (id) {
    const x = await api.get(`/ap/payments/${id}`)
    Object.assign(p, { supplier_id: x.supplier_id, payment_date: x.payment_date, bank_account_id: x.bank_account_id, payment_method: x.payment_method,
      cheque_no: x.cheque_no || '', is_advance: x.is_advance, description: x.description })
    await loadOpen()
    if (x.is_advance) advance.value = Number(x.gross_amount)
    for (const l of x.lines) { const o = open.value.find((i) => i.document_id === l.document_id); if (o) Object.assign(o, { sel: true, amount: Number(l.amount) }) }
    preview()
  }
})
</script>
