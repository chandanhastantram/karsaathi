import { useState } from 'react'
import { api, d, dt, inr } from '../api'
import { LANGS } from '../App'
import { Card, Cite, Drawer, Seg, Status, useApp, useLoad } from '../ui'

const HEADS = [['txval', 'Taxable'], ['iamt', 'IGST'], ['camt', 'CGST'], ['samt', 'SGST']]

export default function Return() {
  const { cid, meta, lang, setLang, role, who, toast, refresh, openDoc, go, tick } = useApp()
  const period = meta.filing_period
  const [r, reload] = useLoad(() => api.get(`/api/clients/${cid}/return?period=${period}&lang=${lang}`), [cid, period, lang, tick])
  const [src, setSrc] = useState(null)
  if (!r) return <div className="empty">Loading…</div>
  const c = r.computation
  const rec = r.record

  const sources = async (title, ids) => {
    if (!ids?.length) return toast('No documents behind this figure')
    setSrc({ title, docs: await api.get(`/api/clients/${cid}/documents?ids=${ids.join(',')}`) })
  }
  const onRef = (ref) => {
    if (ref.startsWith('doc:')) return openDoc(Number(ref.slice(4)))
    if (ref === 'held') return go('suppliers')
    if (ref === 'set_off' || ref === 'late') return document.getElementById('setoff')?.scrollIntoView({ behavior: 'smooth' })
    const [t, k] = ref.split('.')
    const h = c[t]?.[k]
    if (h) sources(k.replace(/_/g, ' '), h.doc_ids)
  }
  const act = async (step) => {
    try {
      const out = await api.post(`/api/clients/${cid}/return/${step}`, { by: who, period })
      toast(step === 'file' ? `Filed (simulated). ARN ${out.arn}` : step === 'check' ? 'Checked and signed' : 'Prepared for the accountant')
      reload(); refresh()
    } catch (e) { toast(e.message, true) }
  }
  const download = (name, obj) => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' }))
    a.download = name
    a.click()
  }

  const st = rec.status
  const stages = [
    ['Draft', 'Computed from books', true],
    ['Prepared', rec.maker ? `${rec.maker} · ${dt(rec.maker_at)}` : 'Owner prepares (maker)', ['prepared', 'approved', 'filed'].includes(st)],
    ['Checked & signed', rec.checker ? `${rec.checker} · ${dt(rec.checker_at)}` : 'Accountant checks (checker)', ['approved', 'filed'].includes(st)],
    ['Filed (simulated)', rec.arn ? `ARN ${rec.arn}` : 'Mock portal acknowledgement', st === 'filed'],
  ]
  const nowIdx = stages.findIndex((s) => !s[2])

  const Row = ({ label, h, path }) => (
    <tr className="click" onClick={() => sources(label, h.doc_ids)} title="Show source documents">
      <td>{label}</td>
      {HEADS.map(([k]) => <td key={k} className="num">{h[k] != null ? inr(h[k]) : ''}</td>)}
      <td className="small muted">{h.doc_ids?.length || 0} docs</td>
    </tr>
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{c.form} · {c.period_label}</h1>
          <p>{c.client} · {c.gstin} · due {d(c.due, { day: 'numeric', month: 'short', year: 'numeric' })} · computed under rule set v{c.rule_version}</p>
        </div>
        <div className="row wrap">
          <button className="btn sm" onClick={() => download(`${c.form}_${c.gstin}_${c.period}.json`, r.payload.gstr3b)}>GSTR-3B JSON</button>
          <button className="btn sm" onClick={() => download(`GSTR1_${c.gstin}_${c.period}.json`, r.gstr1)}>GSTR-1 JSON</button>
        </div>
      </div>

      <div className="pipeline" style={{ marginBottom: 16 }}>
        {stages.map(([k, v, done], i) => (
          <div key={k} className={`pipe ${done ? 'done' : ''} ${i === nowIdx ? 'now' : ''}`}><div className="k">{i + 1}. {k}</div><div className="v">{v}</div></div>
        ))}
      </div>
      {rec.stale && <div className="note error" style={{ marginBottom: 12 }}>The books changed after this return was prepared. The signature no longer matches; prepare it again.</div>}
      {r.review_pending > 0 && <div className="note warn" style={{ marginBottom: 12 }}>{r.review_pending} document(s) are still in the review queue and are not counted here. <a href="#" onClick={(e) => { e.preventDefault(); go('documents', 'review') }}>Open the queue</a></div>}

      <div className="grid g2">
        <Card title="In plain words" right={<Seg value={lang} onChange={setLang} options={LANGS} />}
          sub="Every number comes from the rule engine; the words come from fixed templates. Tap a sentence to see its source.">
          <div className="explain">
            {r.explain.map((x, i) => (
              <p key={i} className={x.refs.length ? 'ref' : ''} onClick={() => x.refs[0] && onRef(x.refs[0])}>{x.text}</p>
            ))}
          </div>
        </Card>
        <Card title="Approval" sub="Owner prepares, accountant checks, both names are bound to the payload hash." right={<Status s={st} />}>
          <div style={{ fontSize: 30, fontWeight: 650 }} className="num">{inr(c.cash_payable)}</div>
          <div className="small muted" style={{ marginBottom: 12 }}>cash to pay · {c.late.days_late ? `${c.late.days_late} days late: fee ${inr(c.late.late_fee)} + interest ${inr(c.late.interest)}` : 'no late fee yet'}</div>
          <div className="row wrap">
            {role === 'owner' && st !== 'filed' && st !== 'approved' && <button className="btn primary" onClick={() => act('prepare')}>{st === 'prepared' ? 'Prepare again' : 'Prepare (maker)'}</button>}
            {role === 'accountant' && st === 'prepared' && <button className="btn primary" onClick={() => act('check')}>Check & sign (checker)</button>}
            {st === 'approved' && <button className="btn primary" onClick={() => act('file')}>File (simulated)</button>}
            {st !== 'approved' && st !== 'filed' && <button className="btn ghost sm" onClick={() => act('file')} title="Shows that the agent cannot file without approval">Try filing without approval</button>}
            {role === 'owner' && st === 'prepared' && <span className="small muted">Switch to Accountant to check and sign.</span>}
            {role === 'accountant' && st === 'draft' && <span className="small muted">Waiting for the owner to prepare.</span>}
          </div>
          <dl className="kv" style={{ marginTop: 14 }}>
            <dt>Payload hash</dt><dd className="hash">{rec.payload_hash?.slice(0, 16)}…{rec.payload_hash?.slice(-6)}</dd>
            {rec.signature && <><dt>Signature</dt><dd className="hash">{rec.signature.slice(0, 16)}…{rec.signature.slice(-6)}</dd></>}
            {rec.arn && <><dt>ARN</dt><dd className="mono">{rec.arn} <span className="chip">simulated</span></dd></>}
          </dl>
        </Card>
      </div>

      <Card title="GSTR-3B draft" sub="Click any row to see the bills behind it." style={{ marginTop: 16 }}>
        <div className="tbl-wrap">
          <table>
            <thead><tr><th>Table</th>{HEADS.map(([k, l]) => <th key={k} className="num">{l}</th>)}<th></th></tr></thead>
            <tbody>
              <tr><td colSpan={6} className="small muted" style={{ fontWeight: 600 }}>3.1 Outward and reverse-charge supplies</td></tr>
              <Row label="3.1(a) Outward taxable supplies" h={c.table_3_1.a_outward_taxable} />
              <Row label="3.1(d) Inward supplies on reverse charge" h={c.table_3_1.d_inward_rcm} />
              <tr><td colSpan={6} className="small muted" style={{ fontWeight: 600 }}>4. Eligible ITC</td></tr>
              <Row label="4A(3) Reverse charge" h={c.table_4.A3_rcm} />
              <Row label="4A(5) All other ITC (in GSTR-2B, accepted)" h={c.table_4.A5_all_other} />
              <Row label="4B(1) Reversed: Section 17(5) blocked" h={c.table_4.B1_blocked_17_5} />
              <Row label="4B(2) Reversed: Rule 37 (unpaid 180 days)" h={c.table_4.B2_rule37} />
              <tr style={{ fontWeight: 650 }}><td>4C Net ITC</td><td></td>{['iamt', 'camt', 'samt'].map((k) => <td key={k} className="num">{inr(c.table_4.C_net[k])}</td>)}<td></td></tr>
            </tbody>
          </table>
        </div>
        <div className="row wrap" style={{ marginTop: 8 }}>{c.cites.map((x, i) => <Cite key={i} c={x} />)}</div>
      </Card>

      <Card title="6.1 Payment of tax (Rule 88A set-off order)" id="setoff" style={{ marginTop: 16 }}
        sub="IGST credit is used first; CGST credit never pays SGST and vice versa. Reverse-charge tax is paid in cash.">
        <div className="tbl-wrap">
          <table>
            <thead><tr><th>Head</th><th className="num">Liability</th><th className="num">Paid by ITC</th><th className="num">Cash</th><th className="num">Credit carried forward</th></tr></thead>
            <tbody>
              {[['igst', 'iamt', 'IGST'], ['cgst', 'camt', 'CGST'], ['sgst', 'samt', 'SGST']].map(([h, a, l]) => {
                const liab = c.table_3_1.a_outward_taxable[a]
                return (
                  <tr key={h}><td>{l}</td><td className="num">{inr(liab)}</td><td className="num">{inr(liab - c.set_off.cash[h])}</td>
                    <td className="num">{inr(c.set_off.cash[h])}</td><td className="num">{inr(c.set_off.carry_forward[h])}</td></tr>
                )
              })}
              <tr><td>Reverse charge (cash only)</td><td className="num">{inr(c.summary.rcm)}</td><td className="num">₹0</td><td className="num">{inr(c.summary.rcm)}</td><td></td></tr>
              <tr style={{ fontWeight: 650 }}><td>Total cash</td><td></td><td></td><td className="num">{inr(c.cash_payable)}</td><td></td></tr>
            </tbody>
          </table>
        </div>
        <div className="small muted" style={{ marginTop: 8 }}>
          Utilised: {Object.entries(c.set_off.utilised).map(([k, v]) => `${k.replace('->', ' → ').toUpperCase()} ${inr(v)}`).join(' · ') || 'none'}
        </div>
      </Card>

      {src && (
        <Drawer modal onClose={() => setSrc(null)}>
          <h2 style={{ textTransform: 'capitalize' }}>{src.title}</h2>
          <p className="muted small">{src.docs.length} source document(s)</p>
          <table>
            <thead><tr><th>Date</th><th>Invoice</th><th>Party</th><th className="num">Taxable</th><th className="num">GST</th></tr></thead>
            <tbody>
              {src.docs.map((x) => (
                <tr key={x.id} className="click" onClick={() => { setSrc(null); openDoc(x.id) }}>
                  <td>{d(x.inv_date)}</td><td className="mono">{x.inv_no}</td><td>{x.party_name}</td>
                  <td className="num">{inr(x.taxable)}</td><td className="num">{inr(x.cgst + x.sgst + x.igst)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Drawer>
      )}
    </>
  )
}
