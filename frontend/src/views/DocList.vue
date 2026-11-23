<template>
  <div>
    <div class="page-head"><h1>{{ cfg.title }}</h1>
      <div class="actions"><router-link v-if="cfg.newPath && session.can(cfg.createPerm)" class="btn primary" :to="cfg.newPath">{{ cfg.newLabel || 'New' }}</router-link></div>
    </div>
    <div class="panel">
      <form class="filters" @submit.prevent="load(1)">
        <div class="field"><label>Search</label><input v-model="f.q" placeholder="Number, reference, text" /></div>
        <div class="field"><label>Status</label><select v-model="f.status"><option value="">All</option><option v-for="s in statuses" :key="s">{{ s }}</option></select></div>
        <div class="field"><label>From</label><input v-model="f.date_from" type="date" /></div>
        <div class="field"><label>To</label><input v-model="f.date_to" type="date" /></div>
        <div class="field" style="flex:0 0 auto"><button class="btn">Filter</button></div>
      </form>
      <DataTable :columns="cfg.columns" :rows="rows" :total="total" :page="page" :page-size="50" :loading="loading"
                 :row-link="(r) => `${cfg.viewBase}/${r.id}`" @page="load" />
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, showError } from '../api.js'
import { session } from '../store.js'
import DataTable from '../components/DataTable.vue'
const props = defineProps({ kind: String })
const route = useRoute()
const statuses = ['DRAFT', 'SUBMITTED', 'CHECKED', 'APPROVED', 'POSTED', 'REVERSED', 'CANCELLED']
const CFG = {
  journal: { title: 'Journal vouchers', ep: '/journals', viewBase: '/journals', newPath: '/journals/new', newLabel: 'New journal', createPerm: 'journal.create',
    columns: [{ key: 'posting_date', label: 'Date', type: 'date' }, { key: 'number', label: 'Number', render: (r) => r.number || `Draft #${r.id}` },
      { key: 'journal_type', label: 'Type' }, { key: 'description', label: 'Description' }, { key: 'source_module', label: 'Source' },
      { key: 'total_debit', label: 'Amount', type: 'money' }, { key: 'status', label: 'Status', type: 'status' }] },
  ap_doc: { title: 'Supplier invoices & notes', ep: '/ap/documents', viewBase: '/ap/documents', newPath: '/ap/documents/new', newLabel: 'New invoice / note', createPerm: 'ap_invoice.create',
    columns: [{ key: 'invoice_date', label: 'Date', type: 'date' }, { key: 'number', label: 'Number' }, { key: 'doc_type', label: 'Type' },
      { key: 'supplier_name', label: 'Supplier' }, { key: 'supplier_invoice_no', label: 'Supplier ref' }, { key: 'due_date', label: 'Due', type: 'date' },
      { key: 'total', label: 'Total', type: 'money' }, { key: 'outstanding', label: 'Outstanding', type: 'money' },
      { key: 'payment_status', label: 'Payment', type: 'status' }, { key: 'status', label: 'Status', type: 'status' }] },
  ap_payment: { title: 'Supplier payments', ep: '/ap/payments', viewBase: '/ap/payments', newPath: '/ap/payments/new', newLabel: 'New payment', createPerm: 'ap_payment.create',
    columns: [{ key: 'payment_date', label: 'Date', type: 'date' }, { key: 'number', label: 'Number' }, { key: 'supplier_name', label: 'Supplier' },
      { key: 'cheque_no', label: 'Cheque' }, { key: 'gross_amount', label: 'Gross', type: 'money' }, { key: 'wht_amount', label: 'WHT', type: 'money' },
      { key: 'stw_amount', label: 'ST withheld', type: 'money' }, { key: 'net_amount', label: 'Net paid', type: 'money' }, { key: 'status', label: 'Status', type: 'status' }] },
  ar_doc: { title: 'Customer invoices & notes', ep: '/ar/documents', viewBase: '/ar/documents', newPath: '/ar/documents/new', newLabel: 'New invoice / note', createPerm: 'ar_invoice.create',
    columns: [{ key: 'invoice_date', label: 'Date', type: 'date' }, { key: 'number', label: 'Number' }, { key: 'doc_type', label: 'Type' },
      { key: 'customer_name', label: 'Customer' }, { key: 'due_date', label: 'Due', type: 'date' }, { key: 'total', label: 'Total', type: 'money' },
      { key: 'outstanding', label: 'Outstanding', type: 'money' }, { key: 'payment_status', label: 'Payment', type: 'status' }, { key: 'status', label: 'Status', type: 'status' }] },
  ar_receipt: { title: 'Customer receipts', ep: '/ar/receipts', viewBase: '/ar/receipts', newPath: '/ar/receipts/new', newLabel: 'New receipt', createPerm: 'ar_receipt.create',
    columns: [{ key: 'receipt_date', label: 'Date', type: 'date' }, { key: 'number', label: 'Number' }, { key: 'customer_name', label: 'Customer' },
      { key: 'reference', label: 'Reference' }, { key: 'amount_received', label: 'Received', type: 'money' }, { key: 'tax_deducted', label: 'Tax deducted', type: 'money' },
      { key: 'unapplied_amount', label: 'Unapplied', type: 'money' }, { key: 'status', label: 'Status', type: 'status' }] },
  voucher: { title: 'Cash & bank receipts / payments', ep: '/banking/vouchers', viewBase: '/bank/vouchers', newPath: '/bank/vouchers/new', newLabel: 'New voucher', createPerm: 'cash_voucher.create',
    columns: [{ key: 'voucher_date', label: 'Date', type: 'date' }, { key: 'number', label: 'Number' }, { key: 'voucher_type', label: 'Type' },
      { key: 'counterparty', label: 'Counterparty' }, { key: 'description', label: 'Description' }, { key: 'gross_total', label: 'Gross', type: 'money' },
      { key: 'net_total', label: 'Net', type: 'money' }, { key: 'status', label: 'Status', type: 'status' }] },
  transfer: { title: 'Bank & cash transfers', ep: '/banking/transfers', viewBase: '/bank/transfers', newPath: '/bank/transfers/new', newLabel: 'New transfer', createPerm: 'bank_transfer.create',
    columns: [{ key: 'transfer_date', label: 'Date', type: 'date' }, { key: 'number', label: 'Number' }, { key: 'description', label: 'Description' },
      { key: 'amount', label: 'Amount', type: 'money' }, { key: 'via_transit', label: 'Via transit', type: 'bool' }, { key: 'received_date', label: 'Received', type: 'date' },
      { key: 'status', label: 'Status', type: 'status' }] },
}
const cfg = computed(() => CFG[props.kind])
const f = reactive({ q: route.query.q || '', status: '', date_from: '', date_to: '' })
const rows = ref([]); const total = ref(0); const page = ref(1); const loading = ref(false)
async function load(p = 1) {
  loading.value = true
  try { const r = await api.get(cfg.value.ep, { ...f, page: p }); rows.value = r.items; total.value = r.total; page.value = p } catch (e) { showError(e) } finally { loading.value = false }
}
onMounted(load)
</script>
