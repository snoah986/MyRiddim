<script>
  import { apiFetch } from '../lib/api.js'
  import { onDestroy, onMount, tick } from 'svelte'
  import { audio } from '../lib/audio.js'
  import { settings } from '../lib/settings.js'
  import StartMixButton from '../components/StartMixButton.svelte'

  export let track
  export let isPlaying = false
  export let currentTime = 0
  export let duration = 0
  export let shuffle = false
  export let repeat = 'off'
  export let queueOpen = false
  export let onClose = () => {}
  export let onToggle = () => {}
  export let onNext = () => {}
  export let onPrevious = () => {}
  export let onSeek = () => {}
  export let onShuffle = () => {}
  export let onRepeat = () => {}
  export let onQueue = () => {}
  export let recommendations = []
  export let onPlayRecommendation = () => {}
  export let onAddToQueue = () => {}
  export let onStartMix = () => {}
  export let hasVideo = false
  export let companionVideoId = null

  let videoUrl = null
  let videoLoading = false
  let videoErrorMessage = ''
  let isVideoMode = false
  let videoModeTrackId = null
  let videoPausedAudio = false
  let videoPlaying = false
  let currentPlaybackTime = 0
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
  const ANTICIPATION_LEAD = 0.18
  let vizCanvas
  let vizRaf = 0
  let tiltX = 0
  let tiltY = 0
  let tiltActive = false
  let reduceMotion = false

  $: reduceMotion = $settings.reduceMotion || (typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  $: artUrl = resolveArt(track)
  $: playbackTime = isVideoMode ? currentPlaybackTime : currentTime
  $: if (lyricsOpen && track?.videoId) loadLyrics(track.videoId)
  $: if (lyricsOpen && (isPlaying || (isVideoMode && videoPlaying))) startLyricSyncLoop(); else stopLyricSyncLoop()
  $: if (track?.videoId || track?.id) loadTrackOffset(track?.videoId || track?.id)
  $: if (isVideoMode && videoModeTrackId && companionVideoId !== videoModeTrackId) exitVideoMode(true)

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const formatTime = seconds => !Number.isFinite(seconds) ? '0:00' : `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`

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

  function onPointerMove(event) {
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
    videoElement.currentTime = currentPlaybackTime
    videoElement.play().then(() => { videoPlaying = true }).catch(videoPlaybackError)
  }

  function videoPlayed() { videoPlaying = true }
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
    if (isVideoMode && videoElement) {
      if (videoElement.paused) videoElement.play().catch(videoPlaybackError)
      else videoElement.pause()
    } else {
      onToggle()
    }
  }

  function handleSeek(event) {
    const value = Number(event.currentTarget.value)
    if (!Number.isFinite(value)) return
    if (isVideoMode && videoElement) {
      currentPlaybackTime = value
      videoElement.currentTime = value
    } else {
      onSeek(event)
    }
    syncLyricsOnce()
  }

  async function toggleVideo() {
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
    videoErrorMessage = ''
    videoRequest += 1
    videoPausedAudio = false
    onSeek({ currentTarget: { value: currentPlaybackTime } })
    if (shouldResume) {
      await tick()
      onToggle()
    }
  }

  function toggleLyrics() {
    lyricsOpen = !lyricsOpen
    if (!lyricsOpen) lyricsFullscreen = false
  }

  async function loadLyrics(id) {
    const request = ++lyricRequest
    lyrics = []
    plainLyrics = ''
    lyricsSynced = false
    if (!id) return
    try {
      const params = new URLSearchParams({ track_id: id, title: track.title || '', artist: track.artist || '', duration: String(duration || '') })
      const response = await apiFetch(`/api/lyrics?${params}`)
      const data = await response.json()
      if (request !== lyricRequest) return
      lyrics = (data.lines || []).filter(line => line && Number.isFinite(Number(line.time)) && line.text != null && line.text !== '')
      lyricsSynced = data.synced === true && lyrics.length > 0
      plainLyrics = lyrics.length ? '' : (data.text || '')
      syncLyricsOnce()
    } catch { /* lyrics are an enhancement, not a playback failure */ }
  }

  async function scrollToActive() {
    await tick()
    const activeEl = lyricsContainer?.querySelector('.lyric-line.active')
    activeEl?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  // 60 FPS lyric sync: the HTML media element only fires timeupdate ~4x/sec,
  // so the active line is recomputed on every animation frame instead. The
  // effective time adds a 180ms anticipation lead (karaoke convention: a line
  // should light up just before the vocal lands) plus the user's per-track
  // calibration offset, so streaming-specific drift is corrected too.
  function mediaTime() {
    return isVideoMode ? (videoElement?.currentTime ?? currentPlaybackTime) : audio.currentTime
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
  function stopLyricSyncLoop() { cancelAnimationFrame(lyricRaf); lyricRaf = 0 }
  function loadTrackOffset(id) {
    manualOffset = 0
    if (!id) return
    try {
      const saved = localStorage.getItem(`lyric_offset_${id}`)
      if (saved != null && Number.isFinite(Number(saved))) manualOffset = Math.max(-1.5, Math.min(1.5, Number(saved)))
    } catch { /* storage unavailable */ }
  }
  function adjustOffset(delta) {
    manualOffset = Math.round((manualOffset + delta) * 10) / 10
    manualOffset = Math.max(-1.5, Math.min(1.5, manualOffset))
    const id = track?.videoId || track?.id
    if (id) { try { localStorage.setItem(`lyric_offset_${id}`, String(manualOffset)) } catch { /* best-effort */ } }
    syncLyricsOnce()
  }

  function seekLine(time) {
    if (!Number.isFinite(time)) return
    if (isVideoMode && videoElement) {
      currentPlaybackTime = time
      videoElement.currentTime = time
    } else {
      onSeek({ currentTarget: { value: time } })
    }
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
        context.fillStyle = `rgba(255,255,255,${(.18 + value * .5).toFixed(3)})`
        context.fillRect(index * slot + slot * .18, 0, slot * .64, barHeight)
        context.fillRect(index * slot + slot * .18, height - barHeight, slot * .64, barHeight)
      }
    }
    draw()
  }

  onMount(startVisualizer)
  onDestroy(() => {
    lyricRequest += 1
    stopLyricSyncLoop()
    if (vizRaf) cancelAnimationFrame(vizRaf)
    if (isVideoMode) exitVideoMode(true)
  })
