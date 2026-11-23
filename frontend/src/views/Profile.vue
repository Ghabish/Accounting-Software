<template>
  <div>
    <div class="page-head"><h1>My profile</h1></div>
    <div v-if="session.user?.must_change_password" class="alert warn">Please set a new password before continuing.</div>
    <div class="grid two">
      <div class="panel">
        <h2>Account</h2>
        <dl class="facts">
          <div><dt>User</dt><dd>{{ session.user?.username }}</dd></div><div><dt>Name</dt><dd>{{ session.user?.full_name }}</dd></div>
          <div><dt>Roles</dt><dd>{{ (session.user?.roles || []).join(', ') }}</dd></div>
          <div><dt>Sites</dt><dd>{{ session.user?.all_sites ? 'All sites' : (session.user?.site_ids || []).join(', ') }}</dd></div>
        </dl>
      </div>
      <form class="panel stack" @submit.prevent="change">
        <h2>Change password</h2>
        <div class="field"><label>Current password</label><input v-model="cur" type="password" required /></div>
        <div class="field"><label>New password</label><input v-model="nw" type="password" required minlength="10" /><small class="muted">At least 10 characters with upper and lower case letters and a digit.</small></div>
        <button class="btn primary">Change password</button>
      </form>
    </div>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, showError } from '../api.js'
import { session, toast } from '../store.js'
const router = useRouter()
const cur = ref('')
const nw = ref('')
async function change() {
  try { await api.post('/auth/change-password', { current_password: cur.value, new_password: nw.value }); toast('Password changed - please sign in again'); session.logout(); router.push('/login') } catch (e) { showError(e) }
}
</script>
