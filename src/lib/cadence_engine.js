// Model-free karaoke cadence fallback. It uses only the supplied lyric text and
// line timestamps; no audio decoding, ML model, or large language data is used.
const VOWELS = /[aeiouy]+/gi

export function estimateSyllables(word) {
  const token = String(word || '').replace(/[^\w']/gu, '')
  if (!token) return 0
  const groups = token.match(VOWELS)?.length || Math.max(1, Math.round(token.length / 3))
  const silentE = /e$/i.test(token) && groups > 1 && !/(le|ye)$/i.test(token)
  return Math.max(1, groups - (silentE ? 1 : 0))
}

export function buildCadenceLines(rawLines, duration = 0, genreHint = '') {
  if (!Array.isArray(rawLines)) return []
  const source = rawLines.slice(0, 400).map((line, index) => {
    const start = Number(line?.time ?? line?.start)
    if (!Number.isFinite(start) || !line?.text) return null
    const next = Number(rawLines[index + 1]?.time ?? rawLines[index + 1]?.start)
    const suppliedWords = Array.isArray(line.words)
      ? line.words.map(word => ({
        text: String(word?.text ?? word?.word ?? '').trim(),
        start: Number(word?.start),
        end: Number(word?.end),
      })).filter(word => word.text && Number.isFinite(word.start) && Number.isFinite(word.end))
      : []
    return {
      start: Math.max(0, start),
      end: Number.isFinite(next) ? next : null,
      text: String(line.text).trim(),
      suppliedWords,
    }
  }).filter(Boolean)
  if (!source.length) return []

  const windows = source.map((line, index) => {
    const fallbackEnd = Number(duration) || line.start + 4
    const end = Math.max(line.start + 0.35, line.end ?? fallbackEnd)
    const words = line.suppliedWords.length
      ? line.suppliedWords
      : line.text.split(/\s+/).filter(Boolean).map(text => ({ text, syllables: estimateSyllables(text) }))
    const syllableCount = Math.max(1, words.reduce((sum, word) => sum + (word.syllables || estimateSyllables(word.text)), 0))
    return { ...line, end, words, syllableCount }
  })
  const typical = windows.reduce((sum, line) => sum + line.syllableCount / Math.max(.35, line.end - line.start), 0) / windows.length
  const hint = String(genreHint).toLowerCase()
  const target = /rap|drill|hip[ -]?hop/.test(hint) ? Math.max(typical, 4.5) : typical

  return windows.map(line => {
    const span = Math.max(.35, line.end - line.start)
    const hasSuppliedTiming = line.suppliedWords.length > 0
    const sps = line.syllableCount / span
    const density = Math.max(.65, Math.min(1.25, sps / Math.max(1, target)))
    const usableStart = line.start + Math.min(.08, span * .02)
    const usableSpan = Math.max(.2, span - (usableStart - line.start))
    let cursor = usableStart
    const words = hasSuppliedTiming
      ? line.words.map(word => ({
        text: word.text,
        start: Number(Math.max(line.start, word.start).toFixed(3)),
        end: Number(Math.max(word.start + .04, word.end).toFixed(3)),
      }))
      : line.words.map(word => {
        const wordEnd = Math.min(line.end, cursor + usableSpan * (word.syllables / line.syllableCount) * density)
        const result = { text: word.text, start: Number(cursor.toFixed(3)), end: Number(Math.max(cursor + .04, wordEnd).toFixed(3)) }
        cursor = wordEnd
        return result
      })
    return { start: Number(line.start.toFixed(3)), end: Number(line.end.toFixed(3)), text: line.text, words, sps: Number(sps.toFixed(2)), cadence: sps >= 5.5 ? 'rapid' : sps <= 2.5 ? 'melodic' : 'flow' }
  })
}
