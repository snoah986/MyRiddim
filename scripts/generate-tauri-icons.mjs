// Generates the icon set Tauri requires (src-tauri/icons/) with zero dependencies:
// 32x32.png, 128x128.png, 128x128@2x.png, icon.png, icon.ico (PNG-in-ICO, which
// Windows accepts), and icon.icns (PNG-based chunks, which macOS accepts).
// Run: node scripts/generate-tauri-icons.mjs
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { drawIcon, encodePNG } from './generate-icons.mjs'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const outDir = join(root, 'src-tauri', 'icons')
mkdirSync(outDir, { recursive: true })

// Windows .ico container with a single PNG-compressed 256x256 entry.
function encodeICO(png) {
  const header = Buffer.alloc(6)
  header.writeUInt16LE(0, 0) // reserved
  header.writeUInt16LE(1, 2) // type: icon
  header.writeUInt16LE(1, 4) // count
  const entry = Buffer.alloc(16)
  entry[0] = 0   // width 256 (0 means 256)
  entry[1] = 0   // height 256
  entry[2] = 0   // palette
  entry[3] = 0   // reserved
  entry.writeUInt16LE(1, 4)    // planes
  entry.writeUInt16LE(32, 6)   // bit count
  entry.writeUInt32LE(png.length, 8)
  entry.writeUInt32LE(22, 12)  // offset (header + entry)
  return Buffer.concat([header, entry, png])
}

// macOS .icns container. Modern macOS and Tauri's bundler accept PNG-based
// chunks (ic07=128, ic08=256, ic09=512, ic10=1024) with no legacy ARGB data.
function encodeICNS(entries) {
  const chunks = entries.map(([type, png]) => {
    const body = Buffer.concat([Buffer.from(type, 'ascii'), Buffer.alloc(4), png])
    body.writeUInt32BE(body.length, 4)
    return body
  })
  const header = Buffer.concat([Buffer.from('icns', 'ascii'), Buffer.alloc(4)])
  header.writeUInt32BE(8 + chunks.reduce((sum, chunk) => sum + chunk.length, 0), 4)
  return Buffer.concat([header, ...chunks])
}

writeFileSync(join(outDir, '32x32.png'), drawIcon(32))
writeFileSync(join(outDir, '128x128.png'), drawIcon(128))
writeFileSync(join(outDir, '128x128@2x.png'), drawIcon(256))
writeFileSync(join(outDir, 'icon.png'), drawIcon(512))
writeFileSync(join(outDir, 'icon.ico'), encodeICO(drawIcon(256)))
writeFileSync(join(outDir, 'icon.icns'), encodeICNS([
  ['ic07', drawIcon(128)],
  ['ic08', drawIcon(256)],
  ['ic09', drawIcon(512)],
  ['ic10', drawIcon(1024)],
]))
console.log('Tauri icons written to', outDir)