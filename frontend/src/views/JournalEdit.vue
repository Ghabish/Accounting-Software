<template>
  <div>
    <div class="page-head"><h1>{{ id ? 'Edit journal' : 'New journal voucher' }}</h1></div>
    <div class="panel">
      <div class="form-grid">
        <div class="field"><label>Document date <span class="req">*</span></label><input v-model="j.transaction_date" type="date" /></div>
        <div class="field"><label>Posting date</label><input v-model="j.posting_date" type="date" /></div>
        <div class="field"><label>Reference</label><input v-model="j.reference" /></div>
        <div class="field"><label class="check"><input v-model="j.is_accrual" type="checkbox" /> Accrual - reverse automatically</label>
          <input v-if="j.is_accrual" v-model="j.auto_reverse_date" type="date" title="Reversal date (default: first day of next period)" /></div>
        <div class="field wide"><label>Narration <span class="req">*</span></label><textarea v-model="j.description" placeholder="Explain the purpose of the journal and the basis of the amounts"></textarea></div>
      </div>
    </div>
    <div class="panel"><LineEditor :lines="j.lines" drcr party dims /></div>
    <div v-if="warnings.length" class="alert warn"><strong>Warnings</strong><ul><li v-for="w in warnings" :key="w">{{ w }}</li></ul></div>
    <div class="row"><span class="spacer"></span><button class="btn" @click="$router.back()">Cancel</button><button class="btn primary" :disabled="busy" @click="save">Save draft</button></div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, showError } from '../api.js'
import { today } from '../format.js'
import { refs } from '../refs.js'
import { toast } from '../store.js'
import LineEditor from '../components/LineEditor.vue'
const route = useRoute()
const router = useRouter()
const id = route.params.id
const busy = ref(false)
const warnings = ref([])
const blank = () => ({ account_id: null, site_id: null, cost_centre_id: null, description: '', debit: '', credit: '' })
const j = reactive({ transaction_date: today(), posting_date: '', reference: '', description: '', is_accrual: false, auto_reverse_date: '', lines: [blank(), blank()] })
let dimTypeOf = {}
async function save() {
  busy.value = true
  const body = { ...j, posting_date: j.posting_date || null, auto_reverse_date: j.auto_reverse_date || null,
    lines: j.lines.filter((l) => l.account_id).map((l) => ({ account_id: l.account_id, site_id: l.site_id, cost_centre_id: l.cost_centre_id,
      supplier_id: l.supplier_id || null, customer_id: l.customer_id || null, employee_id: l.employee_id || null, description: l.description,
      debit: l.debit || 0, credit: l.credit || 0, dimensions: l._dim ? { [dimTypeOf[l._dim]]: l._dim } : {} })) }
  try {
    const r = id ? await api.put(`/journals/${id}`, body) : await api.post('/journals', body)
    warnings.value = r.warnings || []
    toast('Journal saved as draft')
    if (!warnings.value.length) router.push(`/journals/${r.id}`)
  } catch (e) { showError(e) } finally { busy.value = false }
}
onMounted(async () => {
  dimTypeOf = Object.fromEntries((await refs.dimValues()).map((v) => [v.id, v.dimension_type_id]))
  if (!id) return
  const d = await api.get(`/journals/${id}`)
  Object.assign(j, { transaction_date: d.transaction_date, posting_date: d.posting_date, reference: d.reference || '', description: d.description,
    is_accrual: d.is_accrual, auto_reverse_date: d.auto_reverse_date || '',
    lines: d.lines.map((l) => ({ account_id: l.account_id, site_id: l.site_id, cost_centre_id: l.cost_centre_id, supplier_id: l.supplier_id,
      customer_id: l.customer_id, employee_id: l.employee_id, description: l.description, debit: Number(l.debit) || '', credit: Number(l.credit) || '',
      _dim: l.dimension_values[0]?.value_id || null })) })
})
</script>
