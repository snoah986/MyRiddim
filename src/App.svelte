<script>
  import { onMount, onDestroy } from 'svelte'
  import { spring } from 'svelte/motion'
  import { fade } from 'svelte/transition'
  import { get } from 'svelte/store'
  import { openPlaylist } from './lib/store.js'
  import { settings } from './lib/settings.js'
  import SettingsModal from './components/SettingsModal.svelte'
  import SongPage from './pages/SongPage.svelte'
  import TheatreMode from './pages/TheatreMode.svelte'
  import TrackContextMenu from './components/TrackContextMenu.svelte'
  import MediaShelf from './components/MediaShelf.svelte'
  import WindowControls from './components/WindowControls.svelte'
  import { audio } from './lib/audio.js'
  import { queue, hydrateQueue, persistQueue, seed, selectNext, selectPrevious, playUpcoming, playNext, addToQueue, removeUpcoming, clearUpcoming, reorderUpcoming, toggleShuffle, cycleRepeat } from './lib/queue.js'

  const playPulse = spring(1, { stiffness: 320, damping: 14 })
  let pipWindow = null, accent = '#c4b5fd'

  let playlists = [], full = null, checking = true, authenticated = false
  let authText = '', authError = '', connecting = false, actionTrack = null, showAddModal = false, editing = false, editTitle = '', editDescription = ''
  let currentTrack = null, currentIndex = -1, theatreOpen = false, toast = '', toastTimer, activeQueue = { history: [], nowPlaying: null, upNext: [], repeat: 'off', shuffle: false }, isPlaying = false, currentTime = 0, duration = 0, volume = 1, loadingTrack = false, listenRecorded = false, queueOpen = false, draggedIndex = -1
  let quickPicks = [], stats = { month: '', totalMinutes: 0, monthly: [], heavyRotation: [] }, quickScroller, searchQuery = '', searchResults = [], searchTimer, searching = false, showCreate = false, newTitle = '', newDescription = '', preloadedTrackId = null
  let settingsOpen = false
  let homeView = 'all', likedTracks = [], likedLoaded = false, likedLoading = false, likedError = ''
  let sessionState = 'ok', playlistsLoaded = false, playlistsError = '', justSwitched = false, justSwitchTimer
  let restoring = null, sessionBannerDismissed = false, lastPersist = 0
  let unsubscribe, queueUnsubscribe
  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const formatTime = seconds => { if (!Number.isFinite(seconds)) return '0:00'; return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}` }

  async function health() { const response = await fetch('/api/health'); if (!response.ok) throw Error('Could not reach the backend.'); return response.json() }
  async function loadPlaylists() {
    playlistsError = ''
    try {
      const response = await fetch('/api/playlists')
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not load playlists.')
      playlists = data
    } catch (error) { playlistsError = error.message } finally { playlistsLoaded = true }
  }
  async function connect() { authError = ''; connecting = true; try { const response = await fetch('/api/auth/setup', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({auth: authText}) }); const data = await response.json(); if (!response.ok || data.error) throw Error(data.error); authenticated = true; sessionState = 'ok'; authText = ''; await loadPlaylists() } catch (error) { authError = error.message } finally { connecting = false } }
  async function loadDiscovery() {
    const [quickResponse, statsResponse] = await Promise.all([fetch('/api/home/quick-picks'), fetch('/api/stats/monthly-top')])
    if (quickResponse.ok) quickPicks = (await quickResponse.json()).tracks || []
    if (statsResponse.ok) stats = await statsResponse.json()
    // Nothing playing yet: let the first recommendation color the page.
    if (!currentTrack && quickPicks[0]?.thumbnail) extractAccent(quickPicks[0].thumbnail)
  }
  function setHomeView(view) { homeView = view; if (view === 'favorites' && !likedLoaded) loadLiked() }
  async function loadLiked() {
    likedLoading = true
    likedError = ''
    try {
      const response = await fetch('/api/liked')
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not load favorites.')
      likedTracks = data.tracks || []
      likedLoaded = true
    } catch (error) {
      // Never cache a failure: keep likedLoaded false so Retry actually refetches.
      likedTracks = []
      likedLoaded = false
      likedError = error.message || 'Could not load favorites.'
      refreshSession()
    } finally { likedLoading = false }
  }
  async function refreshSession() {
    try {
      const state = await health()
      sessionState = state.session || (state.authenticated ? 'ok' : 'unauthenticated')
    } catch { /* keep the previous state on network failure */ }
  }
  function playQueueShuffled(tracks) {
    const list = [...(tracks || [])]
    for (let i = list.length - 1; i > 0; i -= 1) { const j = Math.floor(Math.random() * (i + 1)); [list[i], list[j]] = [list[j], list[i]] }
    playQueue(list)
  }

  function playNextTrack(track) { const t = normalizePlayable(track); if (t) { playNext(t); showToast('Playing next') } }
  function appendTrack(track) { const t = normalizePlayable(track); if (t) { addToQueue(t); showToast('Added to queue') } }
  function openAddModal(track) { actionTrack = normalizePlayable(track); showAddModal = true }
  async function addTrackToPlaylist(playlistId) {
    if (!actionTrack?.videoId) return
    const target = actionTrack
    showAddModal = false
    try { const response = await fetch('/api/playlist/add-track', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({playlist_id: playlistId, video_id: target.videoId})}); if (!response.ok) throw Error(); showToast('Added to playlist') } catch { showToast('Could not add to playlist') }
  }
  async function removeTrackFromPlaylist(track) { if (!full?.owned) return; const previous = full.tracks; full = {...full, tracks: previous.filter(item => item.videoId !== track.videoId)}; try { const response = await fetch('/api/playlist/remove-track', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({playlist_id:full.id, video_id:track.videoId})}); if (!response.ok) throw Error(); showToast('Removed from playlist') } catch { full = {...full, tracks: previous}; showToast('Could not remove track') } }
  async function savePlaylistEdit() { const previous = full; full = {...full, title:editTitle.trim() || full.title, description:editDescription}; editing = false; try { const response = await fetch('/api/playlist/edit', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({playlist_id:previous.id, title:full.title, description:full.description})}); if (!response.ok) throw Error(); showToast('Playlist updated') } catch { full = previous; showToast('Could not update playlist') } }
  async function deleteCurrentPlaylist() { if (!full?.owned || !confirm(`Delete ${full.title}?`)) return; const deleted = full; full = null; playlists = playlists.filter(item => item.id !== deleted.id); try { const response = await fetch('/api/playlist/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({playlist_id:deleted.id})}); if (!response.ok) throw Error(); showToast('Playlist deleted') } catch { playlists = [deleted, ...playlists]; showToast('Could not delete playlist') } }
  function normalizePlayable(track) {
    const videoId = track?.videoId || track?.id
    if (!videoId) { console.warn('Cannot play track: missing videoId/id', track); return null }
    return { ...track, id: videoId, videoId }
  }
  function extractAccent(url) {
    if (!url) return
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.referrerPolicy = 'no-referrer'
    img.onload = () => {
      try {
        const size = 32
        const canvas = document.createElement('canvas')
        canvas.width = size; canvas.height = size
        const ctx = canvas.getContext('2d')
        ctx.drawImage(img, 0, 0, size, size)
        const { data } = ctx.getImageData(0, 0, size, size)
        // dominant average (drives buttons/sliders) + vivid average of saturated
        // pixels (drives the ambient page glow, YouTube-Music style)
        let r = 0, g = 0, b = 0, n = 0
        let vr = 0, vg = 0, vb = 0, vn = 0
        for (let i = 0; i < data.length; i += 4) {
          const pr = data[i], pg = data[i + 1], pb = data[i + 2], pa = data[i + 3]
          if (pa < 128) continue
          const lum = 0.299 * pr + 0.587 * pg + 0.114 * pb
          if (lum < 20 || lum > 235) continue
          r += pr; g += pg; b += pb; n += 1
          const mx = Math.max(pr, pg, pb), mn = Math.min(pr, pg, pb)
          if (mx - mn > 70 && lum > 35 && lum < 225) { vr += pr; vg += pg; vb += pb; vn += 1 }
        }
        if (n > 0) {
          accent = `rgb(${Math.round(r / n)}, ${Math.round(g / n)}, ${Math.round(b / n)})`
          document.documentElement.style.setProperty('--accent', accent)
          const ambient = vn > 0 ? `rgb(${Math.round(vr / vn)}, ${Math.round(vg / vn)}, ${Math.round(vb / vn)})` : accent
          document.documentElement.style.setProperty('--ambient', ambient)
        }
      } catch { /* artwork accents are cosmetic; ignore failures */ }
    }
    img.src = url
  }
  function pulsePlay() { playPulse.set(0.8); setTimeout(() => playPulse.set(1), 100) }
  async function togglePip() {
    if (pipWindow) { pipWindow.close(); pipWindow = null; return }
    if (!('documentPictureInPicture' in window)) { showToast('Mini player is not supported in this browser'); return }
    try {
      pipWindow = await window.documentPictureInPicture.requestWindow({ width: 380, height: 240 })
      pipWindow.document.title = 'Now Playing'
      pipWindow.document.body.innerHTML = `<div class="pip"><div class="pip-top"><img id="pip-art" alt="" /><div class="pip-meta"><strong id="pip-title"></strong><span id="pip-artist"></span></div><button id="pip-close" title="Close mini player">×</button></div><div class="pip-controls"><button id="pip-prev">|◀</button><button id="pip-play" class="pip-play">▶</button><button id="pip-next">▶|</button></div><div class="pip-seek"><span id="pip-time">0:00</span><input id="pip-seek" type="range" min="0" max="0" value="0" step="0.1" /><span id="pip-dur">0:00</span></div></div>`
      const style = pipWindow.document.createElement('style')
      style.textContent = `body{margin:0;background:#101014;color:#f4f4f5;font-family:Inter,ui-sans-serif,system-ui,sans-serif}.pip{display:flex;flex-direction:column;height:100vh;box-sizing:border-box;padding:16px;background:radial-gradient(ellipse at 15% 0%,var(--accent,#c4b5fd)22,transparent 45%),#101014}.pip-top{display:flex;align-items:center;gap:12px}.pip-top img{width:64px;height:64px;border-radius:10px;object-fit:cover;background:#252331}.pip-meta{flex:1;min-width:0}.pip-meta strong,.pip-meta span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pip-meta strong{font-size:.95rem}.pip-meta span{color:#a1a1aa;font-size:.78rem;margin-top:3px}#pip-close{border:0;background:none;color:#aaa;font-size:1.3rem;cursor:pointer}.pip-controls{display:flex;justify-content:center;align-items:center;gap:26px;margin-top:auto;padding:10px 0}.pip-controls button{border:0;background:none;color:#ddd;font-size:1.15rem;cursor:pointer}.pip-play{width:52px;height:52px;border-radius:50%;color:#111!important;background:#fff!important}.pip-seek{display:flex;align-items:center;gap:10px;color:#a1a1aa;font-size:.7rem}.pip-seek input{flex:1;accent-color:var(--accent,#c4b5fd)}`
      pipWindow.document.head.appendChild(style)
      pipWindow.document.getElementById('pip-play').addEventListener('click', togglePlay)
      pipWindow.document.getElementById('pip-prev').addEventListener('click', previous)
      pipWindow.document.getElementById('pip-next').addEventListener('click', next)
      pipWindow.document.getElementById('pip-close').addEventListener('click', () => togglePip())
      pipWindow.document.getElementById('pip-seek').addEventListener('input', seek)
      pipWindow.addEventListener('pagehide', () => { pipWindow = null })
      syncPip()
    } catch { showToast('Could not open mini player') }
  }
  function syncPip() {
    if (!pipWindow?.document) return
    const doc = pipWindow.document
    const art = doc.getElementById('pip-art')
    if (art) { if (currentTrack?.thumbnail) art.src = currentTrack.thumbnail; else art.style.display = 'none' }
    doc.getElementById('pip-title').textContent = clean(currentTrack?.title) || ''
    doc.getElementById('pip-artist').textContent = clean(currentTrack?.artist) || ''
    doc.getElementById('pip-play').textContent = isPlaying ? '❚❚' : '▶'
    doc.getElementById('pip-time').textContent = formatTime(currentTime)
    doc.getElementById('pip-dur').textContent = formatTime(duration)
    const seekEl = doc.getElementById('pip-seek')
    if (seekEl) { seekEl.max = duration || 0; seekEl.value = currentTime }
    if (accent) doc.documentElement.style.setProperty('--accent', accent)
  }
  function playQueue(tracks, index = 0) {
    const normalized = (tracks || []).map(normalizePlayable).filter(Boolean)
    if (!normalized[index]) { console.warn('Cannot start queue: selected track has no video ID', tracks?.[index]); return }
    seed(normalized, index)
  }

  async function open(pl) { try { const response = await fetch(`/api/playlist/${pl.id}`); const data = await response.json(); if (!response.ok || data.error) throw Error(data.error || 'Could not open playlist.'); full = data; openPlaylist.set({id: pl.id, title: data.title ?? pl.title}) } catch (error) { authError = error.message } }

  async function playTrack(track, index = 0, playlist = full) {
    track = normalizePlayable(track)
    if (!track) return
    currentTrack = track; currentIndex = index; listenRecorded = false; preloadedTrackId = null; loadingTrack = true
    // A recent track switch means a stream load failure is handled by playTrack's
    // own catch (and would double-advance if the error listener also fired).
    justSwitched = true
    clearTimeout(justSwitchTimer)
    justSwitchTimer = setTimeout(() => { justSwitched = false }, 1500)
    // After a crossfade the engine is already playing this track (gapless);
    // skip the redundant stream resolution entirely.
    if (audio.gapFilled && track.videoId === activeQueue.nowPlaying?.videoId) { isPlaying = true; return }
    try { const response = await fetch(`/api/stream/${track.videoId}?quality=${get(settings).quality}`); const data = await response.json(); if (!response.ok || data.error) { console.error("Stream resolution failed:", data.error); throw Error(data.error || 'Could not resolve audio stream.'); } audio.src = data.url; if (restoring && restoring.videoId === track.videoId) { audio.currentTime = Math.max(0, restoring.position || 0); restoring = null; isPlaying = false } else { await audio.play(); isPlaying = true } } catch (error) { console.error('playTrack failed:', error); isPlaying = false; showToast('Track unavailable'); if (activeQueue.upNext.length) selectNext() } finally { loadingTrack = false }
  }
  function showToast(message) { toast = message; clearTimeout(toastTimer); toastTimer = setTimeout(() => toast = '', 4000) }
  // --- session persistence (queue lives in lib/queue.js; here: volume + position) ---
  const PLAYER_KEY = 'ymt.player'
  function savePlayerState() {
    try { localStorage.setItem(PLAYER_KEY, JSON.stringify({ videoId: currentTrack?.videoId || null, position: Number.isFinite(audio.currentTime) ? audio.currentTime : 0, volume })) } catch { /* storage unavailable */ }
  }
  function loadPlayerState() {
    try { return JSON.parse(localStorage.getItem(PLAYER_KEY)) } catch { return null }
  }
  // Keep the audio engine in sync with the playback-related settings.
  $: audio.setFade($settings.crossfade ? Math.min(12, Math.max(0, $settings.crossfadeDuration || 0)) : 0)
  $: audio.setNormalize(!!$settings.volumeNormalize)
  async function refreshAfterAuth() { try { await Promise.all([loadPlaylists(), loadDiscovery()]) } catch { /* refresh is best-effort */ } }
  async function reauthenticate() {
    if (!confirm('Disconnect your YouTube Music account? You can reconnect by pasting browser.json again.')) return
    try {
      const response = await fetch('/api/auth/logout', { method: 'POST' })
      if (!response.ok) throw Error()
      audio?.pause()
      settingsOpen = false
      playlists = []
      full = null
      currentTrack = null
      authenticated = false
      checking = false
      showToast('Account disconnected')
    } catch { showToast('Could not disconnect account') }
  }
  async function preloadNext() {
    if (activeQueue.repeat === 'one') return
    const nextTrack = activeQueue.upNext?.[0]
    if (!nextTrack?.videoId) return
    try {
      const response = await fetch(`/api/stream/${nextTrack.videoId}?quality=${get(settings).quality}`)
      const data = await response.json()
      if (!data.error && data.url) audio.preload(data.url)
    } catch { /* preloading the next track is best-effort */ }
  }
  function searchChanged() { clearTimeout(searchTimer); if (!searchQuery.trim()) { searchResults = []; searching = false; return } searching = true; searchTimer = setTimeout(async () => { try { const response = await fetch(`/api/search?q=${encodeURIComponent(searchQuery)}`); const data = await response.json(); if (!response.ok || data.error) throw Error(data.error || `Search failed (${response.status})`); searchResults = data.results || [] } catch (error) { console.error('Search failed:', error); searchResults = []; showToast('Search unavailable') } finally { searching = false } }, 300) }
  $: songResults = searchResults.filter(r => r.type === 'song')
  $: albumResults = searchResults.filter(r => r.type === 'album')
  $: artistResults = searchResults.filter(r => r.type === 'artist')
  $: playlistResults = searchResults.filter(r => r.type === 'playlist')
  $: browseResults = searchResults.filter(r => !['song', 'album', 'artist', 'playlist'].includes(r.type))
  function focusSearch(event) { if ((event.ctrlKey && event.key.toLowerCase() === 'k') || (event.key === '/' && !['INPUT','TEXTAREA'].includes(event.target.tagName))) { event.preventDefault(); document.querySelector('.global-search')?.focus() } }
  function handleGlobalKeydown(event) { focusSearch(event); if (event.key === ' ' && currentTrack && event.target.tagName === 'BODY') { event.preventDefault(); togglePlay() } }
  async function createPlaylist() { if (!newTitle.trim()) return; try { const response = await fetch('/api/playlist/create', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:newTitle, description:newDescription})}); const data = await response.json(); if (!response.ok || data.error) throw Error(data.error); playlists = [{id:data.id, title:newTitle.trim(), count:0, thumbnail:null}, ...playlists]; showCreate = false; newTitle = ''; newDescription = ''; showToast('Playlist created') } catch (error) { showToast('Could not create playlist') } }
  function togglePlay() { if (!audio || !currentTrack) return; pulsePlay(); if (isPlaying) audio.pause(); else audio.play().catch(error => authError = error.message) }
  function next() { if (activeQueue.repeat === 'one' && currentTrack) { audio.currentTime = 0; audio.play(); return } if (activeQueue.upNext.length) selectNext(); else if (activeQueue.repeat === 'all' && activeQueue.history.length) seed([...activeQueue.history, activeQueue.nowPlaying], 0) }
  function previous() { if (audio?.currentTime > 3) audio.currentTime = 0; else selectPrevious() }
  function jumpTo(track) { playUpcoming(track); queueOpen = false }
  function dragStart(index) { draggedIndex = index }
  function dropAt(index) { reorderUpcoming(draggedIndex, index); draggedIndex = -1 }
  async function recordListen() {
    if (!currentTrack || listenRecorded) return
    listenRecorded = true
    await fetch('/api/track/listen', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({video_id: currentTrack.videoId, title: currentTrack.title, artist: currentTrack.artist, album: currentTrack.album, thumbnail_url: currentTrack.thumbnail, listen_duration_seconds: Math.round(currentTime)}) })
    loadDiscovery().catch(() => {})
  }
  function seek(event) { if (audio) audio.currentTime = Number(event.currentTarget.value) }
  function setVolume(event) { volume = Number(event.currentTarget.value); if (audio) audio.volume = volume; savePlayerState() }
  // Media Session API: physical media keys (Play/Pause/Next/Previous) control the
  // app in the browser and inside the Tauri webview (WebView2 supports it).
  function wireMediaSession() {
    if (!('mediaSession' in navigator)) return
    const updateMetadata = () => {
      try {
        navigator.mediaSession.metadata = new MediaMetadata({
          title: clean(currentTrack?.title) || '',
          artist: clean(currentTrack?.artist) || '',
          album: clean(currentTrack?.album) || '',
          artwork: currentTrack?.thumbnail ? [{ src: currentTrack.thumbnail, sizes: '512x512' }] : [],
        })
        navigator.mediaSession.setPositionState?.({ duration: duration || 0, position: Math.min(currentTime || 0, duration || 0), playbackRate: 1 })
      } catch { /* MediaMetadata is best-effort */ }
    }
    navigator.mediaSession.setActionHandler('play', () => { if (!isPlaying) togglePlay() })
    navigator.mediaSession.setActionHandler('pause', () => { if (isPlaying) togglePlay() })
    navigator.mediaSession.setActionHandler('nexttrack', next)
    navigator.mediaSession.setActionHandler('previoustrack', previous)
    navigator.mediaSession.setActionHandler('seekto', (details) => { if (details.seekTime != null) audio.currentTime = details.seekTime })
    window.__updateMediaSession = updateMetadata
    updateMetadata()
  }

  onMount(async () => {
    // Restore the previous session: volume, queue, and playback position.
    const savedPlayer = loadPlayerState()
    if (savedPlayer && Number.isFinite(savedPlayer.volume)) { volume = savedPlayer.volume; audio.volume = savedPlayer.volume }
    const savedQueue = hydrateQueue()
    if (savedQueue) {
      restoring = { videoId: savedQueue.nowPlaying?.videoId, position: savedQueue.nowPlaying?.videoId === savedPlayer?.videoId ? (savedPlayer?.position || 0) : 0 }
      queue.set(savedQueue)
    }
    window.addEventListener('pagehide', savePlayerState)
    wireMediaSession()
    audio.addEventListener('play', () => { isPlaying = true; syncPip(); window.__updateMediaSession?.() })
    audio.addEventListener('pause', () => { if (!loadingTrack) isPlaying = false; savePlayerState(); syncPip(); window.__updateMediaSession?.() })
    audio.addEventListener('timeupdate', () => { currentTime = audio.currentTime; if (currentTime >= 30) recordListen(); const now = Date.now(); if (now - lastPersist > 5000) { lastPersist = now; savePlayerState() } const upcoming = activeQueue.upNext?.[0]; if (upcoming?.videoId && preloadedTrackId !== upcoming.videoId && duration > 0 && duration - currentTime <= 20) { preloadedTrackId = upcoming.videoId; preloadNext() } syncPip(); window.__updateMediaSession?.() })
    audio.addEventListener('loadedmetadata', () => { duration = audio.duration; syncPip(); window.__updateMediaSession?.() })
    audio.addEventListener('ended', () => { savePlayerState(); next() })
    audio.addEventListener('error', () => { if (loadingTrack || justSwitched || !currentTrack) return; showToast('Playback stalled'); if (activeQueue.upNext.length) selectNext() })
    queueUnsubscribe = queue.subscribe(value => { activeQueue = value; currentTrack = value.nowPlaying; persistQueue(value); if (value.nowPlaying && value.nowPlaying.videoId !== audio.dataset.track) { audio.dataset.track = value.nowPlaying.videoId; playTrack(value.nowPlaying, 0); extractAccent(value.nowPlaying.thumbnail) } syncPip(); window.__updateMediaSession?.() })
    unsubscribe = openPlaylist.subscribe(value => { if (value === null) full = null })
    try {
      const state = await health()
      authenticated = state.authenticated === true || state.session === 'expired'
      sessionState = state.session || (state.authenticated ? 'ok' : 'unauthenticated')
      if (authenticated) { await loadPlaylists(); await loadDiscovery() }
    } catch (error) { authError = error.message } finally { checking = false }
  })
  onDestroy(() => { unsubscribe?.(); queueUnsubscribe?.(); clearTimeout(toastTimer); clearTimeout(justSwitchTimer); window.removeEventListener('pagehide', savePlayerState); audio?.pause() })
