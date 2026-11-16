import { useEffect, useRef, useState } from 'react'
import Lenis from 'lenis'
import { animate, motion, useInView, useMotionValue, useSpring, useTransform } from 'framer-motion'

export const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** Smooth scrolling. Calls onScroll(progress 0..1, lenis). Off for reduced-motion users. */
export function useLenis(onScroll) {
  const cb = useRef(onScroll)
  cb.current = onScroll
  useEffect(() => {
    if (reduced()) {
      const h = () => cb.current?.(window.scrollY / Math.max(1, document.documentElement.scrollHeight - innerHeight))
      window.addEventListener('scroll', h, { passive: true })
      h()
      return () => window.removeEventListener('scroll', h)
    }
    const lenis = new Lenis({ lerp: 0.085, wheelMultiplier: 0.9, smoothWheel: true })
    lenis.on('scroll', (l) => cb.current?.(l.progress || 0, l))
    let id
    const raf = (t) => { lenis.raf(t); id = requestAnimationFrame(raf) }
    id = requestAnimationFrame(raf)
    window.__lenis = lenis
    return () => { cancelAnimationFrame(id); lenis.destroy(); window.__lenis = null }
  }, [])
}

/** Card that tilts toward the pointer in 3D, with a moving highlight. */
export function Tilt({ children, className = '', max = 7, as: As = 'div', ...rest }) {
  const ref = useRef(null)
  const rx = useSpring(0, { stiffness: 220, damping: 18 })
  const ry = useSpring(0, { stiffness: 220, damping: 18 })
  const gx = useMotionValue(50), gy = useMotionValue(50)
  const bg = useTransform([gx, gy], ([x, y]) => `radial-gradient(420px circle at ${x}% ${y}%, rgba(255,255,255,.55), transparent 45%)`)
  const M = motion[As] || motion.div
  const move = (e) => {
    if (reduced()) return
    const r = ref.current.getBoundingClientRect()
    const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height
    ry.set((px - 0.5) * max * 2); rx.set(-(py - 0.5) * max * 2)
    gx.set(px * 100); gy.set(py * 100)
  }
  const leave = () => { rx.set(0); ry.set(0) }
  return (
    <M ref={ref} className={`tilt ${className}`} onMouseMove={move} onMouseLeave={leave}
      style={{ rotateX: rx, rotateY: ry, transformPerspective: 900 }} {...rest}>
      {children}
      <motion.span className="tilt-shine" style={{ background: bg }} aria-hidden />
    </M>
  )
}

/** Number that counts up when scrolled into view. */
export function CountUp({ to, format = (n) => Math.round(n).toLocaleString('en-IN'), duration = 1.4 }) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-40px' })
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (!inView) return
    if (reduced() || !to) { setVal(to || 0); return }
    const c = animate(0, to, { duration, ease: [0.16, 1, 0.3, 1], onUpdate: setVal })
    return () => c.stop()
  }, [inView, to, duration])
  return <span ref={ref}>{format(Number.isFinite(val) ? val : to)}</span>
}

/** Fade + rise into view, optionally staggered by index. */
export function Reveal({ children, i = 0, y = 28, className, as = 'div' }) {
  const M = motion[as] || motion.div
  return (
    <M className={className} initial={{ opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }} transition={{ duration: 0.7, delay: i * 0.07, ease: [0.16, 1, 0.3, 1] }}>
      {children}
    </M>
  )
}

/** Splits a line into words that slide up from a mask. The parent watches the viewport
 *  (the words themselves start clipped, which IntersectionObserver treats as never visible). */
const wordV = { hidden: { y: '110%' }, show: (c) => ({ y: '0%', transition: { duration: 0.9, delay: c, ease: [0.16, 1, 0.3, 1] } }) }
export function SplitText({ text, className, delay = 0 }) {
  return (
    <motion.span className={`split ${className || ''}`} aria-label={text} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.2 }}>
      {text.split(' ').map((w, i) => (
        <span className="split-mask" key={i} aria-hidden>
          <motion.span className="split-word" variants={wordV} custom={delay + i * 0.06}>{w}&nbsp;</motion.span>
        </span>
      ))}
    </motion.span>
  )
}

/** Red dot cursor that grows over links and buttons (pointer devices only). */
export function Cursor() {
  const x = useSpring(-100, { stiffness: 500, damping: 40 })
  const y = useSpring(-100, { stiffness: 500, damping: 40 })
  const [big, setBig] = useState(false)
  useEffect(() => {
    if (!window.matchMedia('(pointer: fine)').matches) return
    const m = (e) => {
      x.set(e.clientX); y.set(e.clientY)
      setBig(!!e.target.closest?.('a,button,[data-cursor]'))
    }
    window.addEventListener('pointermove', m)
    return () => window.removeEventListener('pointermove', m)
  }, [x, y])
  return <motion.div className={`cursor ${big ? 'big' : ''}`} style={{ x, y }} aria-hidden />
}

/** Button that leans toward the pointer. */
export function Magnetic({ children, className = '', ...rest }) {
  const x = useSpring(0, { stiffness: 250, damping: 15 })
  const y = useSpring(0, { stiffness: 250, damping: 15 })
  return (
    <motion.button className={className} style={{ x, y }} {...rest}
      onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); x.set((e.clientX - r.left - r.width / 2) * 0.3); y.set((e.clientY - r.top - r.height / 2) * 0.35) }}
      onMouseLeave={() => { x.set(0); y.set(0) }}>
      {children}
    </motion.button>
  )
}

/** Cycles through lines of text with a soft vertical swap. */
export function Rotator({ lines, every = 3200, className }) {
  const [i, setI] = useState(0)
  useEffect(() => { const id = setInterval(() => setI((x) => (x + 1) % lines.length), every); return () => clearInterval(id) }, [lines.length, every])
  return (
    <span className={`rotator ${className || ''}`}>
      <motion.span key={i} initial={{ y: 14, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.45 }}>{lines[i]}</motion.span>
    </span>
  )
}
