const BASE = import.meta.env.VITE_API || ''

async function req(method, path, body, isForm) {
  const opt = { method, headers: {} }
  if (body !== undefined) {
    if (isForm) opt.body = body
    else { opt.body = JSON.stringify(body); opt.headers['Content-Type'] = 'application/json' }
  }
  const r = await fetch(BASE + path, opt)
  const ct = r.headers.get('content-type') || ''
  const data = ct.includes('json') ? await r.json() : await r.text()
  if (!r.ok) throw new Error((data && data.detail) || r.statusText)
  return data
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b) => req('POST', p, b ?? {}),
  patch: (p, b) => req('PATCH', p, b),
  form: (p, fd) => req('POST', p, fd, true),
  file: (name) => `${BASE}/api/files/${encodeURIComponent(name)}`,
  sample: (name) => `${BASE}/api/samples/${encodeURIComponent(name)}`,
}

const fmt = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
export const inr = (n) => (n == null ? '—' : (n < 0 ? '-₹' : '₹') + fmt.format(Math.abs(Math.round(n))))
export const inrK = (n) => (Math.abs(n) >= 100000 ? `₹${(n / 100000).toFixed(2)} L` : inr(n))
export const d = (s, opt = { day: 'numeric', month: 'short' }) => (s ? new Date(s).toLocaleDateString('en-IN', opt) : '—')
export const dt = (s) => (s ? new Date(s).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—')
export const daysTo = (s, today) => Math.round((new Date(s) - new Date(today)) / 86400000)
