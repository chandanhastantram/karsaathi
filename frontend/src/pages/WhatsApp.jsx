import { useEffect, useRef, useState } from 'react'
import { api, dt } from '../api'
import { Card, Cite, Icon, Seg, useApp, useLoad } from '../ui'

const SAMPLES = [
  { icon: 'file', label: 'E-invoice (signed QR)', file: '1_einvoice_shree_metals.png' },
  { icon: 'photo', label: 'Blurry bill photo', file: '2_photo_kaveri_tiles.png' },
  { icon: 'voice', label: '₹75,000 sale', text: 'sold 60 pipes to Hosur Infra Projects ₹75,000 incl gst 320 km', channel: 'voice' },
  { icon: 'voice', label: 'Cement sale', text: 'sold 20 bags cement to Lakshmi Hardware ₹62,000', channel: 'voice' },
  { icon: 'truck', label: 'Vehicle no.', text: 'KA01AB4521', sender: 'transporter' },
  { icon: 'sms', label: 'UPI SMS', text: 'Rs.71,980.00 debited from A/c XX4821 to SAI CABLES on 16-11-26 UPI Ref 6231908812', channel: 'upi_sms' },
  { icon: 'ask', label: 'How much do I pay?', text: 'how much GST do I pay this month?' },
  { icon: 'ask', label: 'Who has not filed?', text: 'which suppliers have not filed?' },
]

export default function WhatsApp() {
  const { cid, client, meta, lang, refresh, toast, openDoc } = useApp()
  const [msgs, reload] = useLoad(() => api.get(`/api/clients/${cid}/messages`), [cid])
  const [text, setText] = useState('')
  const [sender, setSender] = useState('owner')
  const [busy, setBusy] = useState(false)
  const [sel, setSel] = useState(null)
  const [rec, setRec] = useState(null)
  const chatRef = useRef(null)
  const fileRef = useRef(null)

  useEffect(() => { chatRef.current?.scrollTo(0, 1e9) }, [msgs])
  const lastIn = msgs ? [...msgs].reverse().find((m) => m.direction === 'in' && m.trace?.length) : null
  const shown = (msgs || []).find((m) => m.id === sel) || lastIn

  async function send({ text: t, file, channel, sender: snd }) {
    setBusy(true)
    const fd = new FormData()
    if (t) fd.append('text', t)
    if (file) fd.append('file', file)
    fd.append('channel', channel || (file ? 'whatsapp_photo' : 'whatsapp_text'))
    fd.append('sender', snd || sender)
    try {
      await api.form(`/api/clients/${cid}/inbound`, fd)
      setText('')
      setSel(null)
      reload()
      refresh()
    } catch (e) { toast(e.message, true) }
    setBusy(false)
  }

  async function sample(s) {
    if (s.file) {
      const blob = await (await fetch(api.sample(s.file))).blob()
      send({ file: new File([blob], s.file, { type: blob.type || 'image/png' }) })
    } else send({ text: s.text, channel: s.channel, sender: s.sender })
  }

  function mic() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return toast('Voice input needs Chrome or Edge', true)
    if (rec) { rec.stop(); return }
    const r = new SR()
    r.lang = meta.speech[lang] || 'en-IN'
    r.interimResults = true
    r.onresult = (e) => setText(Array.from(e.results).map((x) => x[0].transcript).join(' '))
    r.onend = () => setRec(null)
    r.onerror = (e) => { toast('Voice: ' + e.error, true); setRec(null) }
    r.start()
    setRec(r)
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>WhatsApp inbox</h1>
          <p>The owner forwards bills here. Photos, PDFs, voice notes and UPI SMS land in one inbox. In production this is the WhatsApp Business webhook (<span className="mono">/webhook/whatsapp</span>).</p>
        </div>
        <Seg value={sender} onChange={setSender} options={[['owner', 'As owner'], ['transporter', 'As transporter']]} />
      </div>
      <div className="wa-wrap">
        <div className="phone">
          <div className="phone-h">
            <div className="av">K</div>
            <div>
              <div style={{ fontWeight: 600 }}>KarSaathi</div>
              <div style={{ fontSize: 11, opacity: .8 }}>{client?.name} · agent online</div>
            </div>
          </div>
          <div className="chat" ref={chatRef}>
            <div className="bub sys">Messages are processed by the agent. Filing always needs a human.</div>
            {(msgs || []).map((m) => (
              <div key={m.id} className={`bub ${m.direction} ${m.trace?.length ? 'click' : ''} ${shown?.id === m.id ? 'sel' : ''}`}
                onClick={() => m.trace?.length && setSel(m.id)}>
                {m.media && /\.(png|jpe?g|webp)$/i.test(m.media) && <img src={api.file(m.media)} alt="bill" />}
                {m.media && /\.pdf$/i.test(m.media) && <div className="row"><Icon name="file" size={14} />{m.media}</div>}
                {m.text}
                <div className="t">{dt(m.at)}</div>
              </div>
            ))}
            {busy && <div className="bub out muted">KarSaathi is reading…</div>}
          </div>
          <div className="chips">
            {SAMPLES.map((s) => (
              <button key={s.label} onClick={() => sample(s)} disabled={busy} style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
                <Icon name={s.icon} size={13} />{s.label}
              </button>
            ))}
          </div>
          <form className="compose" onSubmit={(e) => { e.preventDefault(); text.trim() && send({ text, channel: rec ? 'voice' : undefined }) }}>
            <button type="button" className="round" title="Attach bill photo or PDF" onClick={() => fileRef.current.click()} aria-label="Attach"><Icon name="clip" /></button>
            <input ref={fileRef} type="file" accept="image/*,application/pdf" hidden
              onChange={(e) => { const f = e.target.files[0]; e.target.value = ''; f && send({ file: f }) }} />
            <input type="text" placeholder={rec ? 'Listening…' : 'Type, or tap the mic'} value={text} onChange={(e) => setText(e.target.value)} aria-label="Message" />
            <button type="button" className={`round ${rec ? 'rec' : ''}`} title={`Voice note (${meta.speech[lang]})`} onClick={mic} aria-label="Voice note"><Icon name="mic" /></button>
            <button className="round send" disabled={busy || !text.trim()} title="Send" aria-label="Send"><Icon name="send" /></button>
          </form>
        </div>

        <Card title="What the agent did" sub="Capture → Read (QR → OCR → LLM) → Validate → Compute → Check → Confidence gate. Click any message to see its trace.">
          {!shown && <div className="empty">Send a bill or a message to see the pipeline.</div>}
          {shown && (
            <>
              <div className="small muted" style={{ marginBottom: 12 }}>“{shown.text || shown.media}” · {dt(shown.at)}</div>
              <div className="trace">
                {shown.trace.map((t, i) => (
                  <div className="step" key={i}>
                    <div className={`dot ic ${t.ok ? 'ok' : 'warn'}`}>{t.ok ? '✓' : '!'}</div>
                    <div>
                      <div style={{ fontWeight: 600 }}>{t.step}</div>
                      <div className="ink2">{t.msg}</div>
                      {t.cites && <div className="row wrap" style={{ marginTop: 4 }}>{t.cites.map((c, j) => <Cite key={j} c={c} />)}</div>}
                    </div>
                  </div>
                ))}
              </div>
              {shown.document_id && <button className="btn" onClick={() => openDoc(shown.document_id)}>Open document #{shown.document_id}</button>}
            </>
          )}
        </Card>
      </div>
    </>
  )
}
