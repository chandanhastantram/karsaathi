import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { api, d } from './api'
import { Rotator } from './fx/fx'
import { Ctx, Icon, Seg, Toast } from './ui'
import Home from './pages/Home'
import Overview from './pages/Overview'
import WhatsApp from './pages/WhatsApp'
import Documents, { DocDrawer } from './pages/Documents'
import Suppliers from './pages/Suppliers'
import EwayBills from './pages/EwayBills'
import Return from './pages/Return'
import Deadlines from './pages/Deadlines'
import Rules from './pages/Rules'
import Audit from './pages/Audit'
import Console from './pages/Console'

const Landing = lazy(() => import('./landing/Landing'))

const PAGES = [
  ['home', 'Home', 'home'],
  ['overview', 'Dashboard', 'dash'],
  ['whatsapp', 'WhatsApp inbox', 'chat'],
  ['documents', 'Documents', 'docs'],
  ['suppliers', 'Suppliers & IMS', 'swap'],
  ['eway', 'E-way bills', 'truck'],
  ['return', 'Return & approval', 'check'],
  ['deadlines', 'Deadlines & notices', 'clock'],
]
const ADMIN = [
  ['console', 'Accountant console', 'list'],
  ['rules', 'Rule sets', 'rule'],
  ['audit', 'Audit trail', 'hash'],
]
const ALL = new Set([...PAGES, ...ADMIN].map((p) => p[0]))

// UI language list. Planned next: bn, te, mr, ta, ur, gu, ml, or, pa, as (backend i18n.py first).
export const LANGS = [['en', 'EN'], ['hi', 'हि'], ['kn', 'ಕ']]

export const TIPS = [
  'Suppliers file by the 11th. Some of them… eventually.',
  'The AI reads. The rule book counts. You decide.',
  'A blurry bill is not a crime. It just goes to review.',
  'Vehicle number KA5AB123? Nice try. Pre-flight caught it.',
  'Unpaid for 180 days? Rule 37 is watching.',
  'Every number here has a receipt. Literally.',
  'No filing happens without two humans. Even at 2 AM.',
  'Chai break approved. Return approval needs a signature.',
]

const routeFromHash = () => {
  const h = location.hash.replace(/^#\/?/, '')
  return ALL.has(h) ? h : 'landing'
}

export default function App() {
  const [meta, setMeta] = useState(null)
  const [cid, setCid] = useState(1)
  const [page, setPage] = useState(routeFromHash)
  const [role, setRole] = useState('owner')
  const [lang, setLang] = useState('kn')
  const [toastV, setToastV] = useState(null)
  const [docId, setDocId] = useState(null)
  const [tick, setTick] = useState(0)
  const [pageArg, setPageArg] = useState(null)

  const loadMeta = useCallback(() => api.get('/api/meta').then(setMeta).catch((e) => setToastV({ msg: 'Backend not reachable: ' + e.message, error: true })), [])
  useEffect(() => { loadMeta() }, [loadMeta, tick])
  useEffect(() => { location.hash = page === 'landing' ? '/' : page }, [page])
  useEffect(() => {
    const h = () => setPage(routeFromHash())
    window.addEventListener('hashchange', h)
    return () => window.removeEventListener('hashchange', h)
  }, [])

  const client = meta?.clients.find((c) => c.id === cid)
  useEffect(() => { if (client) setLang(client.language) }, [client?.id])

  const toast = useCallback((msg, error) => {
    setToastV({ msg, error })
    setTimeout(() => setToastV(null), error ? 5000 : 3000)
  }, [])

  const who = role === 'owner' ? `${client?.name.split(' ')[0] || 'Owner'} (owner)` : 'CA Kavya'
  const go = useCallback((p, arg) => { setPageArg(arg ?? null); setPage(p); window.scrollTo(0, 0) }, [])
  const ctx = useMemo(() => ({
    meta, cid, client, role, who, lang, setLang, tick, setRole,
    refresh: () => setTick((t) => t + 1),
    go, pageArg, toast, openDoc: setDocId, setCid,
  }), [meta, cid, client, role, who, lang, tick, pageArg, toast, go])

  if (page === 'landing') {
    return <Suspense fallback={<div className="loading" style={{ background: '#0A0A0A', minHeight: '100vh' }}>Loading the story…</div>}><Landing onEnter={() => go('home')} /></Suspense>
  }
  if (!meta) return <div className="loading">Waking up the munshi…<Toast t={toastV} /></div>

  const P = { home: Home, overview: Overview, whatsapp: WhatsApp, documents: Documents, suppliers: Suppliers, eway: EwayBills,
    return: Return, deadlines: Deadlines, rules: Rules, audit: Audit, console: Console }[page] || Home

  const NavBtn = ([k, label, ic]) => (
    <button key={k} className={page === k ? 'on' : ''} onClick={() => go(k)}><span className="ic"><Icon name={ic} /></span>{label}</button>
  )

  return (
    <Ctx.Provider value={ctx}>
      <div className="shell">
        <aside className="side">
          <button className="brand" onClick={() => go('landing')} title="Back to the story">
            <div className="brand-mark">K</div>
            <div>
              <div className="brand-name">KarSaathi</div>
              <div className="brand-tag">your digital munshi</div>
            </div>
          </button>
          <nav className="nav">
            {PAGES.map(NavBtn)}
            <div className="nav-sep">Accountant</div>
            {ADMIN.map(NavBtn)}
          </nav>
          <div className="motto">
            <b>LLMs read. Rules decide. <span>Humans approve.</span></b>
            Filing is simulated. Nothing leaves for the GST portal.
          </div>
        </aside>
        <div className="main">
          <header className="top">
            <select value={cid} onChange={(e) => setCid(Number(e.target.value))} aria-label="Client">
              {meta.clients.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.city}</option>)}
            </select>
            <span className="tip-line"><b>Munshi says:</b><Rotator lines={TIPS} every={4500} /></span>
            <span className="sp" />
            <Seg value={role} onChange={setRole} options={[['owner', 'Owner'], ['accountant', 'Accountant']]} />
            <Seg value={lang} onChange={setLang} options={LANGS} />
            <span className="chip hide-sm" title="Demo clock">{d(meta.today, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
            <span className="chip dark" title="Active rule set">rules v{meta.rule_version}</span>
            <span className={`chip ${meta.llm ? 'solid' : ''}`} title={meta.llm ? meta.model : 'Set ANTHROPIC_API_KEY to enable Claude reading'}>
              {meta.llm ? 'Claude: on' : 'Claude: off'}
            </span>
          </header>
          <AnimatePresence mode="wait">
            <motion.main className="page" key={`${cid}-${page}`}
              initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}>
              <P />
            </motion.main>
          </AnimatePresence>
        </div>
      </div>
      {docId && <DocDrawer id={docId} onClose={() => setDocId(null)} />}
      <Toast t={toastV} />
    </Ctx.Provider>
  )
}
