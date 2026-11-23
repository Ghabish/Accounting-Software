export const fmtMoney = (v, { zero = '-', decimals = 2 } = {}) => {
  if (v === null || v === undefined || v === '') return ''
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  if (n === 0) return zero
  const s = Math.abs(n).toLocaleString('en-PK', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
  return n < 0 ? `(${s})` : s
}
export const fmtCompact = (v) => {
  const n = Number(v || 0)
  const a = Math.abs(n)
  const s = a >= 1e9 ? `${(a / 1e9).toFixed(2)}bn` : a >= 1e6 ? `${(a / 1e6).toFixed(2)}m` : a >= 1e3 ? `${(a / 1e3).toFixed(1)}k` : a.toFixed(0)
  return n < 0 ? `(${s})` : s
}
export const fmtPct = (v) => (v === null || v === undefined ? '-' : `${Number(v).toFixed(1)}%`)
export const fmtInt = (v) => (v === null || v === undefined || v === '' ? '' : Number(v).toLocaleString('en-PK'))
export const fmtDate = (v) => {
  if (!v) return ''
  const d = new Date(String(v).length <= 10 ? `${v}T00:00:00` : v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}
export const fmtDateTime = (v) => (v ? new Date(v).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '')
export const today = () => new Date().toISOString().slice(0, 10)
export const monthStart = (d = new Date()) => new Date(d.getFullYear(), d.getMonth(), 1).toLocaleDateString('en-CA')
export const monthEnd = (d = new Date()) => new Date(d.getFullYear(), d.getMonth() + 1, 0).toLocaleDateString('en-CA')
export const fyStart = (d = new Date()) => new Date(d.getMonth() >= 6 ? d.getFullYear() : d.getFullYear() - 1, 6, 1).toLocaleDateString('en-CA')
export function format(v, type) {
  if (type === 'money') return fmtMoney(v)
  if (type === 'pct') return fmtPct(v)
  if (type === 'int') return fmtInt(v)
  if (type === 'date') return fmtDate(v)
  if (type === 'datetime') return fmtDateTime(v)
  if (type === 'bool') return v ? 'Yes' : 'No'
  return v ?? ''
}
