<script>
  import { onMount, onDestroy } from 'svelte'
  import { spring } from 'svelte/motion'
  import { fade, fly } from 'svelte/transition'
  import { get } from 'svelte/store'
  import { openPlaylist } from './lib/store.js'
  import { settings } from './lib/settings.js'
  import SettingsModal from './components/SettingsModal.svelte'
  import SmartPlaylistModal from './components/SmartPlaylistModal.svelte'
  import SongPage from './pages/SongPage.svelte'
  import ArtistPage from './pages/ArtistPage.svelte'
  import AlbumPage from './pages/AlbumPage.svelte'
  import TheatreMode from './pages/TheatreMode.svelte'
  import StatsView from './pages/StatsView.svelte'
  import TrackContextMenu from './components/TrackContextMenu.svelte'
  import MediaShelf from './components/MediaShelf.svelte'
  import HomeView from './components/HomeView.svelte'
  import TransportBar from './components/TransportBar.svelte'
  import StartMixButton from './components/StartMixButton.svelte'
  import SidebarLayout from './layouts/SidebarLayout.svelte'
  import TopbarLayout from './layouts/TopbarLayout.svelte'
  import HandheldLayout from './layouts/HandheldLayout.svelte'
  import { audio } from './lib/audio.js'
  import { apiFetch } from './lib/api.js'
  import { createMixController } from './lib/mix.js'
  import { normalizePlayable, normalizeTrack, trackKey } from './lib/tracks.js'
  import { queue, hydrateQueue, persistQueue, seed, selectNext, selectPrevious, playUpcoming, playNext, addToQueue, appendTracks, removeUpcoming, clearUpcoming, clearManualUpcoming, reorderUpcoming, reconcilePartyQueue, toggleShuffle, cycleRepeat } from './lib/queue.js'

  const playPulse = spring(1, { stiffness: 320, damping: 14 })
  let pipWindow = null, pipLyricsOpen = false, pipLyricsFor = null, pipLiked = false, accent = '#f2ece4'
  const DEFAULT_PALETTE = { accent: '#f2ece4', ambient: '#5c2a4a', shadow: '#8a3a2e', neutral: false }
  const NEUTRAL_PALETTE = { accent: '#34302d', ambient: '#24211f', shadow: '#161311', neutral: true }
  const paletteCache = new Map()
  let paletteLoading = false, paletteRequest = 0
  const PALETTE_KEY = 'myriddim.palette.v1'

  let playlists = [], full = null, artistData = null, albumData = null, checking = true, authenticated = false
  let authText = '', authError = '', connecting = false, actionTrack = null, showAddModal = false, editing = false, editTitle = '', editDescription = ''
  let pickerQuery = '', pickerMembership = {}, pickerChecking = false, pickerDragY = 0, pickerDragStart = null, pickerListEl = null
  let oauthTab = 'paste', oauthClientId = '', oauthClientSecret = '', oauthDevice = null, oauthCode = '', oauthError = '', oauthBusy = false, setupTab = 'oauth'
  let currentTrack = null, currentIndex = -1, theatreOpen = false, toast = '', toastTimer, activeQueue = { history: [], nowPlaying: null, upNext: [], repeat: 'off', shuffle: false }, isPlaying = false, currentTime = 0, duration = 0, volume = 1, loadingTrack = false, listenRecorded = false, queueOpen = false, draggedIndex = -1, queueTab = 'queue', playbackRequest = 0, playbackAbort = null
  let remotePollTimer = null, remotePublishTimer = null, remoteCommandsBusy = false, remoteExecutedCommandIds = new Set(), lastRemotePublish = 0
  const REMOTE_SYNC_INTERVAL = 2750
  let partyRoom = null, partyPopoverOpen = false, partySetupOpen = false, partyPollTimer = null, partyInviteBase = '', partyPlayedId = null, partySkipHandledId = null
  let partyQueueSnapshot = null
  const partyAppliedIds = new Set()
  let companionVideoId = null, companionForId = null, hasVideo = false, companionRequest = 0
  let quickPicks = [], recommendations = [], recommendationForId = null, recommendationLoading = false, recommendationRequest = 0, discoverTracks = [], discoverForId = null, discoverLoading = false, discoverRequest = 0, stats = { month: '', totalMinutes: 0, monthly: [], heavyRotation: [] }, searchQuery = '', searchResults = [], searchTimer, searchRequest = 0, searching = false, searchError = '', showCreate = false, newTitle = '', newDescription = '', preloadedTrackId = null
  let smartPlaylists = [], smartPlaylistsLoading = false, smartPlaylistsError = '', showSmartModal = false
  let settingsOpen = false
  $: activeShell = ({ sidebar: SidebarLayout, topbar: TopbarLayout, handheld: HandheldLayout }[$settings.shellLayout] || SidebarLayout)
  let radioFilling = false, radioTopupTimer = null
  let homeView = 'home', likedTracks = [], likedLoaded = false, likedLoading = false, likedError = ''
  let artistMixLoading = false
  let libraryCached = false
  let sessionState = 'ok', playlistsLoaded = false, playlistsError = '', justSwitched = false, justSwitchTimer
  let restoring = null, sessionBannerDismissed = false, lastPersist = 0
  let unsubscribe, queueUnsubscribe
  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const formatTime = seconds => { if (!Number.isFinite(seconds)) return '0:00'; return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}` }

  function remotePayload() {
    return {
      current_track: currentTrack ? { id: currentTrack.id, videoId: currentTrack.videoId, canonicalId: currentTrack.canonicalId, title: currentTrack.title, artist: currentTrack.artist, album: currentTrack.album, thumbnail: currentTrack.thumbnail } : null,
      is_playing: isPlaying,
      current_time: Number.isFinite(currentTime) ? currentTime : 0,
      duration: Number.isFinite(duration) ? duration : 0,
      volume,
      shuffle: !!activeQueue.shuffle,
      repeat: activeQueue.repeat || 'off',
      queue: activeQueue.upNext || [],
    }
  }
  function publishRemoteState() {
    if (remotePublishTimer) return
    const delay = Math.max(0, REMOTE_SYNC_INTERVAL - (Date.now() - lastRemotePublish))
    remotePublishTimer = setTimeout(async () => {
      remotePublishTimer = null
      lastRemotePublish = Date.now()
      try { await apiFetch('/api/remote/state', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(remotePayload()) }) } catch { /* remote control is optional */ }
    }, delay)
  }
  async function executeRemoteCommands(commands) {
    if (remoteCommandsBusy || !Array.isArray(commands) || !commands.length) return
    remoteCommandsBusy = true
    const ids = []
    try {
      for (const command of commands) {
        if (!Number.isInteger(command?.id)) continue
        ids.push(command.id)
        if (remoteExecutedCommandIds.has(command.id)) continue
        const payload = command.payload
        if (command.action === 'toggle_play') togglePlay()
        else if (command.action === 'previous') previous()
        else if (command.action === 'next') next()
        else if (command.action === 'seek') seekTo(payload)
        else if (command.action === 'set_volume') { volume = Number(payload); audio.volume = volume; savePlayerState() }
        else if (command.action === 'toggle_shuffle') toggleShuffle()
        else if (command.action === 'toggle_repeat') cycleRepeat()
        else if (command.action === 'play_track' && payload) playQueue([payload])
        remoteExecutedCommandIds.add(command.id)
      }
      const response = await apiFetch('/api/remote/commands/ack', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ids}) })
      if (!response.ok) throw Error(`Remote command acknowledgement failed (${response.status})`)
      ids.forEach(id => remoteExecutedCommandIds.delete(id))
      publishRemoteState()
    } finally { remoteCommandsBusy = false }
  }
  async function pollRemoteState() {
    try {
      const response = await apiFetch('/api/remote/state')
      if (!response.ok) return
      const data = await response.json()
      await executeRemoteCommands(data.pending_commands)
    } catch { /* phone may be offline */ }
  }
  function startRemoteSync() {
    publishRemoteState()
    pollRemoteState()
    remotePollTimer = setInterval(pollRemoteState, REMOTE_SYNC_INTERVAL)
  }

  async function health() { const response = await apiFetch('/api/health'); if (!response.ok) throw Error('Could not reach the backend.'); return response.json() }

  // --- Party Mode (host) ------------------------------------------------
  // App owns the room lifecycle: create/close, the 2s state poll, and the
  // reconciliation of guest requests into the one real queue. TheatreMode
  // only renders party state and reports host intents back through props.
  const isPublicTunnelUrl = value => /^https:\/\/[a-z0-9][a-z0-9-]*\.(?:trycloudflare\.com|loca\.lt)(?:\/|$)/i.test(String(value || ''))
  function partyUrlForBase(base, code) {
    return `${String(base).replace(/\/$/, '')}/party?room=${encodeURIComponent(code)}`
  }
  function partyBaseFromInvite(url) {
    return String(url || '').replace(/\/(?:party|mobile)(?:\?.*)?\/?$/i, '')
  }
  function decorateParty(data, inviteUrl = '') {
    const safeFallback = inviteUrl || (typeof window !== 'undefined' ? partyUrlForBase(window.location.origin, data.code) : '')
    const finalInvite = safeFallback
    if (isPublicTunnelUrl(finalInvite)) partyInviteBase = partyBaseFromInvite(finalInvite)
    return { ...data, invite_url: finalInvite, inviteUrl: finalInvite, qrDataUrl: finalInvite ? `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(finalInvite)}` : '' }
  }
  async function refreshPartyInviteUrl(room, attempts = 8) {
    if (!room?.code) return room
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const response = await apiFetch('/api/system/network-info')
        const data = await response.json()
        const publicUrl = isPublicTunnelUrl(data.publicUrl) ? data.publicUrl : ''
        const lanIp = String(data.lanIp || '')
        const port = Number(data.port) || 5193
        const lanBase = lanIp && lanIp !== '127.0.0.1' && lanIp !== 'localhost' ? `http://${lanIp}:${port}` : ''
        const base = publicUrl || lanBase || (typeof window !== 'undefined' ? window.location.origin : '')
        if (response.ok && base) return decorateParty(room, partyUrlForBase(base, room.code))
      } catch { /* network discovery is best-effort */ }
      if (attempt < attempts - 1) await new Promise(resolve => setTimeout(resolve, 500))
    }
    return decorateParty(room, typeof window !== 'undefined' ? partyUrlForBase(window.location.origin, room.code) : '')
  }
  function openPartyPopover() {
    if (!partyRoom) partySetupOpen = !partySetupOpen
    else partyPopoverOpen = !partyPopoverOpen
  }
  async function createParty(customSettings = {}) {
    try {
      const response = await apiFetch('/api/party/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          host_name: customSettings.host_name || 'Host',
          settings: customSettings,
        }),
      })
      const data = await response.json()
      if (response.status !== 201 || data.error) throw Error('Failed to start party: check backend server')
      partyAppliedIds.clear(); partyPlayedId = null; partySkipHandledId = null
      partyQueueSnapshot = [...activeQueue.upNext]
      partyRoom = await refreshPartyInviteUrl(decorateParty(data))
      partySetupOpen = false
      partyPopoverOpen = true
      clearInterval(partyPollTimer)
      partyPollTimer = setInterval(pollParty, 2000)
      showToast(`Party room ${data.code || data.room_code} is live`)
      return data
    } catch (error) {
      showToast('Failed to start party: check backend server')
      return null
    }
  }
  function endPartyLocal() {
    clearInterval(partyPollTimer)
    partyPollTimer = null
    partyRoom = null
    partyPopoverOpen = false
    partySetupOpen = false
    partyAppliedIds.clear()
    partyPlayedId = null
    partySkipHandledId = null
    partyQueueSnapshot = null
  }
  async function endParty(mode = 'keep') {
    const room = partyRoom
    if (!room?.code) return
    const guestTracks = [...(room.history || []), ...(room.queue || [])]
      .map(normalizePlayable)
      .filter(Boolean)
    if (mode === 'wipe') {
      queue.set({ ...activeQueue, upNext: partyQueueSnapshot ? [...partyQueueSnapshot] : activeQueue.upNext.filter(item => !room.queue?.some(entry => entry.videoId === item.videoId)) })
    } else if (mode === 'save') {
      const created = await createPlaylistFromName(`Party Mix - ${new Date().toLocaleDateString()}`)
      if (created) {
        for (const item of guestTracks) await saveTrackToPlaylist(item, created.id)
      }
      queue.set({ ...activeQueue, upNext: partyQueueSnapshot ? [...partyQueueSnapshot] : activeQueue.upNext.filter(item => !room.queue?.some(entry => entry.videoId === item.videoId)) })
    }
    apiFetch('/api/party/close', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ code: room.code }) }).catch(() => {})
    endPartyLocal()
    showToast(mode === 'save' ? 'Party session saved' : mode === 'wipe' ? 'Guest tracks removed' : 'Party ended')
  }
  async function partyAction(path, body = {}) {
    if (!partyRoom?.code) return
    try {
      const response = await apiFetch(`/api/party/${path}`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ code: partyRoom.code, ...body }) })
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Party command failed')
      applyPartyCommands(data.commands)
      partyRoom = decorateParty({ ...partyRoom, ...data })
    } catch (error) { showToast(error.message || 'Party command failed') }
  }
  function applyPartyCommands(commands) {
    for (const command of Array.isArray(commands) ? commands : []) {
      if (command.action === 'add_to_queue' && command.payload?.videoId) {
        partyAppliedIds.add(command.payload.videoId)
        const track = normalizePlayable(command.payload)
        if (track) {
          if (command.payload.priority) playNext(track, 'party')
          else addToQueue(track, 'party')
        }
      }
    }
  }
  async function pollParty() {
    if (!partyRoom?.code) return
    try {
      const response = await apiFetch(`/api/party/state?code=${encodeURIComponent(partyRoom.code)}`)
      if (!response.ok) return
      const data = await response.json()
      if (!data.active) { endPartyLocal(); return }
      const previousPending = partyRoom.pending?.length || 0
      partyRoom = decorateParty({ ...partyRoom, ...data })
      const activePartyTrack = data.active_track?.videoId
      if (data.skip_requested && activePartyTrack && partySkipHandledId !== activePartyTrack) {
        partySkipHandledId = activePartyTrack
        await apiFetch('/api/party/played', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ code: partyRoom.code, video_id: activePartyTrack }) }).catch(() => {})
        next()
      }
      // Keep the local party-owned slice in the server's vote/priority order
      // without disturbing listener-added or radio-backed tracks.
      reconcilePartyQueue((data.queue || []).map(entry => ({
        videoId: entry.videoId,
        title: entry.title,
        artist: entry.artist,
        thumbnail: entry.thumbnail,
        duration: entry.duration,
        requested_by: entry.requested_by,
        priority: entry.priority,
      })))
      const pending = data.pending || []
      if (pending.length > previousPending) {
        const latest = pending[pending.length - 1]
        showToast(latest ? `${latest.requested_by} requested ${latest.title}` : 'New song request')
      }
    } catch { /* party polling is best-effort */ }
  }
  async function reportPartyPlayed(track = currentTrack) {
    if (!partyRoom?.code || !track?.videoId) return
    try { await apiFetch('/api/party/played', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ code: partyRoom.code, video_id: track.videoId }) }) } catch { /* best-effort */ }
  }
  function notifyPartyTrackStarted(track) {
    if (!partyRoom?.code || !track?.videoId || partyPlayedId === track.videoId) return
    partyPlayedId = track.videoId
    reportPartyPlayed(track)
  }
  function onPartyApprove(videoId) { partyAction('approve', { video_id: videoId }) }
  function onPartyReject(videoId) { partyAction('reject', { video_id: videoId }) }
  function onPartyRole(guestId, role) { partyAction('role', { guest_id: guestId, role }) }
  function onPartyKick(guestId) { partyAction('kick', { guest_id: guestId }) }
  function onPartySetting(key, value) { partyAction('settings', { settings: { [key]: value } }) }
  function launchParty(settings) { return createParty(settings) }
  function onPartyCopyInvite() { if (partyRoom?.inviteUrl && navigator.clipboard) navigator.clipboard.writeText(partyRoom.inviteUrl).then(() => showToast('Invite link copied')).catch(() => {}) }
  async function waitForBackend(attempts = 20) {
    let lastError
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try { return await health() } catch (error) {
        lastError = error
        await new Promise(resolve => setTimeout(resolve, 350))
      }
    }
    throw lastError || Error('Could not reach the backend.')
  }
  async function loadPlaylists() {
    playlistsError = ''
    try {
      const response = await apiFetch('/api/playlists')
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not load playlists.')
      libraryCached = data.cached === true
      playlists = data.playlists || data
    } catch (error) { playlistsError = error.message } finally { playlistsLoaded = true }
  }
  async function connect() { authError = ''; connecting = true; try { const response = await apiFetch('/api/auth/setup', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({auth: authText}) }); const data = await response.json(); if (!response.ok || data.error) throw Error(data.error); authenticated = true; sessionState = 'ok'; localStorage.setItem('ytm.session', 'ok'); authText = ''; await loadPlaylists(); await loadDiscovery() } catch (error) { authError = error.message } finally { connecting = false } }
  async function oauthStart() { oauthError = ''; oauthBusy = true; try { const response = await apiFetch('/api/auth/oauth/init', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ client_id: oauthClientId.trim(), client_secret: oauthClientSecret.trim() }) }); const data = await response.json(); if (!response.ok || data.error) throw Error(data.error); oauthDevice = data } catch (error) { oauthError = error.message } finally { oauthBusy = false } }
  async function oauthFinish() { oauthError = ''; oauthBusy = true; try { const response = await apiFetch('/api/auth/oauth/complete', { method: 'POST', headers: {'Content-Type':'application/json'} }); const data = await response.json(); if (!response.ok || data.error) throw Error(data.error); authenticated = true; sessionState = 'ok'; localStorage.setItem('ytm.session', 'ok'); oauthDevice = null; oauthCode = ''; await loadPlaylists(); await loadDiscovery() } catch (error) { oauthError = error.message } finally { oauthBusy = false } }
  async function loadDiscovery() {
    const [quickResponse, statsResponse] = await Promise.all([apiFetch('/api/home/quick-picks'), apiFetch('/api/stats/monthly-top')])
    if (quickResponse.ok) quickPicks = ((await quickResponse.json()).tracks || []).map(normalizeTrack).filter(Boolean)
    if (statsResponse.ok) stats = await statsResponse.json()
    // Nothing playing yet: let the first recommendation color the page.
    if (!currentTrack && quickPicks[0]) extractAccent(quickPicks[0])
  }
  async function loadSmartPlaylists() {
    smartPlaylistsLoading = true
    smartPlaylistsError = ''
    try {
      const response = await apiFetch('/api/playlists/smart')
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not load smart playlists')
      smartPlaylists = Array.isArray(data) ? data : []
    } catch (error) {
      smartPlaylists = []
      smartPlaylistsError = error.message || 'Could not load smart playlists'
    } finally { smartPlaylistsLoading = false }
  }
  async function openSmartPlaylist(playlist) {
    try {
      const response = await apiFetch(`/api/playlists/smart/${playlist.id}/tracks`)
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not evaluate smart playlist')
      const tracks = (data.tracks || []).map(normalizePlayable).filter(Boolean)
      if (!tracks.length) { showToast('No matching tracks yet'); return }
      playQueue(tracks)
      showToast(`Playing ${playlist.name}`)
    } catch (error) { showToast(error.message || 'Could not open smart playlist') }
  }
  function handleSmartPlaylistSaved(event) {
    const playlist = event.detail
    smartPlaylists = [playlist, ...smartPlaylists.filter(item => item.id !== playlist.id)]
    showToast('Smart playlist saved')
  }
  async function checkCompanionVideo(track) {
    const id = trackKey(track)
    const requestId = ++companionRequest
    companionForId = id || null
    companionVideoId = null
    hasVideo = false
    if (!id || !/^[A-Za-z0-9_-]{11}$/.test(id)) return
    try {
      const params = new URLSearchParams({ title: track.title || '', artist: track.artist || '', audio_duration: track.duration || '' })
      if (track.musicVideoId || track.music_video_id) params.set('music_video_id', track.musicVideoId || track.music_video_id)
      const response = await apiFetch(`/api/track-video/${encodeURIComponent(id)}?${params}`)
      const data = await response.json()
      if (requestId !== companionRequest || !response.ok) return
      hasVideo = data.has_video === true && /^[A-Za-z0-9_-]{11}$/.test(data.video_id || '')
      companionVideoId = hasVideo ? data.video_id : null
    } catch {
      if (requestId === companionRequest) { hasVideo = false; companionVideoId = null }
    }
  }

  async function loadRecommendations(track) {
    const videoId = track?.videoId || track?.id
    const requestId = ++recommendationRequest
    if (!videoId || !/^[A-Za-z0-9_-]{11}$/.test(videoId)) {
      recommendations = []
      recommendationForId = null
      recommendationLoading = false
      return
    }
    recommendationLoading = true
    recommendationForId = videoId
    try {
      const response = await apiFetch(`/api/recommendations?video_id=${encodeURIComponent(videoId)}`)
      const data = await response.json()
      if (requestId !== recommendationRequest) return
      if (!response.ok || data.error) throw Error(data.error || 'Could not load recommendations.')
      recommendations = (data.tracks || []).map(normalizeTrack).filter(Boolean).filter(item => item.videoId !== videoId)
    } catch (error) {
      if (requestId === recommendationRequest) {
        recommendations = quickPicks.filter(item => item.videoId !== videoId).slice(0, 8)
      }
    } finally {
      if (requestId === recommendationRequest) recommendationLoading = false
    }
  }
  // Fresh Discoveries: 60/40 hybrid shelf, quietly refreshed per track change
  // so it never blocks playback or the home render.
  async function loadDiscover(track) {
    const videoId = track?.videoId || track?.id || ''
    const requestId = ++discoverRequest
    if (!/^[A-Za-z0-9_-]{11}$/.test(videoId)) {
      discoverTracks = []
      discoverForId = null
      discoverLoading = false
      return
    }
    discoverLoading = true
    discoverForId = videoId
    try {
      const response = await apiFetch(`/api/recommendations/discover?seed_track_id=${encodeURIComponent(videoId)}`)
      const data = await response.json()
      if (requestId !== discoverRequest) return
      if (!response.ok || data.error) throw Error(data.error || 'Discovery unavailable')
      discoverTracks = (data.recommendations || []).map(normalizeTrack).filter(Boolean).filter(item => item.videoId !== videoId)
    } catch {
      if (requestId === discoverRequest) discoverTracks = []
    } finally {
      if (requestId === discoverRequest) discoverLoading = false
    }
  }
  // --- Global entity navigation + favorite artist persistence ---
  let favoriteArtists = [], rotationTracks = [], recentPlaylists = []
  async function loadFavoriteArtists() {
    try {
      const response = await apiFetch('/api/artists/favorites')
      const data = await response.json()
      if (response.ok && Array.isArray(data.artists)) favoriteArtists = data.artists
    } catch { /* favorites are optional */ }
  }
  async function toggleFavoriteArtist(artist) {
    if (!artist?.id || !artist?.name) return
    const existed = favoriteArtists.some(item => item.id === artist.id)
    favoriteArtists = existed ? favoriteArtists.filter(item => item.id !== artist.id) : [artist, ...favoriteArtists]
    try {
      const response = await apiFetch('/api/artists/favorite', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ id: artist.id, name: artist.name, thumbnail: artist.thumbnail || null }) })
      if (!response.ok) throw Error()
      showToast(existed ? 'Removed from favorite artists' : 'Added to favorite artists')
    } catch {
      favoriteArtists = existed ? [artist, ...favoriteArtists] : favoriteArtists.filter(item => item.id !== artist.id)
      showToast('Could not update favorites')
    }
  }
  function isFavoriteArtist(id) { return favoriteArtists.some(item => item.id === id) }
  async function openArtistEntity(idOrName, name) {
    const query = idOrName || name
    if (!query) return
    full = null; albumData = null; artistData = null
    try {
      const response = await apiFetch(`/api/artist/resolve?q=${encodeURIComponent(query)}`)
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not open artist')
      artistData = data
    } catch (error) { showToast(error.message || 'Could not open artist') }
  }
  async function openAlbumEntity(albumId, title, artist) {
    const params = new URLSearchParams()
    if (albumId) params.set('title', albumId)
    else { params.set('title', title || ''); params.set('artist', artist || '') }
    if (!params.get('title')) return
    full = null; artistData = null; albumData = null
    try {
      const response = await apiFetch(`/api/album/resolve?${params}`)
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not open album')
      albumData = data
    } catch (error) { showToast(error.message || 'Could not open album') }
  }
  async function loadHomeExtras() {
    const [rotationResponse, recentResponse] = await Promise.all([apiFetch('/api/home/stats-rotation'), apiFetch('/api/playlists/recent')])
    if (rotationResponse.ok) rotationTracks = ((await rotationResponse.json()).tracks || []).map(normalizeTrack).filter(Boolean)
    if (recentResponse.ok) recentPlaylists = (await recentResponse.json()).playlists || []
  }
  let moods = [], activeMood = null, moodPlaylists = [], moodLoading = false
  let ytmShelves = [], ytmFeedLoading = false, ytmFeedLoaded = false
  let smartMix = [], smartMixLoading = false
  async function loadSmartMix() {
    smartMixLoading = true
    try {
      const response = await apiFetch('/api/recommendations/smart-mix')
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not build mix')
      smartMix = [...(data.mix || []), ...(data.discovery || [])].map(normalizeTrack).filter(Boolean)
    } catch { smartMix = [] } finally { smartMixLoading = false }
  }
  $: if (authenticated && !smartMix.length && !smartMixLoading && stats.totalMinutes > 0) loadSmartMix()
  async function loadMoods() {
    try {
      const response = await apiFetch('/api/moods')
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not load moods')
      moods = data.sections || []
    } catch { moods = [] }
  }
  async function openMood(category) {
    activeMood = category.title
    moodPlaylists = []
    moodLoading = true
    try {
      const response = await apiFetch(`/api/moods/playlists?params=${encodeURIComponent(category.params)}`)
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not load mood playlists')
      moodPlaylists = data.playlists || []
    } catch { moodPlaylists = [] } finally { moodLoading = false }
  }
  function setHomeView(view) { homeView = view; localStorage.setItem('ytm.view', view); if (view === 'favorites' && !likedLoaded) loadLiked() }
  $: if (homeView === 'discover') { if (!moods.length) loadMoods(); if (!ytmFeedLoaded && !ytmFeedLoading) loadYtmFeed() }
  async function loadYtmFeed() {
    if (ytmFeedLoading) return
    ytmFeedLoading = true
    try {
      const response = await apiFetch('/api/ytm/feed')
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Feed unavailable')
      ytmShelves = data.shelves || []
      ytmFeedLoaded = true
    } catch { ytmShelves = [] } finally { ytmFeedLoading = false }
  }
  async function loadLiked() {
    likedLoading = true
    likedError = ''
    try {
      const response = await apiFetch('/api/liked')
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not load favorites.')
      libraryCached = libraryCached || data.cached === true
      likedTracks = (data.tracks || []).map(normalizeTrack).filter(Boolean)
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
      localStorage.setItem('ytm.session', sessionState)
    } catch { /* keep the previous state on network failure */ }
  }
  function playQueueShuffled(tracks) {
    const list = [...(tracks || [])]
    for (let i = list.length - 1; i > 0; i -= 1) { const j = Math.floor(Math.random() * (i + 1)); [list[i], list[j]] = [list[j], list[i]] }
    playQueue(list)
  }

  function playNextTrack(track) { const t = normalizePlayable(track); if (t) { playNext(t); showToast('Playing next') } }
  function appendTrack(track) { const t = normalizePlayable(track); if (t) { addToQueue(t); showToast('Added to queue') } }
  async function startMix(track) {
    const tracks = await mixController.start(track)
    if (!tracks) return
    playQueue(tracks)
    showToast(`Radio mix started · ${tracks.length - 1} tracks queued`)
  }
  async function compileArtistMix(artists) {
    const selected = (artists || []).map(item => ({ id: item.id || null, name: clean(item.name || item.title) })).filter(item => item.name)
    artistMixLoading = true
    if (selected.length < 2 || selected.length > 4) {
      showToast('Choose 2–4 artists to compile a mix')
      return
    }
    try {
      const response = await apiFetch('/api/queue/artist-mix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artists: selected }),
      })
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not compile artist mix')
      const tracks = (data.tracks || []).map(normalizePlayable).filter(Boolean)
      if (!tracks.length) { showToast('No playable tracks found for those artists'); return }
      playQueue(tracks)
      showToast(`Artist mix started · ${tracks.length} tracks queued`)
    } catch (error) {
      showToast(error.message || 'Could not compile artist mix')
    } finally {
      artistMixLoading = false
    }
  }
  async function saveTrackToPlaylist(track, playlistId = null) {
    const rememberedId = localStorage.getItem('myriddim_last_playlist')
    const remembered = playlists.find(item => item.id === rememberedId && item.owned)
    const target = playlists.find(item => item.id === playlistId && item.owned) || remembered || playlists.find(item => item.owned) || playlists.find(item => /favorites/i.test(item.title || '') && item.owned)
    if (!target?.id || !track?.videoId) { showToast('Create a playlist before saving'); return null }
    try {
      const response = await apiFetch('/api/playlist/add-track', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ playlist_id: target.id, video_id: track.videoId }) })
      if (!response.ok) throw Error()
      localStorage.setItem('myriddim_last_playlist', target.id)
      playlists = playlists.map(item => item.id === target.id ? { ...item, count: Number(item.count || 0) + 1 } : item)
      showToast(`Added to "${target.title}"`)
      return target
    } catch { showToast('Could not save to playlist'); return null }
  }  async function createPlaylistFromName(name) {
    const title = String(name || '').trim()
    if (!title) return null
    try {
      const response = await apiFetch('/api/playlist/create', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ title, description: '' }) })
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error)
      const created = { id: data.id, title, count: 0, thumbnail: null, owned: true }
      playlists = [created, ...playlists]
      localStorage.setItem('myriddim_last_playlist', created.id)
      showToast(`Created ${title}`)
      return created
    } catch { showToast('Could not create playlist'); return null }
  }

  async function saveQueueAsPlaylist(name, tracks) {
    const items = (tracks || []).filter(item => item?.videoId)
    if (!items.length) return null
    const playlist = await createPlaylistFromName(name)
    if (!playlist) return null
    let saved = 0
    try {
      for (const item of items) {
        const response = await apiFetch('/api/playlist/add-track', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ playlist_id: playlist.id, video_id: item.videoId }),
        })
        if (!response.ok) throw Error()
        saved += 1
      }
      playlists = playlists.map(item => item.id === playlist.id ? { ...item, count: saved } : item)
      showToast(`Saved queue as "${playlist.title}"`)
      return { ...playlist, count: saved }
    } catch {
      showToast(`Could only save ${saved} of ${items.length} tracks`)
      return null
    }
  }

  function flushManualQueue() { clearManualUpcoming(); showToast('Manual queue cleared') }

  function toggleTrackFavorite(track) {
    const id = track?.videoId
    if (!id) return
    const exists = likedTracks.some(item => item.videoId === id)
    likedTracks = exists ? likedTracks.filter(item => item.videoId !== id) : [track, ...likedTracks]
    showToast(exists ? 'Removed from favorites' : 'Added to favorites')
  }

  function openAddModal(track) {
    actionTrack = normalizePlayable(track)
    pickerQuery = ''
    pickerMembership = {}
    pickerDragY = 0
    showAddModal = true
    const videoId = actionTrack?.videoId
    if (!videoId) return
    pickerChecking = true
    apiFetch(`/api/playlist/membership?video_id=${encodeURIComponent(videoId)}`)
      .then(async (response) => { const data = await response.json().catch(() => ({})); return { ok: response.ok, data } })
      .then(({ ok, data }) => { if (actionTrack?.videoId !== videoId) return; if (ok && data.membership) pickerMembership = data.membership })
      .catch(() => {})
      .finally(() => { if (actionTrack?.videoId === videoId) pickerChecking = false })
  }
  function onPickerDragStart(event) { pickerDragStart = event.touches?.[0]?.clientY ?? null }
  function onPickerDragMove(event) {
    if (pickerDragStart == null) return
    const dy = event.touches[0].clientY - pickerDragStart
    if (dy <= 0) return
    // Only pull the sheet down once the list is already at the top, so a
    // mid-list downward swipe scrolls the list instead of dismissing it.
    if (pickerListEl && pickerListEl.scrollTop > 0) return
    pickerDragY = dy
    event.preventDefault()
  }
  function onPickerDragEnd() {
    if (pickerDragStart == null) return
    const dismiss = pickerDragY > 96
    pickerDragStart = null
    pickerDragY = 0
    if (dismiss) showAddModal = false
  }
  async function addTrackToPlaylist(playlistId) {
    if (!actionTrack?.videoId) return
    const target = actionTrack
    try { const response = await apiFetch('/api/playlist/add-track', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({playlist_id: playlistId, video_id: target.videoId})}); if (!response.ok) throw Error(); pickerMembership = { ...pickerMembership, [playlistId]: true }; showToast('Added to playlist') } catch { showToast('Could not add to playlist') }
  }
  async function removeTrackFromPlaylist(track) { if (!full?.owned) return; const previous = full.tracks; full = {...full, tracks: previous.filter(item => item.videoId !== track.videoId)}; try { const response = await apiFetch('/api/playlist/remove-track', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({playlist_id:full.id, video_id:track.videoId})}); if (!response.ok) throw Error(); showToast('Removed from playlist') } catch { full = {...full, tracks: previous}; showToast('Could not remove track') } }
  async function savePlaylistEdit() { const previous = full; full = {...full, title:editTitle.trim() || full.title, description:editDescription}; editing = false; try { const response = await apiFetch('/api/playlist/edit', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({playlist_id:previous.id, title:full.title, description:full.description})}); if (!response.ok) throw Error(); showToast('Playlist updated') } catch { full = previous; showToast('Could not update playlist') } }
  async function deleteCurrentPlaylist() { if (!full?.owned || !confirm(`Delete ${full.title}?`)) return; const deleted = full; full = null; playlists = playlists.filter(item => item.id !== deleted.id); try { const response = await apiFetch('/api/playlist/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({playlist_id:deleted.id})}); if (!response.ok) throw Error(); showToast('Playlist deleted') } catch { playlists = [deleted, ...playlists]; showToast('Could not delete playlist') } }
  function applyPalette(palette) {
    const next = { ...DEFAULT_PALETTE, ...(palette || {}) }
    accent = next.accent
    document.documentElement.style.setProperty('--accent', next.accent)
    document.documentElement.style.setProperty('--ambient', next.ambient)
    document.documentElement.style.setProperty('--shadow', next.shadow)
    document.documentElement.style.setProperty('--palette-neutral', next.neutral ? '1' : '0')
  }
  function readPaletteCache() {
    try {
      const stored = JSON.parse(localStorage.getItem(PALETTE_KEY) || '{}')
      Object.entries(stored).forEach(([id, palette]) => paletteCache.set(id, palette))
    } catch { /* palette cache is cosmetic */ }
  }
  function writePaletteCache(id, palette) {
    paletteCache.set(id, palette)
    try {
      const entries = Object.fromEntries([...paletteCache.entries()].slice(-100))
      localStorage.setItem(PALETTE_KEY, JSON.stringify(entries))
    } catch { /* private mode: memory cache still works */ }
    apiFetch(`/api/palette/${encodeURIComponent(id)}`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(palette) }).catch(() => {})
  }
  function rgb(r, g, b) { return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})` }
  function paletteFromPixels(data, stride = 1) {
    let r = 0, g = 0, b = 0, n = 0, vr = 0, vg = 0, vb = 0, vn = 0
    for (let i = 0; i < data.length; i += 4 * stride) {
      const pr = data[i], pg = data[i + 1], pb = data[i + 2], pa = data[i + 3]
      if (pa < 128) continue
      const lum = 0.299 * pr + 0.587 * pg + 0.114 * pb
      if (lum < 14 || lum > 246) continue
      r += pr; g += pg; b += pb; n += 1
      const spread = Math.max(pr, pg, pb) - Math.min(pr, pg, pb)
      if (spread > 32 && lum > 25 && lum < 240) { vr += pr; vg += pg; vb += pb; vn += 1 }
    }
    if (!n) return { ...NEUTRAL_PALETTE }
    const average = { r: r / n, g: g / n, b: b / n }
    const saturation = (Math.max(average.r, average.g, average.b) - Math.min(average.r, average.g, average.b)) / Math.max(1, Math.max(average.r, average.g, average.b))
    if (saturation < 0.12 || !vn) return { ...NEUTRAL_PALETTE }
    return { accent: rgb(r / n, g / n, b / n), ambient: rgb(vr / vn, vg / vn, vb / vn), shadow: rgb(Math.max(0, average.r * .7), Math.max(0, average.g * .7), Math.max(0, average.b * .7)), neutral: false }
  }
  function paletteFromAverage(data) {
    const [r, g, b, a] = data
    if (a < 128) return { ...NEUTRAL_PALETTE }
    const maximum = Math.max(r, g, b)
    const minimum = Math.min(r, g, b)
    if ((maximum - minimum) / Math.max(1, maximum) < 0.12) return { ...NEUTRAL_PALETTE }
    return { accent: rgb(r, g, b), ambient: rgb(r, g, b), shadow: rgb(r * .7, g * .7, b * .7), neutral: false }
  }
  async function extractAccent(track) {
    const id = trackKey(track)
    const url = track?.thumbnail || (typeof track === 'string' ? track : '')
    // Only the active track is allowed to change the page palette. Artwork for
    // other cards loads in parallel and must never win this request.
    if (currentTrack && id && trackKey(currentTrack) !== id) return
    const request = ++paletteRequest
    if (!url) { applyPalette(DEFAULT_PALETTE); paletteLoading = false; return }
    if (id && paletteCache.has(id)) { applyPalette(paletteCache.get(id)); paletteLoading = false; return }
    paletteLoading = true
    let timeout
    const finish = (palette) => {
      if (request !== paletteRequest) return
      clearTimeout(timeout)
      applyPalette(palette)
      paletteLoading = false
      if (id) writePaletteCache(id, palette)
    }
    if (id) {
      try {
        const response = await apiFetch(`/api/palette/${encodeURIComponent(id)}`)
        const data = await response.json()
        if (request !== paletteRequest) return
        if (response.ok && data.palette) {
          applyPalette(data.palette)
          paletteLoading = false
          paletteCache.set(id, data.palette)
          return
        }
      } catch { /* local image extraction remains the fallback */ }
    }
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.referrerPolicy = 'no-referrer'
    timeout = setTimeout(() => finish(NEUTRAL_PALETTE), 3500)
    img.onload = async () => {
      try {
        // onload is the gate: never sample the new track before it is decoded.
        await img.decode?.()
        const instant = document.createElement('canvas')
        instant.width = 1; instant.height = 1
        const instantContext = instant.getContext('2d', { willReadFrequently: true })
        instantContext.drawImage(img, 0, 0, 1, 1)
        const first = paletteFromAverage(instantContext.getImageData(0, 0, 1, 1).data)
        if (request === paletteRequest) { applyPalette(first); paletteLoading = false }
        setTimeout(() => {
          if (request !== paletteRequest) return
          try {
            const canvas = document.createElement('canvas')
            canvas.width = 32; canvas.height = 32
            const context = canvas.getContext('2d', { willReadFrequently: true })
            context.drawImage(img, 0, 0, 32, 32)
            finish(paletteFromPixels(context.getImageData(0, 0, 32, 32).data))
          } catch { finish(first) }
        }, 120)
      } catch { finish(NEUTRAL_PALETTE) }
    }
    img.onerror = () => finish(NEUTRAL_PALETTE)
    img.src = url
  }
  function pulsePlay() { playPulse.set(0.8); setTimeout(() => playPulse.set(1), 100) }
  async function togglePip() {
    if (pipWindow) { pipWindow.close(); pipWindow = null; pipLyricsOpen = false; return }
    if (!('documentPictureInPicture' in window)) { showToast('Mini player is not supported in this browser'); return }
    try {
      pipWindow = await window.documentPictureInPicture.requestWindow({ width: 400, height: 330 })
      pipWindow.document.title = 'Now Playing'
      pipWindow.document.body.innerHTML = `<div class="pip"><div class="pip-top"><div class="pip-art-wrap"><img id="pip-art" alt="" /></div><div class="pip-meta"><strong id="pip-title"></strong><span id="pip-artist"></span><div class="pip-actions"><button id="pip-like" title="Like this song" aria-label="Like this song">♡</button><button id="pip-lyrics" title="Show lyrics" aria-label="Show lyrics">🎤</button></div></div><button id="pip-close" title="Close mini player" aria-label="Close mini player">×</button></div><div id="pip-lyrics-drawer" class="pip-lyrics-drawer" hidden><div class="pip-lyrics-head"><strong>Lyrics</strong><span id="pip-lyrics-status"></span></div><div id="pip-lyrics-lines" class="pip-lyrics-lines"></div></div><div class="pip-controls"><button id="pip-prev" aria-label="Previous">|◀</button><button id="pip-play" class="pip-play" aria-label="Play">▶</button><button id="pip-next" aria-label="Next">▶|</button></div><div class="pip-seek"><span id="pip-time">0:00</span><input id="pip-seek-range" type="range" min="0" max="0" value="0" step="0.1" aria-label="Seek" /><span id="pip-dur">0:00</span></div><label class="pip-volume"><span>Volume</span><input id="pip-volume-range" type="range" min="0" max="1" value="${volume}" step="0.01" aria-label="Volume" /></label></div>`
      const style = pipWindow.document.createElement('style')
      style.textContent = `*{box-sizing:border-box}body{margin:0;background:#101014;color:#f4f4f5;font-family:Inter,ui-sans-serif,system-ui,sans-serif}.pip{position:relative;display:flex;flex-direction:column;min-height:100vh;padding:18px;overflow:hidden;background:radial-gradient(circle at 12% 0%,var(--ambient,#8b75c7) 0%,transparent 42%),radial-gradient(circle at 100% 100%,var(--accent,#c4b5fd) 0%,transparent 48%),#101014}.pip:before{content:'';position:absolute;inset:-35%;z-index:0;background:var(--ambient,#8b75c7);opacity:.12;filter:blur(70px);border-radius:50%;pointer-events:none}.pip>*{position:relative;z-index:1}.pip-top{display:flex;align-items:flex-start;gap:12px;padding:2px}.pip-art-wrap{width:76px;height:76px;flex:0 0 auto;padding:2px;border-radius:20px;background:linear-gradient(135deg,#ffffff55,#ffffff08);box-shadow:0 12px 32px #0008}.pip-art-wrap img{width:100%;height:100%;border-radius:18px;object-fit:cover;background:#252331}.pip-meta{flex:1;min-width:0;padding-top:3px}.pip-meta strong,.pip-meta span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pip-meta strong{font-size:1rem;line-height:1.25}.pip-meta span{margin-top:5px;color:#b4b4bf;font-size:.78rem}.pip-actions{display:flex;gap:6px;margin-top:11px}.pip-actions button{width:28px;height:28px;border:1px solid #ffffff1c;border-radius:9px;color:#c7c7d0;background:#ffffff0b;cursor:pointer;font-size:.85rem}.pip-actions button:hover,.pip-actions button.active{color:#111;background:var(--accent,#c4b5fd)}#pip-close{width:28px;height:28px;border:0;border-radius:50%;color:#aaa;background:#ffffff0b;font-size:1.25rem;line-height:1;cursor:pointer}#pip-close:hover{color:#fff;background:#ffffff1c}.pip-controls{display:flex;justify-content:center;align-items:center;gap:28px;margin-top:auto;padding:12px 0 8px}.pip-controls button{border:0;background:none;color:#ddd;font-size:1.05rem;cursor:pointer}.pip-play{width:50px;height:50px;border-radius:50%;color:#111!important;background:#fff!important;box-shadow:0 6px 20px #0008}.pip-seek{display:flex;align-items:center;gap:9px;color:#a1a1aa;font-size:.68rem;font-variant-numeric:tabular-nums}.pip-seek input,.pip-volume input{flex:1;min-width:0;accent-color:var(--accent,#c4b5fd);cursor:pointer}.pip-volume{display:flex;align-items:center;gap:9px;margin-top:8px;color:#a1a1aa;font-size:.68rem}.pip-volume input{width:auto}.pip-lyrics-drawer{height:120px;margin-top:12px;padding:10px;border:1px solid #ffffff16;border-radius:14px;background:#08080bb8;overflow:hidden}.pip-lyrics-drawer[hidden]{display:none}.pip-lyrics-head{display:flex;justify-content:space-between;margin-bottom:6px;color:#ddd;font-size:.75rem}.pip-lyrics-head span{color:#999;font-size:.65rem}.pip-lyrics-lines{height:88px;overflow:auto;color:#d4d4d8;font-size:.75rem;line-height:1.55;scrollbar-width:thin}.pip-lyric{display:block;width:100%;padding:2px 0;border:0;color:#a1a1aa;background:none;text-align:left;cursor:pointer}.pip-lyric.active{color:#fff;font-weight:700}`
      pipWindow.document.head.appendChild(style)
      pipWindow.document.getElementById('pip-play').addEventListener('click', togglePlay)
      pipWindow.document.getElementById('pip-prev').addEventListener('click', previous)
      pipWindow.document.getElementById('pip-next').addEventListener('click', next)
      pipWindow.document.getElementById('pip-close').addEventListener('click', () => togglePip())
      pipWindow.document.getElementById('pip-seek-range').addEventListener('change', seek)
      pipWindow.document.getElementById('pip-volume-range').addEventListener('change', setPipVolume)
      pipWindow.document.getElementById('pip-lyrics').addEventListener('click', togglePipLyrics)
      pipWindow.document.getElementById('pip-like').addEventListener('click', togglePipLike)
      pipWindow.addEventListener('pagehide', () => { pipWindow = null; pipLyricsOpen = false })
      syncPip()
    } catch { showToast('Could not open mini player') }
  }
  function setPipVolume(event) {
    setVolume(event)
    syncPip()
  }
  function togglePipLyrics() {
    pipLyricsOpen = !pipLyricsOpen
    const drawer = pipWindow?.document?.getElementById('pip-lyrics-drawer')
    const button = pipWindow?.document?.getElementById('pip-lyrics')
    if (drawer) drawer.hidden = !pipLyricsOpen
    if (button) button.classList.toggle('active', pipLyricsOpen)
    if (pipLyricsOpen) loadPipLyrics()
  }
  async function loadPipLyrics() {
    if (!pipWindow?.document || !currentTrack?.videoId) return
    const id = currentTrack.videoId
    pipLyricsFor = id
    const status = pipWindow.document.getElementById('pip-lyrics-status')
    const target = pipWindow.document.getElementById('pip-lyrics-lines')
    if (!target) return
    target.textContent = ''
    if (status) status.textContent = 'Loading…'
    try {
      const params = new URLSearchParams({ track_id: id, title: currentTrack.title || '', artist: currentTrack.artist || '', duration: String(duration || '') })
      const response = await apiFetch(`/api/lyrics?${params}`)
      const data = await response.json()
      if (!pipWindow?.document || pipLyricsFor !== id) return
      const lines = (data.lines || []).filter(line => line && Number.isFinite(Number(line.time)) && line.text)
      if (!lines.length) { if (status) status.textContent = 'No lyrics'; return }
      if (status) status.textContent = data.estimated ? 'Estimated timing' : 'Synced'
      for (const line of lines) {
        const button = pipWindow.document.createElement('button')
        button.className = 'pip-lyric'
        button.textContent = line.text
        button.dataset.time = String(line.time)
        button.addEventListener('click', () => seekLine(Number(line.time)))
        target.appendChild(button)
      }
      updatePipLyricsActive()
    } catch { if (status) status.textContent = 'Lyrics unavailable' }
  }
  function seekLine(time) { if (Number.isFinite(time)) seekTo(time) }
  function updatePipLyricsActive() {
    if (!pipWindow?.document) return
    const lines = [...pipWindow.document.querySelectorAll('.pip-lyric')]
    let active = -1
    lines.forEach((line, index) => { if (Number(line.dataset.time) <= currentTime) active = index })
    lines.forEach((line, index) => line.classList.toggle('active', index === active))
  }
  async function togglePipLike() {
    if (!currentTrack?.videoId) return
    const nextLiked = !pipLiked
    pipLiked = nextLiked
    syncPip()
    try {
      const response = await apiFetch('/api/track/rate', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ video_id: currentTrack.videoId, rating: nextLiked ? 'LIKE' : 'INDIFFERENT' }) })
      if (!response.ok) throw Error()
      if (nextLiked && !likedTracks.some(track => track.videoId === currentTrack.videoId)) likedTracks = [currentTrack, ...likedTracks]
      if (!nextLiked) likedTracks = likedTracks.filter(track => track.videoId !== currentTrack.videoId)
      showToast(nextLiked ? 'Added to Favorites' : 'Removed from Favorites')
    } catch { pipLiked = !nextLiked; syncPip(); showToast('Could not update Favorite') }
  }
  function syncPip() {
    if (!pipWindow?.document) return
    const doc = pipWindow.document
    const art = doc.getElementById('pip-art')
    if (art) {
      if (currentTrack?.thumbnail) {
        art.src = currentTrack.thumbnail
        art.style.display = ''
      } else {
        art.style.display = 'none'
      }
    }
    doc.getElementById('pip-title').textContent = clean(currentTrack?.title) || ''
    doc.getElementById('pip-artist').textContent = clean(currentTrack?.artist) || ''
    doc.getElementById('pip-play').textContent = isPlaying ? '❚❚' : '▶'
    doc.getElementById('pip-time').textContent = formatTime(currentTime)
    doc.getElementById('pip-dur').textContent = formatTime(duration)
    const seekEl = doc.getElementById('pip-seek-range')
    if (seekEl) { seekEl.max = duration || 0; seekEl.value = currentTime }
    if (accent) doc.documentElement.style.setProperty('--accent', accent)
    if (accent) doc.documentElement.style.setProperty('--ambient', accent)
    pipLiked = !!currentTrack?.liked || likedTracks.some(track => track.videoId === currentTrack?.videoId)
    const likeButton = doc.getElementById('pip-like')
    if (likeButton) { likeButton.textContent = pipLiked ? '♥' : '♡'; likeButton.classList.toggle('active', pipLiked) }
    const lyricsButton = doc.getElementById('pip-lyrics')
    if (lyricsButton) { lyricsButton.classList.toggle('active', pipLyricsOpen); if (pipLyricsOpen && pipLyricsFor !== currentTrack?.videoId) loadPipLyrics() }
    updatePipLyricsActive()
  }
  function playQueue(tracks, index = 0) {
    const normalized = (tracks || []).map(normalizePlayable).filter(Boolean)
    if (!normalized[index]) { console.warn('Cannot start queue: selected track has no video ID', tracks?.[index]); return }
    seed(normalized, index)
    // Auto-open Theatre on user-initiated playback. A returning session's
    // restored queue must not fling the stage open on launch.
    if (!restoring) theatreOpen = true
  }

  async function open(pl) { try { const response = await apiFetch(`/api/playlist/${pl.id}`); const data = await response.json(); if (!response.ok || data.error) throw Error(data.error || 'Could not open playlist.'); full = data; openPlaylist.set({id: pl.id, title: data.title ?? pl.title}) } catch (error) { authError = error.message } }
  async function openArtist(browseId) {
    if (!browseId) return
    full = null; albumData = null; artistData = null
    try {
      const response = await apiFetch(`/api/artist/${encodeURIComponent(browseId)}`)
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not load artist')
      artistData = data
    } catch (error) { showToast(error.message || 'Could not load artist') }
  }
  async function openAlbum(browseId) {
    if (!browseId) return
    full = null; artistData = null; albumData = null
    try {
      const response = await apiFetch(`/api/album/${encodeURIComponent(browseId)}`)
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not load album')
      albumData = data
    } catch (error) { showToast(error.message || 'Could not load album') }
  }
  function openBrowse(card) {
    const id = card?.id || card?.browseId
    if (!id) { showToast('No details available for this item'); return }
    if (card?.type === 'artist') openArtist(id)
    else if (card?.type === 'album') openAlbum(id)
    else showToast('Open on YouTube Music to browse this item')
  }

  async function playTrack(track, index = 0, playlist = full) {
    track = normalizePlayable(track)
    if (!track) return
    const requestId = ++playbackRequest
    const streamTrackId = track.canonicalId || track.videoId
    const gaplessHandoff = audio.gapFilled && track.videoId === activeQueue.nowPlaying?.videoId
    currentTrack = track; currentIndex = index; listenRecorded = false; preloadedTrackId = null; loadingTrack = true; isPlaying = true
    publishRemoteState()
    notifyPartyTrackStarted(track)
    // Unified audio-state lock: abort any in-flight stream fetch and clear both
    // media buffers before the new request can resolve. A gapless handoff is
    // already playing the requested track on the other engine element, so it
    // is the sole intentional exception.
    if (playbackAbort) playbackAbort.abort()
    const abortController = new AbortController()
    playbackAbort = abortController
    if (!gaplessHandoff) audio.clear()
    audio.dataset.currentTrackId = track.videoId
    if (!gaplessHandoff) audio.dataset.loadedTrackId = null
    // A recent track switch means a stream load failure is handled by playTrack's
    // own catch (and would double-advance if the error listener also fired).
    justSwitched = true
    clearTimeout(justSwitchTimer)
    justSwitchTimer = setTimeout(() => { justSwitched = false }, 1500)
    // After a crossfade the engine is already playing this track (gapless);
    // skip the redundant stream resolution entirely.
    if (gaplessHandoff) {
      // The incoming deck is already playing. Adopt it as the app's active
      // track without assigning a source or resetting its currentTime.
      audio.adoptGapless(track.videoId)
      loadingTrack = false
      return
    }
    try {
      const response = await apiFetch(`/api/stream/${encodeURIComponent(streamTrackId)}?quality=${get(settings).quality}`, { signal: abortController.signal })
      if (requestId !== playbackRequest) return
      const status = response.status
      let data = null
      try { data = await response.json() } catch { data = null }
      if (requestId !== playbackRequest) return
      // Backend rate-limits stream resolution (8 per 20s). Auto-advancing here
      // would cascade-skip the whole queue while the window is shut, so surface
      // it and keep the track selected for a manual retry instead.
      if (data?.error && status === 429) {
        const retry = data.retry_after ? ` — try again in ${Math.ceil(Number(data.retry_after) || 0)}s` : ''
        throw Object.assign(Error(`Stream rate-limited${retry}`), { transient: true })
      }
      // Non-JSON body: the proxy/backend returned an HTML error page (5xx). That
      // is a transient backend condition, not a refusal of this track — advancing
      // would only cascade through the queue on a dead proxy.
      if (!data) throw Object.assign(Error(`Stream unavailable (HTTP ${status})`), { transient: true })
      if (!response.ok || data.error) { console.error("Stream resolution failed:", data.error); throw Error(data.error || 'Could not resolve audio stream.') }
      // Hard mismatch guard: a plain YouTube track must come back with its own
      // video id. Canonical/remote routing legitimately resolves to a different
      // source id, so the check only applies to direct YouTube requests.
      if (!track.canonicalId && data.video_id !== track.videoId) {
        console.error(`[MISMATCH PREVENTED] Requested ${track.videoId}, backend returned ${data.video_id}`)
        throw Error('Stream did not match the requested track')
      }
      // Explicitly halt the previous stream before mounting the new one so the
      // browser never ghosts the old buffer onto the new src.
      audio.src = data.url
      audio.dataset.loadedTrackId = track.videoId
      if (restoring && restoring.videoId === track.videoId) { audio.currentTime = Math.max(0, restoring.position || 0); restoring = null; isPlaying = false } else { await audio.play(); isPlaying = true }
    } catch (error) {
      if (requestId !== playbackRequest) return
      console.error('playTrack failed:', error)
      isPlaying = false
      // Rate limits and dead proxies are transient: never auto-advance through
      // them, or a single skip could silently drain the entire queue. Only
      // definite refusals (resolver errors, format failures, mismatches) skip.
      if (!error?.transient && activeQueue.upNext.length) selectNext()
      showToast(error?.transient ? error.message : 'Track unavailable')
    } finally {
      if (requestId === playbackRequest) loadingTrack = false
    }
  }
  function showToast(message) { toast = message; clearTimeout(toastTimer); toastTimer = setTimeout(() => toast = '', 4000) }
  const mixController = createMixController({
    fetcher: apiFetch,
    onStart: () => showToast('Creating radio mix…'),
    onError: (error) => showToast(error.message || 'Could not create radio mix'),
  })
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
      const response = await apiFetch('/api/auth/logout', { method: 'POST' })
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
      const response = await apiFetch(`/api/stream/${nextTrack.videoId}?quality=${get(settings).quality}`)
      const data = await response.json()
      if (!data.error && data.url) audio.preload(data.url, nextTrack.videoId)
    } catch { /* preloading the next track is best-effort */ }
  }
  async function radioTopup(seedTrack, announce = false) {
    const seedId = seedTrack?.videoId || seedTrack?.id
    if (!seedId || !/^[A-Za-z0-9_-]{11}$/.test(seedId) || radioFilling) return
    radioFilling = true
    try {
      const response = await apiFetch(`/api/recommendations?video_id=${encodeURIComponent(seedId)}`)
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Radio unavailable')
      const seen = new Set(activeQueue.history.map(item => item?.videoId).filter(Boolean))
      seen.add(seedId)
      const fresh = (data.tracks || []).filter(item => item?.videoId && !seen.has(item.videoId))
      if (fresh.length) {
        appendTracks(fresh)
        if (announce) showToast('♪ Continuing with similar songs')
      }
    } catch { if (announce) showToast('Radio unavailable') } finally { radioFilling = false }
  }
  function searchChanged(valueOrEvent) {
    const input = typeof valueOrEvent === 'string' ? null : valueOrEvent?.currentTarget
    const value = typeof valueOrEvent === 'string' ? valueOrEvent : input?.value ?? ''
    const query = value.trim()
    searchQuery = value
    clearTimeout(searchTimer)
    const requestId = ++searchRequest
    searchError = ''
    if (!query) {
      searchResults = []
      searching = false
      if (homeView === 'search') setHomeView('home')
      return
    }
    // Switch synchronously on the first character. The shell owns the input,
    // so the route change does not remount it; explicitly restoring focus also
    // covers shells that flush their slot during the same input event.
    if (homeView !== 'search') {
      homeView = 'search'
      try { localStorage.setItem('ytm.view', 'search') } catch { /* storage is optional */ }
    }
    Promise.resolve().then(() => input?.focus())
    searching = true
    searchTimer = setTimeout(async () => {
      try {
        const response = await apiFetch(`/api/search?q=${encodeURIComponent(query)}`)
        const data = await response.json()
        if (requestId !== searchRequest) return
        if (!response.ok || data.error) throw Error(data.error || `Search failed (${response.status})`)
        // Keep the previous result set visible until this response succeeds.
        searchResults = Array.isArray(data.results) ? data.results : []
      } catch (error) {
        if (requestId !== searchRequest) return
        console.error('Search failed:', error)
        searchError = error.message || 'Search unavailable'
      } finally {
        if (requestId === searchRequest) searching = false
      }
    }, 250)
  }  function focusSearch(event) { if ((event.ctrlKey && event.key.toLowerCase() === 'k') || (event.key === '/' && !['INPUT','TEXTAREA'].includes(event.target.tagName))) { event.preventDefault(); document.querySelector('.global-search')?.focus() } }
  const CARD_SELECTOR = 'button.row-main, .tile, .playlist-card, .browse-card, .quick-card, .search-row > button, .recap, .smart-item, .hero-play, .sheet-item, .track[role="button"]'
  // Desktop-style grid navigation: arrow keys move focus to the nearest card
  // in that direction (overlap-aware), Enter activates it natively.
  function gridNav(event) {
    const directions = { ArrowDown: [0, 1], ArrowUp: [0, -1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] }
    const direction = directions[event.key]
    if (!direction || !(event.target instanceof HTMLElement)) return false
    const current = event.target.closest(CARD_SELECTOR)
    if (!current) return false
    const currentRect = current.getBoundingClientRect()
    let best = null
    let bestScore = Infinity
    for (const candidate of document.querySelectorAll(CARD_SELECTOR)) {
      if (candidate === current) continue
      const rect = candidate.getBoundingClientRect()
      if (!rect.width || !rect.height) continue
      const dx = rect.left - currentRect.left
      const dy = rect.top - currentRect.top
      if (direction[0] && Math.sign(dx) !== direction[0]) continue
      if (direction[1] && Math.sign(dy) !== direction[1]) continue
      const overlap = direction[0]
        ? Math.min(rect.bottom, currentRect.bottom) - Math.max(rect.top, currentRect.top)
        : Math.min(rect.right, currentRect.right) - Math.max(rect.left, currentRect.left)
      const primary = direction[0] ? Math.abs(dx) : Math.abs(dy)
      const score = primary * 1000 - Math.max(0, overlap)
      if (score < bestScore) { bestScore = score; best = candidate }
    }
    if (best) {
      event.preventDefault()
      best.scrollIntoView({ block: 'nearest' })
      best.focus()
      return true
    }
    return false
  }
  function handleGlobalKeydown(event) {
    focusSearch(event)
    if (event.shiftKey && (event.key === 'ArrowLeft' || event.key === 'ArrowRight') && currentTrack && !['INPUT', 'TEXTAREA'].includes(event.target.tagName)) {
      event.preventDefault()
      const delta = event.key === 'ArrowLeft' ? -5 : 5
      seekTo(Math.max(0, Math.min(duration || 0, audio.currentTime + delta)))
      return
    }
    if (gridNav(event)) return
    if (event.key === 'Escape') {
      if (showAddModal) { showAddModal = false; return }
      if (queueOpen) { queueOpen = false; return }
      if (settingsOpen) { settingsOpen = false; return }
      return
    }
    // Space toggles playback from anywhere except inputs and focused buttons
    // (a focused button already activates natively, so intercepting it would
    // double-fire).
    if (event.key === ' ' && currentTrack && !['INPUT', 'TEXTAREA', 'BUTTON', 'SELECT'].includes(event.target.tagName)) { event.preventDefault(); togglePlay() }
  }
  let dragActive = false
  // Native Tauri window chrome: file-drop staging overlay and tray menu events.
  // Safe no-ops in plain browser builds; the modules are imported dynamically.
  async function wireDesktopChrome() {
    if (typeof window === 'undefined' || !('__TAURI_INTERNALS__' in window)) return
    try {
      const [{ getCurrentWindow }, { listen }] = await Promise.all([import('@tauri-apps/api/window'), import('@tauri-apps/api/event')])
      getCurrentWindow().onDragDropEvent((event) => {
        if (event.payload.type === 'over') { dragActive = true; return }
        dragActive = false
        if (event.payload.type !== 'drop') return
        const audioFiles = (event.payload.paths || []).filter(path => /\.(mp3|flac|wav|m4a|ogg|opus|aac|aiff)$/i.test(path))
        if (audioFiles.length) showToast(`Staged ${audioFiles.length} audio ${audioFiles.length === 1 ? 'file' : 'files'} for your library`)
        else showToast('No audio files in that drop')
      }).catch(() => {})
      listen('tray-toggle-play', () => togglePlay())
      listen('tray-next', () => next())
      listen('tray-prev', () => previous())
    } catch { /* browser mode: desktop chrome is optional */ }
  }
  async function createPlaylist() { if (!newTitle.trim()) return; try { const response = await apiFetch('/api/playlist/create', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:newTitle, description:newDescription})}); const data = await response.json(); if (!response.ok || data.error) throw Error(data.error); playlists = [{id:data.id, title:newTitle.trim(), count:0, thumbnail:null}, ...playlists]; showCreate = false; newTitle = ''; newDescription = ''; showToast('Playlist created') } catch (error) { showToast('Could not create playlist') } }
  function togglePlay() {
    if (!audio || !currentTrack) return
    pulsePlay()
    // Optimistic, same-tick feedback: swap the icon before the media element
    // reports its handshake, and wake the audio pipeline inside the gesture.
    audio.warm()
    if (isPlaying) {
      isPlaying = false
      audio.pause()
    } else {
      isPlaying = true
      audio.play().catch(error => { isPlaying = false; authError = error.message })
    }
    publishRemoteState()
  }
  function next() { if (activeQueue.repeat === 'one' && currentTrack) { seekTo(0); audio.play(); return } if (duration > 0 && currentTime > 0) reportEvent(duration - currentTime <= duration * 0.2 ? 'completed' : (currentTime < 30 ? 'skipped' : null)); if (activeQueue.upNext.length) { selectNext(); return } if (activeQueue.repeat === 'all' && activeQueue.history.length) { seed([...activeQueue.history, activeQueue.nowPlaying], 0); return } if ($settings.autoRadio !== false && currentTrack) radioTopup(currentTrack, true).then(() => { if (activeQueue.upNext.length) selectNext() }) }
  function previous() { if (audio?.currentTime > 3) seekTo(0); else selectPrevious() }
  function jumpTo(track) { playUpcoming(track); queueOpen = false }
  function dragStart(index) { draggedIndex = index }
  function dropAt(index) { reorderUpcoming(draggedIndex, index); draggedIndex = -1 }
  async function recordListen() {
    if (!currentTrack || listenRecorded) return
    listenRecorded = true
    notifyPartyTrackStarted(currentTrack)
    await apiFetch('/api/track/listen', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({video_id: currentTrack.videoId, title: currentTrack.title, artist: currentTrack.artist, album: currentTrack.album, thumbnail_url: currentTrack.thumbnail, listen_duration_seconds: Math.round(currentTime)}) })
    // Playback reporting: tell YouTube Music's watch history we played this
    // track so the recommendation engine learns from actual listening. The
    // scrobble uses the same authenticated session as every other call.
    if ($settings.scrobble !== false && currentTrack.videoId && currentTrack.source !== 'soundcloud') {
      apiFetch('/api/scrobble', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({video_id: currentTrack.videoId}) }).catch(() => {})
    }
    loadDiscovery().catch(() => {})
  }
  // Local recommendation signals: report completion (>80% played) or an early
  // skip (<30s) so the local scoring engine learns actual listening habits.
  function reportEvent(event) {
    if (!currentTrack?.videoId) return
    const payload = { video_id: currentTrack.videoId, title: currentTrack.title, artist: currentTrack.artist, album: currentTrack.album, thumbnail_url: currentTrack.thumbnail, event, listen_duration_seconds: Math.round(currentTime) }
    apiFetch('/api/stats/event', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) }).catch(() => {})
  }
  function seekTo(value) {
    const nextTime = Number(value)
    if (!Number.isFinite(nextTime)) return
    if (audio) audio.currentTime = nextTime
    currentTime = nextTime
    publishRemoteState()
  }
  function seek(event) { seekTo(event.currentTarget.value) }
  function setVolume(event) {
    volume = Number(event.currentTarget.value)
    if (audio) audio.volume = volume
    savePlayerState()
    publishRemoteState()
  }
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
    navigator.mediaSession.setActionHandler('seekto', (details) => { if (details.seekTime != null) seekTo(details.seekTime) })
    window.__updateMediaSession = updateMetadata
    updateMetadata()
  }

  onMount(async () => {
    // Restore the previous session: volume, queue, and playback position.
    const savedPlayer = loadPlayerState()
    readPaletteCache()
    applyPalette(DEFAULT_PALETTE)
    audio.warm()
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
    audio.addEventListener('ended', () => { reportEvent('completed'); savePlayerState(); next() })
    audio.addEventListener('error', () => { if (loadingTrack || justSwitched || !currentTrack) return; showToast('Playback stalled'); if (activeQueue.upNext.length) selectNext() })
    // Audio element integrity check: if the hardware ever starts playing a track
    // different from what the UI is showing, halt it and resync instead of
    // letting the wrong song play under the wrong metadata.
    audio.addEventListener('playing', () => {
      const expected = currentTrack?.videoId
      const loaded = audio.dataset.loadedTrackId
      if (!expected || loaded === expected) return
      console.error(`[CRITICAL MISMATCH] Audio playing ${loaded} while UI shows ${expected}; halting and resyncing`)
      audio.pause()
      audio.dataset.loadedTrackId = expected
      playTrack(currentTrack, 0)
    })
    queueUnsubscribe = queue.subscribe(value => { activeQueue = value; currentTrack = value.nowPlaying; persistQueue(value); publishRemoteState(); if (trackKey(value.nowPlaying) !== companionForId) checkCompanionVideo(value.nowPlaying); if (value.nowPlaying && value.nowPlaying.videoId !== audio.dataset.track) { audio.dataset.track = value.nowPlaying.videoId; playTrack(value.nowPlaying, 0); extractAccent(value.nowPlaying) } if (value.nowPlaying?.videoId !== recommendationForId) loadRecommendations(value.nowPlaying); if (value.nowPlaying?.videoId !== discoverForId) loadDiscover(value.nowPlaying); if ($settings.autoRadio !== false && value.upNext.length <= 2 && !radioFilling && (value.nowPlaying || value.upNext[0])) { clearTimeout(radioTopupTimer); radioTopupTimer = setTimeout(() => { if ($settings.autoRadio !== false && activeQueue.upNext.length <= 2 && !radioFilling) radioTopup(activeQueue.upNext.at(-1) || activeQueue.nowPlaying) }, 1200) } syncPip(); window.__updateMediaSession?.() })
    unsubscribe = openPlaylist.subscribe(value => { if (value === null) full = null })
    // Restore the active view and session status immediately from localStorage
    // so a refresh doesn't reset the UI while the health probe is in flight.
    const savedViewRaw = localStorage.getItem('ytm.view')
    const savedView = savedViewRaw === 'all' ? 'home' : savedViewRaw
    if (['home', 'recent', 'favorites', 'discover', 'stats'].includes(savedView)) homeView = savedView
    const savedSession = localStorage.getItem('ytm.session')
    if (savedSession) sessionState = savedSession
    startRemoteSync()
    wireDesktopChrome()
    // Stale-while-revalidate: a returning session paints the home shell
    // immediately from restored state; the health probe and data feeds
    // reconcile quietly in the background without blocking first paint.
    const hasSavedSession = savedSession === 'ok' || savedSession === 'expired'
    if (hasSavedSession) {
      authenticated = true
      checking = false
    }
    try {
      const state = await waitForBackend()
      authenticated = state.authenticated === true || state.session === 'expired'
      sessionState = state.session || (state.authenticated ? 'ok' : 'unauthenticated')
      localStorage.setItem('ytm.session', sessionState)
      if (authenticated) {
        // Every section owns its own loading/error state, so these fire in
        // parallel and land as they arrive instead of gating the whole UI.
        loadPlaylists()
        loadDiscovery().catch(() => {})
        loadSmartPlaylists()
        loadLiked()
        loadFavoriteArtists()
        loadHomeExtras().catch(() => {})
      }
    } catch (error) {
      if (!hasSavedSession) authError = error.message
      // With a saved session, keep the painted home: per-section retry and
      // offline notices handle reconciliation instead of a full-screen gate.
    } finally { checking = false }
  })
  onDestroy(() => { unsubscribe?.(); queueUnsubscribe?.(); mixController.cancel(); clearTimeout(toastTimer); clearTimeout(justSwitchTimer); clearTimeout(remotePublishTimer); clearTimeout(searchTimer); clearTimeout(radioTopupTimer); clearInterval(remotePollTimer); clearInterval(partyPollTimer); remoteExecutedCommandIds.clear(); window.removeEventListener('pagehide', savePlayerState); audio?.pause() })
