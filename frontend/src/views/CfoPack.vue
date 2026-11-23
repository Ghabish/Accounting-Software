<template>
  <div>
    <div class="page-head"><h1>CFO monthly reporting pack</h1></div>
    <div class="panel stack">
      <p class="small muted">Management accounts for the month: summary KPIs and ratios, P&amp;L (period, YTD, monthly, budget, site-wise), balance sheet, cash flow, cash position, AP / AR aging, tax position and cinema revenue analysis - all derived from the posted ledger.</p>
      <div class="filters"><div class="field"><label>Period</label><select v-model="period"><option v-for="p in periods" :key="p.id" :value="p.id">{{ p.name }}</option></select></div>
        <div class="field" style="flex:0 0 auto"><button class="btn primary" :disabled="busy" @click="get('pdf')">Download PDF</button></div>
        <div class="field" style="flex:0 0 auto"><button class="btn" :disabled="busy" @click="get('xlsx')">Download Excel</button></div></div>
      <div v-if="ratios" class="grid kpis">
        <div v-for="(v, k) in ratios" :key="k" class="kpi"><div class="label">{{ k.replaceAll('_', ' ') }}</div><div class="value">{{ v === null ? '-' : (String(k).includes('pct') ? fmtPct(v) : (Math.abs(Number(v)) > 1000 ? fmtCompact(v) : v)) }}</div></div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref, watch } from 'vue'
import { api, showError } from '../api.js'
import { fmtCompact, fmtPct } from '../format.js'
import { refs } from '../refs.js'
const periods = ref([]); const period = ref(null); const busy = ref(false); const ratios = ref(null)
async function get(fmt) { busy.value = true; try { await api.download('/cfo/pack', { period_id: period.value, format: fmt }) } catch (e) { showError(e) } finally { busy.value = false } }
watch(period, async () => { const p = periods.value.find((x) => x.id === period.value); if (p) ratios.value = await api.get('/cfo/ratios', { as_of: p.end_date }).catch(() => null) })
onMounted(async () => { periods.value = await refs.periods(); const t = new Date().toISOString().slice(0, 10); period.value = (periods.value.find((p) => p.start_date <= t && p.end_date >= t) || periods.value[0])?.id })
</script>
