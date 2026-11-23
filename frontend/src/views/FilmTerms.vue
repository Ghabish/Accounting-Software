<template>
  <div v-if="film">
    <div class="page-head"><h1>Distributor terms - {{ film.title }}</h1></div>
    <div class="panel">
      <p class="small muted">Distributor share of net box office (after taxes) by week since release ({{ fmtDate(film.release_date) }}). Leave site blank for all sites.</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Site</th><th>Week from</th><th>Week to</th><th>Share (e.g. 0.50)</th><th>Minimum guarantee</th><th></th></tr></thead>
        <tbody><tr v-for="(t, i) in terms" :key="i">
          <td><Picker v-model="t.site_id" :options="sites" placeholder="All sites" /></td>
          <td><input v-model="t.week_from" type="number" min="1" /></td><td><input v-model="t.week_to" type="number" min="1" /></td>
          <td><input v-model="t.share_pct" type="number" step="0.01" min="0" max="1" /></td><td><input v-model="t.minimum_guarantee" type="number" step="0.01" /></td>
          <td><button class="btn sm ghost" @click="terms.splice(i, 1)">✕</button></td></tr></tbody>
      </table></div>
      <div class="row" style="margin-top:.75rem"><button class="btn" @click="terms.push({ site_id: null, week_from: 1, week_to: 999, share_pct: 0.5 })">+ Add term</button>
        <span class="spacer"></span><button class="btn primary" @click="save">Save terms</button></div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, showError } from '../api.js'
import { fmtDate } from '../format.js'
import { opt, refs } from '../refs.js'
import { toast } from '../store.js'
import Picker from '../components/Picker.vue'
const props = defineProps({ id: [String, Number] })
const film = ref(null); const terms = ref([]); const sites = ref([])
async function save() {
  try { await api.put(`/cinema/films/${props.id}/terms`, terms.value.map((t) => ({ ...t, minimum_guarantee: t.minimum_guarantee || null }))); toast('Terms saved') } catch (e) { showError(e) }
}
onMounted(async () => {
  film.value = await api.get(`/cinema/films/${props.id}`)
  terms.value = film.value.terms.map((t) => ({ site_id: t.site_id, week_from: t.week_from, week_to: t.week_to, share_pct: Number(t.share_pct), minimum_guarantee: t.minimum_guarantee }))
  sites.value = (await refs.sites()).map(opt.coded)
})
</script>
