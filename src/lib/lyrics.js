export function cleanTrackMeta(title, artist) {
  const cleanTitle = String(title ?? '')
    .replace(/\s*[\(\[](?:feat\.|ft\.|with).*?[\)\]]/gi, '')
    .replace(/\s*[\(\[](?:(?:official\s*(?:music\s*)?(?:video|audio))|visualizer|lyrics?|hd|4k|remastered).*?[\)\]]/gi, '')
    .replace(/\s+-\s+.*$/, '')
    .replace(/\s+/g, ' ')
    .trim()

  const cleanArtist = String(artist ?? '')
    .replace(/\s*-\s*Topic(?=\s*(?:,|$))/i, '')
    .replace(/,.*$/, '')
    .replace(/\s+/g, ' ')
    .trim()

  return { cleanTitle, cleanArtist }
}

export function applyKaraokeOffset(rawLines, offsetSeconds, needsSync = false) {
  const lines = Array.isArray(rawLines) ? rawLines : []
  const offset = Number(offsetSeconds) || 0
  if (offset === 0) {
    return needsSync
      ? [{ start: 0, end: 0.5, text: '♪ [Intro in progress — Tap to sync beat] ♪', words: [], isPrompt: true }, ...lines]
      : lines
  }

  const shifted = lines.map(line => ({
    ...line,
    start: Number((Number(line.start) + offset).toFixed(3)),
    end: Number((Number(line.end) + offset).toFixed(3)),
    words: (line.words || []).map(word => ({
      ...word,
      start: Number((Number(word.start) + offset).toFixed(3)),
      end: Number((Number(word.end) + offset).toFixed(3))
    }))
  }))

  return [
    ...(offset > 0 ? [{ start: 0, end: offset, text: '♪ [Cinematic Intro] ♪', words: [], isIntro: true }] : []),
    ...shifted
  ]
}

export function applyVideoOffset(rawLyrics, offsetSeconds, needsSync = false) {
  const lines = Array.isArray(rawLyrics) ? rawLyrics : []
  const offset = Number(offsetSeconds) || 0
  if (offset === 0) {
    return needsSync
      ? [{ time: 0, text: '♪ [Intro in progress — Tap to sync beat] ♪', isPrompt: true }, ...lines]
      : lines
  }

  const shifted = lines.map(line => ({
    ...line,
    time: Number((Number(line.time) + offset).toFixed(2))
  }))

  return [
    ...(offset > 0 ? [{ time: 0, text: '♪ [Cinematic Intro] ♪', isIntro: true, duration: offset }] : []),
    ...shifted
  ]
}
