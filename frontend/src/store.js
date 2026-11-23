import { reactive } from 'vue'

const saved = (() => { try { return JSON.parse(sessionStorage.getItem('ucf.session') || 'null') } catch { return null } })()

export const session = reactive({
  token: saved?.token || null,
  user: saved?.user || null,
  login(token, user) {
    this.token = token
    this.user = user
    try { sessionStorage.setItem('ucf.session', JSON.stringify({ token, user })) } catch { /* private mode */ }
  },
  logout() {
    this.token = null
    this.user = null
    try { sessionStorage.removeItem('ucf.session') } catch { /* ignore */ }
    lookups.clear()
  },
  can(perm) {
    if (!this.user) return false
    if (this.user.is_superuser) return true
    return (this.user.permissions || []).includes(perm)
  },
  canAny(...perms) { return perms.some((p) => this.can(p)) },
})

export const ui = reactive({ toasts: [], sidebarOpen: false })
let toastId = 0
export function toast(message, kind = 'success', details = []) {
  const id = ++toastId
  ui.toasts.push({ id, message, kind, details })
  setTimeout(() => { const i = ui.toasts.findIndex((t) => t.id === id); if (i >= 0) ui.toasts.splice(i, 1) }, kind === 'error' ? 9000 : 3500)
}

// Cached reference data used by pickers (refreshed on demand)
const cache = new Map()
export const lookups = {
  async get(key, loader) {
    if (!cache.has(key)) cache.set(key, loader().catch((e) => { cache.delete(key); throw e }))
    return cache.get(key)
  },
  invalidate(key) { cache.delete(key) },
  clear() { cache.clear() },
}
