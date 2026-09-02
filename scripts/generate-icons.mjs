// Generates public/icons/icon-192.png and icon-512.png with zero dependencies
// (Node's built-in zlib + a hand-rolled PNG encoder). Run: node scripts/generate-icons.mjs
import { deflateSync } from 'node:zlib'
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const outDir = join(root, 'public', 'icons')
mkdirSync(outDir, { recursive: true })

// ---------- minimal PNG encoder ----------
const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n += 1) {
    let c = n
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  return table
})()

function crc32(buf) {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i += 1) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))
  return Buffer.concat([len, body, crc])
}

function encodePNG(width, height, rgba) {
  const stride = 1 + width * 4
  const raw = Buffer.alloc(height * stride)
  for (let y = 0; y < height; y += 1) {
    raw[y * stride] = 0 // filter: none
    rgba.copy(raw, y * stride + 1, y * width * 4, (y + 1) * width * 4)
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // color type: RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

// ---------- icon painter ----------
function roundedRectSDF(px, py, half, radius) {
  const qx = Math.abs(px - half) - (half - radius)
  const qy = Math.abs(py - half) - (half - radius)
  const ox = Math.max(qx, 0)
  const oy = Math.max(qy, 0)
  return Math.hypot(ox, oy) + Math.min(Math.max(qx, qy), 0) - radius
}

function pointInTriangle(px, py, a, b, c) {
  const s1 = (b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0])
  const s2 = (c[0] - b[0]) * (py - b[1]) - (c[1] - b[1]) * (px - b[0])
  const s3 = (a[0] - c[0]) * (py - c[1]) - (a[1] - c[1]) * (px - c[0])
  const hasNeg = s1 < 0 || s2 < 0 || s3 < 0
  const hasPos = s1 > 0 || s2 > 0 || s3 > 0
  return !(hasNeg && hasPos)
}

function drawIcon(size) {
  const px = new Uint8Array(size * size * 4)
  const half = size / 2
  const radius = size * 0.21
  const glow = { x: size * 0.3, y: size * 0.28, r: size * 0.6 }
  const tri = [
    [size * 0.43, size * 0.345],
    [size * 0.43, size * 0.655],
    [size * 0.685, size * 0.5],
  ]
  const SS = 2 // supersampling for anti-aliasing
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let cover = 0
      let tCover = 0
      for (let sy = 0; sy < SS; sy += 1) {
        for (let sx = 0; sx < SS; sx += 1) {
          const px2 = x + (sx + 0.5) / SS
          const py2 = y + (sy + 0.5) / SS
          cover += Math.max(0, Math.min(1, 0.5 - roundedRectSDF(px2, py2, half, radius)))
          if (pointInTriangle(px2, py2, tri[0], tri[1], tri[2])) tCover += 1
        }
      }
      cover /= SS * SS
      tCover /= SS * SS
      // vertical dark gradient background
      const t = y / size
      let r = 44 + (16 - 44) * t
      let g = 45 + (17 - 45) * t
      let b = 56 + (20 - 56) * t
      // accent glow top-left
      const gd = Math.hypot(x - glow.x, y - glow.y) / glow.r
      if (gd < 1) {
        const w2 = (1 - gd) * 0.45
        r += (124 - r) * w2 * 0.4
        g += (95 - g) * w2 * 0.4
        b += (199 - b) * w2 * 0.4
      }
      // white play triangle
      r = r * (1 - tCover) + 255 * tCover
      g = g * (1 - tCover) + 255 * tCover
      b = b * (1 - tCover) + 255 * tCover
      const i = (y * size + x) * 4
      px[i] = Math.round(r)
      px[i + 1] = Math.round(g)
      px[i + 2] = Math.round(b)
      px[i + 3] = Math.round(255 * cover)
    }
  }
  return encodePNG(size, size, Buffer.from(px))
}

export { drawIcon, encodePNG }

// Run directly: node scripts/generate-icons.mjs
import { pathToFileURL } from 'node:url'
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  writeFileSync(join(outDir, 'icon-192.png'), drawIcon(192))
  writeFileSync(join(outDir, 'icon-512.png'), drawIcon(512))
  console.log('Icons written to', outDir)
}