</script>

<svelte:window on:keydown={(event) => event.key === 'Escape' && onClose()} />

<div class:lyrics-mode={lyricsOpen} class:lyrics-fullscreen={lyricsFullscreen} class="theatre" role="dialog" tabindex="-1" aria-modal="true" aria-label="Now playing" on:mousemove={onPointerMove} on:mouseleave={onPointerLeave}>
  <div class="theatre-content">
    <header class="theatre-topbar">
      <button class="round-button close-button" on:pointerdown|preventDefault={onClose} aria-label="Minimize Theatre Mode" title="Close Theatre Mode">⌄</button>
      <div class="mode-badge"><span class:video-dot={isVideoMode}></span>{lyricsOpen ? 'Synced Lyrics' : isVideoMode ? 'Official Video' : 'Now Playing'}</div>
      <div class="topbar-actions">
        {#if lyricsOpen}<button class="round-button" on:click={() => lyricsFullscreen = !lyricsFullscreen} aria-label="Toggle full-screen lyrics">{lyricsFullscreen ? '↙' : '↗'}</button>{:else}<span class="topbar-spacer" aria-hidden="true"></span>{/if}
      </div>
    </header>

    <main class="theatre-main">
      {#if lyricsOpen}
        {#if isVideoMode && videoUrl}
          <div class="lyrics-video-backdrop" aria-hidden="true">
            <video bind:this={videoElement} src={videoUrl} playsinline preload="auto" autoplay class="backdrop-video" on:loadedmetadata={videoMetadataLoaded} on:play={videoPlayed} on:pause={videoPaused} on:timeupdate={videoTimeUpdated} on:error={videoPlaybackError}></video>
            <div class="backdrop-shade"></div>
          </div>
        {/if}
        <section class="lyrics-stage" aria-label="Synchronized lyrics">
          <div class="lyrics-heading"><span>{track?.title || 'Lyrics'}</span><small>{lyricsSynced ? 'Synced' : videoLoading ? 'Loading visual…' : 'Tap a line to seek'}</small><div class="offset-pill" aria-label="Lyric timing offset"><button type="button" on:pointerdown|preventDefault={() => adjustOffset(-0.2)} aria-label="Shift lyrics earlier by 0.2s">−0.2s</button><span>{manualOffset >= 0 ? `+${manualOffset.toFixed(1)}s` : `${manualOffset.toFixed(1)}s`}</span><button type="button" on:pointerdown|preventDefault={() => adjustOffset(0.2)} aria-label="Shift lyrics later by 0.2s">+0.2s</button></div></div>
          {#if lyrics.length}
            <div class="lyrics-scroll" bind:this={lyricsContainer}>{#each lyrics as line, index}<button class:active={index === activeLyric} class="lyric-line" on:click={() => seekLine(Number(line.time))}>{line.text}</button>{/each}</div>
          {:else if plainLyrics}<div class="plain-lyrics">{plainLyrics}</div>
          {:else}<div class="lyrics-empty">Lyrics unavailable for this track.</div>{/if}
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
                <button class="video-exit" on:click={() => exitVideoMode(true)} aria-label="Return to artwork">× <span>Artwork</span></button>
              {:else}
                {#if artUrl}<img class="art" src={artUrl} referrerpolicy="no-referrer" alt="{clean(track?.title)} artwork" />{:else}<div class="art placeholder">♫</div>{/if}
                {#if hasVideo && companionVideoId}<button class="video-trigger" on:click={toggleVideo} aria-label="Watch this track in HD"><span class="video-trigger-icon">▶</span><span>Watch music video</span></button>{/if}
              {/if}
            </div>
          </div>
          <section class="metadata"><h1>{clean(track?.title) || 'No Track Selected'}</h1><p>{clean(track?.artist) || 'Unknown Artist'}</p>{#if clean(track?.album)}<span>{clean(track.album)}</span>{/if}</section>
        </section>
      {/if}
    </main>

    <footer class="bottom-dock">
      <div class="timeline"><span>{formatTime(playbackTime)}</span><input type="range" min="0" max={duration || 0} value={playbackTime} step=".1" on:input={handleSeek} aria-label="Seek through track" /><span>{formatTime(duration)}</span></div>
      <div class="control-deck">
        <div class="aux-controls"><button class:active={shuffle} class="aux-button" on:click={onShuffle} aria-label="Toggle shuffle" title="Shuffle">⇄</button><button class:active={repeat !== 'off'} class="aux-button" on:click={onRepeat} aria-label="Toggle repeat" title={`Repeat ${repeat}`}>↻{#if repeat === 'one'}<b>1</b>{/if}</button></div>
        <div class="main-controls"><button class="skip-button" on:pointerdown|preventDefault={onPrevious} aria-label="Previous track">|◀</button><button class="main-control" on:pointerdown|preventDefault={togglePlayback} aria-label={(isVideoMode ? videoPlaying : isPlaying) ? 'Pause' : 'Play'}>{(isVideoMode ? videoPlaying : isPlaying) ? 'Ⅱ' : '▶'}</button><button class="skip-button" on:pointerdown|preventDefault={onNext} aria-label="Next track">▶|</button></div>
        <div class="aux-controls right"><button class:active={lyricsOpen} class="aux-button" on:click={toggleLyrics} aria-label="Toggle lyrics" title="Lyrics">“</button><button class:active={queueOpen} class="aux-button" on:click={onQueue} aria-label="Toggle queue" title="Queue">☷</button></div>
      </div>
      {#if recommendations.length}<section class="recommendation-carousel" aria-label="Up next"><div class="recommendation-head"><strong>Up next</strong><span>{recommendations.length} more tracks</span></div><div class="recommendation-list">{#each recommendations.slice(0, 12) as rec, index (rec.videoId || index)}<div class="recommendation-chip-wrap mixable-track"><button class="recommendation-chip" on:pointerdown|preventDefault={() => onPlayRecommendation(rec)} aria-label="Play {clean(rec.title)}"><span class="recommendation-chip-art">{#if rec.thumbnail}<img src={rec.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="recommendation-chip-title">{clean(rec.title)}</span></button><StartMixButton track={rec} onStartMix={onStartMix} /></div>{/each}</div></section>{/if}
    </footer>
  </div>
</div>

<style>
  .theatre { position:fixed; inset:0; z-index:100; width:100vw; height:100vh; overflow:hidden; color:#fff; background:#09090b; font-family:Inter,ui-sans-serif,system-ui,sans-serif; user-select:none; }
  .theatre-content { position:relative; display:flex; flex-direction:column; width:100%; height:100%; min-height:0; box-sizing:border-box; padding:1.5rem; }
  .theatre-topbar { display:flex; flex:0 0 48px; align-items:center; justify-content:space-between; width:100%; z-index:20; }
  .round-button { display:grid; place-items:center; width:40px; height:40px; border:1px solid #ffffff1a; border-radius:50%; color:#b8b8c0; background:#ffffff08; cursor:pointer; backdrop-filter:blur(16px); transition:transform .35s cubic-bezier(.2,.8,.2,1),background .35s ease,color .35s ease; }
  .round-button:hover { color:#fff; background:#ffffff18; transform:translateY(-2px); }
  .close-button { font-size:1.3rem; }
  .mode-badge { display:flex; align-items:center; gap:.5rem; padding:.45rem .8rem; border:1px solid #ffffff12; border-radius:999px; color:#c7c7cf; background:#ffffff08; font-size:.68rem; font-weight:700; letter-spacing:.08em; }
  .mode-badge span { width:.42rem; height:.42rem; border-radius:50%; background:#a78bfa; }.mode-badge span.video-dot { background:#34d399; box-shadow:0 0 12px #34d399; }
  .topbar-actions,.topbar-spacer { display:flex; align-items:center; justify-content:flex-end; width:40px; height:40px; }
  .theatre-main { position:relative; display:flex; flex:1 1 auto; min-height:0; align-items:center; justify-content:center; margin:.75rem 0; z-index:2; }
  .center-stage { display:flex; flex-direction:column; align-items:center; justify-content:center; width:min(100%,1180px); min-height:0; }
  .stage-frame-wrap { position:relative; display:grid; place-items:center; width:min(72vh,420px); max-width:100%; aspect-ratio:1; }
  .stage-frame-wrap.video-wrap { width:min(100%,1180px); height:min(46vh,560px); max-height:46vh; aspect-ratio:16 / 9; }
  .viz-canvas { position:absolute; inset:-10%; width:120%; height:120%; pointer-events:none; }
  .art-frame { position:relative; z-index:1; width:min(100%,420px); aspect-ratio:1; overflow:hidden; border:1px solid #ffffff1a; border-radius:26px; background:#0b0b0d; box-shadow:0 28px 70px #0009; transform-style:preserve-3d; transition:transform .5s cubic-bezier(.2,.8,.2,1),width .35s ease,height .35s ease,border-radius .35s ease; }
  .art-frame.video-frame { width:100%; height:100%; max-width:1180px; aspect-ratio:16 / 9; border-radius:28px; box-shadow:0 30px 90px #000b,0 0 70px #ffffff10; }
  .art-frame.tilt-reset { transition:transform .6s cubic-bezier(.2,.8,.2,1); }
  .art,.native-video { display:block; width:100%; height:100%; object-fit:cover; }.native-video { position:absolute; inset:0; object-fit:contain; background:#000; cursor:pointer; }
  .placeholder { display:grid; place-items:center; color:#fff; background:linear-gradient(135deg,#252331,#4d3640); font-size:7rem; }
  .native-video-shell { position:absolute; inset:0; display:grid; place-items:center; background:#000; }
  .video-message { position:relative; z-index:2; display:flex; align-items:center; gap:.55rem; color:#ffffffb8; font-size:.75rem; }.video-message span { width:.45rem; height:.45rem; border-radius:50%; background:#34d399; box-shadow:0 0 12px #34d399; animation:pulse 1s ease-in-out infinite alternate; }.video-message.error { flex-direction:column; max-width:80%; color:#ffffff99; text-align:center; }.video-message.error strong { color:#fca5a5; }.video-message small { overflow-wrap:anywhere; }
  @keyframes pulse { to { opacity:.3; transform:scale(.7); } }
  .video-trigger { position:absolute; inset:0; z-index:3; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:.65rem; border:0; color:#fff; background:#0008; opacity:0; cursor:pointer; transition:opacity .35s cubic-bezier(.2,.8,.2,1),background .35s ease; }.art-frame:hover .video-trigger,.video-trigger:focus-visible { opacity:1; }.video-trigger:hover { background:#0009; }.video-trigger-icon { display:grid; place-items:center; width:54px; height:54px; border:1px solid #ffffff55; border-radius:50%; background:#ffffff26; font-size:1.2rem; }.video-trigger > span:last-child { padding:.32rem .7rem; border:1px solid #ffffff1c; border-radius:999px; background:#0009; font-size:.7rem; font-weight:700; }
  .video-exit { position:absolute; top:1rem; right:1rem; z-index:4; display:flex; align-items:center; gap:.35rem; padding:.5rem .85rem; border:1px solid #ffffff1a; border-radius:999px; color:#ffffffd9; background:#0009; cursor:pointer; font-size:.75rem; opacity:0; backdrop-filter:blur(16px); transition:opacity .35s ease,background .35s ease; }.art-frame.video-frame:hover .video-exit,.video-exit:focus-visible { opacity:1; }.video-exit:hover { background:#000; }
  .metadata { width:min(100%,560px); margin-top:1.1rem; text-align:center; }.metadata h1 { margin:0; overflow:hidden; color:#fff; font-family:'Outfit',Inter,sans-serif; font-size:clamp(1.2rem,2.5vw,1.75rem); font-weight:700; letter-spacing:-.02em; line-height:1.2; text-overflow:ellipsis; white-space:nowrap; }.metadata p { margin:.35rem 0 0; color:#fff; opacity:.72; font-size:1rem; }.metadata span { display:block; margin-top:.3rem; color:#fff; opacity:.45; font-size:.78rem; }
  .bottom-dock { display:flex; flex:0 0 auto; flex-direction:column; gap:.75rem; width:min(100%,1120px); margin:0 auto; z-index:20; }
  .timeline { display:flex; align-items:center; gap:.7rem; width:100%; color:#ffffffa8; font-size:.68rem; font-variant-numeric:tabular-nums; }.timeline input { flex:1; min-width:0; accent-color:#f2ece4; cursor:pointer; }
  .control-deck { display:flex; align-items:center; justify-content:space-between; padding:0 .6rem; }.aux-controls,.main-controls { display:flex; align-items:center; gap:.65rem; }.aux-controls { width:150px; }.aux-controls.right { justify-content:flex-end; }.main-controls { gap:1rem; }
  .aux-button,.skip-button,.main-control { display:grid; place-items:center; border:0; cursor:pointer; transition:transform .35s cubic-bezier(.2,.8,.2,1),background .35s ease,color .35s ease,box-shadow .35s ease; }.aux-button { position:relative; width:38px; height:38px; border:1px solid #ffffff12; border-radius:50%; color:#a1a1aa; background:#ffffff08; font-size:1.1rem; }.aux-button:hover { color:#fff; background:#ffffff14; transform:scale(1.05); }.aux-button.active { color:#111; border-color:#fff; background:#fff; box-shadow:0 8px 24px #0006; }.aux-button b { position:absolute; right:3px; bottom:2px; font-size:.5rem; }.skip-button { width:40px; height:40px; border:1px solid #ffffff10; border-radius:50%; color:#fff; background:#ffffff08; font-size:.85rem; }.skip-button:hover { background:#ffffff18; transform:scale(1.05); }.main-control { width:56px; height:56px; border-radius:50%; color:#111; background:#fff; font-size:1.25rem; box-shadow:0 10px 30px #0008; }.main-control:hover { transform:scale(1.06); box-shadow:0 12px 34px #000b; }.main-control:active,.skip-button:active,.aux-button:active { transform:scale(.95); }
  .recommendation-carousel { width:100%; padding:.55rem .6rem .6rem; border:1px solid #ffffff14; border-radius:16px; background:#141210cc; box-shadow:0 16px 40px #0007; backdrop-filter:blur(22px); }.recommendation-head { display:flex; align-items:center; justify-content:space-between; gap:.75rem; margin-bottom:.4rem; }.recommendation-head strong { color:#e4e4e7; font-size:.68rem; }.recommendation-head span { color:#71717a; font-size:.62rem; }  .recommendation-list { display:flex; gap:.5rem; overflow-x:auto; padding:.1rem .1rem .15rem; scrollbar-width:thin; scrollbar-color:#ffffff26 transparent; }.recommendation-chip-wrap { position:relative; flex:0 0 auto; }.recommendation-chip-wrap .mix-trigger { top:2px; right:2px; }.recommendation-chip { display:flex; flex:0 0 auto; align-items:center; gap:.5rem; min-width:0; max-width:240px; padding:.38rem .65rem .38rem .4rem; border:1px solid #ffffff0d; border-radius:999px; color:#f2ece4; background:#ffffff0b; cursor:pointer; transition:background .25s ease,border-color .25s ease; }.recommendation-chip:hover { border-color:#ffffff22; background:#ffffff14; }.recommendation-chip-art { display:grid; place-items:center; width:28px; height:28px; flex:0 0 auto; overflow:hidden; border-radius:8px; color:#d8cbbf; background:#252331; }.recommendation-chip-art img { width:100%; height:100%; object-fit:cover; }.recommendation-chip-title { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:.7rem; }
  .lyrics-video-backdrop { position:absolute; inset:-1.5rem; z-index:0; overflow:hidden; }.backdrop-video { width:100%; height:100%; object-fit:cover; transform:scale(1.08); filter:blur(16px) brightness(.35); }.backdrop-shade { position:absolute; inset:0; background:linear-gradient(180deg,#0009 0%,#0003 48%,#000d 100%); }.lyrics-stage { position:relative; z-index:1; display:flex; flex-direction:column; width:min(100%,780px); height:100%; min-height:0; overflow:hidden; pointer-events:none; }.lyrics-heading { display:flex; flex:0 0 auto; align-items:baseline; justify-content:space-between; gap:1rem; padding:0 .5rem; color:#fff; }.lyrics-heading span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:.8rem; font-weight:700; }.lyrics-heading small { color:#ffffff99; font-size:.68rem; }.lyrics-scroll { flex:1; min-height:0; overflow-y:auto; padding:34vh 1rem 30vh; scrollbar-width:none; mask-image:linear-gradient(to bottom,transparent 0%,black 15%,black 85%,transparent 100%); }.lyrics-scroll::-webkit-scrollbar { display:none; }.lyrics-heading, .lyrics-scroll, .plain-lyrics { pointer-events:auto; }.lyrics-scroll { padding-bottom:max(3.5rem,30vh); }.offset-pill { display:flex; align-items:center; gap:.1rem; padding:.15rem .3rem; border:1px solid #ffffff14; border-radius:999px; color:#a1a1aa; background:#ffffff0d; font-size:.62rem; white-space:nowrap; }.offset-pill button { border:0; padding:.2rem .35rem; border-radius:999px; color:#c7c7cf; background:none; cursor:pointer; font:inherit; }.offset-pill button:hover { color:#fff; background:#ffffff14; }.offset-pill span { min-width:2.6em; text-align:center; font-variant-numeric:tabular-nums; }.lyric-line { display:block; width:100%; padding:.55rem 0; border:0; color:#fff; background:none; text-align:center; font-size:clamp(1.45rem,3.4vw,2.8rem); font-weight:700; letter-spacing:-.025em; line-height:1.3; opacity:.32; filter:blur(1.4px); cursor:pointer; transition:opacity .35s ease,filter .35s ease,transform .35s ease,color .35s ease; }.lyric-line.active { color:#fff; opacity:1; filter:none; transform:scale(1.03); text-shadow:0 10px 30px #000b; }.plain-lyrics { flex:1; min-height:0; overflow:auto; padding:2rem 1rem 8rem; color:#ffffffc4; text-align:center; white-space:pre-wrap; font-size:clamp(1.25rem,2.4vw,2rem); line-height:1.6; }.lyrics-empty { display:grid; flex:1; min-height:0; place-items:center; color:#ffffff99; text-align:center; }
  .lyrics-fullscreen .lyrics-stage { width:min(100%,1000px); }.lyrics-fullscreen .lyrics-heading { justify-content:center; }.lyrics-fullscreen .lyrics-heading span { font-size:1rem; }.lyrics-fullscreen .lyrics-scroll { padding-top:36vh; }
  @media (prefers-reduced-motion:reduce) { .ambient-bg,.backdrop-video { animation:none; }.art-frame,.aux-button,.skip-button,.main-control,.lyric-line { transition:none; }.art-frame { transform:none!important; } }
  @media (max-width:720px) { .theatre-content { padding:1rem; }.theatre-topbar { flex-basis:42px; }.theatre-main { margin:.45rem 0; }.stage-frame-wrap { width:min(64vh,88vw); }.stage-frame-wrap.video-wrap { width:100%; height:min(42vh,380px); }.metadata { margin-top:.75rem; }.metadata h1 { font-size:1.25rem; }.metadata p { font-size:.85rem; }.control-deck { padding:0; }.aux-controls { width:92px; }.main-controls { gap:.65rem; }.aux-button { width:35px; height:35px; }.skip-button { width:36px; height:36px; font-size:.75rem; }.main-control { width:50px; height:50px; }.recommendation-carousel { padding:.55rem; }.recommendation-head span { display:none; }.recommendation-row { flex-basis:195px; }.lyrics-scroll { padding-top:30vh; }.lyric-line { font-size:clamp(1.35rem,7vw,2.2rem); } }
</style>
