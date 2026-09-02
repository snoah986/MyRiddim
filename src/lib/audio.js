// Web Audio playback engine: two <audio> elements routed through GainNodes so the
// next track can be preloaded and crossfaded in, plus an AnalyserNode for the
// Theatre Mode visualizer. Exposed as a drop-in proxy that mirrors the old
// single-<audio> API used by App.svelte.
const FADE = 3.5        // default crossfade duration (seconds)
const PRELOAD_WINDOW = 15 // start buffering the next track this close to the end

let ctx = null
let master = null
let normGain = null      // volume-normalization gain (before the analyser)
let analyser = null
let fadeSeconds = FADE   // user-configurable crossfade duration (0 = disabled)
let normalizeOn = false
let normalizeTimer = null
const els = { A: { el: null, gain: null }, B: { el: null, gain: null } }
let live = 'A'          // element whose timeline/events are exposed to the UI
let volume = 1
let pendingSrc = null   // next track stream URL (from preload)
let preloaded = false   // pendingSrc applied to els.B
let fading = false
let fadeTimer = null
let gapFilled = false   // true right after a crossfade: the next track is already playing
const dataset = { track: null }
const handlers = { play: [], pause: [], timeupdate: [], loadedmetadata: [], ended: [], error: [] }

const otherOf = which => (which === 'A' ? 'B' : 'A')
const isLive = el => els[live].el === el
const emit = type => { for (const fn of handlers[type] || []) fn() }

function ensure() {
  if (ctx) return
  ctx = new (window.AudioContext || window.webkitAudioContext)()
  master = ctx.createGain()
  master.gain.value = volume
  normGain = ctx.createGain()
  normGain.gain.value = 1
  analyser = ctx.createAnalyser()
  analyser.fftSize = 256
  analyser.smoothingTimeConstant = 0.82
  master.connect(normGain)
  normGain.connect(analyser)
  analyser.connect(ctx.destination)
  for (const key of ['A', 'B']) {
    const el = new Audio()
    const gain = ctx.createGain()
    gain.gain.value = key === 'A' ? volume : 0
    ctx.createMediaElementSource(el).connect(gain)
    gain.connect(master)
    els[key].el = el
    els[key].gain = gain
    el.addEventListener('play', () => { if (isLive(el)) emit('play') })
    el.addEventListener('pause', () => { if (isLive(el)) emit('pause') })
    el.addEventListener('timeupdate', onTimeUpdate)
    el.addEventListener('loadedmetadata', () => { if (isLive(el)) emit('loadedmetadata') })
    el.addEventListener('ended', () => { if (isLive(el)) emit('ended') })
    el.addEventListener('error', () => { if (isLive(el)) emit('error') })
  }
}

// Point the engine at `which` element playing `url` (or keep its current src when url is undefined).
function resetTo(which, url) {
  ensure()
  if (fadeTimer) { clearTimeout(fadeTimer); fadeTimer = null }
  fading = false
  pendingSrc = null
  preloaded = false
  gapFilled = false
  live = which
  const other = otherOf(which)
  els[other].el.pause()
  els[other].el.removeAttribute('src')
  els[other].el.load()
  for (const key of ['A', 'B']) {
    els[key].gain.gain.cancelScheduledValues(ctx.currentTime)
    els[key].gain.gain.setValueAtTime(key === which ? volume : 0, ctx.currentTime)
  }
  if (url !== undefined) els[which].el.src = url
}

function abortFade() {
  if (!fading) return
  fading = false
  if (fadeTimer) { clearTimeout(fadeTimer); fadeTimer = null }
  const now = ctx.currentTime
  const other = otherOf(live)
  els[live].gain.gain.cancelScheduledValues(now)
  els[live].gain.gain.setValueAtTime(volume, now)
  els[other].gain.gain.cancelScheduledValues(now)
  els[other].gain.gain.setValueAtTime(0, now)
  els[other].el.pause()
  els[other].el.removeAttribute('src')
  els[other].el.load()
  preloaded = false
}

