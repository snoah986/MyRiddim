<script>
  import { apiFetch } from '../lib/api.js'
  import { onDestroy, onMount, tick } from 'svelte'
  import { audio, getActiveAudio } from '../lib/audio.js'
  import { settings } from '../lib/settings.js'
  import { buildCadenceLines } from '../lib/cadence_engine.js'
  import { applyKaraokeOffset, applyVideoOffset, cleanTrackMeta } from '../lib/lyrics.js'
  import KaraokeLyrics from '../components/KaraokeLyrics.svelte'

  export let track
  export let isPlaying = false
  export let currentTime = 0
  export let duration = 0
  export let shuffle = false
  export let repeat = 'off'
  export let queueOpen = false
  export let upNext = []
  export let history = []
  export let recentPlaylists = []
  export let playlists = []
  export let onSaveToPlaylist = async () => null
  export let onCreatePlaylist = async () => null
  export let onFavorite = () => {}
  export let onClearManualQueue = () => {}
  export let onToggle = () => {}
  export let onNext = () => {}
  export let onPrevious = () => {}
  export let onSeek = () => {}
  export let onShuffle = () => {}
  export let onRepeat = () => {}
  export let onQueue = () => {}
  export let onPlayQueue = () => {}
  export let hasVideo = false
  export let companionVideoId = null
  export let recommendations = []
  export let onPlayRecommendation = () => {}
  export let onAddToQueue = () => {}
  export let onRemoveUpcoming = () => {}
  export let onReorder = () => {}

  // --- Party Mode (host) -------------------------------------------------
  export let party = null // { code, guests, pending, settings } | null
  export let onPartyApprove = () => {}
  export let onPartyReject = () => {}
  export let onPartyOpen = () => {} // request the popover (App owns room lifecycle)
  export let partyPopoverOpen = false
  export let onPartyRole = () => {}
  export let onPartyKick = () => {}
  export let onPartySetting = () => {}
  export let onPartyCopyInvite = () => {}
  export let onPartyEnd = () => {}

  $: connectedGuests = (party?.guests || []).filter(guest => guest.connected)
  $: pendingCount = (party?.pending || []).length

  let queueTab = 'queue'
  let recTracks = []
  let recSeen = new Set()
  let recLoading = false
  let recRequest = 0
  let recForTrack = null
  let recLastSeed = null
  let dragQueueIndex = -1
  let savedTrack = null
  let savedPlaylistName = ''
  let savePopoverOpen = false
  let newPlaylistName = ''
  let saveBusy = false
  let saveToastTimer
  let flushTimer
  let flushProgress = 0

  function requestFlush(event) {
    event?.preventDefault()
    if ($settings.instantQueueFlush) {
      onClearManualQueue()
      announceSync('Manual queue cleared')
      return
    }
    startFlush(event)
  }

  function startFlush(event) {
    event?.preventDefault()
    if (!upNext.some(item => item?.queueSource === 'manual')) return
    flushProgress = 0
    clearInterval(flushTimer)
    const started = Date.now()
    flushTimer = setInterval(() => {
      flushProgress = Math.min(1, (Date.now() - started) / 800)
      if (flushProgress >= 1) {
        clearInterval(flushTimer)
        flushTimer = null
        onClearManualQueue()
        announceSync('Manual queue cleared')
      }
    }, 16)
  }
  function stopFlush() {
    if (!flushTimer) return
    clearInterval(flushTimer)
    flushTimer = null
    flushProgress = 0
  }
  async function saveFromQueue(item, playlistId = null) {
    if (!item || saveBusy) return
    saveBusy = true
    try {
      const target = await onSaveToPlaylist(item, playlistId)
      if (target) {
        savedTrack = item
        savedPlaylistName = target.title || target.name || 'your playlist'
        savePopoverOpen = false
        clearTimeout(saveToastTimer)
        saveToastTimer = setTimeout(() => { savedTrack = null; savePopoverOpen = false }, 4000)
      }
    } finally { saveBusy = false }
  }
  async function createAndSave() {
    const created = await onCreatePlaylist(newPlaylistName)
    if (created && savedTrack) {
      await saveFromQueue(savedTrack, created.id)
      newPlaylistName = ''
    }
  }

  let videoUrl = null
  let videoLoading = false
  let videoErrorMessage = ''
  let isVideoMode = false
  let videoModeTrackId = null
  let videoPausedAudio = false
  let videoPlaying = false
  let currentPlaybackTime = 0
  let videoDuration = 0
  let videoElement
  let videoRequest = 0

  let lyricsOpen = false
  let lyricsFullscreen = false
  let lyrics = []
  let lyricsSynced = false
  let plainLyrics = ''
  let lyricsContainer
  let lyricRequest = 0
  let lyricRaf = 0
  let activeLyric = -1
  let manualOffset = 0
  let videoOffset = 0
  let videoOffsetSource = 'none'
  let videoNeedsSync = false
  let rawLyrics = []
  let rawKaraokeLines = []
  let karaokeLines = []
  let karaokeLoading = false
  let karaokeRequest = 0
  let videoOffsetRequest = 0
  let syncToast = ''
  let syncToastTimer
  const ANTICIPATION_LEAD = 0.18
  const VIDEO_OFFSET_MAX = 30

  let meshPalette = ['rgb(74, 57, 92)', 'rgb(34, 48, 64)', 'rgb(76, 45, 45)']
  let vizCanvas
  let vizRaf = 0
  let tiltX = 0
  let tiltY = 0
  let tiltActive = false
  let reduceMotion = false
  let chromeAwake = true
  let cinemaTimer

  $: reduceMotion = $settings.reduceMotion || (typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  $: artUrl = resolveArt(track)
  $: playbackTime = isVideoMode ? currentPlaybackTime : currentTime
  $: playbackDuration = isVideoMode ? (videoDuration || duration) : duration
  $: meshStyle = `--mesh-a:${meshPalette[0]};--mesh-b:${meshPalette[1]};--mesh-c:${meshPalette[2]}`
  $: sourceLabel = isVideoMode ? 'OFFICIAL VIDEO' : track?.source ? String(track.source).replace(/_/g, ' ').toUpperCase() : 'MY MUSIC'
  $: statusLabel = lyricsOpen ? (lyricsSynced ? 'SYNCED' : 'LYRICS') : isVideoMode ? 'VIDEO' : 'AUDIO'
  $: if (lyricsOpen && track?.videoId) {
    loadLyrics(track.videoId)
    loadKaraokeLyrics(track.videoId)
  }
  $: if (lyricsOpen && (isPlaying || (isVideoMode && videoPlaying))) startLyricSyncLoop(); else stopLyricSyncLoop()
  $: if (track?.videoId || track?.id) loadTrackOffset(track?.videoId || track?.id)
  $: if (isVideoMode && videoModeTrackId && companionVideoId !== videoModeTrackId) exitVideoMode(true)
  $: if (isVideoMode && videoModeTrackId) loadVideoOffset(videoModeTrackId)
  $: if (isPlaying || videoPlaying) armCinemaTimer(); else wakeChrome(false)

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const formatTime = seconds => !Number.isFinite(Number(seconds)) ? '0:00' : `${Math.floor(Number(seconds) / 60)}:${String(Math.floor(Number(seconds) % 60)).padStart(2, '0')}`
  const formatQueueDuration = value => {
    if (typeof value === 'string' && value.includes(':')) return value
    const seconds = Number(value)
    return Number.isFinite(seconds) && seconds > 0 ? formatTime(seconds) : '—'
  }

  function getHighResArt(url) {
    if (!url) return ''
    if (url.includes('googleusercontent.com')) return url.replace(/=w\\d+-h\\d+/, '=w1080-h1080').replace(/=s\\d+/, '=s1080')
    if (url.includes('ytimg.com/vi/')) {
      const videoId = url.split('/vi/')[1]?.split('/')[0]
      return videoId ? `https://i.ytimg.com/vi/${videoId}/maxresdefault.jpg` : url
    }
    return url
  }

  function resolveArt(value) {
    if (!value) return ''
    const raw = value.artwork?.url || value.artwork || value.thumbnails || value.thumbnail || ''
    if (Array.isArray(raw)) {
      const urls = raw.map(item => typeof item === 'string' ? item : item?.url).filter(Boolean)
      return getHighResArt(urls[urls.length - 1] || '')
    }
    if (raw && typeof raw === 'object') return getHighResArt(raw.url || '')
    return getHighResArt(String(raw))
  }

  function sampleArtwork(event) {
    const image = event?.currentTarget
    if (!image?.naturalWidth || !image.naturalHeight) return
    try {
      const canvas = document.createElement('canvas')
      canvas.width = 32
      canvas.height = 32
      const context = canvas.getContext('2d', { willReadFrequently: true })
      context.drawImage(image, 0, 0, 32, 32)
      const pixels = context.getImageData(0, 0, 32, 32).data
      const buckets = new Map()
      for (let index = 0; index < pixels.length; index += 16) {
        const red = pixels[index]
        const green = pixels[index + 1]
        const blue = pixels[index + 2]
        const alpha = pixels[index + 3]
        if (alpha < 128) continue
        const luminance = .299 * red + .587 * green + .114 * blue
        const saturation = (Math.max(red, green, blue) - Math.min(red, green, blue)) / Math.max(1, Math.max(red, green, blue))
        if (luminance < 10 || luminance > 248 || saturation < .08) continue
        const key = [red, green, blue].map(value => Math.round(value / 24) * 24).join(',')
        const bucket = buckets.get(key) || { red: 0, green: 0, blue: 0, weight: 0 }
        const weight = 1 + saturation * 2
        bucket.red += red * weight
        bucket.green += green * weight
        bucket.blue += blue * weight
        bucket.weight += weight
        buckets.set(key, bucket)
      }
      const hues = [...buckets.values()]
        .sort((left, right) => right.weight - left.weight)
        .slice(0, 3)
        .map(bucket => `rgb(${Math.round(bucket.red / bucket.weight)}, ${Math.round(bucket.green / bucket.weight)}, ${Math.round(bucket.blue / bucket.weight)})`)
      if (hues.length) meshPalette = [...hues, ...meshPalette].slice(0, 3)
    } catch {
      // Cross-origin artwork may deny canvas reads; the low-luminance fallback remains.
    }
  }

  function onPointerMove(event) {
    wakeChrome()
    if (reduceMotion || isVideoMode) return
    const rect = event.currentTarget.getBoundingClientRect()
    const nx = ((event.clientX - rect.left) / rect.width) * 2 - 1
    const ny = ((event.clientY - rect.top) / rect.height) * 2 - 1
    tiltY = Math.max(-6, Math.min(6, nx * 6))
    tiltX = Math.max(-6, Math.min(6, -ny * 6))
    tiltActive = true
  }

  function onPointerLeave() {
    tiltActive = false
    tiltX = 0
    tiltY = 0
  }

  function wakeChrome(rearm = true) {
    chromeAwake = true
    clearTimeout(cinemaTimer)
    if (rearm && (isPlaying || videoPlaying)) armCinemaTimer()
  }

  function armCinemaTimer() {
    clearTimeout(cinemaTimer)
    if (!isPlaying && !videoPlaying) return
    cinemaTimer = setTimeout(() => { chromeAwake = false }, 3500)
  }

  // Reset the Recommended drawer whenever the playing track changes, so the
  // list can never mix rows seeded from two different tracks.
  $: if ((track?.videoId || track?.id || null) !== recForTrack) {
    recForTrack = track?.videoId || track?.id || null
    recRequest += 1
    recTracks = []
    recSeen = new Set()
    recLastSeed = null
    recLoading = false
  }

  async function openRecTab() {
    queueTab = 'recommended'
    wakeChrome()
    if (recTracks.length || recLoading) return
    // Paint instantly from the shelf App already fetched for this track.
    if (recommendations.length) {
      recTracks = [...recommendations]
      recSeen = new Set(recTracks.map(item => item?.videoId).filter(Boolean))
      return
    }
    const seedId = track?.videoId
    if (!seedId) return
    recLoading = true
    const request = ++recRequest
    try {
      const response = await apiFetch(`/api/recommendations?video_id=${encodeURIComponent(seedId)}`)
      const data = await response.json()
      if (request !== recRequest || !response.ok || data.error) return
      const fresh = (data.tracks || []).filter(item => item?.videoId && item.videoId !== seedId)
      if (fresh.length) {
        recSeen = new Set(fresh.map(item => item.videoId))
        recTracks = fresh
      }
    } catch { /* drawer recommendations are best-effort */ }
    finally { if (request === recRequest) recLoading = false }
  }

  // Infinite scroll: chain pages by seeding each fetch from the last row.
  async function loadMoreRecs() {
    const seedId = recTracks[recTracks.length - 1]?.videoId
    if (!seedId || recLoading || seedId === recLastSeed) return
    recLastSeed = seedId
    const request = ++recRequest
    recLoading = true
    try {
      const response = await apiFetch(`/api/recommendations?video_id=${encodeURIComponent(seedId)}`)
      const data = await response.json()
      if (request !== recRequest || !response.ok || data.error) return
      const fresh = (data.tracks || []).filter(item => item?.videoId && !recSeen.has(item.videoId))
      if (fresh.length) {
        recSeen = new Set([...recSeen, ...fresh.map(item => item.videoId)])
        recTracks = [...recTracks, ...fresh]
      }
    } catch { /* drawer recommendations are best-effort */ }
    finally { if (request === recRequest) recLoading = false }
  }

  function onRecScroll(event) {
    const element = event.currentTarget
    if (element.scrollTop + element.clientHeight >= element.scrollHeight - 320) loadMoreRecs()
  }

  function handleWindowKeydown(event) {
    wakeChrome()
    if (event.altKey && event.key.toLowerCase() === 'a' && party?.pending?.length) {
      event.preventDefault()
      onPartyApprove(party.pending[0].videoId)
      return
    }
    if (event.key.toLowerCase() === 's' && isVideoMode && videoNeedsSync) {
      event.preventDefault()
      syncBeat()
      return
    }
    if (event.key === 'Escape') {
      if (queueOpen) onQueue()
      else if (isVideoMode) exitVideoMode(true)
      else onClose()
    }
  }

  $: tiltStyle = `transform: perspective(1000px) rotateX(${tiltX}deg) rotateY(${tiltY}deg)`

  async function loadVideo(id) {
    const request = ++videoRequest
    videoUrl = null
    videoErrorMessage = ''
    if (!id) return false
    videoLoading = true
    try {
      const response = await apiFetch(`/api/video-url/${encodeURIComponent(id)}`)
      const data = await response.json()
      const resolvedUrl = data.stream_url || data.url
      if (!response.ok || request !== videoRequest || !resolvedUrl) throw Error(data.error || 'No progressive video stream')
      videoUrl = resolvedUrl
      return true
    } catch (error) {
      if (request === videoRequest) {
        videoErrorMessage = error?.message || 'Failed to resolve video stream'
        console.error('Video resolve failed:', error)
      }
      return false
    } finally {
      if (request === videoRequest) videoLoading = false
    }
  }

  function videoMetadataLoaded() {
    if (!videoElement || !isVideoMode) return
    videoDuration = Number.isFinite(videoElement.duration) ? videoElement.duration : 0
    videoElement.currentTime = Math.min(currentPlaybackTime, videoDuration || currentPlaybackTime)
    videoElement.play().then(() => { videoPlaying = true }).catch(videoPlaybackError)
  }

  function videoPlayed() { videoPlaying = true; wakeChrome() }
  function videoPaused() { videoPlaying = false }

  function videoPlaybackError(event) {
    videoPlaying = false
    videoErrorMessage = 'Playback blocked by the media server.'
    console.error('Video element playback error:', event?.currentTarget?.error || event)
  }

  function videoTimeUpdated() {
    if (videoElement && isVideoMode) currentPlaybackTime = videoElement.currentTime
  }

  function togglePlayback() {
    wakeChrome()
    if (isVideoMode && videoElement) {
      if (videoElement.paused) videoElement.play().catch(videoPlaybackError)
      else videoElement.pause()
    } else onToggle()
  }

  function handleSeek(event) {
    const value = Number(event.currentTarget.value)
    if (!Number.isFinite(value)) return
    if (isVideoMode && videoElement) {
      currentPlaybackTime = value
      videoElement.currentTime = value
    } else onSeek(event)
    syncLyricsOnce()
  }

  async function toggleVideo() {
    wakeChrome()
    if (isVideoMode) {
      await exitVideoMode(true)
      return
    }
    if (!hasVideo || !companionVideoId) return
    currentPlaybackTime = Number.isFinite(currentTime) ? currentTime : 0
    videoPlaying = false
    videoModeTrackId = companionVideoId
    videoPausedAudio = isPlaying
    isVideoMode = true
    if (videoPausedAudio) onToggle()
    await loadVideo(companionVideoId)
  }

  async function exitVideoMode(resumeAudio = true) {
    if (!isVideoMode) return
    currentPlaybackTime = videoElement?.currentTime ?? currentPlaybackTime
    videoElement?.pause()
    videoPlaying = false
    const shouldResume = resumeAudio && videoPausedAudio
    isVideoMode = false
    videoModeTrackId = null
    videoUrl = null
    videoDuration = 0
    videoErrorMessage = ''
    videoOffsetRequest += 1
    videoOffset = 0
    videoOffsetSource = 'none'
    videoNeedsSync = false
    lyrics = rawLyrics
    karaokeLines = rawKaraokeLines
    videoPausedAudio = false
    onSeek({ currentTarget: { value: currentPlaybackTime } })
    if (shouldResume) {
      await tick()
      onToggle()
    }
  }

  function toggleLyrics() {
    wakeChrome()
    lyricsOpen = !lyricsOpen
    if (!lyricsOpen) lyricsFullscreen = false
    if (lyricsOpen && isVideoMode && videoModeTrackId) loadVideoOffset(videoModeTrackId)
  }

  async function loadKaraokeLyrics(id) {
    const request = ++karaokeRequest
    rawKaraokeLines = []
    karaokeLines = []
    karaokeLoading = true
    if (!id) { karaokeLoading = false; return }
    try {
      const meta = cleanTrackMeta(track?.title || '', track?.artist || '')
      const params = new URLSearchParams({ track_id: id, title: meta.cleanTitle, artist: meta.cleanArtist, duration: String(duration || '') })
      const response = await apiFetch(`/api/karaoke-lyrics?${params}`)
      const data = await response.json()
      if (request !== karaokeRequest) return
      rawKaraokeLines = (data.lines || []).filter(line => line && Number.isFinite(Number(line.start)) && line.text)
      if (!rawKaraokeLines.length && rawLyrics.length) rawKaraokeLines = buildCadenceLines(rawLyrics, duration)
      karaokeLines = isVideoMode ? applyKaraokeOffset(rawKaraokeLines, videoOffset, videoNeedsSync) : rawKaraokeLines
    } catch {
      if (request === karaokeRequest && rawLyrics.length) {
        rawKaraokeLines = buildCadenceLines(rawLyrics, duration)
        karaokeLines = isVideoMode ? applyKaraokeOffset(rawKaraokeLines, videoOffset, videoNeedsSync) : rawKaraokeLines
      }
      // Syllable precision is optional; regular LRCLIB/YTM lyrics remain available.
    } finally {
      if (request === karaokeRequest) karaokeLoading = false
    }
  }

  async function loadLyrics(id) {
    const request = ++lyricRequest
    lyrics = []
    plainLyrics = ''
    lyricsSynced = false
    activeLyric = -1
    if (!id) return
    try {
      const meta = cleanTrackMeta(track.title || '', track.artist || '')
      const params = new URLSearchParams({ track_id: id, title: meta.cleanTitle, artist: meta.cleanArtist, duration: String(duration || '') })
      const response = await apiFetch(`/api/lyrics?${params}`)
      const data = await response.json()
      if (request !== lyricRequest) return
      rawLyrics = (data.lines || []).filter(line => line && Number.isFinite(Number(line.time)) && line.text != null && line.text !== '')
      if (!rawKaraokeLines.length && rawLyrics.length) {
        const fallback = buildCadenceLines(rawLyrics, duration)
        karaokeLines = isVideoMode ? applyKaraokeOffset(fallback, videoOffset, videoNeedsSync) : fallback
      }
      lyrics = isVideoMode ? applyVideoOffset(rawLyrics, videoOffset, videoNeedsSync) : rawLyrics
      lyricsSynced = data.synced === true && lyrics.length > 0
      plainLyrics = lyrics.length ? '' : (data.text || '')
      syncLyricsOnce()
    } catch {
      // Lyrics are optional and must never interrupt playback.
    }
  }

  async function scrollToActive() {
    await tick()
    const activeEl = lyricsContainer?.querySelector('.lyric-line.active')
    activeEl?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' })
  }

  function mediaTime() {
    return isVideoMode ? (videoElement?.currentTime ?? currentPlaybackTime) : (getActiveAudio()?.currentTime ?? audio.currentTime)
  }

  function computeActiveLyric() {
    const effectiveTime = mediaTime() + ANTICIPATION_LEAD + manualOffset
    return lyrics.reduce((found, line, index) => line.time <= effectiveTime ? index : found, -1)
  }

  function syncLyricsOnce() {
    if (!lyricsOpen || !lyrics.length) return
    const index = computeActiveLyric()
    if (index !== activeLyric) {
      activeLyric = index
      if (index >= 0) scrollToActive()
    }
  }

  function startLyricSyncLoop() {
    cancelAnimationFrame(lyricRaf)
    const sync = () => {
      syncLyricsOnce()
      if (lyricsOpen && (isPlaying || (isVideoMode && videoPlaying))) lyricRaf = requestAnimationFrame(sync)
    }
    lyricRaf = requestAnimationFrame(sync)
  }

  function stopLyricSyncLoop() {
    cancelAnimationFrame(lyricRaf)
    lyricRaf = 0
  }

  function loadTrackOffset(id) {
    manualOffset = 0
    // Audio-mode lyrics always use their source timestamps. Never let a
    // previously resolved companion-video offset leak into the studio cut.
    if (!isVideoMode) {
      videoOffset = 0
      videoOffsetSource = 'none'
      videoNeedsSync = false
    }
    if (!id || isVideoMode) return
    try {
      const saved = localStorage.getItem(`lyric_offset_${id}`)
      if (saved != null && Number.isFinite(Number(saved))) manualOffset = Math.max(-10, Math.min(10, Number(saved)))
    } catch {
      // Storage is optional.
    }
  }

  async function loadVideoOffset(id) {
    const requestId = ++videoOffsetRequest
    videoOffset = 0; videoOffsetSource = 'none'; videoNeedsSync = false
    if (!id || id !== videoModeTrackId || !isVideoMode) return
    try {
      const meta = cleanTrackMeta(track?.title || '', track?.artist || '')
      const params = new URLSearchParams({ video_id: id, audio_duration: String(duration || ''), title: meta.cleanTitle, artist: meta.cleanArtist })
      const response = await apiFetch(`/api/video-offset?${params}`)
      const data = await response.json()
      if (requestId !== videoOffsetRequest || !response.ok) return
      videoOffset = Math.max(-VIDEO_OFFSET_MAX, Math.min(VIDEO_OFFSET_MAX, Number(data.intro_offset) || 0))
      videoOffsetSource = data.source || 'none'
      videoNeedsSync = videoOffsetSource === 'needs_sync' || videoOffsetSource === 'delta_estimate'
      if (rawLyrics.length) { lyrics = applyVideoOffset(rawLyrics, videoOffset, videoNeedsSync); syncLyricsOnce() }
      if (rawKaraokeLines.length) karaokeLines = applyKaraokeOffset(rawKaraokeLines, videoOffset, videoNeedsSync)
    } catch { /* offset resolution is optional */ }
  }

  function announceSync(message) {
    syncToast = message
    clearTimeout(syncToastTimer)
    syncToastTimer = setTimeout(() => { syncToast = '' }, 2200)
  }

  function saveVideoOffset(offset, source = 'manual') {
    // Offset calibration belongs exclusively to the companion video timeline.
    // Audio mode must remain at LRCLIB/YTM's original timestamps.
    if (!isVideoMode) return
    const id = videoModeTrackId || companionVideoId
    if (!id) return
    videoOffset = Math.max(-VIDEO_OFFSET_MAX, Math.min(VIDEO_OFFSET_MAX, Number(offset) || 0))
    videoOffsetSource = source
    videoNeedsSync = false
    lyrics = applyVideoOffset(rawLyrics, videoOffset, false)
    if (rawKaraokeLines.length) karaokeLines = applyKaraokeOffset(rawKaraokeLines, videoOffset, false)
    try { apiFetch('/api/video-offset', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ video_id: id, intro_offset: videoOffset, source }) }).catch(() => {}) } catch { /* optional persistence */ }
    syncLyricsOnce()
  }

  function syncBeat() {
    if (!isVideoMode) return
    saveVideoOffset(mediaTime(), 'manual')
    announceSync('Beat synced & saved!')
  }

  function adjustOffset(delta) {
    if (isVideoMode) { saveVideoOffset(videoOffset + delta, 'manual'); announceSync('Offset saved'); return }
    manualOffset = Math.round((manualOffset + delta) * 10) / 10
    manualOffset = Math.max(-10, Math.min(10, manualOffset))
    const id = track?.videoId || track?.id
    if (id) {
      try { localStorage.setItem(`lyric_offset_${id}`, String(manualOffset)) } catch { /* best-effort */ }
    }
    syncLyricsOnce()
  }

  function seekLine(time) {
    if (!Number.isFinite(time)) return
    if (isVideoMode && videoElement) {
      currentPlaybackTime = time
      videoElement.currentTime = time
    } else onSeek({ currentTarget: { value: time } })
    syncLyricsOnce()
  }

  function startVisualizer() {
    if (!vizCanvas || reduceMotion) return
    const analyser = audio.getAnalyser()
    const bins = new Uint8Array(analyser.frequencyBinCount)
    const canvas = vizCanvas
    const context = canvas.getContext('2d')
    const draw = () => {
      vizRaf = requestAnimationFrame(draw)
      const width = canvas.clientWidth
      const height = canvas.clientHeight
      if (!width || !height) return
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      if (canvas.width !== Math.round(width * dpr)) {
        canvas.width = Math.round(width * dpr)
        canvas.height = Math.round(height * dpr)
      }
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      context.clearRect(0, 0, width, height)
      analyser.getByteFrequencyData(bins)
      const bars = 64
      const slot = width / bars
      for (let index = 0; index < bars; index += 1) {
        const value = (bins[Math.floor((index / bars) * bins.length * .6)] || 0) / 255
        const barHeight = Math.max(1.5, value * height * .18)
        context.fillStyle = `rgba(255,255,255,${(.16 + value * .46).toFixed(3)})`
        context.fillRect(index * slot + slot * .18, 0, slot * .64, barHeight)
        context.fillRect(index * slot + slot * .18, height - barHeight, slot * .64, barHeight)
      }
    }
    draw()
  }

  onMount(() => {
    startVisualizer()
    wakeChrome(false)
    return () => {
      if (vizRaf) cancelAnimationFrame(vizRaf)
      clearTimeout(cinemaTimer)
    }
  })

  onDestroy(() => {
    lyricRequest += 1
    stopLyricSyncLoop()
    clearTimeout(saveToastTimer)
    stopFlush()
    if (isVideoMode) exitVideoMode(true)
  })
