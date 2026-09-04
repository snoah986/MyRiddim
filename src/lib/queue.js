import { writable } from 'svelte/store'

export const queue = writable({ history: [], nowPlaying: null, upNext: [], repeat: 'off', shuffle: false })

const KEY = 'ymt.queue'

export function persistQueue(value) {
  try {
    localStorage.setItem(KEY, JSON.stringify(value))
  } catch { /* storage unavailable (private mode): state just won't survive a refresh */ }
}

export function hydrateQueue() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY))
    if (raw && raw.nowPlaying && Array.isArray(raw.upNext)) {
      return {
        history: Array.isArray(raw.history) ? raw.history : [],
        nowPlaying: raw.nowPlaying,
        upNext: raw.upNext,
        repeat: raw.repeat === 'one' || raw.repeat === 'all' ? raw.repeat : 'off',
        shuffle: !!raw.shuffle,
      }
    }
  } catch { /* corrupt or missing state: start empty */ }
  return null
}

export function seed(tracks, index = 0) {
  const list = tracks || []
  queue.set({ history: [], nowPlaying: list[index] || null, upNext: list.slice(index + 1).map(track => ({ ...track, queueSource: track.queueSource || 'radio' })), repeat: 'off', shuffle: false })
}

export function selectNext() {
  queue.update(value => {
    if (!value.upNext.length) return value
    return { ...value, history: value.nowPlaying ? [...value.history, value.nowPlaying] : value.history, nowPlaying: value.upNext[0], upNext: value.upNext.slice(1) }
  })
}

export function selectPrevious() {
  queue.update(value => {
    if (!value.history.length) return value
    const previous = value.history[value.history.length - 1]
    return { ...value, history: value.history.slice(0, -1), upNext: value.nowPlaying ? [value.nowPlaying, ...value.upNext] : value.upNext, nowPlaying: previous }
  })
}

export function playUpcoming(track) {
  queue.update(value => ({ ...value, history: value.nowPlaying ? [...value.history, value.nowPlaying] : value.history, nowPlaying: track, upNext: value.upNext.filter(item => item.videoId !== track.videoId) }))
}

export function playNext(track) {
  const queued = { ...track, queueSource: 'manual' }
  queue.update(value => ({ ...value, upNext: [queued, ...value.upNext.filter(item => item.videoId !== queued.videoId)] }))
}

export function addToQueue(track) {
  const queued = { ...track, queueSource: 'manual' }
  queue.update(value => ({ ...value, upNext: [...value.upNext.filter(item => item.videoId !== queued.videoId), queued] }))
}

export function appendTracks(tracks) {
  queue.update(value => {
    const known = new Set([value.nowPlaying?.videoId, ...value.upNext.map(item => item.videoId)].filter(Boolean))
    const fresh = (tracks || []).filter(item => item?.videoId && !known.has(item.videoId)).map(item => ({ ...item, queueSource: item.queueSource || 'radio' }))
    if (!fresh.length) return value
    return { ...value, upNext: [...value.upNext, ...fresh] }
  })
}

export function removeUpcoming(videoId) {
  queue.update(value => ({ ...value, upNext: value.upNext.filter(track => track.videoId !== videoId) }))
}

export function clearUpcoming() {
  queue.update(value => ({ ...value, upNext: [] }))
}

// Smart flush removes only tracks explicitly added by the listener. Tracks
// supplied by radio/mix backfill remain in Up Next, so the queue never loses
// its continuous listening path.
export function clearManualUpcoming() {
  queue.update(value => ({
    ...value,
    upNext: value.upNext.filter(track => track?.queueSource !== 'manual'),
  }))
}

export function reorderUpcoming(from, to) {
  queue.update(value => {
    if (from === to || from < 0 || to < 0 || from >= value.upNext.length || to >= value.upNext.length) return value
    const next = [...value.upNext]
    const [item] = next.splice(from, 1)
    next.splice(to, 0, item)
    return { ...value, upNext: next }
  })
}

export function toggleShuffle() {
  queue.update(value => {
    const upNext = [...value.upNext]
    for (let i = upNext.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[upNext[i], upNext[j]] = [upNext[j], upNext[i]]
    }
    return { ...value, shuffle: !value.shuffle, upNext }
  })
}

export function cycleRepeat() {
  queue.update(value => ({ ...value, repeat: value.repeat === 'off' ? 'all' : value.repeat === 'all' ? 'one' : 'off' }))
}