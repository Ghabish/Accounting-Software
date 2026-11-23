// Thin fetch wrapper: bearer token, JSON, error normalisation, downloads.
import { session, toast } from './store.js'

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message || `Request failed (${status})`)
    this.status = status
    this.code = body?.error
    this.details = body?.details
  }
}

function qs(params) {
  if (!params) return ''
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    p.append(k, Array.isArray(v) ? v.join(',') : v)
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

async function request(method, path, { params, body, form, raw } = {}) {
  const headers = {}
  if (session.token) headers.Authorization = `Bearer ${session.token}`
  let payload
  if (form) payload = form
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  const res = await fetch(`/api${path}${qs(params)}`, { method, headers, body: payload })
  if (res.status === 401 && !path.startsWith('/auth/login')) {
    session.logout()
    location.hash = ''
    throw new ApiError(401, { message: 'Your session has expired. Please sign in again.' })
  }
  if (raw) {
    if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => ({})))
    return res
  }
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) throw new ApiError(res.status, data)
  return data
}

export const api = {
  get: (p, params) => request('GET', p, { params }),
  post: (p, body, params) => request('POST', p, { body: body ?? {}, params }),
  put: (p, body) => request('PUT', p, { body }),
  patch: (p, body) => request('PATCH', p, { body }),
  del: (p) => request('DELETE', p),
  upload: (p, form) => request('POST', p, { form }),
  async download(p, params, fallbackName = 'report') {
    const res = await request('GET', p, { params, raw: true })
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition') || ''
    const m = cd.match(/filename="?([^"]+)"?/)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = m ? m[1] : fallbackName
    document.body.appendChild(a)
    a.click()
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove() }, 1000)
  },
}

export function showError(e) {
  const details = Array.isArray(e?.details) ? e.details : (e?.details && typeof e.details === 'object' ? Object.values(e.details) : [])
  toast(e?.message || String(e), 'error', details)
}
