import { useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { billTexture, mulberry, stampTexture } from './billTexture'

/*
  The story in four acts, driven by progress p (0..1). Timed so each act completes
  as its text card reaches the centre of the screen:
    0.00-0.30  chaos: a bag of bills swirling
    0.30-0.50  sorted: three piles (sales, purchases, needs review)
    0.56-0.74  merged: one return
    0.78-0.90  stamped: red seal drops; camera orbits to the end
*/
const seg = (p, a, b) => THREE.MathUtils.smoothstep(p, a, b)
const v = new THREE.Vector3()
const q = new THREE.Quaternion()
const e = new THREE.Euler()

function Bills({ count, progress, auto }) {
  const group = useRef()
  const meshes = useRef([])
  const shown = useRef(0)
  const data = useMemo(() => {
    const r = mulberry(11)
    let kSale = 0, kBuy = 0, kRev = 0
    return Array.from({ length: count }, (_, i) => {
      const pile = i % 9 === 4 ? 2 : i % 2
      const k = pile === 0 ? kSale++ : pile === 1 ? kBuy++ : kRev++
      const th = r() * Math.PI * 2, ph = Math.acos(2 * r() - 1), rad = 2.6 + r() * 3.2
      return {
        tex: billTexture(i),
        chaos: new THREE.Vector3(rad * Math.sin(ph) * Math.cos(th), rad * Math.cos(ph) * 0.7, rad * Math.sin(ph) * Math.sin(th)),
        chaosRot: new THREE.Euler(r() * 6, r() * 6, r() * 6),
        spin: (r() - 0.5) * 0.8,
        sorted: new THREE.Vector3((pile - 1) * 2.4, -1.1 + k * 0.07, (r() - 0.5) * 0.08),
        merged: new THREE.Vector3((r() - 0.5) * 0.06, -1.1 + i * 0.036, (r() - 0.5) * 0.06),
        flat: new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, (r() - 0.5) * 0.25)),
        review: pile === 2,
      }
    })
  }, [count])

  useFrame((state, dt) => {
    const t = state.clock.elapsedTime
    const target = auto ? (Math.sin(t * 0.35 - 1.6) + 1) / 2 * 0.78 : progress.current
    shown.current = THREE.MathUtils.damp(shown.current, target, 3.2, dt)
    const p = shown.current
    const a = seg(p, 0.3, 0.5), b = seg(p, 0.56, 0.74)
    group.current.rotation.y = (1 - a) * t * 0.12 + (auto ? 0 : seg(p, 0.85, 1) * Math.PI * 0.35)
    data.forEach((d, i) => {
      const m = meshes.current[i]
      if (!m) return
      // position: chaos -> sorted -> merged
      v.copy(d.chaos).applyAxisAngle(THREE.Object3D.DEFAULT_UP, t * d.spin * 0.15)
      v.y += Math.sin(t * 0.8 + i) * 0.12
      v.lerp(d.sorted, a).lerp(d.merged, b)
      m.position.copy(v)
      // rotation: tumbling -> lying flat
      e.set(d.chaosRot.x + t * d.spin, d.chaosRot.y + t * d.spin * 0.7, d.chaosRot.z)
      q.setFromEuler(e)
      m.quaternion.copy(q).slerp(d.flat, Math.max(a, b))
      // the review pile glows red while sorted
      const glow = d.review ? a * (1 - b) : 0
      m.material[4].emissive.setRGB(glow * 0.9, 0, 0)
    })
  })

  const edge = useMemo(() => new THREE.MeshStandardMaterial({ color: '#EDEAE3', roughness: 0.9 }), [])
  return (
    <group ref={group}>
      {data.map((d, i) => (
        <mesh key={i} ref={(el) => (meshes.current[i] = el)}
          material={[edge, edge, edge, edge,
            new THREE.MeshStandardMaterial({ map: d.tex, roughness: 0.75, emissive: '#000000' }),
            new THREE.MeshStandardMaterial({ color: '#E8E5DE', roughness: 0.9 })]}>
          <boxGeometry args={[1.05, 1.4, 0.012]} />
        </mesh>
      ))}
    </group>
  )
}

function Stamp({ progress, count, auto }) {
  const ref = useRef()
  const shown = useRef(0)
  const mats = useMemo(() => [
    new THREE.MeshStandardMaterial({ color: '#B80500', roughness: 0.4, metalness: 0.2 }),
    new THREE.MeshStandardMaterial({ map: stampTexture(), roughness: 0.5 }),
    new THREE.MeshStandardMaterial({ color: '#B80500' }),
  ], [])
  useFrame((state, dt) => {
    const target = auto ? 0 : progress.current
    shown.current = THREE.MathUtils.damp(shown.current, target, 3.2, dt)
    const s = seg(shown.current, 0.78, 0.9)
    const top = -1.1 + count * 0.036 + 0.1
    ref.current.position.y = THREE.MathUtils.lerp(5, top, s)
    ref.current.rotation.y = (1 - s) * 4 + Math.PI / 2 // texture reads upright toward the camera when landed
    const squash = s > 0.98 ? 1 - Math.sin((shown.current - 0.9) * 40) * 0.04 : 1
    ref.current.scale.set(1, squash, 1)
    ref.current.visible = shown.current > 0.7
  })
  return (
    <mesh ref={ref} material={mats} position={[0, 5, 0]}>
      <cylinderGeometry args={[0.75, 0.75, 0.16, 64]} />
    </mesh>
  )
}

function Rig({ progress, auto }) {
  const { camera, pointer } = useThree()
  const shown = useRef(0)
  const look = useMemo(() => new THREE.Vector3(), [])
  useFrame((_, dt) => {
    const target = auto ? 0.3 : progress.current
    shown.current = THREE.MathUtils.damp(shown.current, target, 2.6, dt)
    const p = shown.current
    const a = seg(p, 0.3, 0.5), b = seg(p, 0.56, 0.76), c = seg(p, 0.85, 1)
    const z = THREE.MathUtils.lerp(THREE.MathUtils.lerp(10, 7.2, a), 5.2, b) - c * 0.8
    const y = THREE.MathUtils.lerp(THREE.MathUtils.lerp(0.4, 3, a), 3.6, b)
    // pan so the scene sits opposite the text card: right card -> scene left, and back
    const xOff = auto ? 0 : (1.9 * a - 3.8 * b + 3.8 * c) * (innerWidth > 900 ? 1 : 0)
    camera.position.lerp(v.set(xOff + pointer.x * 0.6, y + pointer.y * 0.3, z), 0.08)
    look.set(xOff, THREE.MathUtils.lerp(0, -0.6, a), 0)
    camera.lookAt(look)
  })
  return null
}

export default function BillScene({ progress, count = 34, auto = false, className }) {
  const fallback = useRef(0)
  const p = progress || fallback
  return (
    <Canvas className={className} dpr={[1, 1.75]} camera={{ position: [0, 0.4, 10], fov: 42 }} gl={{ antialias: true, alpha: true }}>
      <fog attach="fog" args={['#0A0A0A', 9, 18]} />
      <ambientLight intensity={0.9} />
      <directionalLight position={[3, 6, 5]} intensity={1.6} />
      <pointLight position={[-4, -1, 3]} intensity={30} color="#E10600" distance={12} />
      <pointLight position={[4, 2, -3]} intensity={12} color="#FFFFFF" distance={12} />
      <Bills count={count} progress={p} auto={auto} />
      {!auto && <Stamp progress={p} count={count} />}
      <Rig progress={p} auto={auto} />
    </Canvas>
  )
}