</script>

<svelte:window on:keydown={handleGlobalKeydown} />

<main class="app-root" class:with-player={currentTrack} class:home-shell={!checking && authenticated && !artistData && !albumData && !full}>
  {#if checking}<section class="loading"><span class="spinner"></span><p>Checking your account…</p></section>
  {:else if !authenticated}<section class="setup" aria-labelledby="setup-title"><div class="setup-mark">♫</div><h1 id="setup-title">Connect your YouTube Music</h1><div class="setup-tabs" role="tablist"><button role="tab" class:active={setupTab === 'oauth'} aria-selected={setupTab === 'oauth'} on:click={() => setupTab = 'oauth'}>Connect with Google</button><button role="tab" class:active={setupTab === 'paste'} aria-selected={setupTab === 'paste'} on:click={() => setupTab = 'paste'}>Paste credentials</button></div>
    {#if setupTab === 'oauth'}<div class="oauth-flow"><ol class="oauth-steps"><li>Create an OAuth client in <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer">Google Cloud Console</a> (type <strong>TVs and Limited Input devices</strong>, YouTube Data API v3 enabled) and paste its ID and secret:</li></ol><div class="oauth-fields"><input bind:value={oauthClientId} placeholder="Client ID" aria-label="OAuth client ID" autocomplete="off" /><input bind:value={oauthClientSecret} type="password" placeholder="Client secret" aria-label="OAuth client secret" autocomplete="off" /><button class="connect" disabled={oauthBusy || !oauthClientId.trim() || !oauthClientSecret.trim()} on:click={oauthStart}>{oauthBusy ? 'Starting…' : 'Start'}</button></div>
      {#if oauthDevice}<ol class="oauth-steps" start="2"><li>Open <a href={oauthDevice.verification_url + '?user_code=' + oauthDevice.user_code} target="_blank" rel="noreferrer">{oauthDevice.verification_url}</a> and enter code <strong class="user-code">{oauthDevice.user_code}</strong></li><li>After approving, click below:</li></ol><button class="connect" disabled={oauthBusy} on:click={oauthFinish}>{oauthBusy ? 'Connecting…' : 'I approved — connect me'}</button>{/if}
      {#if oauthError}<p class="error" role="alert">{oauthError}</p>{/if}</div>
    {:else}<p class="intro">Paste your <code>browser.json</code> contents or raw authentication headers to load your library.</p><textarea bind:value={authText} placeholder="Paste browser.json or request headers here…" aria-label="YouTube Music authentication data"></textarea>{#if authError}<p class="error" role="alert">{authError}</p>{/if}<button class="connect" disabled={connecting || !authText.trim()} on:click={connect}>{connecting ? 'Connecting…' : 'Connect Account'}</button>{/if}</section>
  {:else}  <svelte:component this={activeShell} homeView={homeView} searchQuery={searchQuery} onSearchChanged={searchChanged} onViewChange={setHomeView} onCreatePlaylist={() => showCreate = true} onOpenSmartCreator={() => showSmartModal = true} onOpenSettings={() => settingsOpen = true} playlists={playlists} onOpenPlaylist={open}>
    {#if artistData}<ArtistPage data={artistData} track={currentTrack} favorite={favoriteArtists.some(item => item.id === artistData?.browseId)} onToggleFavorite={() => toggleFavoriteArtist({ id: artistData?.browseId, name: artistData?.name, thumbnail: artistData?.thumbnail })} onPlay={(tracks) => tracks?.[0] && playQueue(tracks)} onTrack={(tracks, index) => playQueue(tracks, index)} onOpenAlbum={openAlbum} onPlayNext={playNextTrack} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} onStartMix={startMix} onClose={() => artistData = null} />
    {:else if albumData}<AlbumPage data={albumData} track={currentTrack} onPlay={(tracks) => tracks?.[0] && playQueue(tracks)} onTrack={(tracks, index) => playQueue(tracks, index)} onOpenArtist={(id, name) => openArtistEntity(id, name)} onOpenArtistEntity={openArtistEntity} onPlayNext={playNextTrack} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} onStartMix={startMix} onClose={() => albumData = null} />
    {:else if full}<div in:fade={{ duration: 200 }} out:fade={{ duration: 120 }}><SongPage playlist={full} track={currentTrack} onTrack={(track, index) => { if (activeQueue.nowPlaying?.videoId === track.videoId) togglePlay(); else { seed(full.tracks, index) } }} onPlay={() => full?.tracks?.[0] && playQueue(full.tracks)} onShuffle={() => playQueueShuffled(full?.tracks)} onPlayNext={playNextTrack} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} onStartMix={startMix} onRemoveTrack={removeTrackFromPlaylist} /></div>    {:else}<HomeView embedded searchQuery={searchQuery} onSearchChanged={searchChanged} searchResults={searchResults} searching={searching} searchError={searchError} homeView={homeView} onViewChange={setHomeView} sessionState={sessionState} sessionBannerDismissed={sessionBannerDismissed} onReconnect={reauthenticate} onDismissSession={() => sessionBannerDismissed = true} libraryCached={libraryCached} onDismissOffline={() => libraryCached = false} playlists={playlists} playlistsError={playlistsError} playlistsLoaded={playlistsLoaded} onRetryPlaylists={loadPlaylists} onOpenPlaylist={open} onCreatePlaylist={() => showCreate = true} onOpenSmartCreator={() => showSmartModal = true} onOpenSettings={() => settingsOpen = true} smartPlaylists={smartPlaylists} smartPlaylistsLoading={smartPlaylistsLoading} smartPlaylistsError={smartPlaylistsError} onRefreshSmart={loadSmartPlaylists} onOpenSmartPlaylist={openSmartPlaylist} stats={stats} quickPicks={quickPicks} smartMix={smartMix} recommendations={recommendations} currentTrack={currentTrack} recommendationLoading={recommendationLoading} upNext={activeQueue.upNext} history={activeQueue.history} currentTime={currentTime} duration={duration} isPlaying={isPlaying} volume={volume} loading={loadingTrack} onToggle={togglePlay} onOpenQueue={() => queueOpen = true} onOpenTheatre={() => theatreOpen = true} likedTracks={likedTracks} likedLoading={likedLoading} likedError={likedError} onRetryLiked={loadLiked} onPlayQueue={playQueue} onPlayNext={playNextTrack} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} onStartMix={startMix} onOpenBrowse={openBrowse} onArtworkLoad={extractAccent} moods={moods} activeMood={activeMood} moodPlaylists={moodPlaylists} moodLoading={moodLoading} onOpenMood={openMood} onOpenMoodPlaylist={(item) => item.browseId && open({id: item.browseId, title: item.title})} discoverTracks={discoverTracks} discoverLoading={discoverLoading} favoriteArtists={favoriteArtists} rotationTracks={rotationTracks} recentPlaylists={recentPlaylists} ytmShelves={ytmShelves} ytmFeedLoading={ytmFeedLoading} onRetryYtmFeed={loadYtmFeed} onOpenArtistEntity={openArtistEntity} onOpenAlbumEntity={openAlbumEntity} onOpenRecentPlaylist={(item) => item?.id && open({id: item.id, title: item.title})} onCompileArtistMix={compileArtistMix}/>
    {/if}
  </svelte:component>
  {/if}
</main>
{#if showCreate}<div class="modal-backdrop"><form class="modal" on:submit|preventDefault={createPlaylist}><h2>New Playlist</h2><input bind:value={newTitle} placeholder="Playlist name" required /><textarea bind:value={newDescription} placeholder="Description (optional)"></textarea><div><button type="button" on:click={() => showCreate = false}>Cancel</button><button class="primary" type="submit">Create</button></div></form></div>{/if}
<SmartPlaylistModal bind:isOpen={showSmartModal} on:saved={handleSmartPlaylistSaved} />
{#if showAddModal}<div class="sheet-backdrop" class:over-theatre={theatreOpen} role="presentation" on:click|self={() => showAddModal = false}><div class="picker-sheet" class:dragging={pickerDragStart !== null} style:transform={pickerDragY ? `translateY(${pickerDragY}px)` : null} role="dialog" tabindex="-1" aria-modal="true" aria-label="Add to playlist" transition:fly={{ y: 180, duration: 260 }} on:touchstart={onPickerDragStart} on:touchmove={onPickerDragMove} on:touchend={onPickerDragEnd} on:touchcancel={onPickerDragEnd}><div class="sheet-grab" aria-hidden="true"></div><header class="sheet-head"><div class="sheet-title"><h2>Add to Playlist</h2><p class="sheet-track">{clean(actionTrack?.title)} — {clean(actionTrack?.artist)}</p></div><button class="sheet-close" type="button" on:click={() => showAddModal = false} aria-label="Close playlist picker">×</button></header><div class="sheet-search"><input bind:value={pickerQuery} type="search" placeholder="Filter playlists" aria-label="Filter playlists" /><span class="sheet-checking" class:visible={pickerChecking}>Checking…</span></div><div class="sheet-list" bind:this={pickerListEl} role="listbox" aria-label="Playlists">{#each playlists.filter(p => p.owned && (!pickerQuery || clean(p.title).toLowerCase().includes(pickerQuery.toLowerCase()))) as p (p.id)}<button class="sheet-item" class:added={pickerMembership[p.id]} disabled={pickerMembership[p.id]} role="option" aria-selected={pickerMembership[p.id]} on:click={() => addTrackToPlaylist(p.id)}><span class="sheet-art">{#if p.thumbnail}<img src={p.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="sheet-name">{clean(p.title)}</span><span class="sheet-count">{p.count ?? 0}</span><span class="sheet-badge">{#if pickerMembership[p.id]}Added{/if}</span></button>{/each}{#if !playlists.some(p => p.owned)}<p class="sheet-empty">No editable playlists found. Create one first.</p>{:else if !playlists.filter(p => p.owned).some(p => !pickerQuery || clean(p.title).toLowerCase().includes(pickerQuery.toLowerCase()))}<p class="sheet-empty">No playlists match “{pickerQuery}”.</p>{/if}</div><footer class="sheet-foot"><button type="button" on:click={() => showAddModal = false}>Done</button></footer></div></div>{/if}
{#if settingsOpen}<SettingsModal onClose={() => settingsOpen = false} onDisconnect={reauthenticate} onToast={showToast} onDataRefresh={refreshAfterAuth} />{/if}
{#if toast}<div class="toast" role="status">{toast}</div>{/if}
{#if dragActive}<div class="drop-overlay" aria-hidden="true"><div class="drop-card"><strong>Drop to add to your library</strong><span>mp3, flac, wav, m4a</span></div></div>{/if}
<TransportBar track={currentTrack} isPlaying={isPlaying} currentTime={currentTime} duration={duration} volume={volume} shuffle={activeQueue.shuffle} repeat={activeQueue.repeat} loading={loadingTrack} onPrevious={previous} onToggle={togglePlay} onNext={next} onShuffle={toggleShuffle} onRepeat={cycleRepeat} onSeek={seek} onVolume={setVolume} onQueue={() => queueOpen = !queueOpen} onTheatre={() => theatreOpen = true} onPip={togglePip} onPlayNext={playNextTrack} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} onStartMix={startMix} onOpenArtist={openArtistEntity} />  {#if theatreOpen}<TheatreMode track={currentTrack} isPlaying={isPlaying} currentTime={currentTime} duration={duration} shuffle={activeQueue.shuffle} repeat={activeQueue.repeat} hasVideo={hasVideo} companionVideoId={companionVideoId} history={activeQueue.history} upNext={activeQueue.upNext} recommendations={recommendations} onClose={() => theatreOpen = false} party={partyRoom} partyPopoverOpen={partyPopoverOpen} partySetupOpen={partySetupOpen} onPartyOpen={openPartyPopover} onPartyLaunch={launchParty} onPartyApprove={onPartyApprove} onPartyReject={onPartyReject} onPartyRole={onPartyRole} onPartyKick={onPartyKick} onPartySetting={onPartySetting} onPartyCopyInvite={onPartyCopyInvite} onPartyEnd={endParty} queueOpen={queueOpen} onQueue={() => queueOpen = !queueOpen} onToggle={togglePlay} onNext={next} onPrevious={previous} onSeek={seek} onShuffle={toggleShuffle} onRepeat={cycleRepeat} onPlayQueue={jumpTo} onPlayRecommendation={startMix} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} onSaveToPlaylist={saveTrackToPlaylist} onSaveQueueAsPlaylist={saveQueueAsPlaylist} playlists={playlists} onCreatePlaylist={createPlaylistFromName} onFavorite={toggleTrackFavorite} onRemoveUpcoming={(track) => removeUpcoming(track?.videoId)} onClearQueue={clearUpcoming} onClearManualQueue={flushManualQueue} onReorder={(from, to) => reorderUpcoming(from, to)} onStartMix={startMix} />{/if}
{#if queueOpen && !theatreOpen}<aside class="queue-drawer" class:over-theatre={theatreOpen} aria-label="Playback queue"><div class="queue-head"><h2>Playback Manager</h2><button class="queue-close" on:pointerdown|preventDefault={() => queueOpen = false} on:keydown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); queueOpen = false } }} aria-label="Close queue" title="Close queue"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 18 18 6M6 6l12 12"></path></svg></button></div><div class="queue-tabs" role="tablist" aria-label="Playback manager views"><button class:active={queueTab === 'queue'} role="tab" aria-selected={queueTab === 'queue'} on:click={() => queueTab = 'queue'}>Up Next <span>{activeQueue.upNext.length}</span></button><button class:active={queueTab === 'recommendations'} role="tab" aria-selected={queueTab === 'recommendations'} on:click={() => queueTab = 'recommendations'}>Recommended <span>{recommendations.length}</span></button></div>{#if queueTab === 'queue'}<div class="queue-section"><h3>History <span>{activeQueue.history.length}</span></h3>{#if activeQueue.history.length}<div class="history-row"><span class="queue-art">{#if activeQueue.history.at(-1).thumbnail}<img src={activeQueue.history.at(-1).thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="queue-title">{clean(activeQueue.history.at(-1).title)}<small>{clean(activeQueue.history.at(-1).artist)}</small></span></div>{:else}<p class="empty">Nothing played yet</p>{/if}</div><div class="queue-section upcoming"><div class="upcoming-head"><h3>Up Next <span>{activeQueue.upNext.length}</span></h3><button on:click={clearUpcoming} disabled={!activeQueue.upNext.length}>Clear</button></div>{#each activeQueue.upNext as item, index (item.videoId)}<div class="queue-row" class:dragging={draggedIndex === index} role="listitem" draggable="true" on:dragstart={() => dragStart(index)} on:dragend={() => draggedIndex = -1} on:dragover|preventDefault on:drop={() => dropAt(index)}><span class="grip">⋮⋮</span><button class="queue-item" on:click={() => jumpTo(item)}><span class="queue-art">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="queue-title">{clean(item.title)}<small>{clean(item.artist)}</small></span></button><button class="remove" on:click={() => removeUpcoming(item.videoId)} aria-label="Remove {clean(item.title)}">×</button><TrackContextMenu track={item} onPlayNext={playNextTrack} onAddToQueue={appendTrack} onAddToPlaylist={openAddModal} onStartMix={startMix} /></div>{/each}{#if !activeQueue.upNext.length}<p class="empty">Queue is empty</p>{/if}</div>{:else}<div class="queue-recommendations">{#if recommendations.length}{#each recommendations as rec, index (rec.videoId || index)}<div class="queue-recommendation-row mixable-track"><button class="queue-item" on:click={() => playQueue([rec])}><span class="queue-art">{#if rec.thumbnail}<img src={rec.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="queue-title">{clean(rec.title)}<small>{clean(rec.artist)}</small></span></button><button class="queue-add" on:click={() => appendTrack(rec)} aria-label="Add {clean(rec.title)} to queue">＋</button><StartMixButton track={rec} onStartMix={startMix} /></div>{/each}{:else}<div class="queue-empty-state"><strong>No recommendations loaded</strong><span>Play a track to discover similar songs.</span></div>{/if}</div>{/if}</aside>{/if}

<style>
  .app-root { height: 100vh; min-height: 0; display: flex; flex-direction: column; overflow: hidden; box-sizing: border-box; padding: 0; color: #f2ece4; --font-display: 'Anton', Impact, sans-serif; --font-ui: 'Manrope', ui-sans-serif, sans-serif; background: #09090b; font-family: var(--font-ui); } .app-root.with-player { padding-bottom: 0; } .home-shell { isolation: isolate; } .view-transition { display: contents; } h1 { margin: 0; font-family: var(--font-display); font-size: clamp(2rem, 4vw, 3rem); }.home-head { display: flex; align-items: end; justify-content: space-between; margin-bottom: 28px; } .home-head h1 { background: linear-gradient(115deg, #fff 15%, color-mix(in srgb, var(--accent, #c4b5fd) 75%, #fff) 60%, color-mix(in srgb, var(--accent, #c4b5fd) 60%, #fff)); -webkit-background-clip: text; background-clip: text; color: transparent; letter-spacing: -.03em; } .ambient-blob { position: fixed; top: -28vh; left: 50%; transform: translateX(-50%); width: 150vmax; height: 90vh; border-radius: 50%; background: radial-gradient(circle at 50% 50%, var(--ambient, #7c5fc7), transparent 62%); opacity: .22; filter: blur(110px); z-index: 0; pointer-events: none; transition: background 1.5s ease; } .loading, .setup { position: relative; z-index: 1; } .view-transition > * { position: relative; z-index: 1; } .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 6px; } .chip { padding: 7px 16px; border: 1px solid rgba(255,255,255,.12); border-radius: 999px; color: #b8b8c0; background: rgba(255,255,255,.05); cursor: pointer; font-size: .78rem; font-weight: 600; transition: all .18s ease; backdrop-filter: blur(12px); } .chip:hover { color: #fff; border-color: rgba(255,255,255,.24); background: rgba(255,255,255,.1); } .chip.active { color: #111; background: var(--accent, #c4b5fd); border-color: transparent; box-shadow: 0 2px 14px color-mix(in srgb, var(--accent, #c4b5fd) 45%, transparent); }  .status.expired { border: 1px solid #fbbf2433; border-radius: 999px; padding: 6px 12px; color: #fbbf24; background: #fbbf240f; cursor: pointer; font-size: .78rem; font-weight: 600; transition: background .15s ease; } .status.expired:hover { background: #fbbf241f; } .empty-shelf.library-empty { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; padding: 26px 4px; } .library-empty strong { color: #f4f4f5; font-size: .95rem; } .library-empty span { color: #a1a1aa; font-size: .82rem; } .chip-row { display: flex; gap: 8px; margin-top: 6px; }  .rotation,.quick { margin: 28px 0 34px; }  .rotation { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:18px; padding:24px; border:1px solid rgba(255,255,255,.08); border-radius:18px; background:linear-gradient(135deg, rgba(255,255,255,.07) 0%, rgba(255,255,255,.02) 100%); backdrop-filter: blur(20px); }.rotation h2,.quick h2,.section-head h2 { margin:0; font-family: var(--font-display); font-size:1.45rem; letter-spacing:-.01em; }.rotation-copy,.section-head>span { color:#a1a1aa; font-size:.83rem; }.recap { display:flex; align-items:center; gap:12px; min-width:280px; padding:10px; border:1px solid rgba(255,255,255,.07); border-radius:12px; color:#eee; background:#ffffff0b; text-align:left; cursor:pointer; }.recap-art,.quick-art { position:relative; display:grid; place-items:center; overflow:hidden; background:linear-gradient(135deg,#252331,#4d3640); }.recap-art { width:58px; height:58px; border-radius:8px; }  .recap-art img,.quick-art img { width:100%; height:100%; object-fit:cover; }.recap div:nth-child(2) { display:flex; flex-direction:column; flex:1; }.recap span,.quick-card>span { color:#a1a1aa; font-size:.78rem; margin-top:3px; }.quick { overflow:hidden; } .quick-card-wrap { position:relative; flex:0 0 150px; min-width:0; } .quick-card-wrap .quick-card { width:100%; } .pl-art::after, .quick-art::after, .card-art::after, .recap-art::after { content: ''; position: absolute; inset: 0; z-index: 0; background: linear-gradient(to top, rgba(0,0,0,.4), transparent 42%); pointer-events: none; }.section-head { display:flex; justify-content:space-between; align-items:end; margin-bottom:14px; }.carousel-controls { display:flex; align-items:center; gap:10px; }.carousel-controls button { display:grid; place-items:center; width:28px; height:28px; border:1px solid #ffffff1c; border-radius:50%; color:#ddd; background:#ffffff0a; cursor:pointer; opacity:.55; transition:.2s; }.quick:hover .carousel-controls button { opacity:1; }.quick-row { display:flex; gap:14px; overflow-x:auto; padding:3px 4px 14px; scrollbar-width:none; -ms-overflow-style:none; } .quick-card-wrap .mix-trigger { top:8px; right:8px; }.quick-row::-webkit-scrollbar { display:none; }  .quick-card { flex:0 0 150px; border:0; padding:0; color:#eee; background:none; text-align:left; cursor:pointer; transition: transform .2s ease; }.quick-card:hover { transform: translateY(-4px) scale(1.02); }.quick-art { aspect-ratio:1; margin-bottom:10px; border-radius:12px; border:1px solid rgba(255,255,255,.06); box-shadow: 0 4px 14px rgba(0,0,0,.3); transition: transform .2s ease, box-shadow .2s ease; }.quick-card:hover .quick-art { transform: scale(1.02); box-shadow: 0 12px 30px rgba(0,0,0,.6); }.quick-art i { position:absolute; right:8px; bottom:8px; z-index:1; display:grid; place-items:center; width:32px; height:32px; border-radius:50%; color:#111; background:#fff; font-style:normal; opacity:0; transition:.2s; }.quick-card:hover .quick-art i { opacity:1; }.quick-card strong,.quick-card>span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.quick-card strong { font-size:.88rem; }.error { color: #fca5a5; }  .empty-shelf { color:#71717a; font-size:.85rem; padding:20px 4px; } .session-banner { display:flex; align-items:center; gap:12px; margin:0 0 18px; padding:11px 14px; border:1px solid #fbbf2433; border-radius:12px; color:#fde68a; background:#fbbf240f; font-size:.84rem; } .session-banner.offline { border-color:#38bdf833; color:#bae6fd; background:#38bdf80f; } .session-banner.offline .banner-close { color:#7dd3fc; } .banner-link { border:0; border-radius:8px; padding:6px 12px; color:#fff; background:#fbbf2433; cursor:pointer; font-size:.78rem; font-weight:600; } .banner-link:hover { background:#fbbf2450; } .banner-close { margin-left:auto; border:0; background:none; color:#fbbf24; cursor:pointer; font-size:1.1rem; } .setup-tabs { display:flex; gap:8px; margin:20px 0 18px; } .setup-tabs button { flex:1; padding:10px 8px; border:1px solid #ffffff1c; border-radius:10px; color:#a1a1aa; background:#ffffff08; cursor:pointer; font-size:.85rem; font-weight:600; transition:.18s; } .setup-tabs button.active { color:#fff; background:#ffffff18; border-color:#ffffff38; } .oauth-flow .oauth-steps { margin:0 0 14px; padding-left:20px; color:#a1a1aa; font-size:.88rem; line-height:1.6; } .oauth-flow .oauth-steps a { color:#c4b5fd; } .oauth-flow .oauth-steps .user-code { color:#fff; font-size:1.15rem; letter-spacing:.12em; } .oauth-fields { display:flex; flex-direction:column; gap:10px; margin-bottom:14px; } .oauth-fields input { padding:12px 14px; border:1px solid #ffffff24; border-radius:12px; color:#eee; background:#0005; font-size:.9rem; }.pl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 28px; }  .pl { position: relative; overflow: hidden; text-align: left; color: #eee; background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.09);border-radius: 22px; padding: 18px; cursor:pointer; transition: .25s ease; backdrop-filter: blur(20px); }.pl.hero { grid-column: span 2; display: grid; grid-template-columns: 128px 1fr; align-items: center; gap: 18px; padding: 22px; background: linear-gradient(135deg, color-mix(in srgb, var(--accent, #c4b5fd) 13%, rgba(255,255,255,.05)), rgba(255,255,255,.02)); }.pl.hero .pl-art { width: 128px; margin: 0; border-radius: 14px; }.pl.hero .pl-title { font-family: var(--font-display); font-size: 1.35rem; }.pl.hero .pl-count { margin-top: 6px; }.pl.ghost { background: none; border: 1px dashed rgba(255,255,255,.12); backdrop-filter: none; padding: 14px; display: flex; align-items: center; gap: 14px; border-radius: 14px; }.pl.ghost:hover { transform: none; box-shadow: none; border-color: rgba(255,255,255,.22); background: rgba(255,255,255,.03); }.pl.ghost .pl-art { width: 48px; flex: 0 0 auto; margin: 0; font-size: 1.3rem; border-radius: 10px; }.pl.ghost .pl-title { font-size: .92rem; }.pl.ghost .pl-count { margin-top: 2px; font-size: .74rem; }.pl.ghost .float-play { display: none; }.pl:hover { border-color: rgba(255,255,255,.18); transform: translateY(-4px) scale(1.02); box-shadow: 0 12px 30px rgba(0,0,0,.6); }.pl-art { position: relative; display: grid; place-items: center; aspect-ratio: 1; overflow: hidden; border-radius: 12px; margin-bottom: 14px; background: linear-gradient(135deg, #252331, #4d3640); color: #fff; font-size: 4rem; }.pl-art img, .mini-art img { width: 100%; height: 100%; object-fit: cover; }  .float-play { position: absolute; right: 12px; bottom: 12px; z-index: 1; display: grid; place-items: center; width: 42px; height: 42px; border-radius: 50%; color: #111; background: #fff; font-size: .9rem; opacity: 0; transition: .2s ease; }.pl-title { font-weight: 600; }.setup { width: min(560px,100%); margin: 7vh auto 0; padding: 38px; border: 1px solid #ffffff1f; border-radius: 24px; background: #ffffff0b; backdrop-filter: blur(20px); }.setup-mark { display: grid; place-items: center; width: 58px; height: 58px; border-radius: 16px; background: linear-gradient(135deg,#7c5fc7,#d18564); font-size: 2rem; }.intro { color: #a1a1aa; line-height: 1.55; }textarea { display: block; width: 100%; min-height: 150px; box-sizing: border-box; margin: 24px 0 12px; padding: 14px; border: 1px solid #ffffff24; border-radius: 12px; color: #eee; background: #0005; font: .8rem ui-monospace,monospace; }.connect { border: 0; border-radius: 22px; padding: 12px 20px; cursor: pointer; font-weight: 700; }.connect:disabled { opacity: .45; }  .loading { display:grid; place-items:center; min-height:70vh; color:#a1a1aa; }.spinner { width:24px;height:24px;border:2px solid #444;border-top-color:#fff;border-radius:50%;animation:spin .8s linear infinite }@keyframes spin {to{transform:rotate(360deg)}}
  .drop-overlay { position: fixed; inset: 0; z-index: 200; display: grid; place-items: center; background: #0d0b0a99; backdrop-filter: blur(6px); pointer-events: none; }
  .drop-card { display: flex; flex-direction: column; align-items: center; gap: 7px; padding: 36px 52px; border: 2px dashed #f2ece466; border-radius: 26px; color: #f2ece4; background: #17110fe6; }
  .drop-card strong { font-family: 'Anton', Impact, sans-serif; font-size: 1.45rem; font-weight: 400; letter-spacing: .01em; }
  .drop-card span { color: #a99b8f; font-size: .78rem; }
  .search-wrap { position:relative; display:flex; align-items:center; }.global-search { width:min(420px,55vw); padding:12px 58px 12px 16px; border:1px solid #ffffff1c; border-radius:12px; color:#fff; background:#ffffff0b; outline:none; }.global-search:focus { border-color:var(--accent,#c4b5fd); box-shadow:0 0 0 3px color-mix(in srgb, var(--accent,#c4b5fd) 13%, transparent); }.search-wrap kbd { position:absolute; right:12px; color:#888; font-size:.7rem; }.search-results { margin:30px 0; }.search-shelf { margin:26px 0; }.search-shelf h3 { margin:0 0 12px; color:#a1a1aa; font-size:.75rem; text-transform:uppercase; letter-spacing:.14em; }.song-list { border:1px solid #ffffff10; border-radius:14px; overflow:hidden; background:#ffffff06; }.song-row { display:flex; align-items:center; gap:6px; padding-right:8px; }.song-row:hover { background:#ffffff0d; }.song-main { display:flex; align-items:center; gap:12px; flex:1; min-width:0; border:0; padding:9px 12px; color:#eee; background:none; text-align:left; cursor:pointer; }.song-art { width:44px; height:44px; flex:0 0 auto; display:grid; place-items:center; overflow:hidden; border-radius:8px; background:linear-gradient(135deg,#252331,#4d3640); font-size:1.2rem; }.song-art img { width:100%; height:100%; object-fit:cover; }.song-meta { min-width:0; flex:1; display:flex; flex-direction:column; }.song-meta strong,.song-meta small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.song-meta strong { font-size:.9rem; }.song-meta small { color:#a1a1aa; font-size:.78rem; margin-top:3px; }.song-dur { color:#71717a; font-size:.8rem; font-variant-numeric:tabular-nums; }.song-play { color:#a1a1aa; font-size:.8rem; margin:0 6px; }.song-row:hover .song-play { color:var(--accent,#c4b5fd); } .song-main { transition: transform .18s ease; } .song-row:hover .song-main { transform: translateX(3px); }.card-row { display:flex; gap:16px; overflow-x:auto; padding:3px 4px 12px; scrollbar-width:none; -ms-overflow-style:none; }.card-row::-webkit-scrollbar { display:none; }.browse-card { flex:0 0 150px; border:0; padding:0; color:#eee; background:none; text-align:left; cursor:pointer; transition: transform .2s ease; }.browse-card:hover { transform: translateY(-3px); }.card-art { aspect-ratio:1; display:grid; place-items:center; overflow:hidden; border-radius:14px; background:linear-gradient(135deg,#252331,#4d3640); font-size:2.5rem; margin-bottom:9px; transition:.2s; }.browse-card:hover .card-art { transform:scale(1.03); box-shadow:0 12px 30px #0009; }.card-art img { width:100%; height:100%; object-fit:cover; }.browse-card strong,.browse-card>span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.browse-card strong { font-size:.86rem; }.browse-card>span { color:#a1a1aa; font-size:.76rem; margin-top:3px; }  .new-playlist { border:1px solid #ffffff1c; border-radius:8px; padding:6px 8px; color:#ddd; background:#ffffff0b; cursor:pointer; margin-left:12px; }.smart-playlist-launcher { border:1px solid #9b87ff55; border-radius:8px; padding:6px 9px; color:#c4b5fd; background:#9b87ff12; cursor:pointer; margin-left:8px; font-size:.78rem; font-weight:600; }.smart-playlist-launcher:hover { background:#9b87ff22; }.smart-collections { margin:28px 0 34px; padding:20px; border:1px solid #9b87ff24; border-radius:16px; background:linear-gradient(135deg,#9b87ff0d,#ffffff03); }.smart-refresh { border:0; border-radius:8px; padding:6px 9px; color:#aaa; background:#ffffff0a; cursor:pointer; font-size:.72rem; }.smart-refresh:hover { color:#fff; background:#ffffff14; }.smart-refresh:disabled { cursor:wait; opacity:.5; }.smart-list { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:8px; }.smart-collection { display:flex; align-items:center; gap:10px; min-width:0; padding:11px; border:1px solid #ffffff0c; border-radius:11px; color:#eee; background:#ffffff06; text-align:left; cursor:pointer; }.smart-collection:hover { border-color:#9b87ff55; background:#ffffff0d; }.smart-icon { display:grid; place-items:center; width:30px; height:30px; flex:0 0 auto; border-radius:8px; color:#c4b5fd; background:#9b87ff1a; }.smart-copy { min-width:0; flex:1; }.smart-copy strong,.smart-copy small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.smart-copy strong { font-size:.82rem; }.smart-copy small { margin-top:3px; color:#858593; font-size:.68rem; }.smart-live { color:#b9aaff; font-size:.68rem; white-space:nowrap; }.search-status { color:#a1a1aa; }.sheet-backdrop { position:fixed; inset:0; z-index:90; display:flex; align-items:flex-end; justify-content:center; background:#000a; }.picker-sheet { display:flex; flex-direction:column; width:min(560px,100%); max-height:85vh; padding:14px 20px calc(18px + env(safe-area-inset-bottom)); border:1px solid #ffffff1c; border-bottom:0; border-radius:22px 22px 0 0; background:#1b1b22; box-shadow:0 -18px 60px #000a; transform:translateZ(0); transition:transform .25s cubic-bezier(.2,.8,.2,1); }.picker-sheet.dragging { transition:none; }.sheet-grab { width:42px; height:4px; flex:0 0 auto; margin:0 auto 12px; border-radius:999px; background:#ffffff2b; }.sheet-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }.sheet-head h2 { margin:0; font-size:1.05rem; }.sheet-track { margin:4px 0 0; color:#a1a1aa; font-size:.82rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.sheet-close { flex:0 0 auto; width:30px; height:30px; border:0; border-radius:50%; color:#aaa; background:#ffffff0b; cursor:pointer; font-size:1.2rem; line-height:1; }.sheet-close:hover { color:#fff; background:#ffffff18; }.sheet-search { position:relative; display:flex; align-items:center; margin:14px 0 10px; }.sheet-search input { box-sizing:border-box; width:100%; padding:11px 88px 11px 13px; border:1px solid #ffffff1c; border-radius:11px; background:#0004; color:#fff; outline:none; font:inherit; }.sheet-search input:focus { border-color:var(--accent,#c4b5fd); }.sheet-checking { display:none; position:absolute; right:13px; color:#71717a; font-size:.72rem; pointer-events:none; }.sheet-checking.visible { display:block; }.sheet-list { display:flex; flex:1; min-height:0; flex-direction:column; gap:6px; overflow-y:auto; overscroll-behavior:contain; padding:2px 4px 2px 0; scrollbar-width:thin; scrollbar-color:#ffffff2b transparent; }.sheet-list::-webkit-scrollbar { width:6px; }.sheet-list::-webkit-scrollbar-track { background:transparent; }.sheet-list::-webkit-scrollbar-thumb { border-radius:999px; background:#ffffff2b; }.sheet-list::-webkit-scrollbar-thumb:hover { background:#ffffff4a; }.sheet-item { display:flex; align-items:center; gap:11px; width:100%; border:0; border-radius:12px; padding:10px 12px; color:#eee; background:#ffffff08; text-align:left; cursor:pointer; }.sheet-item:not(:disabled):hover { background:#ffffff14; }.sheet-item:disabled { cursor:default; opacity:.8; }.sheet-art { width:40px; height:40px; flex:0 0 auto; display:grid; place-items:center; overflow:hidden; border-radius:8px; background:linear-gradient(135deg,#252331,#4d3640); font-size:1rem; }.sheet-art img { width:100%; height:100%; object-fit:cover; }.sheet-name { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:.88rem; }.sheet-count { color:#71717a; font-size:.75rem; }.sheet-badge { flex:0 0 auto; padding:3px 9px; border:1px solid #2d5e3a; border-radius:999px; color:#8fd6a2; background:#1d3323; font-size:.68rem; font-weight:600; }.sheet-empty { color:#71717a; font-size:.85rem; padding:20px 4px; text-align:center; }.sheet-foot { display:flex; justify-content:flex-end; margin-top:14px; padding-top:12px; border-top:1px solid #ffffff0c; }.sheet-foot button { padding:9px 15px; border:0; border-radius:8px; color:#eee; background:#ffffff12; cursor:pointer; }.modal-backdrop { position:fixed;inset:0;z-index:90;display:grid;place-items:center;background:#0009; }.modal { width:min(420px,calc(100vw - 32px)); padding:26px; border:1px solid #ffffff1c; border-radius:18px; background:#1b1b22; box-shadow:0 25px 70px #0009; }.modal h2 { margin-top:0; }.modal input,.modal textarea { box-sizing:border-box;width:100%;margin:8px 0;padding:11px;border:1px solid #ffffff1c;border-radius:9px;background:#0004;color:#fff; }.modal textarea { min-height:90px; }.modal>div { display:flex;justify-content:flex-end;gap:8px;margin-top:12px; }.modal button { padding:9px 15px;border:0;border-radius:8px;cursor:pointer; }.modal .primary { background:#fff;color:#111; }
  .player { position: fixed; z-index: 30; left: 18px; right: 18px; bottom: 18px; display: flex; align-items: center; gap: 22px; min-height: 68px; padding: 12px 18px; border: 1px solid color-mix(in srgb, var(--accent, #c4b5fd) 24%, transparent); border-radius: 16px; background: linear-gradient(120deg, color-mix(in srgb, var(--accent, #c4b5fd) 9%, #17171c) 0%, #17171cd9 65%); box-shadow: 0 15px 45px #0009, 0 0 42px color-mix(in srgb, var(--accent, #c4b5fd) 16%, transparent); backdrop-filter: blur(20px); }.now { display:flex; align-items:center; gap:10px; width: 25%; min-width: 170px; }.mini-art { width:46px;height:46px;display:grid;place-items:center;flex:0 0 auto;overflow:hidden;border-radius:7px;background:linear-gradient(135deg,#252331,#4d3640); }.now-meta { min-width:0;display:flex;flex-direction:column; }.now-meta strong,.now-meta span { overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }.now-meta span { color:#a1a1aa;font-size:.8rem;margin-top:3px; }  .controls { display:flex;align-items:center;gap:14px; }.controls .secondary { width:24px;font-size:.8rem;opacity:.55; }.controls .secondary:hover { opacity:1; }.controls .secondary.enabled { opacity:1; }.controls button { border:0;background:none;color:#aaa;cursor:pointer;font-size:1rem; transition: color .15s ease; }.controls button:hover { color:#f4f4f5; }.controls button.enabled { color:var(--accent,#c4b5fd); }.controls .pause { width:38px;height:38px;border-radius:50%;color:#111;background:#f4f4f5; box-shadow:0 0 18px color-mix(in srgb, var(--accent,#c4b5fd) 45%, transparent); will-change: transform; }.progress { display:flex;align-items:center;gap:10px;flex:1;color:#a1a1aa;font-size:.72rem; }.progress input { flex:1; accent-color:var(--accent,#c4b5fd); }.volume { display:flex;align-items:center;gap:5px;color:#aaa; }.volume input { width:75px;accent-color:var(--accent,#c4b5fd); }  .loading-label { color:var(--accent,#c4b5fd);font-size:.72rem; }.queue-toggle,.expand-toggle,.pip-toggle { border:0; border-radius:8px; padding:7px 8px; color:#bbb; background:none; cursor:pointer; font-size:.88rem; transition: background .15s ease, color .15s ease; }.queue-toggle:hover,.expand-toggle:hover,.pip-toggle:hover { background:#ffffff14; color:#fff; }.queue-toggle .label,.expand-toggle .label,.pip-toggle .label { margin-left:5px; font-size:.74rem; }
  .settings-toggle { border:1px solid #ffffff1c; border-radius:8px; padding:7px 10px; color:#ddd; background:#ffffff0a; cursor:pointer; margin-left:10px; font-size:1rem; transition: background .15s ease, color .15s ease; }.settings-toggle:hover { background:#ffffff18; color:#fff; }
  html.reduce-motion *, html.reduce-motion *::before, html.reduce-motion *::after { animation: none !important; transition: none !important; }
  .queue-drawer { position:fixed; z-index:40; top:0; right:0; bottom:0; width:min(360px,92vw); padding:24px 16px; overflow:auto; color:#f4f4f5; background:rgba(10,10,12,.75); box-shadow:-20px 0 60px #0008; backdrop-filter:blur(24px); }.queue-tabs { display:grid; grid-template-columns:1fr 1fr; gap:4px; margin:0 0 10px; padding:4px; border:1px solid #ffffff0d; border-radius:10px; background:#ffffff08; }.queue-tabs button { border:0; border-radius:7px; padding:8px 6px; color:#a1a1aa; background:transparent; cursor:pointer; font-size:.74rem; font-weight:600; transition:background .15s ease, color .15s ease; }.queue-tabs button:hover { color:#fff; background:#ffffff0b; }.queue-tabs button.active { color:#111; background:#fff; box-shadow:0 3px 10px #0005; }.queue-tabs button span { margin-left:3px; color:inherit; opacity:.65; font-weight:400; }.queue-recommendations { display:flex; flex-direction:column; gap:2px; }.queue-recommendation-row { display:flex; align-items:center; border-radius:6px; transition:background .15s ease; }.queue-recommendation-row:hover { background:#ffffff0d; }.queue-recommendation-row .queue-item { padding:7px 4px; }.queue-add { width:30px; height:30px; border:0; border-radius:50%; color:#a1a1aa; background:none; cursor:pointer; font-size:1.1rem; }.queue-add:hover { color:#fff; background:#ffffff18; }.queue-empty-state { display:flex; flex-direction:column; gap:5px; align-items:center; justify-content:center; min-height:220px; color:#71717a; text-align:center; }.queue-empty-state strong { color:#a1a1aa; font-size:.86rem; }.queue-empty-state span { font-size:.76rem; }.queue-head,.upcoming-head { display:flex; align-items:center; justify-content:space-between; }.queue-drawer.over-theatre { z-index:200; }.sheet-backdrop.over-theatre { z-index:210; }.queue-head h2 { margin:0 0 16px; color:#ffffffed; font-family:var(--font-ui),ui-sans-serif,sans-serif; font-size:.82rem; font-weight:650; letter-spacing:.08em; text-transform:uppercase; }.queue-head>button,.upcoming-head button { border:0;background:none;color:#aaa;cursor:pointer;font-size:1.5rem; }.queue-head .queue-close { display:grid; place-items:center; width:30px; height:30px; margin-top:-5px; border:1px solid #ffffff12; border-radius:50%; color:#ffffff8c; background:#ffffff08; transition:background .18s ease,color .18s ease,transform .18s ease; }.queue-head .queue-close:hover { color:#fff; background:#ffffff16; transform:scale(1.05); }.queue-head .queue-close svg { width:15px; height:15px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }.queue-section { padding:14px 0; }.queue-section h3 { margin:0 0 10px;font-size:.72rem;text-transform:uppercase;letter-spacing:.14em;color:#a1a1aa; }.queue-section h3 span { color:#71717a;font-weight:400; }.history-row,.queue-row { border-radius:6px; }.history-row { display:flex;align-items:center;gap:10px;padding:8px;color:#a1a1aa; }  .queue-row { display:flex;align-items:center;margin:2px 0;transition:background .15s ease, transform .18s ease, opacity .18s ease; }.queue-row:hover { background:rgba(255,255,255,.05); }.queue-row.dragging { transform: scale(1.03); opacity:.65; background:rgba(255,255,255,.06); }.queue-item { display:flex;align-items:center;gap:10px;flex:1;min-width:0;border:0;padding:8px;background:none;color:#eee;text-align:left;cursor:pointer; }.queue-art { width:40px;height:40px;flex:0 0 auto;display:grid;place-items:center;overflow:hidden;border-radius:6px;background:linear-gradient(135deg,#252331,#4d3640);font-size:.9rem; }.queue-art img { width:100%;height:100%;object-fit:cover; }.queue-title { min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.86rem;font-weight:600; }.queue-title small { display:block;color:#a1a1aa;font-weight:400;margin-top:2px;font-size:.74rem; }.grip { color:#555;opacity:0;padding:0 4px;font-size:.9rem;cursor:grab;transition:opacity .15s ease; }.queue-row:hover .grip { opacity:1; }.remove { opacity:0;border:0;background:none;color:#fca5a5;cursor:pointer;font-size:1.1rem;padding:8px 10px; }.queue-row:hover .remove { opacity:1; }.empty { color:#71717a;font-size:.85rem;padding:4px; }.upcoming-head button { font-size:.75rem;border:0;background:none;color:#aaa;cursor:pointer; }.upcoming-head button:disabled { opacity:.4; }.now-menu { color:#71717a; }.now-menu .dot-btn { font-size:.95rem; }@media(max-width:720px){main{padding:24px 16px}.pl.hero{grid-column:auto;grid-template-columns:96px 1fr}.pl.hero .pl-art{width:96px}.player{left:8px;right:8px;bottom:8px;flex-wrap:wrap;gap:8px}.now{width:100%}.progress{order:3;width:100%}.volume{display:none}.queue-toggle .label,.expand-toggle .label,.pip-toggle .label{display:none}}
</style>
