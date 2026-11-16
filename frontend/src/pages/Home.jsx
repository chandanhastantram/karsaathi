import { Suspense, lazy } from 'react'
import { motion } from 'framer-motion'
import { api, d, daysTo, inr } from '../api'
import { TIPS } from '../App'
import { Reveal, Rotator, Tilt } from '../fx/fx'
import { Card, Icon, Kpi, useApp, useLoad } from '../ui'

const BillScene = lazy(() => import('../three/BillScene'))

const HELLO = {
  en: (n, h) => `${h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'}, ${n}`,
  hi: (n) => `नमस्ते, ${n} जी`,
  kn: (n) => `ನಮಸ್ಕಾರ, ${n}`,
}

export default function Home() {
  const { cid, client, lang, go, meta, tick } = useApp()
  const [o, , err] = useLoad(() => api.get(`/api/clients/${cid}/overview`), [cid, tick])
  if (err) return <div className="note error">{err}</div>
  if (!o) return <div className="loading">Counting rupees…</div>
  const k = o.kpis
  const first = client.name.split(' ')[0]
  const days = k.next_due ? daysTo(k.next_due.due, meta.today) : null
  const alerts = o.eway_bills.filter((e) => e.watch && e.watch.level !== 'ok')
  const drafts = o.eway_bills.filter((e) => e.status === 'draft')

  const todo = [
    k.review > 0 && { hot: true, t: `${k.review} bill${k.review > 1 ? 's' : ''} need your eyes`, s: 'The agent was not sure. You decide in 10 seconds each.', go: () => go('documents', 'review') },
    o.credit_at_risk.length > 0 && { hot: true, t: `Nudge ${o.credit_at_risk.map((x) => x.supplier).join(' and ')}`, s: `${inr(k.credit_at_risk)} of your credit is stuck with them.`, go: () => go('suppliers') },
    alerts.length > 0 && { hot: true, t: alerts[0].watch.msg, s: 'Extend before the truck meets a checkpoint.', go: () => go('eway') },
    drafts.length > 0 && { t: `${drafts.length} e-way bill${drafts.length > 1 ? 's' : ''} waiting for pre-flight`, s: 'Vehicle number first, then your approval.', go: () => go('eway') },
    o.return.status !== 'filed' && { t: `Approve the ${o.period_label} ${o.return.form}`, s: `${inr(o.return.cash)} due by ${d(k.payment_due_on)}. Owner prepares, CA signs.`, go: () => go('return') },
    o.ageing.length > 0 && { t: `Pay ${o.ageing[0].supplier} (${o.ageing[0].age_days} days)`, s: 'Rule 37 reverses credit after 180 days unpaid.', go: () => go('overview') },
  ].filter(Boolean)

  const mods = [
    ['whatsapp', 'chat', 'WhatsApp inbox', 'Forward it like a meme.', '24×7'],
    ['overview', 'dash', 'Dashboard', 'Due, at risk, needs a look.', inr(k.payment_due)],
    ['documents', 'docs', 'Documents', 'Every bill, with receipts.', `${k.documents}`],
    ['suppliers', 'swap', 'Suppliers & IMS', 'Who forgot the 11th?', inr(k.credit_at_risk)],
    ['eway', 'truck', 'E-way bills', 'Catch it before the checkpoint does.', `${o.eway_bills.length}`],
    ['return', 'check', 'Return & approval', 'Two humans. One ARN.', o.return.form],
    ['deadlines', 'clock', 'Deadlines & notices', 'ASMT-10, now in Kannada.', days != null ? `${days} d` : '—'],
    ['rules', 'rule', 'Rule sets', 'Rules are data. Not vibes.', `v${o.rule_version}`],
  ]

  return (
    <>
      <motion.section className="home-hero" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}>
        <div className="txt">
          <div className="hi">{client.name} · {client.city} · {o.period_label} return</div>
          <h1>{(HELLO[lang] || HELLO.en)(first, new Date().getHours())}<span className="red">.</span></h1>
          <p>
            {k.review === 0 && k.credit_at_risk === 0
              ? 'Nothing is on fire today. Go have chai.'
              : <>Your munshi sorted <b>{k.documents}</b> bills. {todo.length} thing{todo.length !== 1 ? 's' : ''} need a human today, and the next deadline is <b>{days} days</b> away.</>}
          </p>
          <div className="row wrap">
            <button className="btn primary" onClick={() => go(todo[0] ? 'documents' : 'return', todo[0] ? 'review' : null)}>Start with the urgent stuff →</button>
            <button className="btn" style={{ background: 'transparent', color: '#fff', borderColor: '#3a3a3a' }} onClick={() => go('whatsapp')}>Send a bill</button>
          </div>
          <div className="munshi" style={{ marginTop: 22 }}><b>Munshi says</b><Rotator lines={TIPS} every={4000} /></div>
        </div>
        <div className="scene" aria-hidden>
          <Suspense fallback={null}><BillScene auto count={18} /></Suspense>
        </div>
      </motion.section>

      <div className="grid g4" style={{ marginBottom: 18 }}>
        <Kpi i={0} label={`Pay by ${d(k.payment_due_on)} (${k.payment_form})`} num={k.payment_due} fmt={inr} sub="cash, after credit" tone="black" />
        <Kpi i={1} label="Credit at risk" num={k.credit_at_risk} fmt={inr} tone={k.credit_at_risk ? 'alert' : 'good'} sub={`${o.credit_at_risk.length} supplier(s) owe you a filing`} />
        <Kpi i={2} label="Needs a human" num={k.review} tone={k.review ? 'alert' : 'good'} sub={`of ${k.documents} documents`} />
        <Kpi i={3} label="Days to next deadline" num={days ?? 0} tone={days != null && days <= 5 ? 'alert' : 'good'} sub={k.next_due ? `${k.next_due.form} on ${d(k.next_due.due)}` : ''} />
      </div>

      <div className="grid home-split">
        <Card title="Today’s to-do" sub="Sorted by how much it costs you to ignore it.">
          {todo.length === 0 && <div className="empty">All clear. Suspiciously clear.</div>}
          {todo.map((x, i) => (
            <Reveal key={i} i={i}>
              <div className={`todo ${x.hot ? 'hot' : ''}`} onClick={x.go} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && x.go()}>
                <span className="n">{i + 1}</span>
                <div className="grow"><b>{x.t}</b><div className="small muted">{x.s}</div></div>
                <span className="go">→</span>
              </div>
            </Reveal>
          ))}
        </Card>
        <div className="grid g2" style={{ alignContent: 'start' }}>
          {mods.map(([p, ic, t, s, big], i) => (
            <Reveal key={p} i={i % 4}>
              <Tilt className="mod" onClick={() => go(p)} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && go(p)}>
                <span className="ic"><Icon name={ic} size={20} /></span>
                <h3>{t}</h3>
                <p>{s}</p>
                <div className="big">{big}</div>
              </Tilt>
            </Reveal>
          ))}
        </div>
      </div>
    </>
  )
}
