<template>
  <div>
    <div class="page-head">
      <h1>CFO dashboard</h1>
      <div class="actions"><router-link class="btn" to="/cfo-pack">Monthly pack</router-link></div>
    </div>
    <div class="panel no-print">
      <div class="filters">
        <div class="field"><label>From</label><input v-model="f.date_from" type="date" /></div>
        <div class="field"><label>To</label><input v-model="f.date_to" type="date" /></div>
        <div class="field"><label>Site</label><Picker v-model="f.site_ids" :options="sites" placeholder="All sites" /></div>
        <div class="field"><label>Cost centre</label><Picker v-model="f.cost_centre_ids" :options="ccs" placeholder="All" /></div>
        <div class="field"><label>Revenue stream</label><select v-model="f.revenue_stream"><option value="">All</option><option value="TICKETING">Ticketing</option><option value="FNB">Food &amp; beverage</option><option value="ADVERTISING">Advertising</option><option value="OTHER">Other</option></select></div>
        <div class="field" style="flex:0 0 auto"><button class="btn primary" @click="load">Apply</button></div>
      </div>
    </div>
    <div v-if="!d" class="panel empty">{{ loading ? 'Loading…' : '' }}</div>
    <template v-else>
      <div class="grid kpis" style="margin-top:1rem">
        <Kpi label="Revenue" :value="d.kpis.revenue" :sub="`YTD ${fmtCompact(d.kpis.ytd_revenue)}`" />
        <Kpi label="Gross profit" :value="d.kpis.gross_profit" :sub="`Margin ${fmtPct(d.kpis.gross_margin)}`" />
        <Kpi label="EBITDA" :value="d.kpis.ebitda" :sub="`Margin ${fmtPct(d.kpis.ebitda_margin)}`" />
        <Kpi label="Net profit" :value="d.kpis.net_profit" :sub="`YTD ${fmtCompact(d.kpis.ytd_net_profit)}`" />
        <Kpi label="Bank balances" :value="d.kpis.bank_balance" :sub="`Cash in hand ${fmtCompact(d.kpis.cash_balance)}`" />
        <Kpi label="Receivables" :value="d.kpis.receivables" />
        <Kpi label="Payables" :value="d.kpis.payables" />
        <Kpi label="Net tax payable" :value="d.kpis.tax_payable" :sub="`Recoverable ${fmtCompact(d.kpis.tax_recoverable)}`" />
        <Kpi label="Admissions" :value="d.cinema.admissions" int :sub="`ATP ${fmtMoney(d.cinema.average_ticket_price)}`" />
        <Kpi label="F&B spend per head" :value="d.cinema.spend_per_head" :sub="`Film rental ${fmtPct(d.cinema.film_rental_pct)}`" />
      </div>
      <div class="grid two" style="margin-top:1rem">
        <div class="panel"><h3>Monthly revenue by stream</h3><ChartBox :config="trendChart" /></div>
        <div class="panel"><h3>Monthly P&amp;L</h3><ChartBox :config="plChart" /></div>
        <div class="panel"><h3>Site performance</h3><ChartBox :config="siteChart" /></div>
        <div class="panel"><h3>Revenue mix</h3><ChartBox :config="mixChart" /></div>
      </div>
      <div class="grid three" style="margin-top:1rem">
        <div class="panel">
          <h3>Budget vs actual (YTD)</h3>
          <div v-if="!d.budget_vs_actual" class="muted small">No approved budget for this year.</div>
          <table v-else><thead><tr><th></th><th class="num">Actual</th><th class="num">Budget</th><th class="num">Variance</th></tr></thead>
            <tbody><tr v-for="(v, k) in d.budget_vs_actual" :key="k"><td>{{ labels[k] }}</td><td class="num">{{ fmtCompact(v.actual) }}</td><td class="num">{{ fmtCompact(v.budget) }}</td><td class="num" :class="{ neg: v.variance < 0 }">{{ fmtCompact(v.variance) }}</td></tr></tbody></table>
        </div>
        <div class="panel">
          <h3>Top expenses</h3>
          <table><tbody><tr v-for="e in d.top_expenses" :key="e.account"><td>{{ e.account }}</td><td class="num">{{ fmtCompact(e.amount) }}</td></tr></tbody></table>
        </div>
        <div class="panel">
          <h3>Cost-centre spend</h3>
          <table><tbody><tr v-for="c in d.cost_centres" :key="c.cost_centre"><td>{{ c.cost_centre }}</td><td class="num">{{ fmtCompact(c.expense) }}</td></tr></tbody></table>
        </div>
        <div class="panel">
          <h3>Outstanding payables (aging)</h3>
          <table><tbody><tr v-for="b in buckets" :key="b[0]"><td>{{ b[1] }}</td><td class="num">{{ fmtMoney(d.ap_aging[b[0]]) }}</td></tr></tbody></table>
          <router-link to="/reports/ap-aging" class="small">Open AP aging →</router-link>
        </div>
        <div class="panel">
          <h3>Outstanding receivables (aging)</h3>
          <table><tbody><tr v-for="b in buckets" :key="b[0]"><td>{{ b[1] }}</td><td class="num">{{ fmtMoney(d.ar_aging[b[0]]) }}</td></tr></tbody></table>
          <router-link to="/reports/ar-aging" class="small">Open AR aging →</router-link>
        </div>
        <div class="panel">
          <h3>Cash flow (year to date)</h3>
          <table><tbody>
            <tr><td>Opening cash</td><td class="num">{{ fmtMoney(d.cash_flow.opening_cash) }}</td></tr>
            <tr><td>Operating activities</td><td class="num">{{ fmtMoney(d.cash_flow.operating) }}</td></tr>
            <tr><td>Investing activities</td><td class="num">{{ fmtMoney(d.cash_flow.investing) }}</td></tr>
            <tr><td>Financing activities</td><td class="num">{{ fmtMoney(d.cash_flow.financing) }}</td></tr>
            <tr class="st-total"><td>Closing cash</td><td class="num">{{ fmtMoney(d.cash_flow.closing_cash) }}</td></tr>
          </tbody></table>
          <router-link to="/reports/cash-flow" class="small">Open cash flow →</router-link>
        </div>
      </div>
    </template>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref, h } from 'vue'
