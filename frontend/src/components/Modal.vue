<template>
  <div class="modal-bg" @mousedown.self="$emit('close')">
    <div class="modal" :style="{ width: width }">
      <header><strong>{{ title }}</strong><span class="spacer"></span><button class="btn ghost sm" @click="$emit('close')">✕</button></header>
      <div class="body"><slot /></div>
      <footer v-if="$slots.footer"><slot name="footer" /></footer>
    </div>
  </div>
</template>
<script setup>
defineProps({ title: String, width: { type: String, default: 'min(900px, 100%)' } })
defineEmits(['close'])
</script>
