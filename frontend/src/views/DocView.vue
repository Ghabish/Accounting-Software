<template>
  <div v-if="d">
    <div class="page-head">
      <h1>{{ cfg.title(d) }}</h1>
      <span class="badge" :class="d.status">{{ d.status }}</span>
      <span v-if="d.payment_status" class="badge" :class="d.payment_status">{{ d.payment_status }}</span>
      <div class="actions">
        <router-link v-if="cfg.editPath && editable" class="btn" :to="cfg.editPath(d)">Edit</router-link>
        <router-link v-if="d.journal_id" class="btn" :to="`/journals/${d.journal_id}`">GL journal</router-link>
        <button v-if="canReverse" class="btn danger" @click="showReverse = true">Reverse</button>
        <button class="btn" @click="print">Print</button>
      </div>
    </div>
    <WorkflowBar v-if="cfg.wf && !['POSTED', 'REVERSED', 'CANCELLED'].includes(d.status)" :status="d.status" :base="`${cfg.ep}/${id}`"
                 :prefix="cfg.wf.prefix" :check="!!wfConfig[cfg.wf.doc]?.require_check" @done="load" />
    <div v-if="d.rejection_reason && d.status === 'DRAFT'" class="alert warn">Returned: {{ d.rejection_reason }}</div>
    <div class="panel"><dl class="facts"><div v-for="[l, v] in cfg.facts(d)" :key="l"><dt>{{ l }}</dt><dd>{{ v }}</dd></div></dl></div>
    <div class="panel">
      <h3>{{ cfg.linesTitle || 'Lines' }}</h3>
      <DataTable :columns="cfg.lineCols" :rows="cfg.lines ? cfg.lines(d) : d.lines" />
      <div v-if="cfg.totals" class="row" style="justify-content:flex-end;margin-top:.5rem">
        <span v-for="[l, v] in cfg.totals(d)" :key="l" class="kpi" style="padding:.5rem .8rem"><span class="label">{{ l }}</span> <strong class="num">{{ fmtMoney(v) }}</strong></span>
      </div>
    </div>
    <div v-if="extra" class="panel"><component :is="extra[0]" v-bind="extra[1]" @changed="load" /></div>
    <div v-if="d.allocations && d.allocations.length" class="panel">
      <h3>Allocations</h3>
      <DataTable :columns="[{ key: 'allocation_date', label: 'Date', type: 'date' }, { key: 'source_type', label: 'Settled by' }, { key: 'amount', label: 'Amount', type: 'money' }, { key: 'is_active', label: 'Active', type: 'bool' }]" :rows="d.allocations" />
    </div>
    <div class="grid two">
      <Attachments :entity-type="cfg.attach" :entity-id="id" :readonly="d.status === 'REVERSED'" />
      <div class="panel">
        <h3>Approval history</h3>
        <div v-if="!(d.history || []).length" class="muted small">No workflow actions yet</div>
        <div v-for="h in d.history || []" :key="h.id" class="small" style="margin-bottom:.35rem">
          <span class="badge" :class="h.to_status">{{ h.action }}</span> {{ h.user_name || h.username }} · {{ fmtDateTime(h.ts) }}
          <span v-if="h.comment" class="muted"> — {{ h.comment }}</span>
        </div>
      </div>
    </div>
    <Modal v-if="showReverse" title="Reverse posted document" width="min(520px,100%)" @close="showReverse = false">
      <p class="small muted">A reversing journal is posted (or, for manual journals, created for approval). The original is kept unchanged for audit.</p>
      <div class="form-grid">
        <div class="field"><label>Reversal date</label><input v-model="rev.date" type="date" /></div>
        <div class="field wide"><label>Reason</label><textarea v-model="rev.reason"></textarea></div>
      </div>
      <template #footer><button class="btn" @click="showReverse = false">Cancel</button><button class="btn danger" @click="reverse">Reverse</button></template>
    </Modal>
  </div>
  <div v-else class="panel empty">Loading…</div>
</template>
<script setup>
import { computed, h, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, showError } from '../api.js'
import { fmtDate, fmtDateTime, fmtMoney, today } from '../format.js'
import { session, toast } from '../store.js'
import Attachments from '../components/Attachments.vue'
import DataTable from '../components/DataTable.vue'
import Modal from '../components/Modal.vue'
import WorkflowBar from '../components/WorkflowBar.vue'
import AdvanceApply from '../components/AdvanceApply.vue'

