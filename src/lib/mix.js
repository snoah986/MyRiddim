import { normalizePlayable } from './tracks.js'

export function createMixController({ fetcher, onStart, onError }) {
  let requestId = 0
  let abortController = null

  async function start(track) {
    const seed = normalizePlayable(track)
    if (!seed) return false

    const currentRequest = ++requestId
    abortController?.abort()
    abortController = new AbortController()
    onStart?.(seed)

    try {
      const response = await fetcher(`/api/mix/${encodeURIComponent(seed.videoId)}`, {
        signal: abortController.signal,
      })
      const data = await response.json().catch(() => ({}))
      if (currentRequest !== requestId) return false
      if (!response.ok || data.error) throw Error(data.error || 'Could not create radio mix')

      const seen = new Set()
      const tracks = [seed, ...(Array.isArray(data.tracks) ? data.tracks : [])]
        .map(normalizePlayable)
        .filter(item => item && !seen.has(item.videoId) && (seen.add(item.videoId), true))
      if (!tracks.length) throw Error('No radio tracks found')
      return tracks
    } catch (error) {
      if (error?.name === 'AbortError' || currentRequest !== requestId) return false
      onError?.(error)
      return false
    }
  }

  function cancel() {
    requestId += 1
    abortController?.abort()
    abortController = null
  }

  return { start, cancel }
}
