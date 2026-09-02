// Generates the icon set Tauri requires (src-tauri/icons/) with zero dependencies:
// 32x32.png, 128x128.png, 128x128@2x.png, icon.png and icon.ico (PNG-in-ICO, which
// Windows accepts). Run: node scripts/generate-tauri-icons.mjs
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

writeFileSync(join(outDir, '32x32.png'), drawIcon(32))
writeFileSync(join(outDir, '128x128.png'), drawIcon(128))
writeFileSync(join(outDir, '128x128@2x.png'), drawIcon(256))
writeFileSync(join(outDir, 'icon.png'), drawIcon(512))
writeFileSync(join(outDir, 'icon.ico'), encodeICO(drawIcon(256)))
console.log('Tauri icons written to', outDir)