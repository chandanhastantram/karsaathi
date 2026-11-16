import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { inr } from './api'
import { CountUp, Tilt } from './fx/fx'

export const Ctx = createContext(null)

/* Line icons (SVG, currentColor) so nothing renders as a colour emoji. */
const ICONS = {
  home: 'M3 11l9-7 9 7M5 10v10h14V10',
  dash: 'M3 3h8v10H3zM13 3h8v6h-8zM13 11h8v10h-8zM3 15h8v6H3z',
  chat: 'M4 4h16v12H8l-4 4z',
  docs: 'M6 2h9l5 5v15H6zM14 2v6h6M9 13h8M9 17h8',
  swap: 'M4 8h14l-4-4M20 16H6l4 4',
  truck: 'M2 6h12v10H2zM14 10h4l3 3v3h-7M6 19a2 2 0 100-4 2 2 0 000 4zM17 19a2 2 0 100-4 2 2 0 000 4z',
  check: 'M4 12l5 5L20 6',
  clock: 'M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h1M3 12h1M3 18h1',
  rule: 'M5 3h14v18H5zM9 7h6M9 11h6M9 15h3',
  hash: 'M4 9h16M4 15h16M10 3L8 21M16 3l-2 18',
  clip: 'M20 11l-8 8a5 5 0 01-7-7l8-8a3.5 3.5 0 015 5l-8 8a2 2 0 01-3-3l7-7',
  mic: 'M12 3a3 3 0 013 3v6a3 3 0 01-6 0V6a3 3 0 013-3zM5 11a7 7 0 0014 0M12 18v3',
  send: 'M4 12l16-8-6 16-2-7z',
  file: 'M6 2h9l5 5v15H6zM14 2v6h6',
  photo: 'M3 6h18v13H3zM8 13l3-3 4 4 2-2 4 4M8.5 9.5h.01',
  voice: 'M12 3a3 3 0 013 3v6a3 3 0 01-6 0V6a3 3 0 013-3zM5 11a7 7 0 0014 0',
  sms: 'M3 5h18v12H8l-5 4zM7 10h10',
  ask: 'M12 21a9 9 0 100-18 9 9 0 000 18zM9.5 9a2.5 2.5 0 115 0c0 2-2.5 2-2.5 4M12 17h.01',
}
export function Icon({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden style={{ flex: 'none', display: 'block' }}>
      <path d={ICONS[name] || ''} />
    </svg>
  )
}
export const useApp = () => useContext(Ctx)

