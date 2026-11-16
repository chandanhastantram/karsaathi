import { useState } from 'react'
import { api, d, inr } from '../api'
import { LANGS } from '../App'
import { Badge, Card, Cite, Drawer, Kpi, Seg, Status, useApp, useLoad } from '../ui'

function periodOf(iso) {
  const t = new Date(iso)
  return String(t.getMonth() + 1).padStart(2, '0') + t.getFullYear()
}

export default function Suppliers() {
  const { cid, meta, who, toast, refresh, openDoc, lang, tick } = useApp()
  const [period, setPeriod] = useState(meta.filing_period)
  const [rec, reload] = useLoad(() => api.get(`/api/clients/${cid}/reconcile?period=${period}`), [cid, period, tick])
  const [sups] = useLoad(() => api.get(`/api/clients/${cid}/suppliers`), [cid])
  const [pick, setPick] = useState({})
  const [confirm, setConfirm] = useState(false)
  const [nudge, setNudge] = useState(null)

  const cur = periodOf(meta.today)
  const rows = rec?.rows || []
  const chosen = Object.entries(pick).filter(([, a]) => a)

  const apply = async () => {
    const items = chosen.map(([key, action]) => { const [g, n] = key.split('|'); return { supplier_gstin: g, inv_no: n, action } })
    try {
      await api.post(`/api/clients/${cid}/ims`, { by: who, items })
      toast(`${items.length} IMS action(s) recorded (simulated)`)
      setPick({}); setConfirm(false); reload(); refresh()
    } catch (e) { toast(e.message, true) }
  }
  const acceptRecommended = () => {
    const p = {}
    rows.forEach((r) => { if (r.recommend && !r.ims_action) p[`${r.supplier_gstin}|${r.inv_no}`] = r.recommend })
    setPick(p)
  }
  const draft = async (supplier, l = lang) => {
    try { setNudge({ ...(await api.post(`/api/clients/${cid}/nudges`, { supplier, lang: l })), supplier, lang: l }) }
    catch (e) { toast(e.message, true) }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Suppliers & IMS</h1>
          <p>Your purchase register compared with what suppliers reported (IMS / GSTR-2B, from the mock portal). Accepted invoices feed GSTR-2B and then GSTR-3B credit.</p>
        </div>
        <Seg value={period} onChange={(p) => { setPeriod(p); setPick({}) }}
          options={[[meta.filing_period, `${meta.filing_period_label} (filing)`], [cur, 'This month (forecast)']]} />
      </div>
      {rec && (
        <>
          <div className="grid g4" style={{ marginBottom: 16 }}>
            <Kpi label="Credit at risk" value={inr(rec.at_risk_total)} tone={rec.at_risk_total ? 'alert' : 'good'} sub={rec.gstr2b_generated ? 'GSTR-2B generated' : 'Before GSTR-2B (forecast)'} />
            <Kpi label="Matched" value={rec.counts.matched || 0} sub="Invoice, GSTIN and amounts agree" />
            <Kpi label="Missing / mismatched" value={(rec.counts.missing || 0) + (rec.counts.mismatch || 0)} sub="Need the supplier to act" />
            <Kpi label="Late / not in books" value={(rec.counts.late || 0) + (rec.counts.not_in_books || 0)} sub="Next month's 2B, or check the bill" />
          </div>

          {rec.suppliers.length > 0 && (
            <Card title="Who to nudge" sub="Drafted in the owner's language. Sending is a WhatsApp message, nothing is filed." style={{ marginBottom: 16 }}>
              <div className="list">
                {rec.suppliers.map((s) => (
                  <div className="li" key={s.supplier}>
                    <div className="grow"><b>{s.supplier}</b> <span className="muted small">· {s.invoices} invoice(s)</span></div>
                    <span className="num" style={{ fontWeight: 650 }}>{inr(s.at_risk)}</span>
                    <Badge level={s.risk.level}>{s.risk.level} · p {s.risk.p_miss}</Badge>
                    <button className="btn sm" onClick={() => draft(s.supplier)}>Draft nudge</button>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card title={`Invoice match · ${rec.period.slice(0, 2)}/${rec.period.slice(2)}`} sub="Recommended IMS action per invoice. Accepting or rejecting in IMS always needs a human."
            right={<div className="row wrap">
              <button className="btn sm" onClick={acceptRecommended}>Select recommended</button>
              <button className="btn sm primary" disabled={!chosen.length} onClick={() => setConfirm(true)}>Apply {chosen.length || ''} IMS action(s)</button>
            </div>}>
            <div className="tbl-wrap">
              <table>
                <thead><tr><th>Supplier</th><th>Invoice</th><th className="num">Books</th><th className="num">Portal</th><th>Status</th><th>Why</th><th>IMS</th></tr></thead>
                <tbody>
                  {rows.map((r) => {
                    const key = `${r.supplier_gstin}|${r.inv_no}`
                    return (
                      <tr key={key}>
                        <td>{r.supplier}<div className="mono muted">{r.supplier_gstin}</div></td>
                        <td>{r.doc_id ? <a href="#" onClick={(e) => { e.preventDefault(); openDoc(r.doc_id) }} className="mono">{r.inv_no}</a> : <span className="mono">{r.inv_no}</span>}
                          <div className="small muted">{d(r.inv_date)}</div></td>
                        <td className="num">{inr(r.book_itc)}<div className="small muted">on {inr(r.book_taxable)}</div></td>
                        <td className="num">{r.portal_itc != null ? inr(r.portal_itc) : '—'}{r.filed_on && <div className="small muted">filed {d(r.filed_on)}</div>}</td>
                        <td><Status s={r.status} />{!r.itc_eligible && <div className="small muted">blocked 17(5)</div>}</td>
                        <td className="small ink2" style={{ maxWidth: 280 }}>{r.why}</td>
                        <td>
                          {r.ims_action ? <span className="chip dark">{r.ims_action}</span> : r.status === 'missing' ? <span className="muted small">not in IMS</span> : (
                            <select value={pick[key] || ''} onChange={(e) => setPick({ ...pick, [key]: e.target.value })} aria-label="IMS action">
                              <option value="">{r.recommend ? `— (rec: ${r.recommend})` : '—'}</option>
                              <option value="accept">Accept</option><option value="pending">Pending</option><option value="reject">Reject</option>
                            </select>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="small muted" style={{ marginTop: 8 }}><Cite c={rec.cite} /> Data comes from the mock GST portal; no real portal calls.</div>
          </Card>
        </>
      )}

      {sups && (
        <Card title="Supplier risk model" sub="Logistic score on the last 6 months of GSTR-1 filing: missed months, late months, average delay, and whether this month is overdue." style={{ marginTop: 16 }}>
          <div className="tbl-wrap">
            <table>
              <thead><tr><th>Supplier</th><th>Last 6 months (days late after the 11th)</th><th className="num">p(miss)</th><th>Level</th></tr></thead>
              <tbody>
                {sups.filter((s) => s.risk).map((s) => (
                  <tr key={s.id}>
                    <td>{s.name}</td>
                    <td><div className="row">{s.history.slice(-6).map((h, i) => (
                      <span key={i} className={`chip ${h === null ? 'solid' : h > 0 ? 'redc' : 'dark'}`}>
                        {h === null ? 'missed' : h === 0 ? 'on time' : `+${h}d`}
                      </span>))}</div></td>
                    <td className="num">{s.risk.p_miss}</td>
                    <td><Badge level={s.risk.level} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {confirm && (
        <Drawer modal onClose={() => setConfirm(false)}>
          <h2>Approve IMS actions</h2>
          <p className="muted">These decide which supplier invoices give you credit. You are approving as <b>{who}</b>.</p>
          <ul>{chosen.map(([k, a]) => <li key={k}><b>{a}</b> · {k.split('|')[1]}</li>)}</ul>
          <div className="row"><button className="btn primary" onClick={apply}>Approve & record</button><button className="btn" onClick={() => setConfirm(false)}>Cancel</button></div>
        </Drawer>
      )}
      {nudge && (
        <Drawer modal onClose={() => setNudge(null)}>
          <div className="row between"><h2>Reminder to {nudge.supplier}</h2>
            <Seg value={nudge.lang} onChange={(l) => draft(nudge.supplier, l)} options={LANGS} /></div>
          <p className="muted small">Drafted by the agent. Review it, then send from WhatsApp.</p>
          <textarea rows={6} value={nudge.message} onChange={(e) => setNudge({ ...nudge, message: e.target.value })} />
          <div className="row wrap" style={{ marginTop: 10 }}>
            <a className="btn primary" target="_blank" rel="noreferrer" href={`https://wa.me/${(nudge.phone || '').replace(/\D/g, '')}?text=${encodeURIComponent(nudge.message)}`}>Open in WhatsApp</a>
            <button className="btn" onClick={async () => { await api.post(`/api/nudges/${nudge.id}/send`, { by: who }); toast('Marked as sent'); setNudge(null) }}>Mark as sent</button>
          </div>
        </Drawer>
      )}
    </>
  )
}
