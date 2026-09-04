const PLACEHOLDER_TITLES = new Set(['unknown', 'unknown title', 'unknown audio', 'untitled', ''])
const PLACEHOLDER_ARTISTS = new Set(['unknown', 'unknown artist', 'unknown audio', 'untitled', ''])

function textValue(value) {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (!value || typeof value !== 'object') return ''
  if (value.text != null) return textValue(value.text)
  if (value.simpleText != null) return textValue(value.simpleText)
  if (Array.isArray(value.runs)) return value.runs.map(textValue).join(' ')
  for (const key of ['name', 'title', 'label']) {
    if (value[key] != null) return textValue(value[key])
  }
  return ''
}

function artistValue(value) {
  if (Array.isArray(value)) {
    for (const item of value) {
      const artist = artistValue(item)
      if (artist) return artist
    }
    return ''
  }
  return textValue(value)
}

function artworkValue(track) {
  const value = track?.thumbnail || track?.artwork || track?.thumbnails
  if (typeof value === 'string') return value.trim()
  if (Array.isArray(value)) {
    for (const item of [...value].reverse()) {
      const artwork = artworkValue({ thumbnail: item })
      if (artwork) return artwork
    }
    return ''
  }
  if (value && typeof value === 'object') return String(value.url || '').trim()
  return ''
}

function cleanText(value) {
  return textValue(value).replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
}

/**
 * Normalize provider/remote payloads before they can reach a shelf or queue.
 * Invalid metadata is discarded rather than rendered as an "Unknown" card.
 */
export function normalizeTrack(track) {
  if (!track || typeof track !== 'object') return null

  const title = cleanText(track.title) || cleanText(track.name) || cleanText(track.headline)
  const artist = cleanText(artistValue(track.artists || track.artist || track.author))
  const videoId = cleanText(track.videoId || track.id || track.track_id)
  const thumbnail = artworkValue(track)
  if (!videoId || !title || !artist || PLACEHOLDER_TITLES.has(title.toLowerCase()) || PLACEHOLDER_ARTISTS.has(artist.toLowerCase()) || !thumbnail) return null

  return {
    ...track,
    id: videoId,
    videoId,
    title,
    artist,
    thumbnail,
    artwork: cleanText(track.artwork) || thumbnail,
    duration: track.duration ?? track.duration_seconds ?? track.length ?? track.lengthSeconds ?? 0,
  }
}

export function normalizePlayable(track) {
  const normalized = normalizeTrack(track)
  if (!normalized) {
    console.warn('Cannot play track: missing usable title/id/artwork', track)
    return null
  }
  return normalized
}

export function trackKey(track) {
  return track?.videoId || track?.id || ''
}
