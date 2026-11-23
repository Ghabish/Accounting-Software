<template>
  <div>
    <div class="page-head"><h1>{{ id ? 'Edit' : 'New' }} {{ side === 'ap' ? 'supplier' : 'customer' }} document</h1></div>
    <div class="panel">
      <div class="form-grid">
        <div class="field"><label>Document type</label><select v-model="d.doc_type">
          <option value="INVOICE">Invoice</option><option value="CREDIT_NOTE">Credit note</option><option value="DEBIT_NOTE">Debit note</option></select></div>
        <div class="field" style="grid-column: span 2"><label>{{ side === 'ap' ? 'Supplier' : 'Customer' }} <span class="req">*</span></label>
          <Picker v-model="d.party_id" :options="parties" @change="onParty" /></div>
        <div v-if="side === 'ap'" class="field"><label>Supplier document no. <span class="req">*</span></label><input v-model="d.supplier_invoice_no" /></div>
        <div v-else class="field"><label>Customer reference / PO</label><input v-model="d.customer_reference" /></div>
        <div class="field"><label>Document date <span class="req">*</span></label><input v-model="d.invoice_date" type="date" /></div>
        <div class="field"><label>Posting date</label><input v-model="d.posting_date" type="date" /></div>
        <div class="field"><label>Due date</label><input v-model="d.due_date" type="date" placeholder="From payment terms" /></div>
        <div class="field"><label>Site</label><Picker v-model="d.site_id" :options="sites" /></div>
        <div v-if="d.doc_type !== 'INVOICE'" class="field"><label>Related invoice id (auto-allocate)</label><input v-model="d.related_document_id" type="number" /></div>
        <div class="field wide"><label>Description</label><input v-model="d.description" /></div>
      </div>
      <p v-if="partyInfo" class="small muted">{{ partyInfo }}</p>
    </div>
    <div class="panel">
      <LineEditor :lines="d.lines" :tax-field="side === 'ap' ? 'st_tax_code_id' : 'tax_code_id'" :tax-label="side === 'ap' ? 'Sales tax (blank = supplier default)' : 'Output tax (blank = default)'"
                  :tax-filter="(t) => side === 'ap' ? ['SALES_TAX_INPUT', 'PST_INPUT'].includes(t.tax_type) : ['SALES_TAX_OUTPUT', 'PST_OUTPUT'].includes(t.tax_type)" />
      <p class="small muted">Sales tax is calculated from the effective rate for the tax code. Withholding tax is deducted automatically when the invoice is paid.</p>
    </div>
    <div v-if="warnings.length" class="alert warn"><ul><li v-for="w in warnings" :key="w">{{ w }}</li></ul></div>
    <div class="row"><span class="spacer"></span><button class="btn" @click="$router.back()">Cancel</button><button class="btn primary" :disabled="busy" @click="save">Save draft</button></div>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, showError } from '../api.js'
import { today } from '../format.js'
import { opt, refs } from '../refs.js'
import { toast } from '../store.js'
import LineEditor from '../components/LineEditor.vue'
import Picker from '../components/Picker.vue'
const props = defineProps({ side: String, id: [String, Number] })
const router = useRouter()
const busy = ref(false); const warnings = ref([]); const parties = ref([]); const sites = ref([]); const party = ref(null)
const d = reactive({ doc_type: 'INVOICE', party_id: null, supplier_invoice_no: '', customer_reference: '', invoice_date: today(), posting_date: '', due_date: '',
  site_id: null, description: '', related_document_id: null, lines: [{ account_id: null, site_id: null, cost_centre_id: null, description: '', amount: '' }] })
const partyInfo = computed(() => party.value ? `Terms ${party.value.payment_terms_days} days${party.value.ntn ? ' · NTN ' + party.value.ntn : ''}${party.value.atl_status ? ' · ' + party.value.atl_status : ''}${party.value.payment_hold ? ' · ON PAYMENT HOLD' : ''}` : '')
function onParty(p) { party.value = p }
async function save() {
  busy.value = true
  const lines = d.lines.filter((l) => l.account_id || props.side === 'ar').map((l) => {
    const o = { account_id: l.account_id, site_id: l.site_id || d.site_id, cost_centre_id: l.cost_centre_id, description: l.description, amount: l.amount }
    const tk = props.side === 'ap' ? 'st_tax_code_id' : 'tax_code_id'
    if (l[tk]) o[tk] = l[tk]
    return o
  })
  const body = { doc_type: d.doc_type, invoice_date: d.invoice_date, posting_date: d.posting_date || null, due_date: d.due_date || null, site_id: d.site_id,
    description: d.description || null, related_document_id: d.related_document_id || null, lines }
  if (props.side === 'ap') Object.assign(body, { supplier_id: d.party_id, supplier_invoice_no: d.supplier_invoice_no })
  else Object.assign(body, { customer_id: d.party_id, customer_reference: d.customer_reference || null })
  const base = `/${props.side}/documents`
  try {
    const r = props.id ? await api.put(`${base}/${props.id}`, body) : await api.post(base, body)
    warnings.value = r.warnings || []
    toast(`Saved ${r.number}`)
    router.push(`${base}/${r.id}`)
  } catch (e) { showError(e) } finally { busy.value = false }
}
onMounted(async () => {
  parties.value = (props.side === 'ap' ? await refs.suppliers() : await refs.customers()).map(opt.coded)
  sites.value = (await refs.sites()).map(opt.coded)
  if (!props.id) return
  const x = await api.get(`/${props.side}/documents/${props.id}`)
  Object.assign(d, { doc_type: x.doc_type, party_id: x.supplier_id || x.customer_id, supplier_invoice_no: x.supplier_invoice_no || '', customer_reference: x.customer_reference || '',
    invoice_date: x.invoice_date, posting_date: x.posting_date, due_date: x.due_date, site_id: x.site_id, description: x.description, related_document_id: x.related_document_id,
    lines: x.lines.map((l) => ({ account_id: l.account_id, site_id: l.site_id, cost_centre_id: l.cost_centre_id, description: l.description, amount: Number(l.amount),
      st_tax_code_id: l.st_tax_code_id, tax_code_id: l.tax_code_id })) })
})
</script>
