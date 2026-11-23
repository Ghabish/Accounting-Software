<template>
  <div>
    <div class="page-head"><h1>Month-end checklist - {{ period?.name }}</h1><span v-if="period" class="badge" :class="period.status">{{ period.status }}</span>
      <div class="actions"><button class="btn" @click="load">Re-run checks</button>
        <button v-if="session.can('period.close') && period?.status !== 'CLOSED'" class="btn ok" @click="close">Close period</button></div></div>
    <div class="panel">
      <div class="table-wrap"><table><thead><tr><th>Check</th><th>Status</th><th>Detail</th><th>Sign-off</th><th></th></tr></thead>
        <tbody><tr v-for="i in items" :key="i.id">
          <td>{{ i.title }} <span v-if="!i.is_blocking" class="badge">advisory</span> <span v-if="!i.is_auto" class="badge">manual</span></td>
          <td><span class="badge" :class="i.status">{{ i.status }}</span></td>
          <td class="small">{{ i.detail }}<div v-if="i.comment" class="muted">{{ i.comment }}</div></td>
          <td class="small muted">{{ fmtDateTime(i.signed_off_at) }}</td>
          <td class="nowrap">
            <button v-if="!i.is_auto && i.status !== 'DONE' && session.can('period.close')" class="btn sm ok" @click="sign(i, 'DONE')">Done</button>
            <button v-if="['FAIL', 'PENDING'].includes(i.status) && session.can('period.reopen')" class="btn sm" @click="sign(i, 'WAIVED')">Waive</button>
          </td></tr></tbody></table></div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtDateTime } from '../format.js'
import { session, toast } from '../store.js'
const props = defineProps({ id: [String, Number] })
const items = ref([]); const period = ref(null)
async function load() {
  try { items.value = await api.get(`/closing/${props.id}/checklist`); period.value = (await api.get('/periods')).find((p) => p.id === Number(props.id)) } catch (e) { showError(e) }
}
async function sign(i, status) {
  const comment = status === 'WAIVED' ? prompt('Reason for waiving this check?') : prompt('Comment (optional)') ?? ''
  if (status === 'WAIVED' && !comment) return
  try { await api.post(`/closing/${props.id}/checklist/${i.code}`, { status, comment }); load() } catch (e) { showError(e) }
}
async function close() { try { await api.post(`/closing/${props.id}/close`); toast('Period closed'); load() } catch (e) { showError(e) } }
onMounted(load)
</script>
