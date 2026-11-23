<template><div class="chart-box" :style="{ height }"><canvas ref="cv"></canvas></div></template>
<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Chart from 'chart.js/auto'
const props = defineProps({ config: Object, height: { type: String, default: '280px' } })
const cv = ref(null)
let chart = null
const draw = () => { if (chart) chart.destroy(); if (props.config) chart = new Chart(cv.value, { ...props.config, options: { responsive: true, maintainAspectRatio: false, ...(props.config.options || {}) } }) }
onMounted(draw)
watch(() => props.config, draw, { deep: true })
onBeforeUnmount(() => chart && chart.destroy())
</script>
