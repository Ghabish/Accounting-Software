<template>
  <div>
    <h3>Apply unapplied amount to an invoice</h3>
    <div class="filters">
      <div class="field" style="max-width:420px;flex:2"><label>Open invoice</label>
        <select v-model="invoice"><option :value="null">Select…</option><option v-for="i in invoices" :key="i.document_id" :value="i.document_id">{{ i.number }} · outstanding {{ fmtMoney(i.open) }}</option></select></div>
      <div class="field"><label>Amount</label><input v-model="amount" type="number" step="0.01" /></div>
      <div class="field"><label>Date</label><input v-model="date" type="date" /></div>
      <div class="field" style="flex:0 0 auto"><button class="btn primary" @click="apply">Apply</button></div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtMoney, today } from '../format.js'
import { toast } from '../store.js'
const props = defineProps({ doc: Object, side: String })
const emit = defineEmits(['changed'])
const invoices = ref([]); const invoice = ref(null); const amount = ref(''); const date = ref(today())
onMounted(async () => {
  const party = props.side === 'ap' ? { supplier_id: props.doc.supplier.id } : { customer_id: props.doc.customer.id }
  const items = await api.get(`/${props.side}/open-items`, { as_of: '2999-12-31', ...party })
  invoices.value = items.filter((i) => i.document_id && Number(i.open) > 0)
})
async function apply() {
  const url = props.side === 'ap' ? `/ap/payments/${props.doc.id}/apply-advance` : `/ar/receipts/${props.doc.id}/apply-advance`
  try { await api.post(url, { invoice_id: invoice.value, amount: amount.value, date: date.value }); toast('Applied'); emit('changed') } catch (e) { showError(e) }
}
</script>
