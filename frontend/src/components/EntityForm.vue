<template>
  <div class="form-grid">
    <div v-for="f in visible" :key="f.key" class="field" :class="{ wide: f.wide || f.type === 'textarea' }">
      <label v-if="f.type !== 'checkbox'">{{ f.label }} <span v-if="f.required" class="req">*</span></label>
      <Picker v-if="f.type === 'picker'" v-model="model[f.key]" :options="options[f.key] || []" :disabled="f.readonlyEdit && editing" />
      <select v-else-if="f.type === 'select'" v-model="model[f.key]" :disabled="f.readonlyEdit && editing">
        <option v-if="!f.required" :value="null">—</option>
        <option v-for="o in f.options" :key="o.value ?? o" :value="o.value ?? o">{{ o.label ?? o }}</option>
      </select>
      <textarea v-else-if="f.type === 'textarea'" v-model="model[f.key]"></textarea>
      <label v-else-if="f.type === 'checkbox'" class="check"><input v-model="model[f.key]" type="checkbox" /> {{ f.label }}</label>
      <input v-else v-model="model[f.key]" :type="f.type || 'text'" :step="f.step" :disabled="f.readonlyEdit && editing" :placeholder="f.placeholder" />
      <small v-if="f.help" class="muted">{{ f.help }}</small>
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive } from 'vue'
import Picker from './Picker.vue'
const props = defineProps({ fields: Array, model: Object, editing: Boolean })
const options = reactive({})
const visible = computed(() => props.fields.filter((f) => !(f.createOnly && props.editing) && !(f.editOnly && !props.editing)))
onMounted(async () => {
  for (const f of props.fields) if (f.type === 'picker' && f.load) options[f.key] = await f.load()
})
</script>
