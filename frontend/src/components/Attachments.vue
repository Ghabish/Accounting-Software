<template>
  <div class="panel">
    <h3>Supporting documents</h3>
    <div v-if="!items.length" class="muted small">No attachments</div>
    <div v-for="a in items" :key="a.id" class="row small">
      <a href="#" @click.prevent="download(a)">{{ a.filename }}</a>
      <span class="muted">{{ Math.round(a.size_bytes / 1024) }} KB · {{ fmtDateTime(a.uploaded_at) }}</span>
    </div>
    <div v-if="!readonly" class="row" style="margin-top:.6rem">
      <input ref="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.csv,.xlsx,.docx,.txt" style="max-width:320px" />
      <button class="btn sm" @click="upload">Upload</button>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { toast } from '../store.js'
import { fmtDateTime } from '../format.js'
const props = defineProps({ entityType: String, entityId: [Number, String], readonly: Boolean })
const items = ref([])
const file = ref(null)
async function load() { items.value = await api.get('/attachments', { entity_type: props.entityType, entity_id: props.entityId }) }
async function upload() {
  const f = file.value?.files?.[0]
  if (!f) return
  const fd = new FormData()
  fd.append('entity_type', props.entityType)
  fd.append('entity_id', props.entityId)
  fd.append('file', f)
  try { await api.upload('/attachments', fd); toast('Attachment uploaded'); file.value.value = ''; load() } catch (e) { showError(e) }
}
const download = (a) => api.download(`/attachments/${a.id}/download`, null, a.filename).catch(showError)
onMounted(load)
</script>