</script>

<svelte:window on:keydown={handleWindowKeydown} />

<div
  class:cinema-hidden={!chromeAwake}
  class:lyrics-mode={lyricsOpen}
  class:lyrics-fullscreen={lyricsFullscreen}
  class:queue-visible={queueOpen}
  class="theatre"
  role="dialog"
  tabindex="-1"
  aria-modal="true"
  aria-label="Now playing"
  style={meshStyle}
  on:pointermove={onPointerMove}
  on:pointerdown={() => wakeChrome()}
  on:touchstart={() => wakeChrome()}
  on:mouseleave={onPointerLeave}
>
  <div class="mesh-backdrop" aria-hidden="true"><div class="mesh-orb orb-a"></div><div class="mesh-orb orb-b"></div><div class="mesh-orb orb-c"></div><div class="grain"></div></div>

  <div class="theatre-content">
    <header class="theatre-topbar" class:chrome-hidden={!chromeAwake}>
      <button class="round-button close-button" on:pointerdown|preventDefault={onClose} aria-label="Close Theatre Mode" title="Close Theatre Mode">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
      </button>
      <div class="source-label"><span class="source-dot" class:video-dot={isVideoMode}></span>{sourceLabel}</div>
      <div class="topbar-spacer" aria-hidden="true"></div>
    </header>

    <main class="theatre-main">
      {#if lyricsOpen}
        {#if isVideoMode && videoUrl}
          <div class="lyrics-video-backdrop" aria-hidden="true">
            <video bind:this={videoElement} src={videoUrl} playsinline preload="auto" autoplay class="backdrop-video" on:loadedmetadata={videoMetadataLoaded} on:play={videoPlayed} on:pause={videoPaused} on:timeupdate={videoTimeUpdated} on:error={videoPlaybackError}><track kind="captions" /></video>
            <div class="backdrop-shade"></div>
          </div>
        {/if}
        <section class="lyrics-stage" aria-label="Synchronized lyrics">
          <div class="lyrics-heading">
            <div class="lyrics-title"><span>{clean(track?.title) || 'Lyrics'}</span><span class="micro-badge">{statusLabel}</span></div>
            <div class="offset-controls" aria-label="Lyric timing offset">
              {#if isVideoMode}<button type="button" on:pointerdown|preventDefault={() => adjustOffset(-0.5)} aria-label="Shift video lyrics earlier by 0.5 seconds">−0.5s</button>{:else}<button type="button" on:pointerdown|preventDefault={() => adjustOffset(-0.2)} aria-label="Shift lyrics earlier by 0.2 seconds">−0.2s</button>{/if}
              <span>{isVideoMode ? `Offset ${videoOffset >= 0 ? '+' : ''}${videoOffset.toFixed(1)}s` : (manualOffset >= 0 ? `+${manualOffset.toFixed(1)}s` : `${manualOffset.toFixed(1)}s`)}</span>
              {#if isVideoMode}<button type="button" on:pointerdown|preventDefault={() => adjustOffset(0.5)} aria-label="Shift video lyrics later by 0.5 seconds">+0.5s</button>{:else}<button type="button" on:pointerdown|preventDefault={() => adjustOffset(0.2)} aria-label="Shift lyrics later by 0.2 seconds">+0.2s</button>{/if}
            </div>
          </div>
          {#if syncToast}<div class="sync-toast" role="status">{syncToast}</div>{/if}
          {#if karaokeLines.length}
            <KaraokeLyrics lines={karaokeLines} media={isVideoMode ? videoElement : getActiveAudio()} currentTime={playbackTime} playing={isPlaying || videoPlaying} onSeek={seekLine} onSync={syncBeat} />
          {:else if lyrics.length}
            <div class="lyrics-scroll" bind:this={lyricsContainer}>
              {#each lyrics as line, index}
                <button class:active={index === activeLyric} class:intro-line={line.isIntro} class:prompt-line={line.isPrompt} class="lyric-line" on:click={() => line.isPrompt ? syncBeat() : seekLine(Number(line.time))}>
                  <span>{line.text}</span>
                  {#if line.isIntro && playbackTime < Number(line.duration)}<small>Track starts in {formatTime(Math.max(0, Number(line.duration) - playbackTime))}</small>{/if}
                  {#if line.isPrompt}<small>Tap here when the beat drops · press S</small>{/if}
                </button>
              {/each}
            </div>
          {:else if plainLyrics}
            <div class="plain-lyrics">{plainLyrics}</div>
          {:else}
            <div class="lyrics-empty">{videoLoading || karaokeLoading ? 'Preparing lyrics…' : 'Lyrics unavailable for this track.'}</div>
          {/if}
        </section>
      {:else}
        <section class="center-stage" aria-label="Now playing">
          <div class:video-wrap={isVideoMode} class="stage-frame-wrap">
            {#if !isVideoMode}<canvas class="viz-canvas" bind:this={vizCanvas} aria-hidden="true"></canvas>{/if}
            <div class:video-frame={isVideoMode} class:tilt-reset={!tiltActive || isVideoMode} class="art-frame" style={tiltStyle}>
              {#if isVideoMode && companionVideoId}
                <div class="native-video-shell">
                  {#if videoUrl}<video bind:this={videoElement} class="native-video" src={videoUrl} playsinline preload="auto" autoplay on:loadedmetadata={videoMetadataLoaded} on:play={videoPlayed} on:pause={videoPaused} on:timeupdate={videoTimeUpdated} on:seeking={videoTimeUpdated} on:error={videoPlaybackError} on:ended={onNext} on:pointerdown|stopPropagation|preventDefault={togglePlayback} aria-label="Video for {clean(track?.title)}"><track kind="captions" /></video>{/if}
                  {#if videoLoading}<div class="video-message"><span></span>Resolving video stream…</div>{:else if videoErrorMessage}<div class="video-message error"><strong>Could not load video</strong><small>{videoErrorMessage}</small></div>{:else if !videoUrl}<div class="video-message error">Video unavailable for this track.</div>{/if}
                </div>
                <button class="video-exit" on:pointerdown|preventDefault={() => exitVideoMode(true)} aria-label="Return to album artwork"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg><span>Artwork</span></button>
              {:else}
                {#if artUrl}
                  <button class="art-button" on:click={hasVideo ? toggleVideo : undefined} disabled={!hasVideo} aria-label={hasVideo ? 'Watch the official video' : 'Album artwork'}>
                    <img class="art" src={artUrl} on:load={sampleArtwork} referrerpolicy="no-referrer" alt="{clean(track?.title)} artwork" />
                    {#if hasVideo}<span class="art-hint"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 9 6-9 6z" /></svg><span>Watch video</span></span>{/if}
                  </button>
                {:else}
                  <div class="art placeholder">♫</div>
                {/if}
              {/if}
            </div>
          </div>
          <section class="metadata">
            <h1>{clean(track?.title) || 'No Track Selected'}</h1>
            <p>{clean(track?.artist) || 'Unknown Artist'}</p>
            <div class="metadata-subline"><span class="micro-badge">{statusLabel}</span>{#if clean(track?.album)}<span>{clean(track.album)}</span>{/if}</div>
          </section>
        </section>
      {/if}
    </main>

    <footer class="bottom-dock" class:chrome-hidden={!chromeAwake}>
      <div class="dock-scrubber">
        <span>{formatTime(playbackTime)}</span>
        <input type="range" min="0" max={playbackDuration || 0} value={playbackTime} step=".1" on:input={handleSeek} aria-label="Seek through track" />
        <span>{formatTime(playbackDuration)}</span>
      </div>
      <div class="dock-controls">
        <div class="transport-group secondary-left">
          <button class:active={shuffle} class="icon-button" on:pointerdown|preventDefault={onShuffle} aria-label="Toggle shuffle" title="Shuffle"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h3c4.6 0 5.4 10 10 10h3M17 4h3v3M20 4l-4 4M4 17h3c1.2 0 2.1-.5 2.9-1.3M17 14h3v3M20 20l-4-4" /></svg></button>
          <button class:active={repeat !== 'off'} class="icon-button" on:pointerdown|preventDefault={onRepeat} aria-label={`Repeat ${repeat}`} title={`Repeat ${repeat}`}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3" />{#if repeat === 'one'}<circle cx="12" cy="12" r="2" />{/if}</svg></button>
        </div>
        <div class="transport-group main-transport">
          <button class="skip-button" on:pointerdown|preventDefault={onPrevious} aria-label="Previous track" title="Previous track"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5v14M18 6l-8 6 8 6z" /></svg></button>
          <button class="play-button" on:pointerdown|preventDefault={togglePlayback} aria-label={(isVideoMode ? videoPlaying : isPlaying) ? 'Pause' : 'Play'}>{#if (isVideoMode ? videoPlaying : isPlaying)}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3v14H7zm7 0h3v14h-3z" /></svg>{:else}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 10 7-10 7z" /></svg>{/if}</button>
          <button class="skip-button" on:pointerdown|preventDefault={onNext} aria-label="Next track" title="Next track"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l8 6-8 6zM18 5v14" /></svg></button>
        </div>
        <div class="transport-group secondary-right">
          <button class="party-pill" class:live={party} on:click={() => { wakeChrome(); onPartyOpen() }} aria-label={party ? 'Party guests and invites' : 'Start a party room'} title={party ? 'Party Mode' : 'Start Party Mode'}>
            <span class="party-dot" aria-hidden="true"></span>
            <span>{party ? `${connectedGuests.length} connected` : 'Party'}</span>
            {#if pendingCount}<b class="party-pending">{pendingCount}</b>{/if}
          </button>
          <button class:active={lyricsOpen} class="text-pill" on:pointerdown|preventDefault={toggleLyrics} aria-label="Toggle synced lyrics" title="Toggle synced lyrics"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zm5 9a5 5 0 0 1-10 0M12 17v4M8 21h8" /></svg><span>Lyrics</span></button>
          <button class:active={queueOpen} class="text-pill" on:pointerdown|preventDefault={onQueue} aria-label="Toggle playback queue" title="Toggle playback queue"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10" /></svg><span>Queue</span>{#if upNext.length}<b>{upNext.length}</b>{/if}</button>
        </div>
      </div>
    </footer>
  </div>

  {#if partyPopoverOpen && party}
    <div class="party-overlay" role="presentation" on:pointerdown|self={() => onPartyOpen()}>
      <div class="party-popover" role="dialog" tabindex="-1" aria-modal="true" aria-label="Party Mode host controls">
        <header class="party-head">
          <div>
            <span class="queue-kicker">PARTY MODE</span>
            <h2 class="party-code">{party.code}</h2>
          </div>
          <button class="round-button" on:pointerdown|preventDefault={() => onPartyOpen()} aria-label="Close party controls"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button>
        </header>
        {#if party.qrDataUrl}
          <div class="party-qr"><img src={party.qrDataUrl} alt="QR code joining the party room {party.code}" /></div>
        {/if}
        <div class="party-invite">
          <span class="party-link">{party.inviteUrl || party.code}</span>
          <button class="queue-clear" on:click={() => onPartyCopyInvite?.()}>Copy link</button>
        </div>
        <div class="party-section">
          <h3>Guests · {connectedGuests.length}</h3>
          {#if connectedGuests.length}
            {#each connectedGuests as guest (guest.id)}
              <div class="party-guest">
                <span class="party-guest-name">{guest.name}<small>{guest.role === 'co_dj' ? 'Co-DJ' : guest.role}</small></span>
                <span class="party-guest-actions">
                  <button title="Promote to Co-DJ" disabled={guest.role === 'co_dj'} on:click={() => onPartyRole?.(guest.id, guest.role === 'co_dj' ? 'guest' : 'co_dj')}>♪</button>
                  <button title="Mute" disabled={guest.role === 'muted'} on:click={() => onPartyRole?.(guest.id, 'muted')}>⌀</button>
                  <button title="Kick" class="danger" on:click={() => onPartyKick?.(guest.id)}>✕</button>
                </span>
              </div>
            {/each}
          {:else}
            <p class="party-hint">Waiting for guests to join…</p>
          {/if}
        </div>
        {#if pendingCount}
          <div class="party-section">
            <h3>Pending approval · {pendingCount}</h3>
            {#each party.pending as entry (entry.videoId)}
              <div class="party-guest">
                <span class="party-guest-name">{entry.title}<small>{entry.requested_by}</small></span>
                <span class="party-guest-actions">
                  <button title="Approve" on:click={() => onPartyApprove(entry.videoId)}>✓</button>
                  <button title="Reject" class="danger" on:click={() => onPartyReject(entry.videoId)}>✕</button>
                </span>
              </div>
            {/each}
          </div>
        {/if}
        <div class="party-section party-settings">
          <label><input type="checkbox" checked={party.settings?.require_approval} on:change={(event) => onPartySetting?.('require_approval', event.currentTarget.checked)} /> Require approval</label>
          <label><input type="checkbox" checked={party.settings?.democratic_upvoting} on:change={(event) => onPartySetting?.('democratic_upvoting', event.currentTarget.checked)} /> Democratic upvoting</label>
        </div>
        <button class="party-end" on:click={() => onPartyEnd?.()}>End party</button>
      </div>
    </div>
  {/if}

  {#if queueOpen}
    <div class="queue-overlay" role="presentation" on:click|self={onQueue}>
      <div class="queue-drawer" role="dialog" tabindex="-1" aria-modal="true" aria-label="Up next and recommendations">
        <header class="queue-header">
          <div class="queue-switcher" role="tablist" aria-label="Queue drawer views">
            <button role="tab" aria-selected={queueTab === 'queue'} class:active={queueTab === 'queue'} on:click={() => queueTab = 'queue'}>Up Next{#if upNext.length}<span> · {upNext.length}</span>{/if}</button>
            <button role="tab" aria-selected={queueTab === 'recommended'} class:active={queueTab === 'recommended'} on:click={openRecTab}>Recommended</button>
          </div>
          <div class="queue-actions">
            <button class="flush-button" disabled={!upNext.some(item => item?.queueSource === 'manual')} on:pointerdown={requestFlush} on:pointerup={stopFlush} on:pointerleave={stopFlush} on:pointercancel={stopFlush} aria-label={$settings.instantQueueFlush ? 'Clear manually queued tracks' : 'Hold to clear manually queued tracks'} title={$settings.instantQueueFlush ? 'Clear manual queue' : 'Hold 0.8 seconds to clear manual queue'}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v6m4-6v6" /></svg>{#if flushProgress > 0}<span class="flush-ring" style={`--progress:${flushProgress}`}></span>{/if}
            </button>
            <button class="round-button" on:pointerdown|preventDefault={onQueue} aria-label="Close queue" title="Close queue"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button>
          </div>
        </header>
        {#if queueTab === 'queue'}
          <div class="queue-summary"><span>{history.length + upNext.length + (track ? 1 : 0)} tracks in session</span><span class="queue-hint">Hold trash to flush manual adds</span></div>
          <div class="queue-list" role="list" on:dragover|preventDefault={() => {}}>
            {#if history.length || track || upNext.length}
              {#each history as item, index (item.videoId || `history-${index}`)}
                <div class="queue-row history-item"><span class="queue-grip" aria-hidden="true">·</span><button class="queue-item" on:click={() => onPlayQueue(item)}><span class="queue-art">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="queue-copy"><strong>{clean(item.title) || 'Untitled'}</strong><small>{clean(item.artist) || 'Various Artists'} <i>· played</i></small></span><span class="queue-duration">{formatQueueDuration(item.duration)}</span></button><button class="queue-save" on:click|stopPropagation={() => saveFromQueue(item)} aria-label="Save {clean(item.title)} to playlist">＋</button></div>
              {/each}
              {#if track}<div class="queue-row active-item"><span class="now-equalizer" aria-label="Now playing"><i></i><i></i><i></i></span><button class="queue-item" on:click={() => onPlayQueue(track)}><span class="queue-art">{#if track.thumbnail}<img src={track.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="queue-copy"><strong>{clean(track.title) || 'Untitled'}</strong><small>{clean(track.artist) || 'Various Artists'} <i>· now playing</i></small></span><span class="queue-duration">{formatQueueDuration(track.duration)}</span></button><button class="queue-save" on:click|stopPropagation={() => saveFromQueue(track)} aria-label="Save {clean(track.title)} to playlist">＋</button><button class="queue-favorite" on:click|stopPropagation={() => onFavorite(track)} aria-label="Favorite {clean(track.title)}">♥</button></div>{/if}
              {#each upNext as item, index (item.videoId || item.id || `up-next-${index}`)}
                <div class="queue-row" class:dragging={dragQueueIndex === index} draggable="true" role="listitem" on:dragstart={() => dragQueueIndex = index} on:dragend={() => dragQueueIndex = -1} on:drop|preventDefault={() => { if (dragQueueIndex > -1 && dragQueueIndex !== index) onReorder(dragQueueIndex, index); dragQueueIndex = -1 }}>
                  <span class="queue-grip" aria-hidden="true">⠿</span><button class="queue-item" on:click={() => onPlayQueue(item)}><span class="queue-art">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="queue-copy"><strong>{clean(item.title) || 'Untitled'}</strong><small>{clean(item.artist) || 'Various Artists'} <em>{item.source === 'radio' ? 'RADIO' : item.queueSource === 'manual' ? 'QUEUED' : 'CACHED'}</em></small></span><span class="queue-duration">{formatQueueDuration(item.duration)}</span></button><span class="queue-hover-actions"><button class="queue-save" on:click|stopPropagation={() => saveFromQueue(item)} aria-label="Save {clean(item.title)} to playlist">＋</button><button class="queue-favorite" on:click|stopPropagation={() => onFavorite(item)} aria-label="Favorite {clean(item.title)}">♥</button><button class="queue-remove" on:click|stopPropagation={() => onRemoveUpcoming(item)} aria-label="Remove {clean(item.title)} from queue">×</button></span></div>
              {/each}
            {:else}<div class="queue-empty"><span class="queue-empty-icon">∅</span><strong>Your queue is empty</strong><small>Add tracks from any shelf to keep the session moving.</small></div>{/if}
          </div>
        {:else}
          <div class="queue-list" on:scroll={onRecScroll}>
            {#if recTracks.length}{#each recTracks as item, index (item.videoId || index)}<div class="queue-row recommendation-row"><button class="queue-item" on:click={() => onPlayRecommendation(item)} aria-label="Start a mix from {clean(item.title)}">
<span class="queue-art"><img src={item.thumbnail} referrerpolicy="no-referrer" alt="" /></span><span class="queue-copy"><strong>{clean(item.title) || 'Untitled'}</strong><small>{clean(item.artist) || 'Various Artists'}</small></span><span class="queue-duration">{formatQueueDuration(item.duration)}</span></button><span class="queue-hover-actions"><button class="queue-append" on:click|stopPropagation={() => onAddToQueue(item)} aria-label="Add {clean(item.title)} to Up Next">＋</button><button class="queue-save" on:click|stopPropagation={() => saveFromQueue(item)} aria-label="Save {clean(item.title)} to playlist">♡</button></span></div>{/each}{#if recLoading}<div class="rec-loading"><span class="rec-spinner"></span>Loading more…</div>{/if}{:else if recLoading}<div class="rec-loading"><span class="rec-spinner"></span>Finding related tracks…</div>{:else}<div class="queue-empty"><span class="queue-empty-icon">✦</span><strong>No suggestions yet</strong><small>Related tracks appear here based on what's playing.</small></div>{/if}
          </div>
        {/if}
        {#if savedTrack}<div class="save-toast" role="status"><span>Saved to {savedPlaylistName}</span><button on:click={() => savePopoverOpen = !savePopoverOpen}>Change</button>{#if savePopoverOpen}<div class="save-popover"><strong>Save to…</strong>{#each [...(recentPlaylists || []), ...(playlists || []).filter(item => !(recentPlaylists || []).some(recent => recent.id === item.id))].filter(item => item.owned).slice(0, 3) as playlist (playlist.id)}<button on:click={() => saveFromQueue(savedTrack, playlist.id)}>{playlist.title}</button>{/each}<div class="new-playlist"><input bind:value={newPlaylistName} placeholder="New playlist name" aria-label="New playlist name" on:keydown={(event) => event.key === 'Enter' && createAndSave()} /><button on:click={createAndSave}>＋ New Playlist</button></div></div>{/if}</div>{/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .theatre { position:fixed; inset:0; z-index:100; width:100vw; height:100vh; overflow:hidden; color:#fff; background:#080808; font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif; user-select:none; cursor:default; isolation:isolate; }
  .theatre.cinema-hidden { cursor:none; }
  .mesh-backdrop { position:absolute; inset:0; z-index:-2; overflow:hidden; background:#080808; }
  .mesh-backdrop::after { content:''; position:absolute; inset:0; background:linear-gradient(180deg,#08080888 0%,#08080822 46%,#080808d9 100%); pointer-events:none; }
  .mesh-orb { position:absolute; width:72vw; height:72vw; max-width:980px; max-height:980px; border-radius:50%; opacity:.42; filter:blur(110px); mix-blend-mode:screen; will-change:transform; animation:mesh-drift 24s ease-in-out infinite alternate; }
  .orb-a { top:-30%; left:-16%; background:radial-gradient(circle,var(--mesh-a),transparent 68%); }
  .orb-b { top:7%; right:-27%; background:radial-gradient(circle,var(--mesh-b),transparent 68%); animation-delay:-8s; animation-duration:29s; }
  .orb-c { bottom:-44%; left:24%; background:radial-gradient(circle,var(--mesh-c),transparent 68%); animation-delay:-15s; animation-duration:32s; }
  .grain { position:absolute; inset:-50%; opacity:.055; pointer-events:none; background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.7'/%3E%3C/svg%3E"); transform:rotate(8deg); }
  @keyframes mesh-drift { from { transform:translate3d(-3%,2%,0) scale(1); } to { transform:translate3d(5%,-4%,0) scale(1.12); } }

  .theatre-content { position:relative; display:flex; flex-direction:column; width:100%; height:100%; min-height:0; box-sizing:border-box; padding:1.5rem 2rem 7.5rem; }
  .theatre-topbar { display:flex; flex:0 0 44px; align-items:center; justify-content:space-between; width:100%; z-index:20; transition:opacity .2s ease; }.theatre-topbar.chrome-hidden,.bottom-dock.chrome-hidden { opacity:0; pointer-events:none; }
  .round-button { display:grid; place-items:center; width:38px; height:38px; border:1px solid #ffffff1c; border-radius:50%; color:#ffffffb5; background:#ffffff0b; cursor:pointer; backdrop-filter:blur(18px); transition:transform .2s ease,background .2s ease,color .2s ease; }.round-button:hover { color:#fff; background:#ffffff19; transform:scale(1.05); }.round-button svg { width:17px; height:17px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }.close-button svg { width:19px; height:19px; }.source-label { display:flex; align-items:center; gap:.5rem; color:#ffffffa8; font-size:.62rem; font-weight:700; letter-spacing:.18em; }.source-dot { width:5px; height:5px; border-radius:50%; background:#a78bfa; box-shadow:0 0 12px #a78bfa; }.source-dot.video-dot { background:#34d399; box-shadow:0 0 12px #34d399; }.topbar-spacer { width:38px; }

  .theatre-main { position:relative; display:flex; flex:1 1 auto; min-height:0; align-items:center; justify-content:center; margin:.5rem 0; z-index:2; }.center-stage { display:flex; flex-direction:column; align-items:center; justify-content:center; width:min(100%,1180px); min-height:0; }.stage-frame-wrap { position:relative; display:grid; place-items:center; width:min(62vh,430px); max-width:100%; aspect-ratio:1; transition:width .45s ease,aspect-ratio .45s ease; }.stage-frame-wrap.video-wrap { width:min(100%,1080px); height:min(58vh,608px); aspect-ratio:16 / 9; }.viz-canvas { position:absolute; inset:-16%; width:132%; height:132%; pointer-events:none; opacity:.72; }
  .art-frame { position:relative; z-index:1; width:min(100%,430px); aspect-ratio:1; overflow:hidden; border:1px solid #ffffff1a; border-radius:30px; background:#0b0b0d; box-shadow:0 30px 90px #000b,0 0 60px #0008; transform-style:preserve-3d; transition:transform .55s cubic-bezier(.2,.8,.2,1),width .45s ease,height .45s ease,border-radius .45s ease; }.art-frame.video-frame { width:100%; height:100%; max-width:1080px; aspect-ratio:16 / 9; border-radius:24px; }.art-frame.tilt-reset { transition:transform .65s cubic-bezier(.2,.8,.2,1); }.art,.native-video { display:block; width:100%; height:100%; object-fit:cover; }.native-video { position:absolute; inset:0; object-fit:contain; background:#000; cursor:pointer; }.placeholder { display:grid; place-items:center; color:#fff; background:linear-gradient(135deg,#252331,#4d3640); font-size:7rem; }
  .art-button { position:relative; display:block; width:100%; height:100%; padding:0; border:0; color:inherit; background:none; cursor:pointer; }.art-button:disabled { cursor:default; }.art-button:focus-visible,.queue-item:focus-visible,.text-pill:focus-visible,.icon-button:focus-visible,.skip-button:focus-visible,.play-button:focus-visible { outline:2px solid #fff; outline-offset:4px; }.art-hint { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:.55rem; color:#fff; background:#0008; opacity:0; transition:opacity .25s ease; }.art-button:hover .art-hint,.art-button:focus-visible .art-hint { opacity:1; }.art-hint svg { width:45px; height:45px; padding:13px; border:1px solid #ffffff55; border-radius:50%; fill:currentColor; }.art-hint span { padding:.3rem .65rem; border-radius:999px; background:#000a; font-size:.68rem; font-weight:700; }
  .native-video-shell { position:absolute; inset:0; display:grid; place-items:center; background:#000; }.video-message { position:relative; z-index:2; display:flex; align-items:center; gap:.55rem; color:#ffffffb8; font-size:.75rem; }.video-message > span { width:.45rem; height:.45rem; border-radius:50%; background:#34d399; box-shadow:0 0 12px #34d399; animation:pulse 1s ease-in-out infinite alternate; }.video-message.error { flex-direction:column; max-width:80%; color:#ffffff99; text-align:center; }.video-message.error strong { color:#fca5a5; }.video-message small { overflow-wrap:anywhere; }@keyframes pulse { to { opacity:.3; transform:scale(.7); } }.video-exit { position:absolute; top:1rem; left:1rem; z-index:4; display:flex; align-items:center; gap:.35rem; padding:.5rem .8rem; border:1px solid #ffffff1a; border-radius:999px; color:#ffffffd9; background:#0009; cursor:pointer; font-size:.72rem; opacity:0; backdrop-filter:blur(16px); transition:opacity .25s ease,background .2s ease; }.art-frame.video-frame:hover .video-exit,.video-exit:focus-visible { opacity:1; }.video-exit:hover { background:#000; }.video-exit svg { width:14px; height:14px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
  .metadata { width:min(100%,600px); margin-top:1.25rem; text-align:center; }.metadata h1 { margin:0; overflow:hidden; color:#fff; font-size:clamp(1.5rem,3vw,2.15rem); font-weight:750; letter-spacing:-.035em; line-height:1.12; text-overflow:ellipsis; white-space:nowrap; }.metadata p { margin:.42rem 0 0; color:#ffffff99; font-size:clamp(.86rem,1.5vw,1rem); font-weight:500; }.metadata-subline { display:flex; align-items:center; justify-content:center; gap:.55rem; margin-top:.65rem; color:#ffffff58; font-size:.7rem; }.micro-badge { display:inline-flex; align-items:center; padding:.2rem .45rem; border-radius:5px; color:#ffffff9c; background:#ffffff10; font:700 .56rem/1 Inter,ui-sans-serif,sans-serif; letter-spacing:.12em; }

  .bottom-dock { position:fixed; left:50%; bottom:1.5rem; z-index:40; display:flex; flex-direction:column; gap:.75rem; width:92%; max-width:900px; padding:.85rem 1.25rem .8rem; border:1px solid #ffffff16; border-radius:28px; background:#0c0c0cc7; box-shadow:0 24px 70px #000b; backdrop-filter:blur(28px) saturate(1.2); transform:translateX(-50%); transition:opacity .2s ease; }.dock-scrubber { display:flex; align-items:center; gap:.7rem; color:#ffffff72; font:500 .68rem/1 ui-monospace,SFMono-Regular,Menlo,monospace; font-variant-numeric:tabular-nums; }.dock-scrubber input { flex:1; min-width:0; height:4px; accent-color:#fff; cursor:pointer; transition:height .15s ease; }.dock-scrubber input:hover { height:7px; }.dock-controls { display:flex; align-items:center; justify-content:space-between; gap:1rem; }.transport-group { display:flex; align-items:center; gap:.45rem; }.secondary-left,.secondary-right { flex:1; }.secondary-right { justify-content:flex-end; }.icon-button,.skip-button,.play-button,.text-pill { display:inline-flex; align-items:center; justify-content:center; border:0; cursor:pointer; transition:transform .18s ease,background .18s ease,color .18s ease,box-shadow .18s ease; }.icon-button { width:34px; height:34px; border:1px solid transparent; border-radius:50%; color:#ffffff76; background:transparent; }.icon-button:hover,.icon-button.active { color:#fff; background:#ffffff10; }.icon-button svg,.skip-button svg { width:17px; height:17px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }.icon-button:nth-child(2) svg circle { fill:none; }.skip-button { width:38px; height:38px; border:1px solid #ffffff12; border-radius:50%; color:#fff; background:#ffffff08; }.skip-button:hover { background:#ffffff18; transform:scale(1.05); }.play-button { width:54px; height:54px; border-radius:50%; color:#090909; background:#fff; box-shadow:0 10px 28px #0009; }.play-button:hover { transform:scale(1.06); box-shadow:0 14px 34px #000c; }.play-button:active,.skip-button:active,.icon-button:active,.text-pill:active { transform:scale(.94); }.play-button svg { width:21px; height:21px; fill:currentColor; }.text-pill { gap:.42rem; min-height:34px; padding:.45rem .75rem; border:1px solid #ffffff14; border-radius:999px; color:#ffffffa3; background:#ffffff08; font-size:.7rem; font-weight:600; }.text-pill:hover { color:#fff; background:#ffffff15; }.text-pill.active { color:#111; border-color:#fff; background:#fff; }.text-pill svg { width:14px; height:14px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }.text-pill b { min-width:1.35em; padding:.12rem .3rem; border-radius:999px; color:#fff; background:#ffffff16; font-size:.58rem; text-align:center; }.text-pill.active b { color:#111; background:#0002; }

  .lyrics-video-backdrop { position:absolute; inset:-2rem; z-index:0; overflow:hidden; }.backdrop-video { width:100%; height:100%; object-fit:cover; transform:scale(1.08); filter:blur(18px) brightness(.3) saturate(.85); }.backdrop-shade { position:absolute; inset:0; background:linear-gradient(180deg,#000b 0%,#0003 45%,#000e 100%); }.lyrics-stage { position:relative; z-index:1; display:flex; flex-direction:column; width:min(100%,820px); height:100%; min-height:0; overflow:hidden; pointer-events:none; }.lyrics-heading { display:flex; flex:0 0 auto; align-items:center; justify-content:space-between; gap:1rem; padding:0 .7rem; color:#fff; }.lyrics-title { display:flex; align-items:center; gap:.55rem; min-width:0; }.lyrics-title > span:first-child { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#ffffffcf; font-size:.8rem; font-weight:650; }.offset-controls { display:flex; align-items:center; gap:.1rem; pointer-events:auto; color:#ffffff72; font:500 .62rem/1 ui-monospace,SFMono-Regular,Menlo,monospace; }.offset-controls button { border:0; padding:.28rem .38rem; border-radius:5px; color:#ffffff8d; background:transparent; cursor:pointer; font:inherit; }.offset-controls button:hover { color:#fff; background:#ffffff12; }.offset-controls span { min-width:2.8em; color:#ffffffbc; text-align:center; font-variant-numeric:tabular-nums; }.lyrics-scroll { flex:1; min-height:0; overflow-y:auto; padding:34vh 1rem 30vh; scrollbar-width:none; mask-image:linear-gradient(to bottom,transparent 0%,black 15%,black 85%,transparent 100%); pointer-events:auto; }.lyrics-scroll::-webkit-scrollbar { display:none; }.lyric-line { display:block; width:100%; padding:.62rem 0; border:0; color:#fff; background:none; text-align:center; font-size:clamp(1.45rem,3.4vw,2.8rem); font-weight:650; letter-spacing:-.035em; line-height:1.25; opacity:.3; filter:blur(1.5px); transform:scale(.95); cursor:pointer; transition:opacity .3s ease,filter .3s ease,transform .3s ease,color .3s ease; }  .lyric-line small { display:block; margin-top:.45rem; color:#ffffff58; font:500 .62rem/1 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:0; }
  .lyric-line.intro-line { opacity:.9; color:#ffffffd4; animation:intro-breathe 2.2s ease-in-out infinite alternate; }
  .lyric-line.prompt-line { padding:.8rem 1rem; border:1px solid #ffffff2c; border-radius:14px; background:#ffffff10; opacity:.95; animation:prompt-pulse 1.7s ease-in-out infinite alternate; }
  .lyric-line.prompt-line:hover { background:#ffffff18; }
  @keyframes intro-breathe { from { opacity:.68; } to { opacity:1; } }
  @keyframes prompt-pulse { from { box-shadow:0 0 0 #ffffff00; } to { box-shadow:0 0 28px #ffffff18; } }
  .sync-toast { position:fixed; top:5.5rem; left:50%; z-index:4; padding:.5rem .75rem; border:1px solid #ffffff1a; border-radius:999px; color:#fff; background:#0c0c0cd9; box-shadow:0 12px 28px #0008; transform:translateX(-50%); font-size:.7rem; font-weight:650; backdrop-filter:blur(18px); }
  .plain-lyrics { flex:1; min-height:0; overflow:auto; padding:2rem 1rem 8rem; color:#ffffffc4; text-align:center; white-space:pre-wrap; font-size:clamp(1.2rem,2.4vw,2rem); line-height:1.6; pointer-events:auto; }.lyrics-empty { display:grid; flex:1; min-height:0; place-items:center; color:#ffffff99; text-align:center; }.lyrics-fullscreen .lyrics-stage { width:min(100%,1040px); }.lyrics-fullscreen .lyrics-scroll { padding-top:36vh; }

  .theatre.queue-visible .theatre-main { transform:translateX(-12%) scale(.92); transition:transform .3s ease-out; transform-origin:center center; }
  .queue-overlay { position:fixed; inset:0; z-index:50; background:#0006; backdrop-filter:blur(3px); animation:overlay-in .25s ease; }
  .queue-drawer { position:absolute; top:0; right:0; display:flex; flex-direction:column; width:min(390px,92vw); height:100%; padding:1.25rem 1rem 1rem; border-left:1px solid #ffffff14; color:#fff; background:#09090be0; box-shadow:-24px 0 70px #000b; backdrop-filter:blur(34px) saturate(1.15); animation:drawer-in .3s cubic-bezier(.2,.8,.2,1); }
  .queue-header { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding-bottom:.75rem; border-bottom:1px solid #ffffff0f; }
  .queue-switcher { display:flex; align-items:center; gap:.2rem; min-width:0; padding:.2rem; border:1px solid #ffffff0d; border-radius:10px; background:#ffffff05; }
  .queue-switcher button { border:0; border-radius:8px; padding:.42rem .62rem; color:#ffffff55; background:transparent; cursor:pointer; font-size:.68rem; font-weight:600; transition:color .18s ease,background .18s ease; }
  .queue-switcher button.active { color:#fff; background:#ffffff12; }
  .queue-switcher button:hover { color:#ffffffbf; }
  .queue-switcher button span { color:#ffffff66; font-variant-numeric:tabular-nums; }
  .queue-actions { display:flex; align-items:center; gap:.35rem; }
  .flush-button { position:relative; display:grid; place-items:center; width:34px; height:34px; border:1px solid transparent; border-radius:9px; color:#ffffff55; background:transparent; cursor:pointer; }
  .flush-button:hover:not(:disabled) { color:#fca5a5; background:#ffffff0c; }
  .flush-button:disabled { opacity:.3; cursor:default; }
  .flush-button svg { width:15px; height:15px; fill:none; stroke:currentColor; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round; }
  .flush-ring { position:absolute; inset:2px; border:2px solid transparent; border-top-color:#fca5a5; border-right-color:#fca5a5; border-radius:50%; transform:rotate(-45deg); opacity:.9; background:conic-gradient(#fca5a5 calc(var(--progress) * 360deg),transparent 0); -webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 0); mask:radial-gradient(farthest-side,transparent calc(100% - 2px),#000 0); }
  .queue-clear { border:0; padding:.3rem .6rem; border-radius:999px; color:#ffffff8d; background:#ffffff0a; cursor:pointer; font-size:.62rem; font-weight:650; transition:color .18s ease,background .18s ease; }.queue-clear:hover:not(:disabled) { color:#fff; background:#ffffff16; }.queue-clear:disabled { opacity:.4; cursor:default; }
  .queue-summary { display:flex; align-items:center; justify-content:space-between; gap:.75rem; margin:.8rem 0 .55rem; color:#ffffff70; font-size:.68rem; }.queue-hint { color:#ffffff38; font-size:.6rem; white-space:nowrap; }
  .queue-list { flex:1; min-height:0; overflow-y:auto; padding:.2rem 1rem 2rem .2rem; scrollbar-color:#ffffff2c transparent; scrollbar-width:thin; }
  .queue-list::-webkit-scrollbar { width:5px; }.queue-list::-webkit-scrollbar-track { background:transparent; }.queue-list::-webkit-scrollbar-thumb { border-radius:999px; background:#ffffff2c; }.queue-list::-webkit-scrollbar-thumb:hover { background:#ffffff55; }
  .queue-row { display:flex; align-items:center; gap:.25rem; min-width:0; margin-bottom:.38rem; padding:.25rem .2rem; border:1px solid #ffffff08; border-radius:12px; background:#ffffff03; transition:background .18s ease,border-color .18s ease,opacity .18s ease; }.queue-row:hover { border-color:#ffffff16; background:#ffffff08; }.queue-row.dragging { opacity:.35; }.queue-row.history-item { opacity:.4; }.queue-row.history-item:hover { opacity:.8; }.queue-row.active-item { border-color:#ffffff33; background:#ffffff12; }.queue-row.recommendation-row { border-color:#ffffff0c; }
  .queue-grip { display:grid; place-items:center; flex:0 0 16px; color:#ffffff30; cursor:grab; font-size:.76rem; letter-spacing:-.16em; }.queue-row:hover .queue-grip { color:#ffffff80; }
  .queue-item { display:grid; grid-template-columns:40px minmax(0,1fr) auto; align-items:center; gap:.62rem; flex:1; min-width:0; padding:.3rem; border:0; border-radius:9px; color:#fff; background:transparent; text-align:left; cursor:pointer; }.queue-item:hover { background:#ffffff08; }.queue-item:focus-visible,.queue-switcher button:focus-visible,.flush-button:focus-visible,.queue-save:focus-visible,.queue-favorite:focus-visible,.queue-remove:focus-visible,.queue-append:focus-visible { outline:2px solid #fff; outline-offset:2px; }
  .queue-art { display:grid; place-items:center; width:40px; height:40px; flex:0 0 40px; overflow:hidden; border-radius:9px; color:#d8cbbf; background:#211b1b; }.queue-art img { width:100%; height:100%; object-fit:cover; }
  .queue-copy { display:flex; min-width:0; flex-direction:column; gap:.18rem; }.queue-copy strong,.queue-copy small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.queue-copy strong { font-size:.73rem; font-weight:650; }.queue-copy small { color:#ffffff67; font-size:.62rem; }.queue-copy small i { color:#ffffff42; font-style:normal; }.queue-copy small em { margin-left:.3rem; color:#ffffff38; font:500 .5rem ui-monospace,SFMono-Regular,Menlo,monospace; font-style:normal; letter-spacing:.08em; }
  .queue-duration { color:#ffffff55; font:500 .62rem/1 ui-monospace,SFMono-Regular,Menlo,monospace; font-variant-numeric:tabular-nums; white-space:nowrap; }.queue-hover-actions { display:none; align-items:center; gap:.1rem; flex:0 0 auto; }.queue-row:hover .queue-hover-actions,.queue-row:focus-within .queue-hover-actions { display:flex; }.queue-save,.queue-favorite,.queue-remove,.queue-append { display:grid; place-items:center; width:25px; height:25px; border:0; border-radius:7px; color:#ffffff66; background:transparent; cursor:pointer; font-size:.8rem; }.queue-save:hover,.queue-append:hover { color:#fff; background:#ffffff14; }.queue-favorite:hover { color:#fda4af; background:#ffffff14; }.queue-remove:hover { color:#fca5a5; background:#ffffff14; }.now-equalizer { display:flex; align-items:end; justify-content:center; gap:2px; flex:0 0 16px; width:16px; height:18px; color:#fff; }.now-equalizer i { width:3px; height:75%; border-radius:2px; background:#fff; animation:queue-eq .75s ease-in-out infinite alternate; }.now-equalizer i:nth-child(2) { height:45%; animation-delay:-.3s; }.now-equalizer i:nth-child(3) { height:90%; animation-delay:-.12s; } @keyframes queue-eq { to { height:25%; opacity:.5; } }
  .save-toast { position:absolute; right:1rem; bottom:1.1rem; z-index:4; display:flex; align-items:center; gap:.65rem; max-width:calc(100% - 2rem); padding:.6rem .75rem; border:1px solid #ffffff1c; border-radius:12px; color:#fff; background:#17171beF; box-shadow:0 16px 45px #000b; backdrop-filter:blur(20px); font-size:.68rem; }.save-toast button { border:0; color:#fff; background:transparent; cursor:pointer; font-size:.67rem; font-weight:700; text-decoration:underline; }.save-popover { position:absolute; right:0; bottom:calc(100% + .5rem); display:flex; min-width:210px; flex-direction:column; gap:.25rem; padding:.65rem; border:1px solid #ffffff16; border-radius:12px; background:#15151aeF; box-shadow:0 20px 50px #000c; backdrop-filter:blur(24px); }.save-popover strong { padding:.2rem .35rem .35rem; color:#ffffff80; font-size:.62rem; }.save-popover > button { overflow:hidden; padding:.45rem .5rem; border:0; border-radius:7px; color:#fff; background:transparent; text-align:left; text-overflow:ellipsis; white-space:nowrap; cursor:pointer; font-size:.68rem; }.save-popover > button:hover { background:#ffffff12; }.new-playlist { display:flex; gap:.3rem; margin-top:.3rem; padding-top:.45rem; border-top:1px solid #ffffff10; }.new-playlist input { min-width:0; width:100%; border:0; color:#fff; background:transparent; outline:0; font-size:.65rem; }.new-playlist button { flex:0 0 auto; border:0; color:#fff; background:transparent; cursor:pointer; font-size:.6rem; white-space:nowrap; }
  .rec-loading { display:flex; align-items:center; justify-content:center; gap:.55rem; padding:1.1rem 0 1.4rem; color:#ffffff70; font-size:.7rem; }.rec-spinner { width:14px; height:14px; border:2px solid #ffffff2c; border-top-color:#fff; border-radius:50%; animation:rec-spin .8s linear infinite; }@keyframes rec-spin { to { transform:rotate(360deg); } }
  .queue-empty { display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:50%; padding:2rem; color:#ffffff70; text-align:center; }.queue-empty-icon { display:grid; place-items:center; width:48px; height:48px; margin-bottom:1rem; border:1px solid #ffffff18; border-radius:50%; color:#ffffffa8; font-size:1.5rem; }.queue-empty strong { color:#fff; font-size:.85rem; }.queue-empty small { max-width:220px; margin-top:.45rem; color:#ffffff55; font-size:.7rem; line-height:1.5; }
  @keyframes overlay-in { from { opacity:0; } to { opacity:1; } } @keyframes drawer-in { from { opacity:0; transform:translateX(28px); } to { opacity:1; transform:translateX(0); } }


  /* --- Party Mode (host pill + popover) --- */
  .party-pill { gap:.42rem; min-height:34px; padding:.45rem .75rem; border:1px solid #ffffff14; border-radius:999px; color:#ffffffa3; background:#ffffff08; cursor:pointer; font-size:.7rem; font-weight:600; display:inline-flex; align-items:center; justify-content:center; transition:transform .18s ease,background .18s ease,color .18s ease; }
  .party-pill:hover { color:#fff; background:#ffffff15; }
  .party-pill:active { transform:scale(.94); }
  .party-pill.live { color:#fff; border-color:#34d3993d; background:#34d39914; }
  .party-dot { width:7px; height:7px; border-radius:50%; background:#ffffff66; }
  .party-pill.live .party-dot { background:#34d399; box-shadow:0 0 12px #34d399; animation:pulse 1.2s ease-in-out infinite alternate; }
  .party-pending { display:grid; place-items:center; min-width:1.3em; padding:.12rem .3rem; border-radius:999px; color:#111; background:#fbbf24; font-size:.58rem; }
  .party-overlay { position:fixed; inset:0; z-index:60; display:grid; place-items:center; background:#0007; backdrop-filter:blur(4px); animation:overlay-in .25s ease; }
  .party-popover { display:flex; flex-direction:column; gap:1rem; width:min(360px,92vw); max-height:min(84vh,640px); overflow-y:auto; padding:1.4rem; border:1px solid #ffffff14; border-radius:22px; color:#fff; background:#0c0c0cf0; box-shadow:0 30px 90px #000c; backdrop-filter:blur(30px) saturate(1.15); animation:drawer-in .3s cubic-bezier(.2,.8,.2,1); scrollbar-width:thin; scrollbar-color:#ffffff2c transparent; }
  .party-head { display:flex; align-items:flex-start; justify-content:space-between; }
  .party-code { margin:.35rem 0 0; font-size:1.55rem; font-weight:750; letter-spacing:.14em; }
  .party-qr { align-self:center; padding:.6rem; border:1px solid #ffffff12; border-radius:14px; background:#fff; }
  .party-qr img { display:block; width:168px; height:168px; }
  .party-invite { display:flex; align-items:center; gap:.5rem; }
  .party-link { flex:1; min-width:0; overflow:hidden; padding:.42rem .6rem; border:1px solid #ffffff10; border-radius:9px; color:#ffffffa8; background:#ffffff08; text-overflow:ellipsis; white-space:nowrap; font:500 .62rem/1.3 ui-monospace,SFMono-Regular,Menlo,monospace; }
  .party-section { padding-top:.9rem; border-top:1px solid #ffffff0d; }
  .party-section h3 { margin:0 0 .55rem; color:#ffffff85; font-size:.66rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase; }
  .party-guest { display:flex; align-items:center; justify-content:space-between; gap:.6rem; padding:.4rem 0; }
  .party-guest-name { display:flex; min-width:0; flex-direction:column; }
  .party-guest-name small { color:#ffffff59; font-size:.62rem; }
  .party-guest-actions { display:flex; flex:0 0 auto; gap:.3rem; }
  .party-guest-actions button { display:grid; place-items:center; width:28px; height:28px; border:1px solid #ffffff14; border-radius:8px; color:#ffffff8d; background:#ffffff08; cursor:pointer; font-size:.72rem; transition:color .18s ease,background .18s ease; }
  .party-guest-actions button:hover:not(:disabled) { color:#fff; background:#ffffff16; }
  .party-guest-actions button.danger:hover { color:#fca5a5; }
  .party-guest-actions button:disabled { opacity:.35; cursor:default; }
  .party-hint { margin:.2rem 0; color:#ffffff59; font-size:.7rem; }
  .party-settings label { display:flex; align-items:center; gap:.55rem; padding:.32rem 0; color:#ffffffa8; font-size:.74rem; cursor:pointer; }
  .party-settings input { accent-color:#fff; }
  .party-end { margin-top:.9rem; padding:.55rem 0; border:1px solid #fca5a52e; border-radius:12px; color:#fca5a5; background:#fca5a50d; cursor:pointer; font-size:.72rem; font-weight:650; transition:background .18s ease; }
  .party-end:hover { background:#fca5a51f; }

  @media (prefers-reduced-motion:reduce) { .mesh-orb { animation:none; }.art-frame,.play-button,.skip-button,.icon-button,.text-pill,.party-pill,.queue-item { transition:none; }.art-frame { transform:none!important; }.queue-overlay,.queue-drawer,.party-overlay,.party-popover { animation:none; }.lyric-line { transition:none; } }
  @media (max-width:760px) {
    .theatre.queue-visible .theatre-main { transform:translateX(0) scale(1); }
  }
  @media (max-width:430px) { .source-label { font-size:.54rem; letter-spacing:.14em; }.secondary-left .icon-button:first-child { display:none; }.text-pill { padding-inline:.45rem; }.text-pill span { display:none; }.text-pill svg { width:15px; height:15px; }.dock-scrubber { gap:.45rem; font-size:.61rem; }.queue-drawer { width:100vw; } }
</style>
