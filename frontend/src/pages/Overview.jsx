import { api, d, daysTo, inr } from '../api'
import { Badge, Bars, Card, Check, Cite, Kpi, Status, useApp, useLoad } from '../ui'

export default function Overview() {
  const { cid, go, tick, meta, toast } = useApp()
  const [o, , err] = useLoad(() => api.get(`/api/clients/${cid}/overview`), [cid, tick])
  if (err) return <div className="note error">{err}</div>
  if (!o) return <div className="empty">Loading…</div>
  const k = o.kpis
  const draft = o.eway_bills.find((e) => e.status === 'draft')
  const alerts = o.eway_bills.filter((e) => e.watch && e.watch.level !== 'ok')

  const nudge = async (supplier) => {
    try {
      await api.post(`/api/clients/${cid}/nudges`, { supplier, lang: 'en' })
      toast(`Reminder drafted for ${supplier}`)
      go('suppliers')
    } catch (e) { toast(e.message, true) }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{o.client.name}</h1>
          <p>What is due, what is at risk, what needs a look · {o.period_label} return · {o.client.scheme === 'QRMP' ? 'Quarterly (QRMP)' : 'Monthly'} filer</p>
        </div>
        <button className="btn primary" onClick={() => go('whatsapp')}>Open WhatsApp inbox</button>
      </div>

      {o.health.map((h, i) => (
        <div key={i} className={`note ${h.level}`} style={{ marginBottom: 12 }}>
          <b>Health check:</b> {h.msg} <Cite c={h.cite} />
        </div>
      ))}

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Kpi i={0} tone="black" label={`Payment due (${k.payment_form})`} num={k.payment_due} fmt={inr} sub={`by ${d(k.payment_due_on)} · ${o.period_label}`} />
        <Kpi i={1} label="Credit at risk" num={k.credit_at_risk} fmt={inr} tone={k.credit_at_risk > 0 ? 'alert' : 'good'}
          sub={k.credit_at_risk > 0 ? `${o.credit_at_risk.length} supplier(s) not in GSTR-2B` : 'All suppliers reported'} />
        <Kpi i={2} label="Documents need review" value={<>{k.review} <span className="muted" style={{ fontSize: 15, fontWeight: 500 }}>of {k.documents}</span></>}
          sub={k.review ? 'The agent was unsure; a human decides' : 'Everything settled automatically'} />
        <Kpi i={3} label="Next due date" value={k.next_due ? d(k.next_due.due) : '—'}
          sub={k.next_due ? `${k.next_due.form} · in ${daysTo(k.next_due.due, meta.today)} days` : ''} />
      </div>

      <div className="grid g2">
        <Card title="Credit-at-risk forecast" sub="Invoices that may miss GSTR-2B, with a nudge ready."
          right={<button className="btn ghost sm" onClick={() => go('suppliers')}>All suppliers →</button>}>
          {o.credit_at_risk.length === 0 && <div className="note ok">✓ Every purchase invoice is in your GSTR-2B.</div>}
          <div className="list">
            {o.credit_at_risk.map((s) => (
              <div className="li" key={s.supplier}>
                <div className="grow">
                  <div><b>{s.supplier}</b></div>
                  <div className="small muted">{s.invoices} invoice(s) · model p(miss) {s.risk.p_miss}</div>
                </div>
                <div className="num" style={{ fontWeight: 650 }}>{inr(s.at_risk)}</div>
                <Badge level={s.risk.level}>{s.risk.level}</Badge>
                <button className="btn sm" onClick={() => nudge(s.supplier)}>Send nudge</button>
              </div>
            ))}
          </div>
          {o.ageing.map((a) => (
            <div key={a.doc_id} className={`note ${a.reversed ? 'error' : 'warn'}`} style={{ marginTop: 10 }}>
              <span>Invoice {a.inv_no} ({a.supplier}) unpaid {a.age_days} days: {a.reversed ? `credit ${inr(a.itc)} reversed (Rule 37)` : `reversal of ${inr(a.itc)} after 180 days (${d(a.reversal_on)})`}. <Cite c={a.cite} /></span>
            </div>
          ))}
        </Card>

        <Card title="GST cash forecast" sub="How much cash to keep aside, and by when.">
          <div className="note ok" style={{ marginBottom: 10 }}>
            Keep <b>&nbsp;{inr(o.forecast.keep_aside)}&nbsp;</b> aside by {d(o.forecast.by)} ({o.forecast.form}).
          </div>
          <Bars data={o.forecast.bars} />
        </Card>

        <Card title="E-way bill pre-flight" sub="Errors caught before the truck leaves."
          right={<button className="btn ghost sm" onClick={() => go('eway')}>All e-way bills →</button>}>
          {alerts.map((e) => <div key={e.id} className={`note ${e.watch.level}`} style={{ marginBottom: 8 }}>⏱ {e.watch.msg}</div>)}
          {draft ? (
            <>
              <div className="small muted" style={{ marginBottom: 4 }}>Order {draft.inv_no} · {draft.party} · {inr(draft.total)}</div>
              {draft.preflight.checks.map((c, i) => <Check key={i} level={c.level}>{c.msg}</Check>)}
            </>
          ) : !alerts.length && <div className="muted">No e-way bills waiting.</div>}
        </Card>

        <Card title={`${o.period_label} payment (${o.return.form})`} sub="Plain summary, signed approval, audit trail."
          right={<Status s={o.return.status} />}>
          <div style={{ fontSize: 28, fontWeight: 650 }} className="num">{inr(o.return.cash)}</div>
          <div className="small muted" style={{ marginBottom: 10 }}>
            {o.return.delta >= 0 ? '+' : ''}{inr(o.return.delta)} vs last month
          </div>
          <div className="explain">{o.return.explain.map((x, i) => <p key={i} style={{ fontSize: 14 }}>{x.text}</p>)}</div>
          {k.review > 0 && <div className="note warn" style={{ marginBottom: 10 }}>{k.review} document(s) need your eyes before approval.</div>}
          <div className="row wrap">
            <button className="btn primary" onClick={() => go('return')}>Review & approve</button>
            {k.review > 0 && <button className="btn" onClick={() => go('documents', 'review')}>Open review queue</button>}
            {o.return.arn && <span className="chip dark">ARN {o.return.arn}</span>}
          </div>
          <div className="small muted" style={{ marginTop: 10 }}>Computed under rule set v{o.rule_version} · filing simulated</div>
        </Card>
      </div>
    </>
  )
}
