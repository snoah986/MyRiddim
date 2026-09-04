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
let pendingTrackId = null
let preloaded = false   // pendingSrc applied to els.B
let fading = false
let fadeTimer = null
let gapFilled = false   // true right after a crossfade: the next track is already playing
let gapFilledTrackId = null
const dataset = { track: null }
const handlers = { play: [], playing: [], pause: [], timeupdate: [], loadedmetadata: [], ended: [], error: [] }

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
  // Keep the audio endpoint warm with a looping silent buffer so the
  // hardware DAC never sleeps between tracks — Windows WASAPI resume adds a
  // 200-400ms audible delay on the next play().
  try {
    const keepAlive = ctx.createBuffer(1, 1, 22050)
    const keepAliveSource = ctx.createBufferSource()
    keepAliveSource.buffer = keepAlive
    keepAliveSource.loop = true
    keepAliveSource.connect(ctx.destination)
    keepAliveSource.start()
  } catch { /* keep-alive is best-effort */ }
  for (const key of ['A', 'B']) {
    const el = new Audio()
    el.preload = 'auto'
    el.playsInline = true
    const gain = ctx.createGain()
    gain.gain.value = key === 'A' ? volume : 0
    ctx.createMediaElementSource(el).connect(gain)
    gain.connect(master)
    els[key].el = el
    els[key].gain = gain
    el.addEventListener('play', () => { if (isLive(el)) emit('play') })
    el.addEventListener('playing', () => { if (isLive(el)) emit('playing') })
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
  pendingTrackId = null
  preloaded = false
  gapFilled = false
  gapFilledTrackId = null
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
  pendingSrc = null
  pendingTrackId = null
  preloaded = false
}

function startFade() {
  const outgoing = live
  const incoming = otherOf(outgoing)
  const incomingEl = els[incoming].el
  if (fading || !preloaded || !pendingSrc || !incomingEl.src || incomingEl.readyState < 2) return
  fading = true
  const now = ctx.currentTime
  els[outgoing].gain.gain.cancelScheduledValues(now)
  els[outgoing].gain.gain.setValueAtTime(els[outgoing].gain.gain.value, now)
  els[outgoing].gain.gain.linearRampToValueAtTime(0, now + fadeSeconds)
  els[incoming].gain.gain.cancelScheduledValues(now)
  els[incoming].gain.gain.setValueAtTime(0, now)
  els[incoming].gain.gain.linearRampToValueAtTime(volume, now + fadeSeconds)
  incomingEl.play().catch(() => abortFade())
  fadeTimer = setTimeout(() => {
    if (!fading) return
    fading = false
    gapFilled = !!pendingTrackId
    gapFilledTrackId = pendingTrackId
    live = incoming
    els[outgoing].el.pause()
    els[outgoing].el.removeAttribute('src')
    els[outgoing].el.load()
    els[outgoing].gain.gain.cancelScheduledValues(ctx.currentTime)
    els[outgoing].gain.gain.setValueAtTime(0, ctx.currentTime)
    els[incoming].gain.gain.cancelScheduledValues(ctx.currentTime)
    els[incoming].gain.gain.setValueAtTime(volume, ctx.currentTime)
    pendingSrc = null
    pendingTrackId = null
    preloaded = false
    // The outgoing element never reaches its natural end, so synthesize it:
    // the app advances the queue and adopts the already-playing incoming URL.
    emit('ended')
  }, fadeSeconds * 1000)
}

// Commit the already-audible incoming deck as the current track without
// touching its transport position or source. The queue layer calls this after
// its now-playing state advances in response to the synthetic ended event.
function adoptGapless(trackId) {
  if (!gapFilled || !trackId || trackId !== gapFilledTrackId) return false
  gapFilled = false
  gapFilledTrackId = null
  dataset.currentTrackId = trackId
  dataset.loadedTrackId = trackId
  emit('loadedmetadata')
  emit('playing')
  emit('timeupdate')
  return true
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
    const incoming = otherOf(live)
    els[incoming].el.src = pendingSrc
    preloaded = true
  }
  if (fadeSeconds > 0 && pendingSrc && preloaded && !fading && el.duration && el.duration - el.currentTime <= fadeSeconds) {
    startFade()
  }
  emit('timeupdate')
}

function preload(url, trackId = null) {
  ensure()
  if (fadeSeconds <= 0 || !url) return
  pendingSrc = url
  pendingTrackId = trackId || null
  preloaded = false
  const el = els[live].el
  if (el.duration && el.duration - el.currentTime <= PRELOAD_WINDOW) {
    const incoming = otherOf(live)
    els[incoming].el.src = url
    preloaded = true
  }
}

// Stop both media elements and release their network buffers before a track
// switch. This prevents a late media event or crossfade element from leaking
// the previous track into the new session.
function clear() {
  ensure()
  abortFade()
  pendingSrc = null
  pendingTrackId = null
  preloaded = false
  gapFilled = false
  gapFilledTrackId = null
  for (const key of ['A', 'B']) {
    els[key].el.pause()
    els[key].el.removeAttribute('src')
    els[key].el.load()
    els[key].gain.gain.cancelScheduledValues(ctx.currentTime)
    els[key].gain.gain.setValueAtTime(key === live ? volume : 0, ctx.currentTime)
  }
  dataset.loadedTrackId = null
}

export function getActiveAudio() {
  ensure()
  return els[live].el
}

export const audio = {
  get src() { return els[live].el ? els[live].el.src : '' },
  set src(value) {
    ensure()
    // Post-crossfade, the app re-assigns the URL already playing: adopt that
    // element instead of restarting it. This works after either A→B or B→A.
    const existing = ['A', 'B'].find(key => els[key].el.src === value && els[key].el.readyState >= 1)
    if (gapFilled && existing) resetTo(existing)
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
  // Wake the audio pipeline synchronously: create the context and resume it
  // inside the user gesture so media playback is never held up by async setup.
  warm() {
    ensure()
    if (ctx.state === 'suspended') ctx.resume()
  },
  play() {
    ensure()
    if (ctx.state === 'suspended') ctx.resume()
    return els[live].el.play()
  },
  pause() {
    if (fading) abortFade()
    if (els[live].el) els[live].el.pause()
  },
  clear,
  adoptGapless,
  get gapFilled() { return gapFilled },
  preload,
  setFade,
  setNormalize,
  getAnalyser() { ensure(); return analyser },
  addEventListener(type, fn) { (handlers[type] = handlers[type] || []).push(fn) },
}

