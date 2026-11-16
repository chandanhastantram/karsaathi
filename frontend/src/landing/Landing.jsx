import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useScroll, useSpring, useTransform } from 'framer-motion'
import { CountUp, Cursor, Magnetic, Reveal, Rotator, SplitText, Tilt, useLenis } from '../fx/fx'
import './landing.css'

const BillScene = lazy(() => import('../three/BillScene'))

const ACTS = [
  { k: '01 / CHAOS', h: ['A BAG OF BILLS.', 'A WHATSAPP FULL OF PHOTOS.'], p: 'This is how GST paperwork arrives at most small shops. Crumpled, blurry, and three days before the deadline.' },
  { k: '02 / SORTED', h: ['SORTED BEFORE', 'YOUR CHAI COOLS.'], p: 'Sales on the left. Purchases on the right. The doubtful ones glow red and wait for a human.', tags: ['Sales', 'Purchases', 'Needs a human'] },
  { k: '03 / ONE RETURN', h: ['EVERY RUPEE', 'CITES ITS RULE.'], p: 'A versioned rule book does the maths. Tap any number to see the bill it came from and the rule it used.' },
  { k: '04 / STAMPED', h: ['APPROVED', 'BY A HUMAN.'], p: 'The owner prepares. The accountant signs. Only then does the (simulated) filing happen. No exceptions, no 2 AM surprises.' },
]

const STEPS = [
  ['Capture', 'Owner forwards bills on WhatsApp. Photos, PDFs, voice notes, UPI SMS.', 'Send it like you send memes.'],
  ['Read', 'Signed e-invoice QR first, then OCR, then the LLM, only for what is left.', 'Reads handwriting better than your doctor’s.'],
  ['Compute', 'Dated GST rules decide every rate, head and set-off. Numbers cite their rule.', 'The AI is not allowed near the calculator.'],
  ['Check', 'Suppliers who have not filed, e-way bills before the truck leaves, cash to keep aside.', 'Nags suppliers so you don’t have to.'],
  ['Approve', 'Plain summary in Kannada, Hindi or English. Owner prepares, accountant signs.', 'Two signatures. Zero blind approvals.'],
  ['File (sim.)', 'Mock portal returns an ARN. Every step lands in a hash-chained audit trail.', 'Paperwork done. Business on.'],
]

const NEVER = [
  ['File your return at 2 AM without asking.', 'It waits. Politely. Forever if needed.'],
  ['Guess a tax rate from memory.', 'Rates live in a rule file with a date and a source.'],
  ['Generate an e-way bill on its own.', 'Owner taps approve. Then the truck goes.'],
  ['Accept a supplier invoice for you.', 'It recommends. You decide in IMS.'],
  ['Forget the 11th.', 'Seriously. It has a calendar and it is not afraid to use it.'],
]

const FEATURES = [
  ['WhatsApp bill capture', 'Forward and forget. The agent books it and says what it did.'],
  ['E-invoice QR first', 'Signed IRP data beats any OCR. Verified offline.'],
  ['Credit-at-risk forecast', 'Find missing supplier filings before GSTR-2B, not after.'],
  ['Pre-flight e-way bills', 'Wrong vehicle number? Caught before the checkpoint does.'],
  ['GST cash forecast', '“Keep ₹1,47,240 aside by 25 Nov.” That kind of honest.'],
  ['Notice reader', 'ASMT-10 in plain Kannada, with a draft reply for the CA.'],
  ['Rule-change watch', 'New advisory? New rule version. Old bills re-checked.'],
  ['Accountant console', 'One queue across clients. Only the exceptions.'],
]

const LOAD_LINES = ['Untangling the bag of bills…', 'Asking the rule book, not the AI…', 'Checking who forgot the 11th…', 'Polishing the red stamp…']

