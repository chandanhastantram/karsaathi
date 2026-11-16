import { Fragment, useState } from 'react'
import { api, d, dt, inr } from '../api'
import { Card, Check, Cite, Drawer, Status, useApp, useLoad } from '../ui'

export default function EwayBills() {
  const { cid, tick } = useApp()
  const [list, reload] = useLoad(() => api.get(`/api/clients/${cid}/ewaybills`), [cid, tick])
  const [kit, setKit] = useState(null)
  return (
    <>
      <div className="page-head">
        <div>
          <h1>E-way bills</h1>
          <p>Part A is pre-filled from the invoice; the transporter sends the vehicle number on WhatsApp. Generation and extension are simulated and always need the owner's approval.</p>
        </div>
      </div>
      {list && !list.length && <div className="empty">No e-way bills yet. Send a sale above ₹50,000 in the WhatsApp inbox.</div>}
      <div className="grid g2">
        {(list || []).map((e) => <Ewb key={e.id} e={e} reload={reload} openKit={setKit} />)}
      </div>
      {kit && (
        <Drawer modal onClose={() => setKit(null)}>
          <h2>Checkpoint kit</h2>
          <p className="muted small">No-login page for the driver. Shows what an officer will ask for. (Simulated e-way bill.)</p>
          <dl className="kv">
            <dt>EWB no.</dt><dd className="mono" style={{ fontSize: 18 }}>{kit.ewb_no}</dd>
            <dt>Valid until</dt><dd>{dt(kit.valid_until)}</dd>
            <dt>Vehicle</dt><dd className="mono">{kit.vehicle_no}</dd>
            <dt>From</dt><dd>{kit.from}</dd>
            <dt>To</dt><dd>{kit.to}</dd>
            <dt>Invoice</dt><dd>{kit.invoice} · {d(kit.invoice_date)}</dd>
            <dt>Goods</dt><dd>{kit.description} (HSN {kit.hsn})</dd>
            <dt>Value</dt><dd>{inr(kit.value)}</dd>
          </dl>
          <div className="row" style={{ marginTop: 12 }}><button className="btn" onClick={() => setKit(null)}>Close</button></div>
        </Drawer>
      )}
    </>
  )
}

function Ewb({ e, reload, openKit }) {
  const { who, toast, refresh, role } = useApp()
  const [veh, setVeh] = useState(e.vehicle_no || '')
  const [dist, setDist] = useState(e.distance_km || '')
  const [km, setKm] = useState(e.km_remaining || '')
  const pf = e.preflight
  const save = async () => {
    try { await api.patch(`/api/ewaybills/${e.id}`, { by: who, vehicle_no: veh, distance_km: Number(dist) || 0 }); toast('Saved; pre-flight re-run'); reload() }
    catch (x) { toast(x.message, true) }
  }
  const gen = async () => {
    try { const r = await api.post(`/api/ewaybills/${e.id}/generate`, { by: who }); toast(`E-way bill ${r.ewb_no} generated (simulated)`); reload(); refresh() }
    catch (x) { toast(x.message, true) }
  }
  const extend = async () => {
    try { await api.post(`/api/ewaybills/${e.id}/extend`, { by: who, km_remaining: Number(km) }); toast('Extended (simulated)'); reload() }
    catch (x) { toast(x.message, true) }
  }
  return (
    <Card title={`Invoice ${e.doc.inv_no}`} sub={`${e.doc.party_name} · ${inr(e.doc.total)} · ${e.doc.igst > 0 ? 'inter-state' : 'intra-state'}`} right={<Status s={e.status} />}>
      {e.watch && <div className={`note ${e.watch.level}`} style={{ marginBottom: 10 }}>⏱ {e.watch.msg}</div>}
      {e.status === 'draft' ? (
        <>
          {pf.checks.map((c, i) => <Check key={i} level={c.level}>{c.msg}</Check>)}
          <div className="row wrap" style={{ marginTop: 10 }}>
            <label className="fld">Vehicle no.<input type="text" value={veh} onChange={(x) => setVeh(x.target.value)} placeholder="KA01AB1234" /></label>
            <label className="fld">Distance (km)<input type="number" value={dist} onChange={(x) => setDist(x.target.value)} style={{ width: 110 }} /></label>
            <button className="btn" onClick={save} style={{ alignSelf: 'flex-end' }}>Save & re-check</button>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn primary" disabled={!pf.ready || role !== 'owner'} onClick={gen}
              title={role !== 'owner' ? 'Switch to Owner to approve' : ''}>Approve & generate (simulated)</button>
            {role !== 'owner' && <span className="small muted">Owner approves e-way bills</span>}
          </div>
        </>
      ) : (
        <dl className="kv">
          <dt>EWB no.</dt><dd className="mono">{e.ewb_no}</dd>
          <dt>Vehicle</dt><dd className="mono">{e.vehicle_no}</dd>
          <dt>Generated</dt><dd>{dt(e.generated_at)} by {e.approved_by}</dd>
          <dt>Valid until</dt><dd>{dt(e.valid_until)}</dd>
          <dt>Distance left</dt><dd>{e.km_remaining} km of {e.distance_km} km</dd>
        </dl>
      )}
      {e.ewb_no && (
        <div className="row wrap" style={{ marginTop: 12 }}>
          <button className="btn" onClick={async () => openKit(await api.get(`/api/kit/${e.id}`))}>Driver checkpoint kit</button>
          {e.watch?.can_extend && (
            <>
              <input type="number" value={km} onChange={(x) => setKm(x.target.value)} style={{ width: 90 }} aria-label="km remaining" />
              <button className="btn warn" onClick={extend}>Extend for {km || '?'} km</button>
            </>
          )}
        </div>
      )}
      <details style={{ marginTop: 12 }}>
        <summary className="small muted">Part A (pre-filled from the invoice)</summary>
        <dl className="kv" style={{ marginTop: 8 }}>
          {Object.entries(pf.part_a).map(([k, v]) => (
            <Fragment key={k}><dt>{k.replace(/_/g, ' ')}</dt><dd className="mono">{typeof v === 'number' && k !== 'distance_km' ? inr(v) : String(v ?? '—')}</dd></Fragment>
          ))}
        </dl>
      </details>
      <div style={{ marginTop: 8 }}><Cite c={pf.cite} /></div>
    </Card>
  )
}
