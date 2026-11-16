import { useState } from 'react'
import { api, d, daysTo, inr } from '../api'
import { LANGS } from '../App'
import { Badge, Card, Cite, Seg, useApp, useLoad } from '../ui'

export default function Deadlines() {
  const { cid, meta, lang, toast } = useApp()
  const [cal] = useLoad(() => api.get(`/api/clients/${cid}/calendar`), [cid])
  const [text, setText] = useState('')
  const [nlang, setNlang] = useState(lang)
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)

  const loadSample = async () => setText(await (await fetch(api.sample('notice_asmt10.txt'))).text())
  const explain = async () => {
    setBusy(true)
    try { setRes(await api.post(`/api/clients/${cid}/notices`, { text, lang: nlang })) } catch (e) { toast(e.message, true) }
    setBusy(false)
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Deadlines & notices</h1>
          <p>Due dates come from the rule set, with what a 10-day delay would cost. Notices are explained in plain language with a draft reply for the accountant.</p>
        </div>
      </div>
      <div className="grid g2">
        <Card title="Compliance calendar" sub="Late fee ₹50/day (capped by turnover) plus 18% yearly interest on cash tax.">
          <div className="list">
            {(cal || []).map((x, i) => {
              const days = daysTo(x.due, meta.today)
              return (
                <div className="li" key={i} style={x.done ? { opacity: .55 } : {}}>
                  <div style={{ width: 54, textAlign: 'center' }}>
                    <div style={{ fontSize: 18, fontWeight: 650 }} className="num">{new Date(x.due).getDate()}</div>
                    <div className="small muted">{d(x.due, { month: 'short' })}</div>
                  </div>
                  <div className="grow">
                    <b>{x.form}</b> <span className="muted">· {x.period_label}</span>
                    <div className="small muted">{x.pays_tax ? 'Pays tax' : 'Return only'}{!x.done && x.late_10_days > 0 && ` · 10 days late would cost ${inr(x.late_10_days)}`}</div>
                  </div>
                  {x.done ? <Badge level="plain">past</Badge> : <Badge level={days <= 3 ? 'error' : days <= 10 ? 'warn' : 'ok'}>in {days} d</Badge>}
                </div>
              )
            })}
          </div>
          {cal?.[0] && <div style={{ marginTop: 8 }}><Cite c={cal[0].cite} /></div>}
        </Card>

        <Card title="Notice reader" sub="Paste the notice text (or a photo's text). The agent explains it; it never replies on its own."
          right={<Seg value={nlang} onChange={setNlang} options={LANGS} />}>
          <textarea rows={7} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste a GST notice here…" />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn primary" disabled={!text.trim() || busy} onClick={explain}>{busy ? 'Reading…' : 'Explain'}</button>
            <button className="btn" onClick={loadSample}>Load sample ASMT-10</button>
          </div>
          {res && (
            <div className="stack" style={{ marginTop: 14 }}>
              <div className="row wrap">
                <span className="chip dark">{res.form}</span>
                <Badge level={res.risk === 'high' ? 'error' : res.risk === 'medium' ? 'warn' : 'ok'}>{res.risk} risk</Badge>
                {res.reply_by && <span className="chip">Reply by {d(res.reply_by, { day: 'numeric', month: 'short', year: 'numeric' })}</span>}
                {res.amount_mentioned && <span className="chip">Amount {inr(res.amount_mentioned)}</span>}
                <span className="chip">{res.engine === 'claude' ? 'Explained by Claude' : 'Rule table'}</span>
              </div>
              <div className="explain"><p>{res.plain_summary}</p></div>
              {res.documents_needed?.length > 0 && <div><b className="small">Keep ready:</b> <span className="small ink2">{res.documents_needed.join(' · ')}</span></div>}
              <details>
                <summary className="small" style={{ cursor: 'pointer' }}>Draft reply for the accountant</summary>
                <pre className="mono" style={{ whiteSpace: 'pre-wrap', background: 'var(--surface-2)', padding: 10, borderRadius: 8 }}>{res.reply_draft}</pre>
              </details>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
