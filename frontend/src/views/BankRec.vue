<template>
  <div>
    <div class="page-head"><h1>Bank reconciliation</h1></div>
    <div class="panel">
      <div class="filters">
        <div class="field" style="max-width:340px;flex:2"><label>Bank account</label><Picker v-model="bank" :options="banks" :clearable="false" @change="refresh" /></div>
        <div class="field"><label>As at</label><input v-model="asOf" type="date" @change="refresh" /></div>
        <div class="field" style="flex:0 0 auto"><button class="btn" @click="refresh">Refresh</button></div>
      </div>
    </div>
    <div v-if="bank" class="tabs"><button v-for="t in tabs" :key="t" :class="{ on: tab === t }" @click="tab = t">{{ t }}</button></div>
    <template v-if="bank && tab === 'Import statement'">
      <div class="panel stack">
        <p class="small muted">CSV or Excel with columns date, description, reference, debit (withdrawal), credit (deposit), balance - or a single signed "amount" column.</p>
        <div class="form-grid">
          <div class="field"><label>Opening balance per statement</label><input v-model="imp.opening" type="number" step="0.01" /></div>
          <div class="field"><label>Closing balance per statement</label><input v-model="imp.closing" type="number" step="0.01" /></div>
          <div class="field"><label>File</label><input ref="file" type="file" accept=".csv,.xlsx" /></div>
        </div>
        <div class="row"><button class="btn primary" @click="importFile">Import</button>
          <a href="#" class="small" @click.prevent="api.download('/imports/templates/bank-statement', null, 'bank-statement.csv')">Template</a></div>
      </div>
    </template>
    <template v-if="bank && tab === 'Match'">
      <div class="panel">
        <div class="row"><select v-model="statementId" style="max-width:340px" @change="loadStatement">
          <option v-for="s in statements" :key="s.id" :value="s.id">Statement #{{ s.id }} {{ fmtDate(s.date_from) }} – {{ fmtDate(s.date_to) }} ({{ s.status }})</option></select>
          <button class="btn" :disabled="!statementId" @click="autoMatch">Auto-match</button><span class="spacer"></span>
          <button class="btn primary" :disabled="!selS || !selG.length" @click="manualMatch">Match selected</button></div>
      </div>
      <div class="grid two">
        <div class="panel"><h3>Statement lines</h3>
          <div class="table-wrap"><table><thead><tr><th></th><th>Date</th><th>Description</th><th class="num">Out</th><th class="num">In</th><th>Status</th></tr></thead>
            <tbody><tr v-for="l in stLines" :key="l.id" :class="{ clickable: l.status !== 'MATCHED' }">
              <td><input v-if="l.status !== 'MATCHED'" v-model="selS" type="radio" :value="l.id" /></td><td class="nowrap">{{ fmtDate(l.txn_date) }}</td>
              <td>{{ l.description }} <small class="muted">{{ l.reference }}</small></td><td class="num">{{ fmtMoney(l.debit) }}</td><td class="num">{{ fmtMoney(l.credit) }}</td>
              <td><span class="badge" :class="l.status">{{ l.status }}</span>
                <button v-if="l.status !== 'MATCHED' && session.can('bank.reconcile')" class="btn sm" @click="adjustFor = l">Adjust</button>
                <button v-for="m in l.matches" :key="m.id" class="btn sm ghost" title="Unmatch" @click="unmatch(m)">↺</button></td></tr></tbody></table></div>
        </div>
        <div class="panel"><h3>Unreconciled ledger items</h3>
          <div class="table-wrap"><table><thead><tr><th></th><th>Date</th><th>Journal</th><th>Description</th><th class="num">In</th><th class="num">Out</th><th class="num">Open</th></tr></thead>
            <tbody><tr v-for="g in gl" :key="g.journal_line_id"><td><input v-model="selG" type="checkbox" :value="g.journal_line_id" /></td>
              <td class="nowrap">{{ fmtDate(g.date) }}</td><td>{{ g.number }}</td><td>{{ g.description }}</td><td class="num">{{ fmtMoney(g.debit) }}</td><td class="num">{{ fmtMoney(g.credit) }}</td><td class="num">{{ fmtMoney(g.remaining) }}</td></tr></tbody></table></div>
        </div>
      </div>
    </template>
    <template v-if="bank && tab === 'Reconciliation'">
      <div v-if="rep" class="panel">
        <div class="grid kpis">
          <div class="kpi"><div class="label">Balance per statement</div><div class="value">{{ fmtMoney(rep.statement_balance) }}</div></div>
          <div class="kpi"><div class="label">Add: deposits in transit</div><div class="value">{{ fmtMoney(rep.deposits_in_transit) }}</div></div>
          <div class="kpi"><div class="label">Less: outstanding payments</div><div class="value">{{ fmtMoney(rep.outstanding_payments) }}</div></div>
          <div class="kpi"><div class="label">Adjusted bank balance</div><div class="value">{{ fmtMoney(rep.adjusted_bank_balance) }}</div></div>
          <div class="kpi"><div class="label">Balance per GL</div><div class="value">{{ fmtMoney(rep.gl_balance) }}</div></div>
          <div class="kpi" :class="{ neg: Number(rep.difference) !== 0 }"><div class="label">Difference</div><div class="value">{{ fmtMoney(rep.difference, { zero: '0.00' }) }}</div></div>
        </div>
        <div v-if="rep.unmatched_statement_lines.length" class="alert warn" style="margin-top:.75rem">{{ rep.unmatched_statement_lines.length }} statement line(s) are not yet matched or adjusted.</div>
        <div class="row" style="margin-top:.75rem"><span class="spacer"></span><button class="btn ok" :disabled="!rep.can_complete" @click="complete">Complete reconciliation</button></div>
        <h3 style="margin-top:1rem">Outstanding items</h3>
        <DataTable :columns="[{ key: 'date', label: 'Date', type: 'date' }, { key: 'number', label: 'Journal' }, { key: 'description', label: 'Description' }, { key: 'direction', label: 'Type' }, { key: 'remaining', label: 'Amount', type: 'money' }]" :rows="rep.outstanding_items" />
      </div>
      <div class="panel"><h3>Reconciliation history</h3><DataTable :columns="histCols" :rows="history" /></div>
    </template>
    <Modal v-if="adjustFor" title="Post statement adjustment (bank charges, interest, direct debit / credit)" width="min(560px,100%)" @close="adjustFor = null">
      <p class="small">{{ adjustFor.description }} · {{ fmtMoney(Number(adjustFor.debit) || Number(adjustFor.credit)) }}</p>
      <div class="form-grid">
        <div class="field wide"><label>Account</label><Picker v-model="adj.account_id" :options="accounts" /></div>
        <div class="field"><label>Site</label><Picker v-model="adj.site_id" :options="sites" /></div>
        <div class="field"><label>Cost centre</label><Picker v-model="adj.cost_centre_id" :options="ccs" /></div>
      </div>
      <template #footer><button class="btn" @click="adjustFor = null">Cancel</button><button class="btn primary" @click="adjust">Post and match</button></template>
    </Modal>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtDate, fmtMoney, monthEnd } from '../format.js'