export function Card({ title, sub, right, children, className = '', ...rest }) {
  return (
    <section className={`card ${className}`} {...rest}>
      {(title || right) && (
        <div className="card-h">
          <div>
            {title && <h2>{title}</h2>}
            {sub && <p>{sub}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

/** KPI tile: tilts in 3D, counts up when `num` is given (formatted with `fmt`). */
export function Kpi({ label, value, num, fmt, sub, tone, i = 0 }) {
  return (
    <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}>
      <Tilt className={`card kpi ${tone || ''}`} max={6}>
        <div className="lbl">{label}</div>
        <div className="val">{num != null ? <CountUp to={num} format={fmt || ((n) => Math.round(n).toLocaleString('en-IN'))} duration={1.1} /> : value}</div>
        {sub && <div className="sub">{sub}</div>}
      </Tilt>
    </motion.div>
  )
}

const LEVEL = { High: 'high', Medium: 'med', Low: 'ok', ok: 'ok', warn: 'warn', error: 'error' }
export function Badge({ level, children }) {
  return <span className={`badge ${LEVEL[level] || level || 'plain'}`}>{children ?? level}</span>
}

const STATUS = {
  booked: ['ok', 'Booked'], review: ['warn', 'Needs review'], rejected: ['plain', 'Rejected'],
  matched: ['ok', 'Matched'], missing: ['high', 'Missing in 2B'], mismatch: ['med', 'Mismatch'], late: ['warn', 'Filed late'],
  not_in_books: ['warn', 'Not in books'], draft: ['plain', 'Draft'], prepared: ['warn', 'Prepared'], approved: ['ok', 'Approved'],
  filed: ['ok', 'Filed (simulated)'], generated: ['ok', 'Generated (sim.)'], extended: ['ok', 'Extended (sim.)'], proposed: ['warn', 'Proposed'],
  sent: ['ok', 'Sent'], drafted: ['plain', 'Drafted'],
}
export function Status({ s }) {
  const [lv, label] = STATUS[s] || ['plain', s]
  return <Badge level={lv}>{label}</Badge>
}

export function Check({ level, children }) {
  const sym = level === 'ok' ? '✓' : level === 'warn' ? '!' : '✕'
  return (
    <div className="check">
      <span className={`ic ${level}`} aria-label={level}>{sym}</span>
      <span>{children}</span>
    </div>
  )
}

export function Cite({ c }) {
  if (!c) return null
  return (
    <span className="chip" title={c.source || ''}>
      {c.source ? <a href={c.source} target="_blank" rel="noreferrer">{c.rule_id}</a> : c.rule_id} · v{c.version}
    </span>
  )
}

export function Conf({ v }) {
  if (!v) return null
  const tone = v.conf >= 0.85 ? 'dark' : 'redc'
  return <span className={`chip ${tone}`} title="method · confidence">{v.method} · {Math.round(v.conf * 100)}%</span>
}

export function Seg({ value, onChange, options }) {
  return (
    <div className="seg" role="tablist">
      {options.map(([v, label]) => (
        <button key={v} className={value === v ? 'on' : ''} onClick={() => onChange(v)} role="tab" aria-selected={value === v}>{label}</button>
      ))}
    </div>
  )
}

export function Drawer({ onClose, children, modal }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="scrim" onClick={onClose}>
      <div className={modal ? 'modal-c' : 'drawer'} onClick={(e) => e.stopPropagation()} role="dialog">{children}</div>
    </div>
  )
}

export function Toast({ t }) {
  if (!t) return null
  return <div className={`toast ${t.error ? 'error' : ''}`} role="status">{t.msg}</div>
}

export function useLoad(fn, deps) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [n, setN] = useState(0)
  useEffect(() => {
    let live = true
    setErr(null)
    fn().then((x) => live && setData(x)).catch((e) => live && setErr(e.message))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, n])
  return [data, () => setN((x) => x + 1), err, setData]
}

/* Single-series bar chart: one hue, rounded data-end, 2px gaps, hover tooltip, table fallback. */
export function Bars({ data, height = 190 }) {
  const [hover, setHover] = useState(null)
  const [table, setTable] = useState(false)
  const ref = useRef(null)
  const W = 520, H = height, padL = 46, padB = 26, padT = 18
  const max = Math.max(...data.map((x) => x.amount), 1)
  const step = niceStep(max)
  const top = Math.ceil(max / step) * step
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step)
  const bw = (W - padL) / data.length
  const barW = Math.min(56, bw - 18)
  const y = (v) => padT + (H - padT - padB) * (1 - v / top)
  if (table) {
    return (
      <div>
        <table>
          <thead><tr><th>Month</th><th>Form</th><th>Due</th><th className="num">Cash</th><th>State</th></tr></thead>
          <tbody>{data.map((b) => <tr key={b.period}><td>{b.label}</td><td>{b.form}</td><td>{b.due}</td><td className="num">{inr(b.amount)}</td><td>{b.state}</td></tr>)}</tbody>
        </table>
        <button className="btn ghost sm" onClick={() => setTable(false)}>Show chart</button>
      </div>
    )
  }
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="GST cash payable by month">
        <defs>
          <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="#D6D6D4" /><line x1="0" y1="0" x2="0" y2="6" stroke="#0A0A0A" strokeWidth="1.6" />
          </pattern>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid-l" x1={padL} x2={W} y1={y(t)} y2={y(t)} />
            <text className="axis" x={padL - 8} y={y(t) + 4} textAnchor="end">{t >= 1000 ? `${t / 1000}k` : t}</text>
          </g>
        ))}
        {data.map((b, i) => {
          const x = padL + i * bw + (bw - barW) / 2
          const h = Math.max(0, y(0) - y(b.amount))
          const r = Math.min(4, h)
          const cls = `bar ${b.state === 'projected' ? 'dim' : b.state === 'due' ? 'due' : ''} ${hover === i ? 'focus' : ''}`
          return (
            <g key={b.period}>
              <motion.path className={cls} initial={{ opacity: 0, scaleY: 0 }} animate={{ opacity: 1, scaleY: 1 }}
                style={{ transformOrigin: `${x}px ${y(0)}px` }} transition={{ delay: 0.1 + i * 0.08, duration: 0.6, ease: [0.16, 1, 0.3, 1] }} d={`M${x},${y(0)} V${y(0) - h + r} Q${x},${y(0) - h} ${x + r},${y(0) - h} H${x + barW - r} Q${x + barW},${y(0) - h} ${x + barW},${y(0) - h + r} V${y(0)} Z`} />
              {(b.state === 'due' || hover === i) && <text className="val" x={x + barW / 2} y={y(b.amount) - 6} textAnchor="middle">{inr(b.amount)}</text>}
              <text className="axis" x={x + barW / 2} y={H - 8} textAnchor="middle">{b.label.split(' ')[0]}{b.state === 'projected' ? '*' : ''}</text>
              <rect className="hit" x={padL + i * bw} y={padT} width={bw} height={H - padT - padB}
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
            </g>
          )
        })}
      </svg>
      {hover != null && (() => {
        const b = data[hover]
        const left = ((padL + hover * bw + bw / 2) / W) * 100
        return <div className="tip" style={{ left: `${left}%`, top: `${(y(b.amount) / H) * 100}%` }}>{b.label} · {b.form}: <b>{inr(b.amount)}</b> · {b.state}</div>
      })()}
      <div className="row between small muted"><span><b className="red">■</b> due now · ▨ projected from month-to-date</span><button className="btn ghost sm" onClick={() => setTable(true)}>View as table</button></div>
    </div>
  )
}

function niceStep(max) {
  const raw = max / 4
  const p = Math.pow(10, Math.floor(Math.log10(raw)))
  const n = raw / p
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p
}
