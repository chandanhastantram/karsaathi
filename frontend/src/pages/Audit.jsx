import { useState } from 'react'
import { api } from '../api'
import { Card, Seg, useApp, useLoad } from '../ui'

export default function Audit() {
  const { cid, tick } = useApp()
  const [scope, setScope] = useState('client')
  const [rows] = useLoad(() => api.get(`/api/audit${scope === 'client' ? `?client_id=${cid}` : ''}`), [cid, scope, tick])
  const [v, setV] = useState(null)
  const summary = (dt) => {
    const s = JSON.stringify(dt)
    return s.length > 160 ? s.slice(0, 160) + '…' : s
  }
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Audit trail</h1>
          <p>Every agent and human action, hash-chained: each entry's hash covers the previous one, so any edit breaks verification.</p>
        </div>
        <div className="row">
          <Seg value={scope} onChange={setScope} options={[['client', 'This client'], ['all', 'Everything']]} />
          <button className="btn primary" onClick={async () => setV(await api.get('/api/audit/verify'))}>Verify chain</button>
        </div>
      </div>
      {v && <div className={`note ${v.ok ? 'ok' : 'error'}`} style={{ marginBottom: 12 }}>
        {v.ok ? `✓ Chain intact: ${v.entries} entries. Head ${v.head.slice(0, 16)}…` : `✕ Chain broken at entry #${v.broken_at}`}
      </div>}
      <Card>
        <div className="tbl-wrap">
          <table>
            <thead><tr><th>#</th><th>Time</th><th>Actor</th><th>Action</th><th>Detail</th><th className="hide-sm">Hash</th></tr></thead>
            <tbody>
              {(rows || []).map((a) => (
                <tr key={a.id}>
                  <td className="num muted">{a.id}</td>
                  <td className="small num" style={{ whiteSpace: 'nowrap' }}>{a.at.replace('T', ' ')}</td>
                  <td>{a.actor}</td>
                  <td><span className={`chip ${a.action.startsWith('blocked') ? 'solid' : a.action.startsWith('approved') ? 'dark' : ''}`}>{a.action}</span></td>
                  <td className="mono small" style={{ maxWidth: 420, wordBreak: 'break-all' }}>{summary(a.detail)}</td>
                  <td className="hash hide-sm" title={`prev ${a.prev_hash}`}>{a.hash.slice(0, 10)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  )
}
