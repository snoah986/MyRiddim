import { writable } from 'svelte/store'

const KEY = 'ymt.settings'
const DEFAULTS = {
  reduceMotion: false,
  quality: 'high',
  cacheLimitMb: 1024,
  crossfade: false,
  crossfadeDuration: 4,
  autoRadio: true,
  instantQueueFlush: false,
  scrobble: true,
  volumeNormalize: false,
  dynamicAmbient: true,
  shellLayout: 'sidebar',
}

function load() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '{}')
    return { ...DEFAULTS, ...raw }
  } catch {
    return { ...DEFAULTS }
  }
}

export const settings = writable(load())

settings.subscribe((value) => {
  try {
    localStorage.setItem(KEY, JSON.stringify(value))
  } catch { /* private mode: settings just won't persist */ }
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('reduce-motion', value.reduceMotion)
  }
})

export function updateSetting(key, value) {
  settings.update((current) => ({ ...current, [key]: value }))
}