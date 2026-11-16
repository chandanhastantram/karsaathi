import { Fragment, useState } from 'react'
import { api, d, inr } from '../api'
import { Card, Status, useApp, useLoad } from '../ui'

export default function Rules() {
  const { who, role, toast, refresh, openDoc, setCid } = useApp()
  const [rs, reloadRs] = useLoad(() => api.get('/api/rules'), [])
  const [props, reloadP] = useLoad(() => api.get('/api/rules/proposals/all'), [])
  const [adv, setAdv] = useState(null)
  if (!rs) return <div className="empty">Loading…</div>

  const propose = async () => {
    try { await api.post('/api/rules/advisory', { text: adv ?? rs.simulated_advisory }); toast('Rule change proposed'); reloadP() }
    catch (e) { toast(e.message, true) }
  }
  const decide = async (p, ok) => {
    try {
      const r = await api.post(`/api/rules/proposals/${p.id}/${ok ? 'approve' : 'reject'}`, { by: who })
      toast(ok ? `Rule set v${r.version} active · ${r.flagged?.length || 0} invoice(s) flagged` : 'Rejected')
      reloadP(); reloadRs(); refresh()
    } catch (e) { toast(e.message, true) }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Rule sets</h1>
          <p>GST rules live as dated data, not in the model. Each answer cites the rule id and version. A change ships as a new version after a human approves it; past invoices are re-run.</p>
        </div>
        <span className="chip dark">Active v{rs.active} · versions: {rs.versions.join(', ')}</span>
      </div>

      <div className="grid g2">
        <Card title="Rule-watch" sub="Advisories from CBIC / GSTN are read into a proposed change. For the demo, a simulated advisory arrives.">
          <textarea rows={6} value={adv ?? rs.simulated_advisory} onChange={(e) => setAdv(e.target.value)} />
          <div className="row" style={{ marginTop: 8 }}><button className="btn primary" onClick={propose}>Read advisory → propose change</button></div>
        </Card>
        <Card title="Proposals" sub="Approve to publish a new rule-set version.">
          {props && !props.length && <div className="muted">No proposals yet.</div>}
          {(props || []).map((p) => (
            <div key={p.id} style={{ borderBottom: '1px solid var(--line-2)', paddingBottom: 12, marginBottom: 12 }}>
              <div className="row between"><b>v{p.base_version} → v{p.new_version}</b><Status s={p.status} /></div>
              {p.changes.map((c, i) => (
                <div key={i} className="note info" style={{ margin: '8px 0' }}>
                  HSN {c.hsn} ({c.description}): <b>{c.old_rate}% → {c.new_rate}%</b> from {d(c.effective_from, { day: 'numeric', month: 'short', year: 'numeric' })}
                </div>
              ))}
              <div className="small muted">{p.impact.length} invoice(s) dated on/after the change:</div>
              <table style={{ marginTop: 4 }}>
                <tbody>
                  {p.impact.slice(0, 8).map((x) => (
                    <tr key={x.doc_id} className="click" onClick={() => { setCid(x.client_id); openDoc(x.doc_id) }}>
                      <td className="small">{x.client}</td><td className="mono">{x.inv_no}</td><td className="small">{x.kind} · {x.party}</td>
                      <td className="num small">{x.charged_rate}% → {x.new_rate}%</td><td className="num small">{inr(x.tax_difference)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {p.status === 'proposed' && (
                <div className="row" style={{ marginTop: 10 }}>
                  <button className="btn primary" onClick={() => decide(p, true)}>Approve as {who}</button>
                  <button className="btn" onClick={() => decide(p, false)}>Reject</button>
                  {role !== 'accountant' && <span className="small muted">Usually the accountant approves rule changes.</span>}
                </div>
              )}
              {p.approved_by && <div className="small muted" style={{ marginTop: 6 }}>{p.status} by {p.approved_by}</div>}
            </div>
          ))}
        </Card>
      </div>

      <Card title={`HSN rate table · v${rs.active}`} sub={rs.data.notes} style={{ marginTop: 16 }}>
        <div className="tbl-wrap">
          <table>
            <thead><tr><th>Rule id</th><th>HSN</th><th>Description</th><th className="num">Rate</th><th>From</th><th>To</th><th>Source</th></tr></thead>
            <tbody>
              {rs.data.hsn_rates.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.id}</td><td className="mono">{r.hsn}</td><td>{r.description}{r.rcm && <span className="chip" style={{ marginLeft: 4 }}>RCM</span>}</td>
                  <td className="num">{r.rate}%</td><td>{r.effective_from}</td><td>{r.effective_to || '—'}</td>
                  <td><a href={r.source} target="_blank" rel="noreferrer" className="small">{r.source.startsWith('http') ? 'link' : r.source}</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid g3" style={{ marginTop: 16 }}>
        {['eway_bill', 'due_dates', 'late_fee', 'itc_payment_condition', 'confidence', 'registration'].map((k) => (
          <Card key={k} title={rs.data[k].id} sub={k.replace(/_/g, ' ')}>
            <dl className="kv">
              {Object.entries(rs.data[k]).filter(([kk]) => !['id', 'source', 'source_2', 'validity_source', 'qrmp_cat_a_states', 'vehicle_regex'].includes(kk)).map(([kk, v]) => (
                <Fragment key={kk}><dt>{kk.replace(/_/g, ' ')}</dt><dd className="num">{String(v)}</dd></Fragment>
              ))}
            </dl>
            {rs.data[k].source && <a className="small" href={rs.data[k].source} target="_blank" rel="noreferrer">source</a>}
          </Card>
        ))}
      </div>
    </>
  )
}
