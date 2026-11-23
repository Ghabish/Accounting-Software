<template>
  <div>
    <div class="page-head"><h1>POS sales import</h1></div>
    <div class="grid two">
      <div v-for="k in kinds" :key="k.key" class="panel stack">
        <h2>{{ k.title }}</h2>
        <p class="small muted">{{ k.help }}</p>
        <div class="row"><input :ref="(el) => (inputs[k.key] = el)" type="file" accept=".csv,.xlsx" style="max-width:320px" />
          <button class="btn primary" @click="upload(k)">Import</button>
          <a href="#" class="small" @click.prevent="api.download(`/imports/templates/${k.key}`, null, `${k.key}.csv`)">Download template</a></div>
        <div v-if="results[k.key]" class="alert ok">Imported {{ results[k.key].row_count }} rows (batch #{{ results[k.key].id }}). Post the day close to account for them.</div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { reactive } from 'vue'
import { api, showError } from '../api.js'
import { toast } from '../store.js'
const kinds = [
  { key: 'box-office', title: 'Box office (tickets)', help: 'One row per show, revenue type and payment method: tickets, complimentary tickets, gross, discounts and refunds (prices including tax). The whole file is rejected if any row is invalid.' },
  { key: 'fnb', title: 'Food & beverage', help: 'One row per site, date, F&B category and payment method (prices including tax).' },
]
const inputs = reactive({}); const results = reactive({})
async function upload(k) {
  const f = inputs[k.key]?.files?.[0]
  if (!f) return
  const fd = new FormData(); fd.append('file', f)
  try { results[k.key] = await api.upload(`/cinema/imports/${k.key}/file`, fd); toast('Imported') } catch (e) { showError(e) }
}
</script>