import { api, showError } from '../api.js'
import { fmtCompact, fmtInt, fmtMoney, fmtPct, fyStart, monthEnd, monthStart } from '../format.js'
import { opt, refs } from '../refs.js'
import ChartBox from '../components/ChartBox.vue'
import Picker from '../components/Picker.vue'

const Kpi = (p) => h('div', { class: ['kpi', Number(p.value) < 0 ? 'neg' : ''] }, [
  h('div', { class: 'label' }, p.label), h('div', { class: 'value' }, p.int !== undefined && p.int !== false ? fmtInt(p.value) : fmtCompact(p.value)),
  p.sub ? h('div', { class: 'sub' }, p.sub) : null])
Kpi.props = ['label', 'value', 'sub', 'int']
const f = reactive({ date_from: monthStart(), date_to: monthEnd(), site_ids: null, cost_centre_ids: null, revenue_stream: '' })
const d = ref(null)
const loading = ref(false)
const sites = ref([])
const ccs = ref([])
const labels = { REVENUE: 'Revenue', COST_OF_SALES: 'Cost of sales', OPEX: 'Operating expenses', EBITDA: 'EBITDA', PAT: 'Net profit' }
const buckets = [['current', 'Not yet due'], ['b1', '1-30 days'], ['b2', '31-60 days'], ['b3', '61-90 days'], ['b4', '91-180 days'], ['b5', 'Over 180 days'], ['unapplied', 'Unapplied'], ['total', 'Total']]
const COLORS = { TICKETING: '#1f2a44', FNB: '#c8102e', ADVERTISING: '#f5a623', OTHER: '#6b8fd6' }
const trendChart = computed(() => d.value && ({ type: 'bar', data: { labels: d.value.trend.map((t) => t.month), datasets: Object.keys(COLORS).map((s) => ({ label: s, backgroundColor: COLORS[s], data: d.value.trend.map((t) => Number(t.streams[s] || 0)) })) }, options: { scales: { x: { stacked: true }, y: { stacked: true } } } }))
const plChart = computed(() => d.value && ({ type: 'line', data: { labels: d.value.trend.map((t) => t.month), datasets: [
  { label: 'Revenue', borderColor: '#1f2a44', data: d.value.trend.map((t) => Number(t.revenue)) },
  { label: 'EBITDA', borderColor: '#1a7f4b', data: d.value.trend.map((t) => Number(t.ebitda)) },
  { label: 'Net profit', borderColor: '#c8102e', data: d.value.trend.map((t) => Number(t.pat)) }] } }))
const siteChart = computed(() => d.value && ({ type: 'bar', data: { labels: d.value.sites.map((s) => s.site), datasets: [
  { label: 'Revenue', backgroundColor: '#1f2a44', data: d.value.sites.map((s) => Number(s.revenue)) },
  { label: 'EBITDA', backgroundColor: '#1a7f4b', data: d.value.sites.map((s) => Number(s.ebitda)) }] } }))
const mixChart = computed(() => d.value && ({ type: 'doughnut', data: { labels: Object.keys(d.value.revenue_by_stream), datasets: [{ data: Object.values(d.value.revenue_by_stream).map(Number), backgroundColor: Object.keys(d.value.revenue_by_stream).map((k) => COLORS[k] || '#999') }] } }))
async function load() {
  loading.value = true
  try { d.value = await api.get('/cfo/dashboard', f) } catch (e) { showError(e) } finally { loading.value = false }
}
onMounted(async () => {
  load()
  sites.value = (await refs.sites()).map(opt.coded)
  ccs.value = (await refs.costCentres()).map(opt.coded)
})
</script>
