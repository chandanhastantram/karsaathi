import { useState } from 'react'
import { api, d, inr } from '../api'
import { Badge, Card, Cite, Conf, Drawer, Seg, Status, useApp, useLoad } from '../ui'

export default function Documents() {
  const { cid, openDoc, pageArg, tick } = useApp()
  const [status, setStatus] = useState(pageArg === 'review' ? 'review' : '')
  const [kind, setKind] = useState('')
  const [q, setQ] = useState('')
  const [docs] = useLoad(() => api.get(`/api/clients/${cid}/documents?${status ? 'status=' + status : ''}&${kind ? 'kind=' + kind : ''}`), [cid, status, kind, tick])
  const list = (docs || []).filter((x) => !q || `${x.inv_no} ${x.party_name} ${x.hsn}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Documents</h1>
          <p>Every bill the agent read, with how it was read and which rule it used. Doubtful items wait in the review queue.</p>
        </div>
      </div>
      <Card>
        <div className="row wrap" style={{ marginBottom: 12 }}>
          <Seg value={status} onChange={setStatus} options={[['', 'All'], ['review', 'Review queue'], ['booked', 'Booked'], ['rejected', 'Rejected']]} />
          <Seg value={kind} onChange={setKind} options={[['', 'Sales + purchases'], ['sale', 'Sales'], ['purchase', 'Purchases']]} />
          <input type="text" placeholder="Search invoice, party, HSN" value={q} onChange={(e) => setQ(e.target.value)} className="grow" style={{ maxWidth: 280 }} />
          <span className="muted small">{list.length} shown</span>
        </div>
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr><th>Date</th><th>Type</th><th>Invoice</th><th>Party</th><th className="hide-sm">HSN</th><th className="num">Taxable</th><th className="num">GST</th><th className="hide-sm">Read by</th><th>Status</th></tr>
            </thead>
            <tbody>
              {list.map((x) => (
                <tr key={x.id} className="click" onClick={() => openDoc(x.id)}>
                  <td className="num">{d(x.inv_date)}</td>
                  <td>{x.kind === 'sale' ? 'Sale' : 'Purchase'}{x.rcm && <span className="chip" style={{ marginLeft: 4 }}>RCM</span>}</td>
                  <td className="mono">{x.inv_no || '—'}</td>
                  <td>{x.party_name}{x.status === 'review' && x.question && <div className="q">{x.question}</div>}</td>
                  <td className="hide-sm mono">{x.hsn}</td>
                  <td className="num">{inr(x.taxable)}</td>
                  <td className="num">{inr(x.cgst + x.sgst + x.igst)}</td>
                  <td className="hide-sm"><span className="chip">{x.method}</span></td>
                  <td><Status s={x.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {docs && !list.length && <div className="empty">Nothing here.</div>}
        </div>
      </Card>
    </>
  )
}

const FIELDS = [['kind', 'Type'], ['inv_no', 'Invoice no.'], ['inv_date', 'Date'], ['party_name', 'Party'], ['party_gstin', 'GSTIN'],
  ['hsn', 'HSN'], ['taxable', 'Taxable'], ['rate', 'Rate %'], ['cgst', 'CGST'], ['sgst', 'SGST'], ['igst', 'IGST'], ['total', 'Total']]
const MONEY = new Set(['taxable', 'cgst', 'sgst', 'igst', 'total'])

export function DocDrawer({ id, onClose }) {
  const { who, toast, refresh } = useApp()
  const [doc, reload] = useLoad(() => api.get(`/api/documents/${id}`), [id])
  const [edit, setEdit] = useState(null)
  if (!doc) return <Drawer onClose={onClose}><div className="empty">Loading…</div></Drawer>
  const editing = edit !== null
  const save = async () => {
    try {
      const r = await api.patch(`/api/documents/${id}`, { by: who, fields: edit })
      toast(r.status === 'booked' ? 'Booked after review' : 'Saved; still has a problem')
      setEdit(null); reload(); refresh()
    } catch (e) { toast(e.message, true) }
  }
  const reject = async () => {
    await api.post(`/api/documents/${id}/reject`, { by: who })
    toast('Rejected'); reload(); refresh()
  }
  return (
    <Drawer onClose={onClose}>
      <div className="row between" style={{ marginBottom: 12 }}>
        <div>
          <h1 style={{ fontSize: 18 }}>{doc.kind === 'sale' ? 'Sale' : 'Purchase'} {doc.inv_no || '(no number)'}</h1>
          <div className="muted small">#{doc.id} · {doc.channel} · read by {doc.method} · confidence {Math.round(doc.confidence * 100)}% · rules v{doc.rule_version}</div>
        </div>
        <div className="row"><Status s={doc.status} /><button className="btn sm" onClick={onClose}>Close</button></div>
      </div>
      {doc.question && doc.status === 'review' && <div className="note warn" style={{ marginBottom: 12 }}>Agent asks: {doc.question}</div>}
      {doc.issues?.map((i, k) => <div key={k} className={`note ${i.severity === 'high' ? 'error' : 'warn'}`} style={{ marginBottom: 8 }}>{i.code}: {i.msg}</div>)}
      {!doc.itc_eligible && <div className="note info" style={{ marginBottom: 8 }}>No input credit: {doc.itc_note}</div>}

      <div className="grid g2" style={{ marginTop: 8 }}>
        <Card title="Source">
          {doc.file_path && /\.(png|jpe?g|webp)$/i.test(doc.file_path) && <img className="bill-img" src={api.file(doc.file_path)} alt="Original bill" />}
          {doc.file_path && /\.pdf$/i.test(doc.file_path) && <a href={api.file(doc.file_path)} target="_blank" rel="noreferrer">Open PDF</a>}
          {doc.raw_text && <pre className="mono" style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{doc.raw_text}</pre>}
          {!doc.file_path && !doc.raw_text && <div className="muted">Synthetic seed record (no image).</div>}
          {doc.irn && <div className="small muted" style={{ marginTop: 8 }}>IRN {doc.irn.slice(0, 24)}…</div>}
        </Card>
        <Card title="Fields" right={doc.status !== 'rejected' && !editing && <button className="btn sm" onClick={() => setEdit({})}>Correct</button>}>
          {FIELDS.map(([k, label]) => (
            <div className="fieldrow" key={k}>
              <span className="muted">{label}</span>
              {editing ? (
                <input type={k === 'inv_date' ? 'date' : 'text'} defaultValue={doc[k] ?? ''} onChange={(e) => setEdit({ ...edit, [k]: e.target.value })} />
              ) : (
                <span className={MONEY.has(k) ? 'num' : k.includes('gstin') || k === 'inv_no' ? 'mono' : ''}>
                  {MONEY.has(k) ? inr(doc[k]) : k === 'inv_date' ? d(doc[k], { day: 'numeric', month: 'short', year: 'numeric' }) : String(doc[k] ?? '—')}
                </span>
              )}
              <Conf v={doc.field_conf?.[k]} />
            </div>
          ))}
          {editing && (
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn primary" onClick={save}>Save & re-check</button>
              <button className="btn" onClick={() => setEdit(null)}>Cancel</button>
            </div>
          )}
          {!editing && doc.status === 'review' && (
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn primary" onClick={() => api.patch(`/api/documents/${id}`, { by: who, fields: {} }).then(() => { toast('Re-checked'); reload(); refresh() })}>Confirm as read</button>
              <button className="btn" onClick={reject}>Reject</button>
            </div>
          )}
        </Card>
      </div>
      <Card title="Rules used" style={{ marginTop: 16 }}>
        <div className="row wrap">{doc.cites?.map((c, i) => <Cite key={i} c={c} />)}</div>
        <div className="small muted" style={{ marginTop: 8 }}>
          Amounts are computed by the rule engine from the rule set shown. The model only reads text from the bill.
          {doc.paid_on && <> · Paid on {d(doc.paid_on)}</>}
        </div>
      </Card>
    </Drawer>
  )
}

export { Badge }
