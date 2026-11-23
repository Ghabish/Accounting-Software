<template>
  <router-view v-if="$route.meta.public" />
  <div v-else class="shell">
    <aside class="sidebar" :class="{ open: ui.sidebarOpen }">
      <div class="brand"><img src="/icon.svg" alt="" /> Universal Cinemas</div>
      <nav>
        <div v-for="g in groups" :key="g.group" class="nav-group">
          <button @click="toggle(g.group)">{{ g.group }} <span>{{ collapsed[g.group] ? '+' : '–' }}</span></button>
          <template v-if="!collapsed[g.group]">
            <router-link v-for="i in g.items" :key="i.to" :to="i.to" @click="ui.sidebarOpen = false">{{ i.label }}</router-link>
          </template>
        </div>
      </nav>
    </aside>
    <div class="backdrop" :class="{ show: ui.sidebarOpen }" @click="ui.sidebarOpen = false"></div>
    <div class="main">
      <header class="topbar">
        <button class="btn ghost burger" aria-label="Menu" @click="ui.sidebarOpen = !ui.sidebarOpen">☰</button>
        <form class="grow row hide-sm" @submit.prevent="search">
          <input v-model="q" placeholder="Search journals, suppliers, customers, documents…" style="max-width:420px" />
        </form>
        <span class="spacer"></span>
        <span class="small muted hide-sm">{{ session.user?.full_name }} · {{ (session.user?.roles || []).join(', ') }}</span>
        <router-link class="btn sm" to="/profile">Profile</router-link>
        <button class="btn sm" @click="logout">Sign out</button>
      </header>
      <main class="content"><router-view :key="$route.fullPath" /></main>
    </div>
  </div>
  <div class="toasts">
    <div v-for="t in ui.toasts" :key="t.id" class="toast" :class="t.kind">
      <div>{{ t.message }}</div>
      <ul v-if="t.details && t.details.length"><li v-for="(d, i) in t.details.slice(0, 8)" :key="i">{{ d }}</li></ul>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NAV } from './nav.js'
import { session, ui } from './store.js'
import { api } from './api.js'

const router = useRouter()
const q = ref('')
const collapsed = reactive(JSON.parse(localStorage.getItem('ucf.nav') || '{}'))
const groups = computed(() => NAV.map((g) => ({ ...g, items: g.items.filter((i) => !i.perm || session.can(i.perm)) })).filter((g) => g.items.length))
function toggle(g) { collapsed[g] = !collapsed[g]; try { localStorage.setItem('ucf.nav', JSON.stringify(collapsed)) } catch { /* ignore */ } }
async function logout() { try { await api.post('/auth/logout-all') } catch { /* ignore */ } session.logout(); router.push('/login') }
function search() {
  const s = q.value.trim()
  if (!s) return
  if (/^(V|C)\d{5}$/i.test(s)) router.push(`/masters/${s[0].toUpperCase() === 'V' ? 'suppliers' : 'customers'}?q=${s}`)
  else if (/^(PI|PCN|PDN|POB)-/i.test(s)) router.push(`/ap/documents?q=${s}`)
  else if (/^(SI|SCN|SDN|SOB)-/i.test(s)) router.push(`/ar/documents?q=${s}`)
  else router.push(`/journals?q=${encodeURIComponent(s)}`)
  q.value = ''
}
</script>
