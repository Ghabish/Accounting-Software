<template>
  <div class="picker" ref="root">
    <input :value="open ? term : label" :placeholder="placeholder" :disabled="disabled" @focus="onFocus" @input="term = $event.target.value; open = true; hl = 0"
           @keydown.down.prevent="hl = Math.min(hl + 1, filtered.length - 1)" @keydown.up.prevent="hl = Math.max(hl - 1, 0)"
           @keydown.enter.prevent="choose(filtered[hl])" @keydown.esc="open = false" />
    <div v-if="open" class="list">
      <div v-if="clearable" class="opt" @mousedown.prevent="choose(null)"><small>— none —</small></div>
      <div v-for="(o, i) in filtered" :key="o.value" class="opt" :class="{ hl: i === hl }" @mousedown.prevent="choose(o)">
        {{ o.label }} <small v-if="o.hint"> · {{ o.hint }}</small>
      </div>
      <div v-if="!filtered.length" class="opt"><small>No matches</small></div>
    </div>
  </div>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
const props = defineProps({ modelValue: [Number, String, null], options: { type: Array, default: () => [] }, placeholder: String,
  disabled: Boolean, clearable: { type: Boolean, default: true } })
const emit = defineEmits(['update:modelValue', 'change'])
const open = ref(false)
const term = ref('')
const hl = ref(0)
const root = ref(null)
const label = computed(() => props.options.find((o) => o.value === props.modelValue)?.label || '')
const filtered = computed(() => {
  const t = term.value.trim().toLowerCase()
  const list = t ? props.options.filter((o) => o.label.toLowerCase().includes(t)) : props.options
  return list.slice(0, 200)
})
function onFocus() { term.value = ''; open.value = true; hl.value = 0 }
function choose(o) { emit('update:modelValue', o ? o.value : null); emit('change', o ? o.raw ?? o : null); open.value = false }
const away = (e) => { if (root.value && !root.value.contains(e.target)) open.value = false }
onMounted(() => document.addEventListener('mousedown', away))
onBeforeUnmount(() => document.removeEventListener('mousedown', away))
</script>
