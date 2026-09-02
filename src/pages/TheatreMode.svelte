<script>
  import { onDestroy, onMount, tick } from 'svelte'
  import { audio } from '../lib/audio.js'
  import { settings } from '../lib/settings.js'
  export let track
  export let isPlaying = false
  export let currentTime = 0
  export let duration = 0
  export let shuffle = false
  export let repeat = 'off'
  export let onClose = () => {}
  export let onToggle = () => {}
  export let onNext = () => {}
  export let onPrevious = () => {}
  export let onSeek = () => {}
  export let onShuffle = () => {}
  export let onRepeat = () => {}

  let videoUrl = null, videoLoading = false, lyricsOpen = false, lyricsFullscreen = false, lyrics = [], lyricsSynced = false, plainLyrics = '', lyricsContainer, lyricRequest = 0
  let vizCanvas, vizRaf = 0
  let tiltX = 0, tiltY = 0, tiltActive = false
  $: reduceMotion = $settings.reduceMotion || (typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  const MAX_TILT = 8
  function onPointerMove(event) {
    if (reduceMotion) return
    const rect = event.currentTarget.getBoundingClientRect()
    const nx = ((event.clientX - rect.left) / rect.width) * 2 - 1
    const ny = ((event.clientY - rect.top) / rect.height) * 2 - 1
    tiltY = Math.max(-MAX_TILT, Math.min(MAX_TILT, nx * MAX_TILT))
    tiltX = Math.max(-MAX_TILT, Math.min(MAX_TILT, -ny * MAX_TILT))
    tiltActive = true
    event.currentTarget.style.setProperty('--gx', `${((nx + 1) / 2) * 100}%`)
    event.currentTarget.style.setProperty('--gy', `${((ny + 1) / 2) * 100}%`)
  }
  function onPointerLeave(event) {
    tiltActive = false; tiltX = 0; tiltY = 0
    event.currentTarget.style.setProperty('--gx', '50%'); event.currentTarget.style.setProperty('--gy', '50%')
  }
  $: tiltStyle = `transform: perspective(900px) rotateX(${tiltX}deg) rotateY(${tiltY}deg)`
  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const formatTime = seconds => !Number.isFinite(seconds) ? '0:00' : `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
  const resolveArt = (track) => {
    if (!track) return ''
    const raw = track.artwork?.url || track.artwork || track.thumbnails || track.thumbnail || ''
    if (Array.isArray(raw)) {
      const urls = raw.map(item => typeof item === 'string' ? item : item?.url).filter(Boolean)
      return urls[urls.length - 1] || ''
    }
    if (raw && typeof raw === 'object') return raw.url || ''
    return String(raw)
  }
  $: artUrl = resolveArt(track)
  $: activeLyric = lyrics.reduce((found, line, index) => line.time <= currentTime ? index : found, -1)

  async function loadVideo(id) { const request = ++lyricRequest; videoUrl = null; videoLoading = false; if (!id) return; videoLoading = true; try { const response = await fetch(`/api/stream-video/${id}`); const data = await response.json(); if (request === lyricRequest) videoUrl = data.video_url || null } catch {} finally { if (request === lyricRequest) videoLoading = false } }
  async function loadLyrics(id) { const request = ++lyricRequest; lyrics = []; plainLyrics = ''; lyricsSynced = false; if (!id) return; try { const params = new URLSearchParams({track_id:id, title:track.title || '', artist:track.artist || '', duration:String(duration || '')}); const response = await fetch(`/api/lyrics?${params}`); const data = await response.json(); if (request !== lyricRequest) return; lyrics = data.lines || []; lyricsSynced = data.synced === true; plainLyrics = data.text || '' } catch {} }
  $: if (track?.videoId) loadVideo(track.videoId)
  $: if (lyricsOpen && track?.videoId) loadLyrics(track.videoId)
  $: if (lyricsOpen && activeLyric >= 0 && lyricsContainer) scrollToActive()
  async function scrollToActive() {
    await tick()
    const activeEl = lyricsContainer?.querySelector('.lyric-line.active')
    if (activeEl) activeEl.scrollIntoView({behavior:'smooth', block:'center'})
  }
  function toggleLyrics() { lyricsOpen = !lyricsOpen }
  function seekLine(time) { onSeek({currentTarget:{value:time}}) }
  onMount(() => startVisualizer())
  function startVisualizer() {
    if (!vizCanvas || reduceMotion) return
    const analyser = audio.getAnalyser()
    const bins = new Uint8Array(analyser.frequencyBinCount)
    const cvs = vizCanvas
    const c = cvs.getContext('2d')
    const DPR = Math.min(window.devicePixelRatio || 1, 2)
    const draw = () => {
      vizRaf = requestAnimationFrame(draw)
      const w = cvs.clientWidth, h = cvs.clientHeight
      if (!w || !h) return
      if (cvs.width !== Math.round(w * DPR)) { cvs.width = Math.round(w * DPR); cvs.height = Math.round(h * DPR) }
      c.setTransform(DPR, 0, 0, DPR, 0, 0)
      c.clearRect(0, 0, w, h)
      analyser.getByteFrequencyData(bins)
      let peak = 0
      for (let i = 0; i < bins.length; i += 1) if (bins[i] > peak) peak = bins[i]
      if (peak / 255 < 0.04) return
      const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#c4b5fd'
      const BARS = 56
      const slot = w / BARS
      const depth = h * 0.1
      for (let i = 0; i < BARS; i += 1) {
        const v = bins[Math.floor((i / BARS) * bins.length * 0.6)] / 255
        const hgt = Math.max(1.5, v * depth)
        const x = i * slot
        const alpha = 0.35 + v * 0.6
        c.fillStyle = `rgba(255,255,255,${alpha.toFixed(3)})`
        c.fillRect(x + slot * 0.15, 0, slot * 0.7, hgt)
        c.fillRect(x + slot * 0.15, h - hgt, slot * 0.7, hgt)
        c.globalAlpha = 0.22 + v * 0.4
        c.fillStyle = accent
        c.fillRect(x + slot * 0.15, hgt - 1, slot * 0.7, 1)
        c.fillRect(x + slot * 0.15, h - hgt, slot * 0.7, 1)
        c.globalAlpha = 1
      }
    }
    draw()
  }
  onDestroy(() => { lyricRequest += 1; if (vizRaf) cancelAnimationFrame(vizRaf) })
</script>

<svelte:window on:keydown={(event) => event.key === 'Escape' && onClose()} />
<div class:lyrics-mode={lyricsOpen} class:lyrics-fullscreen={lyricsFullscreen} class="theatre" role="dialog" aria-modal="true" aria-label="Now playing" on:mousemove={onPointerMove} on:mouseleave={onPointerLeave}>
  <div class="bg-layer" aria-hidden="true">
    {#if $settings.dynamicAmbient !== false}{#if videoUrl}<video class="bg-media" src={videoUrl} autoplay loop muted playsinline></video>{:else if artUrl}<img class="bg-media ambient-bg" src={artUrl} referrerpolicy="no-referrer" alt="" />{:else}<div class="bg-fallback ambient-bg"></div>{/if}{:else}<div class="bg-fallback"></div>{/if}
    <div class="vignette"></div>
  </div>
  <button class="dismiss" on:click={onClose} aria-label="Minimize Theatre Mode" title="Close (Esc)">⌄</button>
  {#if lyricsOpen}<button class="lyrics-expand" on:click={() => lyricsFullscreen = !lyricsFullscreen} aria-label="Toggle full-screen lyrics">{lyricsFullscreen ? '↙' : '↗'}</button>{/if}
  <main class="stage">
    {#if lyricsOpen}
      <section class="compact-player">
        <div class="art-frame small">{#if videoUrl}<video class="art" src={videoUrl} autoplay loop muted playsinline></video>{:else if artUrl}<img class="art" src={artUrl} referrerpolicy="no-referrer" alt="{clean(track.title)} artwork" />{:else}<div class="art placeholder">♫</div>{/if}</div>
        <h1>{clean(track?.title)}</h1><p>{clean(track?.artist)}</p>
        <div class="mini-controls"><button on:click={onShuffle} class:enabled={shuffle} aria-label="Shuffle">⇄</button><button on:click={onPrevious} aria-label="Previous">|◀</button><button class="mini-play" on:click={onToggle} aria-label={isPlaying ? 'Pause' : 'Play'}>{isPlaying ? 'Ⅱ' : '▶'}</button><button on:click={onNext} aria-label="Next">▶|</button><button on:click={onRepeat} class:enabled={repeat !== 'off'} aria-label="Repeat">↻</button></div>
      </section>
      <section class="lyrics-panel" aria-label="Synchronized lyrics">
        <div class="lyrics-header"><span>{lyricsSynced ? 'SYNCED LYRICS' : 'LYRICS'}</span>{#if videoLoading}<small>Loading visual…</small>{/if}</div>
        {#if lyrics.length}<div class="lyrics-scroll" bind:this={lyricsContainer}>{#each lyrics as line, index}<button class:active={index === activeLyric} class="lyric-line" on:click={() => seekLine(line.time)}>{line.text}</button>{/each}</div>{:else if plainLyrics}<div class="plain-lyrics">{plainLyrics}</div>{:else}<div class="lyrics-empty">Lyrics unavailable for this track.</div>{/if}
      </section>
    {:else}
      <div class="viz-wrap"><canvas class="viz-canvas" bind:this={vizCanvas} aria-hidden="true"></canvas><div class="art-frame" class:tilt-reset={!tiltActive} style={tiltStyle}>{#if videoUrl}<video class="art" src={videoUrl} autoplay loop muted playsinline aria-label="Video artwork"></video>{:else if artUrl}<img class="art" src={artUrl} referrerpolicy="no-referrer" alt="{clean(track?.title)} artwork" />{:else}<div class="art placeholder">♫</div>{/if}</div></div>
      <section class="metadata"><h1>{clean(track?.title)}</h1><p>{clean(track?.artist)}</p>{#if clean(track?.album)}<span>{clean(track.album)}</span>{/if}</section>
      <div class="timeline"><span>{formatTime(currentTime)}</span><input type="range" min="0" max={duration || 0} value={currentTime} step=".1" on:input={onSeek} aria-label="Seek through track" /><span>{formatTime(duration)}</span></div>
      <div class="controls"><button class:enabled={shuffle} on:click={onShuffle} aria-label="Toggle shuffle">⇄</button><button on:click={onPrevious} aria-label="Previous track">|◀</button><button class="main-control" on:click={onToggle} aria-label={isPlaying ? 'Pause' : 'Play'}>{isPlaying ? 'Ⅱ' : '▶'}</button><button on:click={onNext} aria-label="Next track">▶|</button><button class:enabled={repeat !== 'off'} on:click={onRepeat} aria-label="Repeat {repeat}">↻</button><button class="lyrics-toggle" class:enabled={lyricsOpen} on:click={toggleLyrics} aria-label="Show lyrics">“</button></div>
      {#if videoLoading}<span class="status">Loading visual…</span>{/if}
    {/if}
  </main>
</div>
<style>
.theatre{position:fixed;inset:0;z-index:100;width:100vw;height:100vh;overflow:hidden;color:#fff;background:#15151a;font-family:Inter,ui-sans-serif,system-ui,sans-serif}.bg-layer{position:absolute;top:0;left:0;width:100vw;height:100vh;z-index:-1;overflow:hidden;background:#15151a}.bg-media{width:100%;height:100%;object-fit:cover;filter:blur(60px) brightness(.4);transform:scale(1.1)}.bg-fallback{width:100%;height:100%;background:radial-gradient(circle at 35% 30%,#4c416d,#13131a 62%)}@keyframes ambientDrift{0%{transform:scale(1.1) translate(0,0)}50%{transform:scale(1.2) translate(-2%,2%)}100%{transform:scale(1.1) translate(0,0)}}.ambient-bg{animation:ambientDrift 25s ease-in-out infinite alternate}.vignette{position:absolute;inset:0;background:radial-gradient(ellipse at center,transparent 20%,#05050755 62%,#050507bb 100%);pointer-events:none}.dismiss,.lyrics-expand{position:absolute;z-index:20;width:42px;height:42px;border:1px solid #ffffff2b;border-radius:50%;color:#fff;background:#ffffff12;cursor:pointer;font-size:1.45rem;backdrop-filter:blur(20px)}.dismiss{top:24px;left:28px}.lyrics-expand{top:24px;right:28px}.dismiss:hover,.lyrics-expand:hover{background:#ffffff26}.stage{position:relative;z-index:10;display:flex;flex-direction:column;justify-content:center;align-items:center;width:100vw;height:100vh;box-sizing:border-box;padding:4rem}.lyrics-mode .stage{flex-direction:row;justify-content:space-between;align-items:center;gap:4rem}.viz-wrap{position:relative;display:grid;place-items:center}.viz-canvas{position:absolute;inset:-9%;width:118%;height:118%;z-index:0;pointer-events:none}.viz-wrap .art-frame{z-index:1}.art-frame{position:relative;width:100%;max-width:45vh;max-height:45vh;aspect-ratio:1;flex:0 0 auto;overflow:hidden;border-radius:12px;box-shadow:0 20px 40px rgba(0,0,0,.5);transform-style:preserve-3d;transition:transform .18s ease-out;will-change:transform}.art-frame.tilt-reset{transition:transform .6s cubic-bezier(.22,1,.36,1)}.art-frame:not(.small)::after{content:'';position:absolute;inset:0;border-radius:12px;background:radial-gradient(circle at var(--gx,50%) var(--gy,50%),rgba(255,255,255,.16),transparent 55%);pointer-events:none;mix-blend-mode:screen}.art-frame.small{width:100%;max-width:26vh;max-height:26vh}.art{width:100%;height:100%;display:block;object-fit:cover;border-radius:12px}@media(prefers-reduced-motion:reduce){.art-frame:not(.small){transform:none!important;transition:none}}.placeholder{display:grid;place-items:center;background:linear-gradient(135deg,#252331,#4d3640);font-size:8rem}.metadata{text-align:center;width:100%;margin-top:1.5rem}.metadata h1,.compact-player h1{margin:0;color:#fff;font-size:1.75rem;font-weight:700;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.metadata p,.compact-player p{margin:6px 0 0;color:#fff;opacity:.75;font-size:1.1rem}.metadata span{display:block;margin-top:5px;opacity:.5}.timeline{display:flex;align-items:center;gap:12px;width:min(45vh,100%);margin-top:1.5rem;color:#ffffffb8;font-size:.7rem}.timeline input{width:100%;accent-color:#fff}.controls{display:flex;justify-content:center;align-items:center;gap:1.5rem;margin-top:2rem}.mini-controls{display:flex;justify-content:center;align-items:center;gap:1.5rem;margin-top:2rem}.controls button,.mini-controls button{border:0;color:#fff;background:none;cursor:pointer;font-size:1.2rem;opacity:.82;transition:.2s}.controls button:hover,.mini-controls button:hover{opacity:1;transform:scale(1.1)}.controls button.enabled,.mini-controls button.enabled{color:#d8c8ff;text-shadow:0 0 16px #b99cff}.main-control,.mini-play{display:grid;place-items:center;width:64px;height:64px;border-radius:50%;color:#111!important;background:#fff!important;font-size:1.35rem!important;opacity:1!important}.lyrics-toggle{font-size:1.5rem!important}.status{margin-top:1rem;color:#fff9;font-size:.75rem}.compact-player{flex:0 1 auto;display:flex;flex-direction:column;align-items:center;text-align:center;max-width:34vw}.compact-player h1{max-width:100%;margin-top:20px;font-size:1.35rem}.compact-player p{font-size:.95rem}.mini-controls{gap:1.25rem;margin-top:1.25rem}.mini-play{width:48px;height:48px;font-size:1rem!important}.lyrics-panel{flex:1;min-width:0;height:80vh;display:flex;flex-direction:column;padding:2vh 0 2vh 2vw}.lyrics-header{display:flex;justify-content:space-between;color:#ffffff99;font-size:.7rem;font-weight:700;letter-spacing:.15em;flex:0 0 auto}.lyrics-header small{letter-spacing:0;font-weight:400}.lyrics-scroll{flex:1;min-height:0;height:100%;overflow-y:scroll;scroll-behavior:smooth;padding:40vh 0;scrollbar-width:none}.lyrics-scroll::-webkit-scrollbar{display:none}.lyric-line{display:block;width:100%;padding:.8rem 0;border:0;color:#fff;background:none;text-align:left;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Roboto,sans-serif;font-size:clamp(2rem,3.8vw,3.25rem);font-weight:700;letter-spacing:-.02em;line-height:1.35;opacity:.3;filter:blur(1.5px);transform:scale(1);cursor:pointer;transition:all .3s ease}.lyric-line.active{opacity:1;filter:none;transform:scale(1.02);transform-origin:left center;color:#fff;text-shadow:0 10px 30px rgba(0,0,0,.5);transition:all .3s ease}.plain-lyrics{flex:1;min-height:0;padding-top:30px;max-width:800px;color:rgba(255,255,255,.6);font-size:clamp(1.5rem,2.5vw,2.25rem);line-height:1.6;white-space:pre-wrap;overflow:auto}.lyrics-empty{display:grid;place-items:center;flex:1;min-height:0;text-align:center;color:#fff;opacity:.5;font-size:1.5rem;padding:0 2vw}.lyrics-fullscreen .stage{justify-content:center}.lyrics-fullscreen .compact-player{display:none}.lyrics-fullscreen .lyrics-panel{max-width:1000px;margin:auto;padding:2vh 0}.lyrics-fullscreen .lyric-line{text-align:center;transform-origin:center}.lyrics-fullscreen .lyric-line.active{transform:scale(1.02)}@media(max-height:620px){.stage{padding:3.5rem 3rem}.art-frame{max-width:38vh;max-height:38vh}.metadata{margin-top:.75rem}.timeline{margin-top:.75rem}.controls{margin-top:1rem}.lyrics-panel{height:84vh}}@media(max-width:720px){.dismiss{top:16px;left:16px}.lyrics-expand{top:16px;right:16px}.stage{padding:4.5rem 1.25rem 2rem}.lyrics-mode .stage{flex-direction:column;justify-content:flex-start;gap:2rem;overflow:auto}.compact-player{max-width:100%}.lyrics-panel{width:100%;height:60vh;padding:0}.lyric-line{font-size:clamp(1.5rem,8vw,2.4rem)}}
</style>