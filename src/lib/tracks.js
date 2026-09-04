export function normalizePlayable(track) {
  const videoId = track?.videoId || track?.id
  if (!videoId) {
    console.warn('Cannot play track: missing videoId/id', track)
    return null
  }
  return { ...track, id: videoId, videoId }
}

export function trackKey(track) {
  return track?.videoId || track?.id || ''
}