import { opt, refs } from '../refs.js'
import { session, toast } from '../store.js'
import DataTable from '../components/DataTable.vue'
import Modal from '../components/Modal.vue'
import Picker from '../components/Picker.vue'
const tabs = ['Match', 'Import statement', 'Reconciliation']
const tab = ref('Match'); const bank = ref(null); const banks = ref([]); const asOf = ref(monthEnd())
const statements = ref([]); const statementId = ref(null); const stLines = ref([]); const gl = ref([]); const selS = ref(null); const selG = ref([])
const rep = ref(null); const history = ref([]); const imp = reactive({ opening: '', closing: '' }); const file = ref(null)
const adjustFor = ref(null); const adj = reactive({ account_id: null, site_id: null, cost_centre_id: null }); const accounts = ref([]); const sites = ref([]); const ccs = ref([])
const histCols = [{ key: 'as_of_date', label: 'As at', type: 'date' }, { key: 'statement_balance', label: 'Statement', type: 'money' }, { key: 'gl_balance', label: 'GL', type: 'money' },
  { key: 'outstanding_payments', label: 'Outstanding payments', type: 'money' }, { key: 'deposits_in_transit', label: 'Deposits in transit', type: 'money' }, { key: 'status', label: 'Status', type: 'status' }, { key: 'completed_at', label: 'Completed', type: 'datetime' }]
async function refresh() {
  if (!bank.value) return
  statements.value = await api.get('/banking/statements', { bank_account_id: bank.value })
  if (!statementId.value || !statements.value.find((s) => s.id === statementId.value)) statementId.value = statements.value[0]?.id || null
  await loadStatement()
  gl.value = await api.get(`/banking/accounts/${bank.value}/unreconciled`, { as_of: asOf.value })
  rep.value = await api.get('/banking/reconciliation', { bank_account_id: bank.value, as_of: asOf.value, statement_id: statementId.value })
  history.value = await api.get('/banking/reconciliations', { bank_account_id: bank.value })
  selS.value = null; selG.value = []
}
async function loadStatement() { stLines.value = statementId.value ? (await api.get(`/banking/statements/${statementId.value}`)).lines : [] }
async function importFile() {
  const f = file.value?.files?.[0]
  if (!f) return
  const fd = new FormData(); fd.append('bank_account_id', bank.value); fd.append('opening_balance', imp.opening || 0)
  if (imp.closing !== '') fd.append('closing_balance', imp.closing)
  fd.append('file', f)
  try { const st = await api.upload('/banking/statements/import', fd); statementId.value = st.id; toast(`Imported ${st.lines.length} lines`); tab.value = 'Match'; refresh() } catch (e) { showError(e) }
}
async function autoMatch() { try { const r = await api.post(`/banking/statements/${statementId.value}/auto-match`); toast(`${r.matched} line(s) matched automatically`); refresh() } catch (e) { showError(e) } }
async function manualMatch() { try { await api.post('/banking/matches', selG.value.map((g) => ({ statement_line_id: selS.value, journal_line_id: g }))); toast('Matched'); refresh() } catch (e) { showError(e) } }
async function unmatch(m) { try { await api.del(`/banking/matches/${m.id}`); toast('Unmatched'); refresh() } catch (e) { showError(e) } }
async function adjust() { try { await api.post('/banking/adjustments', { statement_line_id: adjustFor.value.id, ...adj }); toast('Adjustment posted and matched'); adjustFor.value = null; refresh() } catch (e) { showError(e) } }
async function complete() { try { await api.post('/banking/reconciliation/complete', { bank_account_id: bank.value, as_of: asOf.value, statement_id: statementId.value }); toast('Reconciliation completed'); refresh() } catch (e) { showError(e) } }
onMounted(async () => {
  banks.value = (await refs.bankAccounts()).filter((b) => b.kind === 'BANK').map(opt.coded)
  bank.value = banks.value[0]?.value || null
  accounts.value = (await refs.accounts()).map(opt.account); sites.value = (await refs.sites()).map(opt.coded); ccs.value = (await refs.costCentres()).map(opt.coded)
  refresh()
})
</script>
