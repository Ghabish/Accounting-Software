<template>
  <div class="panel">
    <div class="row">
      <div class="steps">
        <span v-for="s in steps" :key="s" class="s" :class="{ done: idx(s) < idx(status), cur: s === status }">{{ s }}</span>
        <span v-if="['REVERSED', 'CANCELLED'].includes(status)" class="s cur">{{ status }}</span>
      </div>
      <span class="spacer"></span>
      <input v-if="needsComment" v-model="comment" placeholder="Comment / reason" style="max-width:260px" />
      <button v-for="a in actions" :key="a.action" class="btn" :class="a.cls" :disabled="busy" @click="run(a.action)">{{ a.label }}</button>
    </div>
  </div>
</template>
<script setup>
import { computed, ref } from 'vue'
import { api, showError } from '../api.js'
import { session, toast } from '../store.js'
const props = defineProps({ status: String, base: String, prefix: String, check: { type: Boolean, default: false } })
const emit = defineEmits(['done'])
const busy = ref(false)
const comment = ref('')
const steps = computed(() => (props.check ? ['DRAFT', 'SUBMITTED', 'CHECKED', 'APPROVED', 'POSTED'] : ['DRAFT', 'SUBMITTED', 'APPROVED', 'POSTED']))
const idx = (s) => steps.value.indexOf(s)
const actions = computed(() => {
  const p = props.prefix
  const s = props.status
  const out = []
  if (s === 'DRAFT' && session.can(`${p}.create`)) out.push({ action: 'submit', label: 'Submit', cls: 'primary' }, { action: 'cancel', label: 'Cancel draft' })
  if (s === 'SUBMITTED' && props.check && session.can(`${p}.check`)) out.push({ action: 'check', label: 'Check', cls: 'primary' })
  const approvable = props.check ? 'CHECKED' : 'SUBMITTED'
  if (s === approvable && session.can(`${p}.approve`)) out.push({ action: 'approve', label: 'Approve', cls: 'ok' })
  if (s === 'APPROVED' && session.can(`${p}.post`)) out.push({ action: 'post', label: 'Post to GL', cls: 'ok' })
  if (['SUBMITTED', 'CHECKED', 'APPROVED'].includes(s) && session.canAny(`${p}.check`, `${p}.approve`)) out.push({ action: 'reject', label: 'Reject', cls: 'danger' })
  return out
})
const needsComment = computed(() => actions.value.some((a) => a.action === 'reject'))
async function run(action) {
  if (action === 'cancel' && !confirm('Cancel this draft? It cannot be reused.')) return
  busy.value = true
  try {
    const res = await api.post(`${props.base}/${action}`, { comment: comment.value || null })
    toast(`Done: ${action}`)
    for (const w of res?.warnings || []) toast(w, 'error')
    comment.value = ''
    emit('done', res)
  } catch (e) { showError(e) } finally { busy.value = false }
}
</script>