const props = defineProps({ kind: String, id: [String, Number] })
const router = useRouter()
const d = ref(null)
const wfConfig = ref({})
const showReverse = ref(false)
const rev = reactive({ date: today(), reason: '' })
const party = (x) => x ? `${x.code} ${x.name}` : ''
const CFG = {
  journal: { ep: '/journals', attach: 'journal', wf: { prefix: 'journal', doc: 'JOURNAL' }, editPath: (x) => `/journals/${x.id}/edit`,
    reverse: (x) => ({ url: `/journals/${x.id}/reverse/request`, body: { reversal_date: rev.date, reason: rev.reason } }), revPerm: 'journal.reverse',
    manualOnly: true,
    title: (x) => `Journal ${x.number || `draft #${x.id}`}`,
    facts: (x) => [['Type', x.journal_type], ['Posting date', fmtDate(x.posting_date)], ['Document date', fmtDate(x.transaction_date)], ['Reference', x.reference || '-'],
      ['Source', `${x.source_module}${x.source_type ? ' / ' + x.source_type : ''}`], ['Description', x.description], ['Prepared by', x.users[x.created_by_id] || '-'],
      ['Approved by', x.users[x.approved_by_id] || '-'], ['Posted by', x.users[x.posted_by_id] || '-'], ['Reversal of', x.reversal_of_id ? `#${x.reversal_of_id}` : '-'],
      ['Reversed by', x.reversed_by_journal ? `${x.reversed_by_journal.number || '#' + x.reversed_by_journal.id} (${x.reversed_by_journal.status})` : '-'], ['Accrual (auto-reverse)', x.is_accrual ? 'Yes' : 'No']],
    lineCols: [{ key: 'account_code', label: 'Account' }, { key: 'account_name', label: 'Name' }, { key: 'site_code', label: 'Site' }, { key: 'cost_centre_code', label: 'CC' },
      { key: 'party', label: 'Party', render: (l) => party(l.party) }, { key: 'dims', label: 'Dimensions', render: (l) => l.dimension_values.map((v) => v.code).join(', ') },
      { key: 'description', label: 'Description' }, { key: 'debit', label: 'Debit', type: 'money' }, { key: 'credit', label: 'Credit', type: 'money' }],
    totals: (x) => [['Debit', x.total_debit], ['Credit', x.total_credit]] },
  ap_doc: { ep: '/ap/documents', attach: 'ap_document', wf: { prefix: 'ap_invoice', doc: 'AP_INVOICE' }, editPath: (x) => `/ap/documents/${x.id}/edit`,
    reverse: (x) => ({ url: `/ap/documents/${x.id}/reverse`, body: { reversal_date: rev.date, reason: rev.reason } }), revPerm: 'ap_invoice.reverse',
    title: (x) => `${x.doc_type.replace('_', ' ').toLowerCase()} ${x.number}`,
    facts: (x) => [['Supplier', party(x.supplier)], ['Supplier document', x.supplier_invoice_no], ['Invoice date', fmtDate(x.invoice_date)], ['Posting date', fmtDate(x.posting_date)],
      ['Due date', fmtDate(x.due_date)], ['Description', x.description], ['Outstanding', fmtMoney(x.outstanding)], ['Opening balance', x.is_opening ? 'Yes' : 'No']],
    lineCols: [{ key: 'line_no', label: '#' }, { key: 'account_code', label: 'Account' }, { key: 'account_name', label: 'Name' }, { key: 'site_code', label: 'Site' }, { key: 'cost_centre_code', label: 'CC' },
      { key: 'description', label: 'Description' }, { key: 'amount', label: 'Amount', type: 'money' },
      { key: 'st_rate', label: 'ST rate', render: (l) => l.st_rate ? `${(Number(l.st_rate) * 100).toFixed(2)}%` : '' }, { key: 'st_amount', label: 'Sales tax', type: 'money' }],
    totals: (x) => [['Subtotal', x.subtotal], ['Tax', x.tax_total], ['Total', x.total]] },
  ap_payment: { ep: '/ap/payments', attach: 'ap_payment', wf: { prefix: 'ap_payment', doc: 'AP_PAYMENT' }, editPath: (x) => `/ap/payments/${x.id}/edit`,
    reverse: (x) => ({ url: `/ap/payments/${x.id}/reverse`, body: { reversal_date: rev.date, reason: rev.reason } }), revPerm: 'ap_payment.reverse',
    title: (x) => `Payment ${x.number}`,
    facts: (x) => [['Supplier', party(x.supplier)], ['Beneficiary', x.supplier.beneficiary_name], ['Date', fmtDate(x.payment_date)], ['Method', x.payment_method],
      ['Cheque', x.cheque_no || '-'], ['Reference', x.reference || '-'], ['Advance', x.is_advance ? 'Yes' : 'No'], ['Unapplied advance', fmtMoney(x.advance_unapplied)]],
    lineCols: [{ key: 'invoice_number', label: 'Invoice', render: (l) => l.invoice_number || 'Advance' }, { key: 'supplier_invoice_no', label: 'Supplier ref' },
      { key: 'amount', label: 'Amount settled', type: 'money' }, { key: 'wht_rate', label: 'WHT %', render: (l) => `${(Number(l.wht_rate) * 100).toFixed(2)}%` },
      { key: 'wht_amount', label: 'WHT', type: 'money' }, { key: 'stw_amount', label: 'ST withheld', type: 'money' }, { key: 'override_reason', label: 'Rate override' }],
    totals: (x) => [['Gross', x.gross_amount], ['WHT', x.wht_amount], ['ST withheld', x.stw_amount], ['Net to bank', x.net_amount]],
    extra: (x) => (x.is_advance && x.status === 'POSTED' && Number(x.advance_unapplied) > 0 ? [AdvanceApply, { doc: x, side: 'ap' }] : null) },
  ar_doc: { ep: '/ar/documents', attach: 'ar_document', wf: { prefix: 'ar_invoice', doc: 'AR_INVOICE' }, editPath: (x) => `/ar/documents/${x.id}/edit`,
    reverse: (x) => ({ url: `/ar/documents/${x.id}/reverse`, body: { reversal_date: rev.date, reason: rev.reason } }), revPerm: 'ar_invoice.reverse',
    title: (x) => `${x.doc_type.replace('_', ' ').toLowerCase()} ${x.number}`,
    facts: (x) => [['Customer', party(x.customer)], ['Customer reference', x.customer_reference || '-'], ['Invoice date', fmtDate(x.invoice_date)],
      ['Due date', fmtDate(x.due_date)], ['Description', x.description], ['Outstanding', fmtMoney(x.outstanding)]],
    lineCols: [{ key: 'line_no', label: '#' }, { key: 'account_code', label: 'Account' }, { key: 'account_name', label: 'Name' }, { key: 'site_code', label: 'Site' }, { key: 'cost_centre_code', label: 'CC' },
      { key: 'description', label: 'Description' }, { key: 'amount', label: 'Amount', type: 'money' }, { key: 'tax_amount', label: 'Tax', type: 'money' }],
    totals: (x) => [['Subtotal', x.subtotal], ['Tax', x.tax_total], ['Total', x.total]] },
  ar_receipt: { ep: '/ar/receipts', attach: 'ar_receipt', wf: { prefix: 'ar_receipt', doc: 'AR_RECEIPT' }, editPath: (x) => `/ar/receipts/${x.id}/edit`,
    reverse: (x) => ({ url: `/ar/receipts/${x.id}/reverse`, body: { reversal_date: rev.date, reason: rev.reason } }), revPerm: 'ar_receipt.reverse',
    title: (x) => `Receipt ${x.number}`,
    facts: (x) => [['Customer', party(x.customer)], ['Date', fmtDate(x.receipt_date)], ['Method', x.receipt_method], ['Reference', x.reference || '-'],
      ['Received in bank', fmtMoney(x.amount_received)], ['Tax deducted by customer', fmtMoney(x.tax_deducted)], ['Unapplied / advance', fmtMoney(x.unapplied_amount)]],
    lineCols: [{ key: 'invoice_number', label: 'Invoice' }, { key: 'amount', label: 'Allocated', type: 'money' }],
    totals: (x) => [['Gross', x.gross_amount]],
    extra: (x) => (x.status === 'POSTED' && Number(x.unapplied_amount) > 0 ? [AdvanceApply, { doc: x, side: 'ar' }] : null) },
  voucher: { ep: '/banking/vouchers', attach: 'cash_voucher', wf: { prefix: 'cash_voucher', doc: 'CASH_VOUCHER' }, editPath: (x) => `/bank/vouchers/${x.id}/edit`,
    reverse: (x) => ({ url: `/banking/vouchers/${x.id}/reverse`, body: { reversal_date: rev.date, reason: rev.reason } }), revPerm: 'cash_voucher.reverse',
    title: (x) => `${x.voucher_type} ${x.number}`,
    facts: (x) => [['Date', fmtDate(x.voucher_date)], ['Counterparty', x.counterparty || '-'], ['Cheque', x.cheque_no || '-'], ['Description', x.description]],
    lineCols: [{ key: 'account_code', label: 'Account' }, { key: 'account_name', label: 'Name' }, { key: 'site_code', label: 'Site' }, { key: 'cost_centre_code', label: 'CC' },
      { key: 'description', label: 'Description' }, { key: 'amount', label: 'Amount', type: 'money' }, { key: 'tax_amount', label: 'Tax', type: 'money' }],
    totals: (x) => [['Gross', x.gross_total], ['Tax', x.tax_total], ['Net', x.net_total]] },
  transfer: { ep: '/banking/transfers', attach: 'bank_transfer', wf: { prefix: 'bank_transfer', doc: 'BANK_TRANSFER' },
    title: (x) => `Transfer ${x.number}`, lines: () => [],
    facts: (x) => [['Date', fmtDate(x.transfer_date)], ['From account', `#${x.from_account_id}`], ['To account', `#${x.to_account_id}`], ['Amount', fmtMoney(x.amount)],
      ['Charges', fmtMoney(x.charges)], ['Via transit', x.via_transit ? 'Yes' : 'No'], ['Received', fmtDate(x.received_date) || (x.via_transit ? 'Awaiting bank credit' : '-')], ['Description', x.description]],
    lineCols: [], extra: (x) => (x.via_transit && x.status === 'POSTED' && !x.receive_journal_id ? [ReceiveTransfer, { doc: x }] : null) },
}
const ReceiveTransfer = {
  props: ['doc'], emits: ['changed'],
  setup(p, { emit }) {
    const dt = ref(today())
    const go = async () => { try { await api.post(`/banking/transfers/${p.doc.id}/receive`, { received_date: dt.value }); toast('Receipt recorded'); emit('changed') } catch (e) { showError(e) } }
    return () => h('div', { class: 'row' }, [h('strong', 'Record bank credit'), h('input', { type: 'date', value: dt.value, onInput: (e) => { dt.value = e.target.value }, style: 'max-width:180px' }), h('button', { class: 'btn primary', onClick: go }, 'Receive')])
  },
}
const cfg = computed(() => CFG[props.kind])
const extra = computed(() => (d.value && CFG[props.kind].extra ? CFG[props.kind].extra(d.value) : null))
const editable = computed(() => ['DRAFT', 'SUBMITTED', 'CHECKED', 'APPROVED'].includes(d.value?.status) && (!CFG[props.kind].manualOnly || (d.value.source_module === 'MANUAL' || d.value.source_module === 'RECURRING')))
const canReverse = computed(() => d.value?.status === 'POSTED' && CFG[props.kind].reverse && session.can(CFG[props.kind].revPerm) && (!CFG[props.kind].manualOnly || d.value.source_module === 'MANUAL' || d.value.source_module === 'RECURRING'))
async function load() { try { d.value = await api.get(`${CFG[props.kind].ep}/${props.id}`) } catch (e) { showError(e) } }
async function reverse() {
  const r = CFG[props.kind].reverse(d.value)
  try {
    const res = await api.post(r.url, r.body)
    toast('Reversal created'); showReverse.value = false
    if (props.kind === 'journal') router.push(`/journals/${res.id}`); else load()
  } catch (e) { showError(e) }
}
const print = () => window.print()
onMounted(async () => { load(); try { wfConfig.value = await api.get('/admin/workflow-config') } catch { /* ignore */ } })
</script>
