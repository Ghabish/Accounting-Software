<template>
  <div class="login-wrap">
    <form class="login" @submit.prevent="submit">
      <div class="logo"><img src="/icon.svg" alt="" /><div><strong>Universal Cinemas</strong><div class="muted small">Finance &amp; Accounting</div></div></div>
      <div v-if="error" class="alert err">{{ error }}</div>
      <div class="stack">
        <div class="field"><label>Username</label><input v-model="username" autocomplete="username" required autofocus /></div>
        <div class="field"><label>Password</label><input v-model="password" type="password" autocomplete="current-password" required /></div>
        <button class="btn primary" :disabled="busy" type="submit">{{ busy ? 'Signing in…' : 'Sign in' }}</button>
      </div>
      <p class="small muted" style="margin-top:1rem">Access is logged. Accounts lock for 15 minutes after 5 failed attempts.</p>
    </form>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import { session } from '../store.js'
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)
async function submit() {
  busy.value = true
  error.value = ''
  try {
    const r = await api.post('/auth/login', { username: username.value, password: password.value })
    session.login(r.access_token, r.user)
    router.push(r.user.must_change_password ? '/profile' : (route.query.next || '/'))
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
</script>