export default function Landing({ onEnter }) {
  const progress = useRef(0)
  const storyRef = useRef(null)
  const canvasWrap = useRef(null)
  const [loaded, setLoaded] = useState(false)
  const [act, setAct] = useState(0)

  useLenis((_, lenis) => {
    const story = storyRef.current
    if (!story) return
    const y = lenis ? lenis.scroll : window.scrollY
    const span = story.offsetHeight - innerHeight
    const p = Math.min(1, Math.max(0, y / span))
    progress.current = p
    setAct(p < 0.4 ? 0 : p < 0.64 ? 1 : p < 0.88 ? 2 : 3)
    if (canvasWrap.current) {
      const fade = Math.min(1, Math.max(0, (y - span) / (innerHeight * 0.6)))
      canvasWrap.current.style.opacity = String(1 - fade)
      canvasWrap.current.style.transform = `scale(${1 + fade * 0.08})`
    }
  })

  useEffect(() => {
    const t = setTimeout(() => setLoaded(true), 2100)
    document.body.classList.add('landing-body')
    return () => { clearTimeout(t); document.body.classList.remove('landing-body') }
  }, [])

  const { scrollYProgress } = useScroll()
  const bar = useSpring(scrollYProgress, { stiffness: 120, damping: 24 })
  const go = (id) => window.__lenis ? window.__lenis.scrollTo(document.getElementById(id), { duration: 1.6 }) : document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })

  return (
    <div className="lp">
      <Cursor />
      <div className="lp-grain" aria-hidden />
      <motion.div className="lp-bar" style={{ scaleX: bar }} />
      <AnimatePresence>{!loaded && <Loader key="ld" />}</AnimatePresence>

      <div className="lp-canvas" ref={canvasWrap} aria-hidden>
        <Suspense fallback={null}><BillScene progress={progress} count={innerWidth < 700 ? 22 : 34} /></Suspense>
      </div>

      <header className="lp-nav">
        <button className="lp-logo" onClick={() => go('top')}><span>K</span>KarSaathi</button>
        <nav>
          <button onClick={() => go('story')}>Story</button>
          <button onClick={() => go('how')}>How it works</button>
          <button onClick={() => go('trust')}>Trust</button>
          <button onClick={() => go('features')}>Features</button>
        </nav>
        <button className="lp-pill" onClick={onEnter}>Open app →</button>
      </header>

      <div className="lp-acts" aria-hidden>
        {ACTS.map((a, i) => <span key={i} className={i === act ? 'on' : ''} />)}
      </div>

      {/* -------- the 3D story: hero + 4 acts -------- */}
      <div ref={storyRef} id="top">
        <section className="lp-hero">
          <motion.div className="lp-eyebrow" initial={{ opacity: 0 }} animate={{ opacity: loaded ? 1 : 0 }} transition={{ delay: 0.3 }}>
            Agentic AI · GST co-pilot for micro enterprises
          </motion.div>
          <h1 className="lp-mega">
            {loaded && <>
              <SplitText text="YOUR BAG OF BILLS" />
              <br />
              <SplitText text="IS NOW A" delay={0.25} /> <span className="red"><SplitText text="RETURN." delay={0.4} /></span>
            </>}
          </h1>
          <motion.p className="lp-lede" initial={{ opacity: 0, y: 20 }} animate={loaded ? { opacity: 1, y: 0 } : {}} transition={{ delay: 0.9, duration: 0.8 }}>
            KarSaathi reads your bills on WhatsApp, does the GST maths with a rule book, and then waits for a human to say yes.
            <br /><b>LLMs read. Rules decide. Humans approve.</b>
          </motion.p>
          <motion.div className="lp-cta-row" initial={{ opacity: 0 }} animate={loaded ? { opacity: 1 } : {}} transition={{ delay: 1.2 }}>
            <Magnetic className="lp-btn red" onClick={onEnter}>Try the demo →</Magnetic>
            <button className="lp-btn ghost" onClick={() => go('story')}>Watch the bills sort themselves ↓</button>
          </motion.div>
          <div className="lp-scrollhint"><span /> scroll</div>
        </section>

        <Marquee items={['GSTR-1', 'GSTR-3B', 'IMS', 'E-WAY BILLS', 'NO LATE FEES', 'NO PANIC', 'RULE 37', 'RULE 88A', 'TDS', 'ಕನ್ನಡ', 'हिन्दी', 'ENGLISH']} />

        <div id="story">
          {ACTS.map((a, i) => (
            <section key={i} className={`lp-act ${i % 2 ? 'right' : ''}`}>
              <div className="lp-act-card">
                <div className="lp-k">{a.k}</div>
                <h2 className="lp-h2">{a.h.map((l, j) => <span key={j} className={j === a.h.length - 1 && i === 3 ? 'red' : ''}><SplitText text={l} delay={j * 0.15} /><br /></span>)}</h2>
                <Reveal i={2}><p>{a.p}</p></Reveal>
                {a.tags && <Reveal i={3}><div className="lp-tags">{a.tags.map((t, j) => <span key={t} className={j === 2 ? 'red' : ''}>{t}</span>)}</div></Reveal>}
                {i === 0 && <Reveal i={3}><div className="lp-bigstat"><CountUp to={20} />&nbsp;hrs<small>a month on GST paperwork. That’s a cricket match every weekend, spent on bills.</small></div></Reveal>}
              </div>
            </section>
          ))}
        </div>
      </div>

      {/* -------- after the story: solid sections -------- */}
      <HowItWorks />

      <section className="lp-stats" id="trust">
        <Reveal><div className="lp-k">THE NUMBERS</div></Reveal>
        <h2 className="lp-h2"><SplitText text="SMALL SHOPS PAY FOR PAPERWORK." /><br /><span className="red"><SplitText text="WE’D RATHER THEY DIDN’T." delay={0.2} /></span></h2>
        <div className="lp-stat-grid">
          <Stat big={<>₹<CountUp to={3000} /></>} label="per filing to an accountant, today" i={0} />
          <Stat big={<><CountUp to={12} />%</>} label="of yearly profit lost to compliance" i={1} />
          <Stat big={<CountUp to={0} />} label="filings without a human approval" i={2} red />
          <Stat big={<><CountUp to={100} />%</>} label="of figures cite a bill and a rule" i={3} />
        </div>
        <p className="lp-foot">Problem-statement figures. Our own numbers come from the synthetic benchmark, reported, not assumed.</p>
      </section>

      <section className="lp-never">
        <div className="lp-k">THINGS KARSAATHI WILL NEVER DO</div>
        <ol>
          {NEVER.map(([a, b], i) => (
            <Reveal as="li" key={i} i={i}>
              <span className="n">0{i + 1}</span>
              <span className="t"><s>{a}</s><em>{b}</em></span>
            </Reveal>
          ))}
        </ol>
      </section>

      <section className="lp-features" id="features">
        <div className="lp-k dark">WHAT’S INSIDE</div>
        <h2 className="lp-h2 dark"><SplitText text="EVERYTHING INSIDE." /> <span className="red"><SplitText text="ONE MUNSHI." delay={0.2} /></span></h2>
        <div className="lp-feat-grid">
          {FEATURES.map(([t, d], i) => (
            <Reveal key={t} i={i % 4}>
              <Tilt className="lp-feat" data-cursor>
                <div className="num">{String(i + 1).padStart(2, '0')}</div>
                <h3>{t}</h3>
                <p>{d}</p>
              </Tilt>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="lp-final">
        <div className="lp-k">READY WHEN YOU ARE</div>
        <h2 className="lp-mega small"><SplitText text="PAPERWORK DONE." /><br /><span className="red"><SplitText text="BUSINESS ON." delay={0.2} /></span></h2>
        <p className="lp-lede center">Walk through a month at <b>Ramesh Traders</b>, a fictional cement and hardware shop in Bengaluru. <Rotator lines={['No real taxpayer data.', 'No real portal calls.', 'Filing is simulated.', 'Bring your own chai.']} /></p>
        <Magnetic className="lp-btn red huge" onClick={onEnter}>Enter KarSaathi →</Magnetic>
      </section>

      <footer className="lp-footer">
        <span>KarSaathi · for micro enterprises that lose time and profit to compliance paperwork</span>
        <span>LLMs read. Rules decide. Humans approve.</span>
      </footer>
    </div>
  )
}

function Loader() {
  const [n, setN] = useState(0)
  useEffect(() => {
    let raf, start
    const tick = (t) => { start ??= t; const p = Math.min(1, (t - start) / 1700); setN(Math.round(100 * (1 - Math.pow(1 - p, 3)))); if (p < 1) raf = requestAnimationFrame(tick) }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])
  return (
    <motion.div className="lp-loader" exit={{ y: '-100%' }} transition={{ duration: 0.9, ease: [0.76, 0, 0.24, 1] }}>
      <div className="lp-loader-n">{String(n).padStart(3, '0')}</div>
      <div className="lp-loader-l">{LOAD_LINES[Math.min(3, Math.floor(n / 26))]}</div>
      <motion.div className="lp-loader-red" initial={{ scaleY: 0 }} exit={{ scaleY: 1 }} transition={{ duration: 0.6 }} />
    </motion.div>
  )
}

function Marquee({ items }) {
  const row = [...items, ...items]
  return (
    <div className="lp-marquee" aria-hidden>
      <div className="lp-marquee-track">{row.map((t, i) => <span key={i}>{t}<i>/</i></span>)}</div>
    </div>
  )
}

function HowItWorks() {
  const ref = useRef(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] })
  const x = useTransform(scrollYProgress, [0, 1], ['2%', '-74%'])
  const fill = useTransform(scrollYProgress, [0, 1], ['0%', '100%'])
  return (
    <section className="lp-how" ref={ref} id="how">
      <div className="lp-how-sticky">
        <div className="lp-how-head">
          <div className="lp-k">HOW IT WORKS</div>
          <h2 className="lp-h2">SIX STEPS. <span className="red">ONE HUMAN YES.</span></h2>
          <div className="lp-how-line"><motion.span style={{ width: fill }} /></div>
        </div>
        <motion.div className="lp-how-track" style={{ x }}>
          {STEPS.map(([t, d, fun], i) => (
            <div className={`lp-step ${i === 4 ? 'red' : ''}`} key={t}>
              <div className="big">{i + 1}</div>
              <h3>{t}</h3>
              <p>{d}</p>
              <em>{fun}</em>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  )
}

function Stat({ big, label, i, red }) {
  return (
    <Reveal i={i}>
      <Tilt className={`lp-stat ${red ? 'red' : ''}`}>
        <div className="v">{big}</div>
        <div className="l">{label}</div>
      </Tilt>
    </Reveal>
  )
}