</script>

<svelte:window on:keydown={handleGlobalKeydown} />

<main class:with-player={currentTrack}><div class="ambient-blob" aria-hidden="true"></div>
  {#if checking}<section class="loading"><span class="spinner"></span><p>Checking your account…</p></section>
  {:else if !authenticated}<section class="setup" aria-labelledby="setup-title"><div class="setup-mark">♫</div><p class="eyebrow">MY MUSIC</p><h1 id="setup-title">Connect your YouTube Music</h1><p class="intro">Paste your <code>browser.json</code> contents or raw authentication headers to load your library.</p><textarea bind:value={authText} placeholder="Paste browser.json or request headers here…" aria-label="YouTube Music authentication data"></textarea>{#if authError}<p class="error" role="alert">{authError}</p>{/if}<button class="connect" disabled={connecting || !authText.trim()} on:click={connect}>{connecting ? 'Connecting…' : 'Connect Account'}</button></section>
  {:else if full}<div in:fade={{ duration: 200 }} out:fade={{ duration: 120 }}><SongPage playlist={full} track={currentTrack} onTrack={(track, index) => { if (activeQueue.nowPlaying?.videoId === track.videoId) togglePlay(); else { seed(full.tracks, index) } }} onPlay={() => full?.tracks?.[0] && playQueue(full.tracks)} onShuffle={() => playQueueShuffled(full?.tracks)} onPlayNext={playNextTrack} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} onRemoveTrack={removeTrackFromPlaylist} /></div>
  {:else}<div in:fade={{ duration: 220 }} out:fade={{ duration: 140 }} class="view-transition"><div class="home-head" data-tauri-drag-region><div class="search-wrap"><input class="global-search" bind:value={searchQuery} on:input={searchChanged} placeholder="Search YouTube Music" aria-label="Search YouTube Music" /><kbd>Ctrl K</kbd></div><div><p class="eyebrow">YOUR LIBRARY</p><h1>My Music</h1></div>{#if sessionState === 'expired'}<button class="status expired" on:click={reauthenticate} title="Reconnect your YouTube Music session">⚠ Session expired — Reconnect</button>{:else}<span class="status">● Connected</span>{/if}<button class="new-playlist" on:click={() => showCreate = true}>＋ New Playlist</button><button class="settings-toggle" on:click={() => settingsOpen = true} aria-label="Open settings" title="Settings">⚙</button><WindowControls /></div>{#if authError}<p class="error" role="alert">{authError}</p>{/if}
    {#if sessionState === 'expired' && !sessionBannerDismissed}<div class="session-banner" role="alert"><span>⚠ Your YouTube Music session has expired.</span><button class="banner-link" on:click={reauthenticate}>Re-authenticate in Settings</button><button class="banner-close" on:click={() => sessionBannerDismissed = true} aria-label="Dismiss session notice">×</button></div>{/if}
    {#if searching}<p class="search-status" in:fade={{ duration: 120 }}>Searching…</p>{:else if searchResults.length}<section class="search-results" in:fade={{ duration: 240 }}><div class="section-head"><div><p class="eyebrow">SEARCH RESULTS</p><h2>{searchQuery}</h2></div></div>{#if songResults.length}<section class="search-shelf"><h3>Songs</h3><div class="song-list">{#each songResults as r, i (r.videoId || i)}<div class="song-row"><button class="song-main" on:click={() => playQueue([r])}><span class="song-art">{#if r.thumbnail}<img src={r.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="song-meta"><strong>{clean(r.title)}</strong><small>{clean(r.artist)}</small></span><span class="song-dur">{r.duration || '—'}</span><span class="song-play">▶</span></button><TrackContextMenu track={r} onPlayNext={playNextTrack} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} /></div>{/each}</div></section>{/if}{#if albumResults.length || artistResults.length || browseResults.length}<section class="search-shelf"><h3>Albums &amp; Artists</h3><div class="card-row">{#each [...albumResults, ...artistResults, ...browseResults] as r, i (r.id || r.title || i)}<button class="browse-card" on:click={() => showToast('Open on YouTube Music to browse this artist or album')}><div class="card-art">{#if r.thumbnail}<img src={r.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</div><strong>{clean(r.title)}</strong><span>{clean(r.artist || r.type)}</span></button>{/each}</div></section>{/if}{#if playlistResults.length}<section class="search-shelf"><h3>Playlists</h3><div class="card-row">{#each playlistResults as r, i (r.id || r.title || i)}<button class="browse-card" on:click={() => open({id: r.id, title: r.title})}><div class="card-art">{#if r.thumbnail}<img src={r.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</div><strong>{clean(r.title)}</strong><span>{clean(r.artist || 'Playlist')}</span></button>{/each}</div></section>{/if}</section>{/if}
    <div class="chips" role="tablist" aria-label="Browse your library">
      <button class="chip" class:active={homeView === 'all'} on:click={() => setHomeView('all')}>All</button>
      <button class="chip" class:active={homeView === 'recent'} on:click={() => setHomeView('recent')}>Recently Played</button>
      <button class="chip" class:active={homeView === 'favorites'} on:click={() => setHomeView('favorites')}>Favorites</button>
      <button class="chip" class:active={homeView === 'discover'} on:click={() => setHomeView('discover')}>Discover</button>
    </div>
    {#if homeView === 'all' || homeView === 'recent'}
    <section class="rotation"><div><p class="eyebrow">{stats.month || 'THIS MONTH'}</p><h2>Heavy Rotation</h2><p class="rotation-copy">{stats.totalMinutes} minutes listened</p></div>{#if stats.monthly[0]}<button class="recap" on:click={() => playQueue(stats.monthly)}><div class="recap-art">{#if stats.monthly[0].thumbnail}<img src={stats.monthly[0].thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</div><div><strong>{clean(stats.monthly[0].title)}</strong><span>{clean(stats.monthly[0].artist)}</span></div><b>▶</b></button>{/if}{#if stats.heavyRotation[0]}<button class="recap" on:click={() => playQueue(stats.heavyRotation)}><div class="recap-art">{#if stats.heavyRotation[0].thumbnail}<img src={stats.heavyRotation[0].thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</div><div><strong>On Repeat</strong><span>{clean(stats.heavyRotation[0].title)}</span></div><b>▶</b></button>{/if}</section>
    {/if}
    {#if homeView === 'recent' && stats.heavyRotation.length}<MediaShelf eyebrow="ALL TIME" title="Your Heavy Rotation" tracks={stats.heavyRotation} onPlayTrack={(t, i) => playQueue(stats.heavyRotation, i)} />{/if}
    {#if homeView === 'all' || homeView === 'discover'}
    {#if quickPicks.length}<section class="quick"><div class="section-head"><div><p class="eyebrow">MADE FOR YOU</p><h2>Quick Picks</h2></div><div class="carousel-controls"><span>{quickPicks.length} recommendations</span><button on:click={() => quickScroller?.scrollBy({left:-340, behavior:'smooth'})} aria-label="Scroll Quick Picks left">‹</button><button on:click={() => quickScroller?.scrollBy({left:340, behavior:'smooth'})} aria-label="Scroll Quick Picks right">›</button></div></div><div class="quick-row" bind:this={quickScroller}>{#each quickPicks as t, i (i)}<button class="quick-card" on:click={() => playQueue(quickPicks, i)}><div class="quick-art">{#if t.thumbnail}<img src={t.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}<i>▶</i></div><strong>{clean(t.title)}</strong><span>{clean(t.artist)}</span></button>{/each}</div></section>{/if}
    {/if}
    {#if homeView === 'favorites'}
    {#if likedTracks.length}<MediaShelf eyebrow="FROM YOUR LIBRARY" title="Favorites" tracks={likedTracks} onPlayTrack={(t, i) => playQueue(likedTracks, i)} />
    {:else if likedLoading}<p class="empty-shelf">Loading favorites…</p>
    {:else if likedError}<div class="empty-shelf library-empty"><strong>{sessionState === 'expired' ? 'Your session has expired' : 'Could not load favorites'}</strong><span>{likedError}</span><div class="chip-row"><button class="chip" on:click={loadLiked}>Retry</button><button class="chip" on:click={reauthenticate}>Reconnect</button></div></div>
    {:else}<p class="empty-shelf">No favorites yet.</p>{/if}
    {/if}
    {#if homeView === 'all'}
    {#if playlistsError}<div class="empty-shelf library-empty"><strong>Could not load your library</strong><span>{playlistsError}</span><div class="chip-row"><button class="chip" on:click={loadPlaylists}>Retry</button></div></div>
    {:else if playlists.length}<div class="pl-grid">{#each playlists as p (p.id)}<button class="pl" on:click={() => open(p)}><div class="pl-art">{#if p.thumbnail}<img src={p.thumbnail} referrerpolicy="no-referrer" alt="" loading="lazy" />{:else}<span>♫</span>{/if}<span class="float-play">▶</span></div><div class="pl-title">{clean(p.title)}</div><div class="pl-count">{p.count} tracks</div></button>{/each}</div>
    {:else if playlistsLoaded}<div class="empty-shelf library-empty"><strong>{sessionState === 'expired' ? 'Your session may have expired' : 'No playlists yet'}</strong><span>{sessionState === 'expired' ? 'Reconnect to restore your library from YouTube Music.' : 'Create your first playlist with ＋ New Playlist.'}</span>{#if sessionState === 'expired'}<div class="chip-row"><button class="chip" on:click={reauthenticate}>Reconnect</button></div>{/if}</div>{/if}
    {/if}</div>{/if}</main>
{#if showCreate}<div class="modal-backdrop"><form class="modal" on:submit|preventDefault={createPlaylist}><h2>New Playlist</h2><input bind:value={newTitle} placeholder="Playlist name" required /><textarea bind:value={newDescription} placeholder="Description (optional)"></textarea><div><button type="button" on:click={() => showCreate = false}>Cancel</button><button class="primary" type="submit">Create</button></div></form></div>{/if}
{#if showAddModal}<div class="modal-backdrop" on:click|self={() => showAddModal = false}><div class="modal picker"><h2>Add to Playlist</h2><p class="picker-track">{clean(actionTrack?.title)} — {clean(actionTrack?.artist)}</p><div class="picker-list">{#each playlists.filter(p => p.owned) as p (p.id)}<button class="picker-item" on:click={() => addTrackToPlaylist(p.id)}><span class="picker-art">{#if p.thumbnail}<img src={p.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="picker-name">{clean(p.title)}</span><span class="picker-count">{p.count}</span></button>{/each}{#if !playlists.some(p => p.owned)}<p class="picker-empty">No editable playlists found. Create one first.</p>{/if}</div><div class="picker-foot"><button type="button" on:click={() => showAddModal = false}>Cancel</button></div></div></div>{/if}
{#if settingsOpen}<SettingsModal onClose={() => settingsOpen = false} onDisconnect={reauthenticate} onToast={showToast} onDataRefresh={refreshAfterAuth} />{/if}
{#if toast}<div class="toast" role="status">{toast}</div>{/if}
{#if currentTrack}<section class="player" aria-label="Now playing"><div class="now"><div class="mini-art">{#if currentTrack.thumbnail}<img src={currentTrack.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</div><div class="now-meta"><strong>{clean(currentTrack.title)}</strong><span>{clean(currentTrack.artist)}</span></div><TrackContextMenu class="now-menu" track={currentTrack} up onPlayNext={playNextTrack} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} /></div><div class="controls"><button on:click={previous} aria-label="Previous">|◀</button><button class="pause" on:click={togglePlay} aria-label={isPlaying ? 'Pause' : 'Play'} style="transform: scale({$playPulse})">{isPlaying ? 'Ⅱ' : '▶'}</button><button on:click={next} aria-label="Next">▶|</button><button class:enabled={activeQueue.shuffle} on:click={toggleShuffle} aria-label="Toggle shuffle" title="Shuffle">⇄</button><button class:enabled={activeQueue.repeat !== 'off'} on:click={cycleRepeat} aria-label="Repeat: {activeQueue.repeat}" title="Repeat: {activeQueue.repeat}">↻{activeQueue.repeat === 'one' ? '1' : ''}</button></div><div class="progress"><span>{formatTime(currentTime)}</span><input aria-label="Seek" type="range" min="0" max={duration || 0} step="0.1" value={currentTime} on:input={seek} /><span>{formatTime(duration)}</span></div><label class="volume" aria-label="Volume">⌕<input type="range" min="0" max="1" step=".01" value={volume} on:input={setVolume} /></label><button class="queue-toggle" on:click={() => queueOpen = !queueOpen} aria-label="Open playback queue" title="Queue">☰♫</button><button class="expand-toggle" on:click={() => theatreOpen = true} aria-label="Open Theatre Mode" title="Theatre Mode">⛶</button><button class="pip-toggle" on:click={togglePip} aria-label="Open mini player" title="Mini player (Picture-in-Picture)">⧉</button>{#if loadingTrack}<span class="loading-label">Loading…</span>{/if}</section>{/if}
{#if theatreOpen}<TheatreMode track={currentTrack} isPlaying={isPlaying} currentTime={currentTime} duration={duration} shuffle={activeQueue.shuffle} repeat={activeQueue.repeat} onClose={() => theatreOpen = false} onToggle={togglePlay} onNext={next} onPrevious={previous} onSeek={seek} onShuffle={toggleShuffle} onRepeat={cycleRepeat} />{/if}
{#if queueOpen}<aside class="queue-drawer" aria-label="Playback queue"><div class="queue-head"><div><p class="eyebrow">UP NEXT</p><h2>Queue</h2></div><button on:click={() => queueOpen = false} aria-label="Close queue">×</button></div><div class="queue-section"><h3>History <span>{activeQueue.history.length}</span></h3>{#if activeQueue.history.length}<div class="history-row"><span class="queue-art">{#if activeQueue.history.at(-1).thumbnail}<img src={activeQueue.history.at(-1).thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="queue-title">{clean(activeQueue.history.at(-1).title)}<small>{clean(activeQueue.history.at(-1).artist)}</small></span></div>{:else}<p class="empty">Nothing played yet</p>{/if}</div><div class="queue-section upcoming"><div class="upcoming-head"><h3>Up Next <span>{activeQueue.upNext.length}</span></h3><button on:click={clearUpcoming} disabled={!activeQueue.upNext.length}>Clear</button></div>{#each activeQueue.upNext as item, index (item.videoId)}<div class="queue-row" class:dragging={draggedIndex === index} role="listitem" draggable="true" on:dragstart={() => dragStart(index)} on:dragend={() => draggedIndex = -1} on:dragover|preventDefault on:drop={() => dropAt(index)}><span class="grip">⋮⋮</span><button class="queue-item" on:click={() => jumpTo(item)}><span class="queue-art">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="queue-title">{clean(item.title)}<small>{clean(item.artist)}</small></span></button><button class="remove" on:click={() => removeUpcoming(item.videoId)} aria-label="Remove {clean(item.title)}">×</button><TrackContextMenu track={item} onPlayNext={playNextTrack} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} /></div>{/each}{#if !activeQueue.upNext.length}<p class="empty">Queue is empty</p>{/if}</div></aside>{/if}

<style>
  main { min-height: 100vh; box-sizing: border-box; padding: 42px; padding-bottom: 42px; color: #f4f4f5; background: radial-gradient(ellipse at 10% 0%, color-mix(in srgb, var(--accent, #c4b5fd) 10%, #302843) 0%, transparent 35%), #09090b; font-family: Inter, ui-sans-serif, system-ui, sans-serif; } main.with-player { padding-bottom: 118px; } .view-transition { display: contents; } h1 { margin: 0; font-size: clamp(2rem, 4vw, 3rem); }.eyebrow { margin: 0 0 8px; color: #a1a1aa; font-size: .68rem; font-weight: 700; letter-spacing: .16em; }.home-head { display: flex; align-items: end; justify-content: space-between; margin-bottom: 28px; } .home-head h1 { background: linear-gradient(115deg, #fff 15%, color-mix(in srgb, var(--accent, #c4b5fd) 75%, #fff) 60%, color-mix(in srgb, var(--accent, #c4b5fd) 60%, #fff)); -webkit-background-clip: text; background-clip: text; color: transparent; letter-spacing: -.03em; } .ambient-blob { position: fixed; top: -28vh; left: 50%; transform: translateX(-50%); width: 150vmax; height: 90vh; border-radius: 50%; background: radial-gradient(circle at 50% 50%, var(--ambient, #7c5fc7), transparent 62%); opacity: .15; filter: blur(100px); z-index: 0; pointer-events: none; transition: background 1.5s ease; } .loading, .setup { position: relative; z-index: 1; } .view-transition > * { position: relative; z-index: 1; } .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 6px; } .chip { padding: 7px 16px; border: 1px solid rgba(255,255,255,.12); border-radius: 999px; color: #b8b8c0; background: rgba(255,255,255,.05); cursor: pointer; font-size: .78rem; font-weight: 600; transition: all .18s ease; backdrop-filter: blur(12px); } .chip:hover { color: #fff; border-color: rgba(255,255,255,.24); background: rgba(255,255,255,.1); } .chip.active { color: #111; background: var(--accent, #c4b5fd); border-color: transparent; box-shadow: 0 2px 14px color-mix(in srgb, var(--accent, #c4b5fd) 45%, transparent); }  .status { color: #86efac; font-size: .8rem; } .status.expired { border: 1px solid #fbbf2433; border-radius: 999px; padding: 6px 12px; color: #fbbf24; background: #fbbf240f; cursor: pointer; font-size: .78rem; font-weight: 600; transition: background .15s ease; } .status.expired:hover { background: #fbbf241f; } .empty-shelf.library-empty { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; padding: 26px 4px; } .library-empty strong { color: #f4f4f5; font-size: .95rem; } .library-empty span { color: #a1a1aa; font-size: .82rem; } .chip-row { display: flex; gap: 8px; margin-top: 6px; }  .rotation,.quick { margin: 28px 0 34px; }  .rotation { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:18px; padding:24px; border:1px solid rgba(255,255,255,.08); border-radius:18px; background:linear-gradient(135deg, rgba(255,255,255,.07) 0%, rgba(255,255,255,.02) 100%); backdrop-filter: blur(20px); }.rotation h2,.quick h2 { margin:0; font-size:1.45rem; }.rotation-copy,.section-head>span { color:#a1a1aa; font-size:.83rem; }.recap { display:flex; align-items:center; gap:12px; min-width:280px; padding:10px; border:1px solid rgba(255,255,255,.07); border-radius:12px; color:#eee; background:#ffffff0b; text-align:left; cursor:pointer; }.recap-art,.quick-art { position:relative; display:grid; place-items:center; overflow:hidden; background:linear-gradient(135deg,#252331,#4d3640); }.recap-art { width:58px; height:58px; border-radius:8px; }  .recap-art img,.quick-art img { width:100%; height:100%; object-fit:cover; }.recap div:nth-child(2) { display:flex; flex-direction:column; flex:1; }.recap span,.quick-card>span { color:#a1a1aa; font-size:.78rem; margin-top:3px; }.quick { overflow:hidden; } .pl-art::after, .quick-art::after, .card-art::after, .recap-art::after { content: ''; position: absolute; inset: 0; z-index: 0; background: linear-gradient(to top, rgba(0,0,0,.4), transparent 42%); pointer-events: none; }.section-head { display:flex; justify-content:space-between; align-items:end; margin-bottom:14px; }.carousel-controls { display:flex; align-items:center; gap:10px; }.carousel-controls button { display:grid; place-items:center; width:28px; height:28px; border:1px solid #ffffff1c; border-radius:50%; color:#ddd; background:#ffffff0a; cursor:pointer; opacity:.55; transition:.2s; }.quick:hover .carousel-controls button { opacity:1; }.quick-row { display:flex; gap:14px; overflow-x:auto; padding:3px 4px 14px; scrollbar-width:none; -ms-overflow-style:none; }.quick-row::-webkit-scrollbar { display:none; }  .quick-card { flex:0 0 150px; border:0; padding:0; color:#eee; background:none; text-align:left; cursor:pointer; transition: transform .2s ease; }.quick-card:hover { transform: translateY(-4px) scale(1.02); }.quick-art { aspect-ratio:1; margin-bottom:10px; border-radius:12px; border:1px solid rgba(255,255,255,.06); box-shadow: 0 4px 14px rgba(0,0,0,.3); transition: transform .2s ease, box-shadow .2s ease; }.quick-card:hover .quick-art { transform: scale(1.02); box-shadow: 0 12px 30px rgba(0,0,0,.6); }.quick-art i { position:absolute; right:8px; bottom:8px; z-index:1; display:grid; place-items:center; width:32px; height:32px; border-radius:50%; color:#111; background:#fff; font-style:normal; opacity:0; transition:.2s; }.quick-card:hover .quick-art i { opacity:1; }.quick-card strong,.quick-card>span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.quick-card strong { font-size:.88rem; }.error { color: #fca5a5; }  .empty-shelf { color:#71717a; font-size:.85rem; padding:20px 4px; } .session-banner { display:flex; align-items:center; gap:12px; margin:0 0 18px; padding:11px 14px; border:1px solid #fbbf2433; border-radius:12px; color:#fde68a; background:#fbbf240f; font-size:.84rem; } .banner-link { border:0; border-radius:8px; padding:6px 12px; color:#fff; background:#fbbf2433; cursor:pointer; font-size:.78rem; font-weight:600; } .banner-link:hover { background:#fbbf2450; } .banner-close { margin-left:auto; border:0; background:none; color:#fbbf24; cursor:pointer; font-size:1.1rem; }.pl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 28px; }  .pl { position: relative; overflow: hidden; text-align: left; color: #eee; background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.09);border-radius: 22px; padding: 18px; cursor:pointer; transition: .25s ease; backdrop-filter: blur(20px); }.pl:hover { border-color: rgba(255,255,255,.18); transform: translateY(-4px) scale(1.02); box-shadow: 0 12px 30px rgba(0,0,0,.6); }.pl-art { position: relative; display: grid; place-items: center; aspect-ratio: 1; overflow: hidden; border-radius: 12px; margin-bottom: 14px; background: linear-gradient(135deg, #252331, #4d3640); color: #fff; font-size: 4rem; }.pl-art img, .mini-art img { width: 100%; height: 100%; object-fit: cover; }  .float-play { position: absolute; right: 12px; bottom: 12px; z-index: 1; display: grid; place-items: center; width: 42px; height: 42px; border-radius: 50%; color: #111; background: #fff; font-size: .9rem; opacity: 0; transition: .2s ease; }.pl:hover .float-play { opacity: 1; }.setup { width: min(560px,100%); margin: 7vh auto 0; padding: 38px; border: 1px solid #ffffff1f; border-radius: 24px; background: #ffffff0b; backdrop-filter: blur(20px); }.setup-mark { display: grid; place-items: center; width: 58px; height: 58px; border-radius: 16px; background: linear-gradient(135deg,#7c5fc7,#d18564); font-size: 2rem; }.intro { color: #a1a1aa; line-height: 1.55; }textarea { display: block; width: 100%; min-height: 150px; box-sizing: border-box; margin: 24px 0 12px; padding: 14px; border: 1px solid #ffffff24; border-radius: 12px; color: #eee; background: #0005; font: .8rem ui-monospace,monospace; }.connect { border: 0; border-radius: 22px; padding: 12px 20px; cursor: pointer; font-weight: 700; }.connect:disabled { opacity: .45; }.loading { display:grid; place-items:center; min-height:70vh; color:#a1a1aa; }.spinner { width:24px;height:24px;border:2px solid #444;border-top-color:#fff;border-radius:50%;animation:spin .8s linear infinite }@keyframes spin {to{transform:rotate(360deg)}}
  .search-wrap { position:relative; display:flex; align-items:center; }.global-search { width:min(420px,55vw); padding:12px 58px 12px 16px; border:1px solid #ffffff1c; border-radius:12px; color:#fff; background:#ffffff0b; outline:none; }.global-search:focus { border-color:var(--accent,#c4b5fd); box-shadow:0 0 0 3px color-mix(in srgb, var(--accent,#c4b5fd) 13%, transparent); }.search-wrap kbd { position:absolute; right:12px; color:#888; font-size:.7rem; }.search-results { margin:30px 0; }.search-shelf { margin:26px 0; }.search-shelf h3 { margin:0 0 12px; color:#a1a1aa; font-size:.75rem; text-transform:uppercase; letter-spacing:.14em; }.song-list { border:1px solid #ffffff10; border-radius:14px; overflow:hidden; background:#ffffff06; }.song-row { display:flex; align-items:center; gap:6px; padding-right:8px; }.song-row:hover { background:#ffffff0d; }.song-main { display:flex; align-items:center; gap:12px; flex:1; min-width:0; border:0; padding:9px 12px; color:#eee; background:none; text-align:left; cursor:pointer; }.song-art { width:44px; height:44px; flex:0 0 auto; display:grid; place-items:center; overflow:hidden; border-radius:8px; background:linear-gradient(135deg,#252331,#4d3640); font-size:1.2rem; }.song-art img { width:100%; height:100%; object-fit:cover; }.song-meta { min-width:0; flex:1; display:flex; flex-direction:column; }.song-meta strong,.song-meta small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.song-meta strong { font-size:.9rem; }.song-meta small { color:#a1a1aa; font-size:.78rem; margin-top:3px; }.song-dur { color:#71717a; font-size:.8rem; font-variant-numeric:tabular-nums; }.song-play { color:#a1a1aa; font-size:.8rem; margin:0 6px; }.song-row:hover .song-play { color:var(--accent,#c4b5fd); } .song-main { transition: transform .18s ease; } .song-row:hover .song-main { transform: translateX(3px); }.card-row { display:flex; gap:16px; overflow-x:auto; padding:3px 4px 12px; scrollbar-width:none; -ms-overflow-style:none; }.card-row::-webkit-scrollbar { display:none; }.browse-card { flex:0 0 150px; border:0; padding:0; color:#eee; background:none; text-align:left; cursor:pointer; transition: transform .2s ease; }.browse-card:hover { transform: translateY(-3px); }.card-art { aspect-ratio:1; display:grid; place-items:center; overflow:hidden; border-radius:14px; background:linear-gradient(135deg,#252331,#4d3640); font-size:2.5rem; margin-bottom:9px; transition:.2s; }.browse-card:hover .card-art { transform:scale(1.03); box-shadow:0 12px 30px #0009; }.card-art img { width:100%; height:100%; object-fit:cover; }.browse-card strong,.browse-card>span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.browse-card strong { font-size:.86rem; }.browse-card>span { color:#a1a1aa; font-size:.76rem; margin-top:3px; }.new-playlist { border:1px solid #ffffff1c; border-radius:8px; padding:6px 8px; color:#ddd; background:#ffffff0b; cursor:pointer; margin-left:12px; }.search-status { color:#a1a1aa; }.picker-track { margin:4px 0 14px; color:#a1a1aa; font-size:.85rem; }.picker-list { display:flex; flex-direction:column; gap:6px; max-height:46vh; overflow:auto; }.picker-item { display:flex; align-items:center; gap:11px; width:100%; border:0; border-radius:10px; padding:8px 10px; color:#eee; background:#ffffff08; text-align:left; cursor:pointer; }.picker-item:hover { background:#ffffff14; }.picker-art { width:38px; height:38px; flex:0 0 auto; display:grid; place-items:center; overflow:hidden; border-radius:7px; background:linear-gradient(135deg,#252331,#4d3640); font-size:1rem; }.picker-art img { width:100%; height:100%; object-fit:cover; }.picker-name { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:.88rem; }.picker-count { color:#71717a; font-size:.75rem; }.picker-empty { color:#71717a; font-size:.85rem; padding:12px 4px; }.picker-foot { display:flex; justify-content:flex-end; margin-top:14px; }.picker-foot button { padding:9px 15px; border:0; border-radius:8px; color:#eee; background:#ffffff12; cursor:pointer; }.modal-backdrop { position:fixed;inset:0;z-index:90;display:grid;place-items:center;background:#0009; }.modal { width:min(420px,calc(100vw - 32px)); padding:26px; border:1px solid #ffffff1c; border-radius:18px; background:#1b1b22; box-shadow:0 25px 70px #0009; }.modal h2 { margin-top:0; }.modal input,.modal textarea { box-sizing:border-box;width:100%;margin:8px 0;padding:11px;border:1px solid #ffffff1c;border-radius:9px;background:#0004;color:#fff; }.modal textarea { min-height:90px; }.modal>div { display:flex;justify-content:flex-end;gap:8px;margin-top:12px; }.modal button { padding:9px 15px;border:0;border-radius:8px;cursor:pointer; }.modal .primary { background:#fff;color:#111; }
  .player { position: fixed; z-index: 30; left: 18px; right: 18px; bottom: 18px; display: flex; align-items: center; gap: 22px; min-height: 68px; padding: 12px 18px; border: 1px solid color-mix(in srgb, var(--accent, #c4b5fd) 24%, transparent); border-radius: 16px; background: linear-gradient(120deg, color-mix(in srgb, var(--accent, #c4b5fd) 9%, #17171c) 0%, #17171cd9 65%); box-shadow: 0 15px 45px #0009, 0 0 42px color-mix(in srgb, var(--accent, #c4b5fd) 16%, transparent); backdrop-filter: blur(20px); }.now { display:flex; align-items:center; gap:10px; width: 25%; min-width: 170px; }.mini-art { width:46px;height:46px;display:grid;place-items:center;flex:0 0 auto;overflow:hidden;border-radius:7px;background:linear-gradient(135deg,#252331,#4d3640); }.now-meta { min-width:0;display:flex;flex-direction:column; }.now-meta strong,.now-meta span { overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }.now-meta span { color:#a1a1aa;font-size:.8rem;margin-top:3px; }  .controls { display:flex;align-items:center;gap:14px; }.controls button { border:0;background:none;color:#aaa;cursor:pointer;font-size:1rem; transition: color .15s ease; }.controls button:hover { color:#f4f4f5; }.controls button.enabled { color:var(--accent,#c4b5fd); }.controls .pause { width:38px;height:38px;border-radius:50%;color:#111;background:#f4f4f5; box-shadow:0 0 18px color-mix(in srgb, var(--accent,#c4b5fd) 45%, transparent); will-change: transform; }.progress { display:flex;align-items:center;gap:10px;flex:1;color:#a1a1aa;font-size:.72rem; }.progress input { flex:1; accent-color:var(--accent,#c4b5fd); }.volume { display:flex;align-items:center;gap:5px;color:#aaa; }.volume input { width:75px;accent-color:var(--accent,#c4b5fd); }  .loading-label { color:var(--accent,#c4b5fd);font-size:.72rem; }.queue-toggle,.expand-toggle,.pip-toggle { border:1px solid #ffffff1c; border-radius:8px; padding:7px 9px; color:#ddd; background:#ffffff0a; cursor:pointer; transition: background .15s ease, color .15s ease; }.queue-toggle:hover,.expand-toggle:hover,.pip-toggle:hover { background:#ffffff18; color:#fff; }
  .settings-toggle { border:1px solid #ffffff1c; border-radius:8px; padding:7px 10px; color:#ddd; background:#ffffff0a; cursor:pointer; margin-left:10px; font-size:1rem; transition: background .15s ease, color .15s ease; }.settings-toggle:hover { background:#ffffff18; color:#fff; }
  html.reduce-motion *, html.reduce-motion *::before, html.reduce-motion *::after { animation: none !important; transition: none !important; }
  .queue-drawer { position:fixed; z-index:40; top:0; right:0; bottom:0; width:min(360px,92vw); padding:24px 16px; overflow:auto; color:#f4f4f5; background:rgba(10,10,12,.75); box-shadow:-20px 0 60px #0008; backdrop-filter:blur(24px); }.queue-head,.upcoming-head { display:flex; align-items:center; justify-content:space-between; }.queue-head h2 { margin:0 0 16px; font-size:1.4rem; }.queue-head>button,.upcoming-head button { border:0;background:none;color:#aaa;cursor:pointer;font-size:1.5rem; }.queue-section { padding:14px 0; }.queue-section h3 { margin:0 0 10px;font-size:.72rem;text-transform:uppercase;letter-spacing:.14em;color:#a1a1aa; }.queue-section h3 span { color:#71717a;font-weight:400; }.history-row,.queue-row { border-radius:6px; }.history-row { display:flex;align-items:center;gap:10px;padding:8px;color:#a1a1aa; }  .queue-row { display:flex;align-items:center;margin:2px 0;transition:background .15s ease, transform .18s ease, opacity .18s ease; }.queue-row:hover { background:rgba(255,255,255,.05); }.queue-row.dragging { transform: scale(1.03); opacity:.65; background:rgba(255,255,255,.06); }.queue-item { display:flex;align-items:center;gap:10px;flex:1;min-width:0;border:0;padding:8px;background:none;color:#eee;text-align:left;cursor:pointer; }.queue-art { width:40px;height:40px;flex:0 0 auto;display:grid;place-items:center;overflow:hidden;border-radius:6px;background:linear-gradient(135deg,#252331,#4d3640);font-size:.9rem; }.queue-art img { width:100%;height:100%;object-fit:cover; }.queue-title { min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.86rem;font-weight:600; }.queue-title small { display:block;color:#a1a1aa;font-weight:400;margin-top:2px;font-size:.74rem; }.grip { color:#555;opacity:0;padding:0 4px;font-size:.9rem;cursor:grab;transition:opacity .15s ease; }.queue-row:hover .grip { opacity:1; }.remove { opacity:0;border:0;background:none;color:#fca5a5;cursor:pointer;font-size:1.1rem;padding:8px 10px; }.queue-row:hover .remove { opacity:1; }.empty { color:#71717a;font-size:.85rem;padding:4px; }.upcoming-head button { font-size:.75rem;border:0;background:none;color:#aaa;cursor:pointer; }.upcoming-head button:disabled { opacity:.4; }.now-menu { color:#71717a; }.now-menu .dot-btn { font-size:.95rem; }@media(max-width:720px){main{padding:24px 16px}.player{left:8px;right:8px;bottom:8px;flex-wrap:wrap;gap:8px}.now{width:100%}.progress{order:3;width:100%}.volume{display:none}}
</style>