function startFade() {
  if (fading || !preloaded || !pendingSrc || !els.B.el.src) return
  fading = true
  const now = ctx.currentTime
  els.A.gain.gain.cancelScheduledValues(now)
  els.A.gain.gain.setValueAtTime(els.A.gain.gain.value, now)
  els.A.gain.gain.linearRampToValueAtTime(0, now + fadeSeconds)
  els.B.gain.gain.cancelScheduledValues(now)
  els.B.gain.gain.setValueAtTime(0, now)
  els.B.gain.gain.linearRampToValueAtTime(volume, now + fadeSeconds)
  els.B.el.play().catch(() => abortFade())
  fadeTimer = setTimeout(() => {
    if (!fading) return
    fading = false
    gapFilled = true
    live = 'B'
    els.A.el.pause()
    els.A.el.removeAttribute('src')
    els.A.el.load()
    els.A.gain.gain.cancelScheduledValues(ctx.currentTime)
    els.A.gain.gain.setValueAtTime(0, ctx.currentTime)
    els.B.gain.gain.cancelScheduledValues(ctx.currentTime)
    els.B.gain.gain.setValueAtTime(volume, ctx.currentTime)
    pendingSrc = null
    preloaded = false
    // The old element never reaches its natural end, so synthesize it: the app
    // advances the queue, and its playTrack() re-assigns the same URL, which the
    // engine adopts without restarting (gapless).
    emit('ended')
  }, fadeSeconds * 1000)
}

// Track-loudness normalization: every 250ms, compare the analyser's RMS level
// to a target and smoothly nudge the normalization gain toward it (slow attack/
// release so it never pumps). Disabling restores unity gain.
function setNormalize(enabled) {
  normalizeOn = !!enabled
  if (!ctx) return
  if (normalizeOn) {
    if (normalizeTimer) return
    const data = new Uint8Array(analyser.fftSize)
    normalizeTimer = setInterval(() => {
      analyser.getByteTimeDomainData(data)
      let sum = 0
      for (let i = 0; i < data.length; i += 1) {
        const v = (data[i] - 128) / 128
        sum += v * v
      }
      const rms = Math.sqrt(sum / data.length)
      const desired = rms > 1e-4 ? 0.12 / rms : 1
      normGain.gain.value = Math.min(2.5, Math.max(0.1, normGain.gain.value * 0.85 + desired * 0.15))
    }, 250)
  } else if (normalizeTimer) {
    clearInterval(normalizeTimer)
    normalizeTimer = null
    if (normGain) normGain.gain.value = 1
  }
}

// User-configurable crossfade. Setting 0 disables preloading/fading entirely
// and the element simply plays to its natural end.
function setFade(seconds) {
  fadeSeconds = Math.max(0, Number(seconds) || 0)
}

function onTimeUpdate() {
  const el = els[live].el
  if (fadeSeconds > 0 && pendingSrc && !preloaded && el.duration && el.duration - el.currentTime <= PRELOAD_WINDOW) {
    preloaded = true
    els.B.el.src = pendingSrc
  }
  if (fadeSeconds > 0 && pendingSrc && preloaded && !fading && el.duration && el.duration - el.currentTime <= fadeSeconds) {
    startFade()
  }
  emit('timeupdate')
}

function preload(url) {
  ensure()
  if (fadeSeconds <= 0) return
  pendingSrc = url
  preloaded = false
  const el = els[live].el
  if (el.duration && el.duration - el.currentTime <= PRELOAD_WINDOW) {
    preloaded = true
    els.B.el.src = url
  }
}

export const audio = {
  get src() { return els[live].el ? els[live].el.src : '' },
  set src(value) {
    ensure()
    // Post-crossfade, the app re-assigns the URL B is already playing: adopt it
    // instead of restarting, which is what makes playback gapless.
    if (els.B.el.src === value && els.B.el.readyState >= 1) resetTo('B')
    else resetTo('A', value)
  },
  get currentTime() { return els[live].el ? els[live].el.currentTime : 0 },
  set currentTime(value) {
    if (fading) abortFade()
    if (els[live].el) els[live].el.currentTime = value
  },
  get duration() {
    const d = els[live].el ? els[live].el.duration : 0
    return Number.isFinite(d) ? d : 0
  },
  get volume() { return volume },
  set volume(value) { volume = value; if (master) master.gain.value = value },
  get dataset() { return dataset },
  play() {
    ensure()
    if (ctx.state === 'suspended') ctx.resume()
    return els[live].el.play()
  },
  pause() {
    if (fading) abortFade()
    if (els[live].el) els[live].el.pause()
  },
  get gapFilled() { return gapFilled },
  preload,
  setFade,
  setNormalize,
  getAnalyser() { ensure(); return analyser },
  addEventListener(type, fn) { (handlers[type] = handlers[type] || []).push(fn) },
}

