<template>
  <div>
    <div v-if="checks.length" class="row" style="margin-bottom:.6rem">
      <span v-for="c in checks" :key="c.label" class="badge" :class="c.ok ? 'PASS' : 'FAIL'">{{ c.label }}: {{ c.ok ? 'OK' : c.text }}</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th v-for="c in report.columns" :key="c.key" :class="{ num: isNum(c) }">{{ c.label }}</th></tr></thead>
        <tbody>
          <tr v-if="!report.rows.length"><td :colspan="report.columns.length" class="empty">No data for the selected filters</td></tr>
          <tr v-for="(r, i) in report.rows" :key="i" :class="`st-${r.style || 'line'}`">
            <td v-for="(c, ci) in report.columns" :key="c.key" :class="[{ num: isNum(c) }, neg(r[c.key], c)]">
              <template v-if="ci === 0">
                <span :style="{ paddingLeft: `${(r.level || 0) * 14}px` }">
                  <a v-if="drillable(r)" class="drill" @click="$emit('drill', r, null)">{{ r[c.key] }}</a>
                  <template v-else>{{ r[c.key] }}</template>
                </span>
              </template>
              <a v-else-if="isNum(c) && r[c.key] !== null && r[c.key] !== undefined && drillable(r) && c.date_from !== undefined" class="drill"
                 @click="$emit('drill', r, c)">{{ format(r[c.key], c.type) }}</a>
              <a v-else-if="c.key === 'number' && r.journal_id" class="drill" @click="$emit('drill', { journal_id: r.journal_id }, null)">{{ r[c.key] }}</a>
              <template v-else>{{ format(r[c.key], c.type) }}</template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { format } from '../format.js'
const props = defineProps({ report: Object })
defineEmits(['drill'])
const isNum = (c) => ['money', 'int', 'pct', 'number'].includes(c.type)
const neg = (v, c) => (c.type === 'money' && Number(v) < 0 ? 'neg' : '')
const drillable = (r) => !!(r.drill || r.journal_id || r.document_id)
const checks = computed(() => {
  const m = props.report.meta || {}
  const out = []
  if (m.balanced === true || m.balanced === false) out.push({ label: 'Balanced', ok: m.balanced, text: `difference ${JSON.stringify(m.difference ?? '')}` })
  if (m.reconciles === true || m.reconciles === false) out.push({ label: 'Cash agrees to balance sheet', ok: m.reconciles, text: `difference ${m.difference}` })
  if (m.reconciled === true || m.reconciled === false) out.push({ label: 'Sub-ledger agrees to GL', ok: m.reconciled, text: 'differences shown below' })
  return out
})
</script>
