import { api, d, inr } from '../api'
import { Badge, Card, Kpi, Status, useApp, useLoad } from '../ui'

export default function Console() {
  const { setCid, go, openDoc, tick } = useApp()
  const [c] = useLoad(() => api.get('/api/console'), [tick])
  if (!c) return <div className="empty">Loading…</div>
  const open = (id, page, arg) => { setCid(id); go(page, arg) }
  const atRisk = c.clients.reduce((s, x) => s + x.credit_at_risk, 0)
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Accountant console</h1>
          <p>One queue across clients. You review only what the agent could not settle, not every bill.</p>
        </div>
      </div>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Kpi label="Clients" value={c.clients.length} sub={`${c.period_label} returns`} />
        <Kpi label="Documents" value={c.totals.documents} sub="read and booked by the agent" />
        <Kpi label="Need a human" value={c.totals.to_review} tone={c.totals.to_review ? 'alert' : 'good'}
          sub={`${((c.totals.to_review / Math.max(c.totals.documents, 1)) * 100).toFixed(1)}% of documents`} />
        <Kpi label="Credit at risk" value={inr(atRisk)} sub="across all clients" />
      </div>
      <Card title="Clients" sub={`${c.totals.to_review} of ${c.totals.documents.toLocaleString('en-IN')} documents need a human`}>
        <div className="tbl-wrap">
          <table>
            <thead><tr><th>Client</th><th className="num">Documents</th><th className="num">To review</th><th className="num">Credit at risk</th><th className="num">Cash payable</th><th>Due</th><th>Return</th><th></th></tr></thead>
            <tbody>
              {c.clients.map((x) => (
                <tr key={x.id}>
                  <td><b>{x.name}</b><div className="small muted">{x.city} · {x.scheme}</div>
                    {!x.bank_verified && <Badge level="error">bank details missing</Badge>}</td>
                  <td className="num">{x.documents}</td>
                  <td className="num">{x.to_review ? <b className="red">{x.to_review}</b> : 0}</td>
                  <td className="num">{inr(x.credit_at_risk)}</td>
                  <td className="num">{inr(x.cash_payable)}</td>
                  <td>{x.form}<div className="small muted">{d(x.due)}</div></td>
                  <td><Status s={x.return_status} /></td>
                  <td><div className="row">
                    <button className="btn sm" onClick={() => open(x.id, 'documents', 'review')} disabled={!x.to_review}>Review</button>
                    <button className="btn sm" onClick={() => open(x.id, 'return')}>Return</button>
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <div className="grid g2" style={{ marginTop: 16 }}>
        {c.clients.filter((x) => x.queue.length).map((x) => (
          <Card key={x.id} title={`${x.name} · exception queue`} sub={`${x.to_review} item(s)`}>
            <div className="list">
              {x.queue.map((q) => (
                <div key={q.id} className="li" style={{ cursor: 'pointer' }} onClick={() => { setCid(x.id); openDoc(q.id) }}>
                  <div className="grow">
                    <div>{q.kind === 'sale' ? 'Sale' : 'Purchase'} {q.inv_no} · {q.party}</div>
                    <div className="q">{q.question}</div>
                  </div>
                  <span className="chip">{Math.round(q.confidence * 100)}%</span>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </>
  )
}
