<template>
  <div>
    <div class="page-head"><h1>New transfer</h1></div>
    <div class="panel">
      <div class="form-grid">
        <div class="field" style="grid-column: span 2"><label>From account</label><Picker v-model="t.from_account_id" :options="banks" /></div>
        <div class="field" style="grid-column: span 2"><label>To account</label><Picker v-model="t.to_account_id" :options="banks" /></div>
        <div class="field"><label>Date</label><input v-model="t.transfer_date" type="date" /></div>
        <div class="field"><label>Amount</label><input v-model="t.amount" type="number" step="0.01" /></div>
        <div class="field"><label>Bank charges</label><input v-model="t.charges" type="number" step="0.01" /></div>
        <div class="field"><label class="check"><input v-model="t.via_transit" type="checkbox" /> Via cash / funds in transit</label><small class="muted">Use for cash deposits: the bank leg is recorded when credited.</small></div>
        <div class="field"><label>Reference</label><input v-model="t.reference" /></div>
        <div class="field wide"><label>Description</label><input v-model="t.description" /></div>
      </div>
    </div>
    <div class="row"><span class="spacer"></span><button class="btn" @click="$router.back()">Cancel</button><button class="btn primary" @click="save">Save draft</button></div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, showError } from '../api.js'
import { today } from '../format.js'
import { opt, refs } from '../refs.js'
import { toast } from '../store.js'
import Picker from '../components/Picker.vue'
const router = useRouter()
const t = reactive({ from_account_id: null, to_account_id: null, transfer_date: today(), amount: '', charges: '', via_transit: false, reference: '', description: '' })
const banks = ref([])
async function save() {
  try { const x = await api.post('/banking/transfers', { ...t, charges: t.charges || 0 }); toast(`Saved ${x.number}`); router.push(`/bank/transfers/${x.id}`) } catch (e) { showError(e) }
}
onMounted(async () => { banks.value = (await refs.bankAccounts()).map(opt.coded) })
</script>
