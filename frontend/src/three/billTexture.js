import * as THREE from 'three'

const SELLERS = ['SAI CABLES', 'SHREE METALS', 'KAVERI TILES', 'MEHTA TRADERS', 'BHARATH CEMENT', 'VINAYAKA PIPES', 'RAMESH TRADERS', 'OM ELECTRICALS']
const cache = new Map()

/** Draws a small invoice onto a canvas: black header, line items, totals, sometimes a QR, sometimes a red stamp. */
export function billTexture(i) {
  const key = i % 16
  if (cache.has(key)) return cache.get(key)
  const W = 256, H = 340
  const c = document.createElement('canvas')
  c.width = W; c.height = H
  const g = c.getContext('2d')
  const rnd = mulberry(key + 7)

  g.fillStyle = '#F7F5F0'
  g.fillRect(0, 0, W, H)
  g.fillStyle = '#0B0B0B'
  g.fillRect(0, 0, W, 46)
  g.fillStyle = '#FFFFFF'
  g.font = 'bold 17px Arial'
  g.fillText(SELLERS[key % SELLERS.length], 14, 29)
  g.fillStyle = '#0B0B0B'
  g.font = 'bold 13px Arial'
  g.fillText('TAX INVOICE', 14, 70)
  g.font = '10px monospace'
  g.fillText(`GSTIN 29${'ABCDE'.slice(0, 3)}${Math.floor(rnd() * 9000 + 1000)}Z${key}`, 14, 88)
  g.fillText(`INV-${Math.floor(rnd() * 9000 + 1000)}   ${Math.floor(rnd() * 27 + 1)}/10/2026`, 14, 103)

  g.strokeStyle = '#0B0B0B'
  g.lineWidth = 1
  g.strokeRect(14, 116, W - 28, 108)
  for (let r = 0; r < 4; r++) {
    const y = 136 + r * 24
    g.fillStyle = '#9A9A9A'
    g.fillRect(22, y - 6, 80 + rnd() * 50, 6)
    g.fillStyle = '#0B0B0B'
    g.fillRect(W - 70, y - 6, 40, 6)
  }
  g.fillStyle = '#0B0B0B'
  g.font = 'bold 12px Arial'
  g.fillText('CGST 9%', 120, 248)
  g.fillText('SGST 9%', 120, 266)
  g.font = 'bold 15px Arial'
  g.fillText(`₹${Math.floor(rnd() * 90 + 10)},${Math.floor(rnd() * 900 + 100)}`, 120, 292)

  if (key % 3 === 0) { // e-invoice QR
    g.fillStyle = '#0B0B0B'
    for (let y = 0; y < 9; y++) for (let x = 0; x < 9; x++) if (rnd() > 0.5 || (x < 3 && y < 3)) g.fillRect(18 + x * 9, 238 + y * 9, 8, 8)
  }
  if (key % 4 === 1) { // red stamp
    g.save()
    g.translate(W - 62, 300)
    g.rotate(-0.35)
    g.strokeStyle = '#E10600'
    g.lineWidth = 3
    g.strokeRect(-46, -16, 92, 32)
    g.fillStyle = '#E10600'
    g.font = 'bold 14px Arial'
    g.textAlign = 'center'
    g.fillText('GST ✓', 0, 5)
    g.restore()
  }
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  cache.set(key, tex)
  return tex
}

export function stampTexture() {
  if (cache.has('stamp')) return cache.get('stamp')
  const c = document.createElement('canvas')
  c.width = c.height = 256
  const g = c.getContext('2d')
  g.fillStyle = '#E10600'
  g.fillRect(0, 0, 256, 256)
  g.strokeStyle = '#FFFFFF'
  g.lineWidth = 8
  g.beginPath(); g.arc(128, 128, 104, 0, Math.PI * 2); g.stroke()
  g.lineWidth = 3
  g.beginPath(); g.arc(128, 128, 88, 0, Math.PI * 2); g.stroke()
  g.fillStyle = '#FFFFFF'
  g.font = 'bold 34px Arial'
  g.textAlign = 'center'
  g.fillText('APPROVED', 128, 140)
  g.font = 'bold 14px Arial'
  g.fillText('BY A HUMAN', 128, 168)
  g.fillText('KARSAATHI', 128, 100)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  cache.set('stamp', tex)
  return tex
}

export function mulberry(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
