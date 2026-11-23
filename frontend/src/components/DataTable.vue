<template>
  <div>
    <div class="table-wrap">
      <table>
        <thead><tr><th v-for="c in columns" :key="c.key" :class="{ num: isNum(c) }">{{ c.label }}</th><th v-if="$slots.actions"></th></tr></thead>
        <tbody>
          <tr v-if="loading"><td :colspan="columns.length + 1" class="empty">Loading…</td></tr>
          <tr v-else-if="!rows.length"><td :colspan="columns.length + 1" class="empty">{{ empty }}</td></tr>
          <tr v-for="(r, i) in rows" v-else :key="r.id ?? i" :class="{ clickable: !!rowLink || clickable }" @click="onRow(r)">
            <td v-for="c in columns" :key="c.key" :class="[{ num: isNum(c) }, negClass(c, r)]">
              <slot :name="`cell-${c.key}`" :row="r" :value="get(r, c.key)">
                <span v-if="c.type === 'status'" class="badge" :class="get(r, c.key)">{{ get(r, c.key) }}</span>
                <template v-else>{{ c.render ? c.render(r) : format(get(r, c.key), c.type) }}</template>
              </slot>
            </td>
            <td v-if="$slots.actions" class="nowrap" @click.stop><slot name="actions" :row="r" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="total > pageSize" class="pager">
      <span class="small muted">{{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, total) }} of {{ total }}</span>
      <button class="btn sm" :disabled="page <= 1" @click="$emit('page', page - 1)">‹ Prev</button>
      <button class="btn sm" :disabled="page * pageSize >= total" @click="$emit('page', page + 1)">Next ›</button>
    </div>
  </div>
</template>
<script setup>
import { useRouter } from 'vue-router'
import { format } from '../format.js'
const props = defineProps({
  columns: Array, rows: { type: Array, default: () => [] }, loading: Boolean, rowLink: Function, clickable: Boolean,
  total: { type: Number, default: 0 }, page: { type: Number, default: 1 }, pageSize: { type: Number, default: 50 },
  empty: { type: String, default: 'No records found' },
})
const emit = defineEmits(['page', 'row'])
const router = useRouter()
const get = (r, k) => k.split('.').reduce((o, p) => (o == null ? o : o[p]), r)
const isNum = (c) => ['money', 'int', 'pct', 'number'].includes(c.type)
const negClass = (c, r) => (c.type === 'money' && Number(get(r, c.key)) < 0 ? 'neg' : '')
function onRow(r) { emit('row', r); if (props.rowLink) router.push(props.rowLink(r)) }
</script>
