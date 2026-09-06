<script>
  import { onMount, onDestroy } from 'svelte'
  import { apiFetch } from '../lib/api.js'
  import StatsView from '../pages/StatsView.svelte'
  import UpdatesView from '../pages/UpdatesView.svelte'
  import TrackCard from './TrackCard.svelte'
  import RecentlyPlayedView from '../pages/RecentlyPlayedView.svelte'
  import DiscoverView from '../pages/DiscoverView.svelte'
  import FavoritesView from '../pages/FavoritesView.svelte'
  import TrackContextMenu from './TrackContextMenu.svelte'
  import { createHoverPreview } from '../lib/preview_controller.js'

  export let embedded = false
  export let searchQuery = ''
  export let onSearchChanged = () => {}
  export let searchResults = []
  export let searching = false
  export let searchError = ''
  export let homeView = 'home'
  export let onViewChange = () => {}
  export let sessionState = 'ok'
  export let sessionBannerDismissed = false
  export let onReconnect = () => {}
  export let onDismissSession = () => {}
  export let libraryCached = false
  export let onDismissOffline = () => {}
  export let playlists = []
  export let playlistsError = ''
  export let playlistsLoaded = false
  export let onRetryPlaylists = () => {}
  export let onOpenPlaylist = () => {}
  export let onCreatePlaylist = () => {}
  export let onOpenSmartCreator = () => {}
  export let onOpenSettings = () => {}
  export let smartPlaylists = []
  export let smartPlaylistsLoading = false
  export let smartPlaylistsError = ''
  export let onRefreshSmart = () => {}
  export let onOpenSmartPlaylist = () => {}
  export let stats = { month: '', totalMinutes: 0, monthly: [], heavyRotation: [] }
  export let quickPicks = []
  export let discoverTracks = []
  export let discoverLoading = false
  export let smartMix = []
  export let recommendations = []
  export let currentTrack = null
  export let currentTime = 0
  export let duration = 0
  export let isPlaying = false
  export let volume = 1
  export let loading = false
  export let upNext = []
  export let history = []
  export let persistentHistory = []
  export let recommendationLoading = false
  export let likedTracks = []
  export let likedLoading = false
  export let likedError = ''
  export let onRetryLiked = () => {}
  export let onPlayQueue = () => {}
  export let onPlayTracks = () => {}
  export let onSaveStatsPlaylist = async () => {}
  export let onPlayNext = () => {}
  export let onAddToQueue = () => {}
  export let onAddToPlaylist = () => {}
  export let onStartMix = () => {}
  export let onOpenBrowse = () => {}
  export let onArtworkLoad = () => {}
  export let moods = []
  export let activeMood = null
  export let moodPlaylists = []
  export let moodLoading = false
  export let onOpenMood = () => {}
  export let onOpenMoodPlaylist = () => {}
  export let favoriteArtists = []
  export let rotationTracks = []
  export let recentPlaylists = []
  export let ytmShelves = []
  export let ytmFeedLoading = false
  export let onRetryYtmFeed = () => {}
  export let onOpenArtistEntity = () => {}
  export let onOpenAlbumEntity = () => {}
  export let onOpenRecentPlaylist = () => {}
  export let onCompileArtistMix = () => {}
  export let onToggle = () => {}
  export let onOpenQueue = () => {}
  export let onOpenTheatre = () => {}

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const key = item => item?.videoId || item?.id || item?.browseId || item?.title
  const trackTitle = item => clean(item?.title || item?.name) || 'Untitled track'
  const trackArtist = item => clean(item?.artist || item?.artists?.[0]?.name || item?.artists?.[0]) || 'Various Artists'
  const trackDuration = value => {
    if (typeof value === 'string' && value.includes(':')) return value
    const seconds = Number(value)
    if (!Number.isFinite(seconds) || seconds <= 0) return ''
    return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
  }
  const playedAt = item => item?.playedAt || item?.played_at || item?.lastPlayed || item?.last_played || item?.timestamp
  function relativeTime(item) {
    const date = playedAt(item) ? new Date(typeof playedAt(item) === 'number' ? playedAt(item) * 1000 : playedAt(item)).getTime() : NaN
    if (!Number.isFinite(date)) return `${Number(item?.plays || item?.count || 0)} plays`
    const minutes = Math.max(0, Math.floor((Date.now() - date) / 60000))
    if (minutes < 1) return 'now'
    if (minutes < 60) return `${minutes}m ago`
    if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`
    return `${Math.floor(minutes / 1440)}d ago`
  }

  $: songs = searchResults.filter(item => item.type === 'song')
  $: artists = searchResults.filter(item => item.type === 'artist')
  $: albums = searchResults.filter(item => item.type === 'album')
  $: playlistsFound = searchResults.filter(item => item.type === 'playlist')
  $: topResult = searchResults[0]

  const genres = ['All', 'UK Real Rap', 'UK Drill', 'US Trap', 'Melodic Drill', 'Pluggnb', 'Afroswing', 'R&B', 'Wave']
  let activeGenre = 'All'
  let genreTracks = []
  let genreLoading = false
  let shelves = []
  let shelfPage = 0
  let shelvesLoading = false
  let homeScroll
  let likedIds = new Set()
  let menuTrack = null
  let menuType = 'track'
  let menuX = 0
  let menuY = 0

  $: jumpBack = (history.length ? history : persistentHistory).slice(-8).reverse()
  $: baseTracks = activeGenre === 'All' ? (quickPicks.length ? quickPicks : rotationTracks) : genreTracks
  $: shelfItems = shelves.flatMap(shelf => shelf.items || [])
  $: if (likedTracks?.length) likedIds = new Set(likedTracks.map(key).filter(Boolean))

  async function loadGenre(genre) {
    activeGenre = genre
    genreLoading = true
    try {
      const response = await apiFetch(`/api/home/recommendations?genre=${encodeURIComponent(genre)}`)
      const data = await response.json()
      genreTracks = response.ok ? (data.tracks || []) : []
    } catch { genreTracks = [] }
    finally { genreLoading = false }
  }

  async function loadShelves(page = 0) {
    if (shelvesLoading) return
    shelvesLoading = true
    try {
      const response = await apiFetch(`/api/home/shelves?page=${page}`)
      const data = await response.json()
      if (response.ok && Array.isArray(data.shelves)) {
        shelves = page === 0 ? data.shelves : [...shelves, ...data.shelves]
        shelfPage = page
      }
    } catch { /* the home feed remains useful from local shelves */ }
    finally { shelvesLoading = false }
  }

  function onHomeScroll(event) {
    const element = event.currentTarget
    if (element.scrollTop + element.clientHeight >= element.scrollHeight - 420) loadShelves(shelfPage + 1)
  }

  function onShelfScroll(event) {
    const element = event.currentTarget
    if (element.scrollLeft + element.clientWidth >= element.scrollWidth - 400) loadShelves(shelfPage + 1)
  }

  function scrollShelf(node, direction) {
    node?.scrollBy({ left: direction * node.clientWidth * .75, behavior: 'smooth' })
  }

  function play(track, index = 0, list = [track]) {
    if (track) onPlayQueue(list, index)
  }

  function context(event, track) {
    event.preventDefault()
    event.stopPropagation()
    menuTrack = track
    menuType = track?.type || 'track'
    menuX = event.clientX
    menuY = event.clientY
  }

  function openSearch(item) {
    if (item.type === 'song') play(item)
    else if (item.type === 'artist') onOpenArtistEntity(item.id, item.title)
    else if (item.type === 'album') onOpenAlbumEntity(item.id, item.title, item.artist)
    else if (item.type === 'playlist') onOpenPlaylist({ id: item.id, title: item.title })
    else onOpenBrowse(item)
  }

  function openArtist(item) {
    onOpenArtistEntity(item?.artistId || item?.artists?.[0]?.id || null, trackArtist(item))
  }

  function openMenuArtist(item) {
    if (item?.type === 'artist') onOpenArtistEntity(item.id, item.title || item.name)
    else openArtist(item)
  }

  function openMenuAlbum(item) {
    onOpenAlbumEntity(item?.albumId || item?.id || null, item?.title || item?.album || '', trackArtist(item))
  }

  function favoriteFromMenu(item) {
    const event = { stopPropagation() {} }
    toggleLike(event, item)
  }

  async function toggleLike(event, item) {
    event.stopPropagation()
    const id = key(item)
    if (!id) return
    const wasLiked = likedIds.has(id)
    const next = new Set(likedIds)
    if (wasLiked) next.delete(id)
    else next.add(id)
    likedIds = next
    try {
      const response = await apiFetch('/api/library/toggle-favorite', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ item }) })
      if (!response.ok) throw Error()
    } catch {
      const rollback = new Set(likedIds)
      if (wasLiked) rollback.add(id)
      else rollback.delete(id)
      likedIds = rollback
    }
  }  const previewController = createHoverPreview({ fetcher: apiFetch, isPlaying: () => isPlaying })

  function isTrack(item) {
    return !item?.type || item.type === 'song' || Boolean(item?.videoId)
  }

  function startPreview(item, node) {
    previewController.start(item, node)
  }

  function resetPreview() {
    previewController.stop()
  }


  function handleKeydown(event) {
    if (event.key === 'Escape') menuTrack = null
  }

  function handleWindowScroll() {
    if (menuTrack) menuTrack = null
  }

  onMount(() => {
    likedIds = new Set((likedTracks || []).map(key).filter(Boolean))
    if (homeView === 'home') loadShelves(0)
    if (homeView === 'home' && activeGenre !== 'All') loadGenre(activeGenre)
    window.addEventListener('keydown', handleKeydown)
    window.addEventListener('scroll', handleWindowScroll, { passive: true })
  })

  onDestroy(() => {
    previewController.destroy()
    window.removeEventListener('keydown', handleKeydown)
    window.removeEventListener('scroll', handleWindowScroll)
  })
</script>

<div class="home-view" on:scroll={onHomeScroll} bind:this={homeScroll}>
  {#if sessionState === 'expired' && !sessionBannerDismissed}<div class="notice" role="alert"><span>Your YouTube Music session has expired.</span><button on:click={onReconnect}>Reconnect</button><button class="close" on:click={onDismissSession} aria-label="Dismiss">×</button></div>{/if}
  {#if libraryCached}<div class="notice" role="status"><span>Showing your cached library.</span><button class="close" on:click={onDismissOffline} aria-label="Dismiss">×</button></div>{/if}

  {#if searchQuery.trim()}
    <section class="search-page" aria-label="Search results" aria-busy={searching}>
      <header class="search-head"><div><p class="eyebrow">SEARCH</p><h1>{clean(searchQuery)}</h1></div>{#if searching}<span class="searching">Searching…</span>{/if}</header>
      {#if searchError}<p class="error" role="alert">{searchError}</p>{/if}
      {#if searching && !searchResults.length}<p class="empty">Searching…</p>{:else if !searchResults.length}<p class="empty">No results</p>{:else}
        <section class="search-group"><h2>Top Result</h2><button class="top-result" on:click={() => openSearch(topResult)}><span class="search-image">{#if topResult.thumbnail}<img src={topResult.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span><strong>{clean(topResult.title)}</strong><small>{clean(topResult.type || 'Result')} {topResult.artist ? `· ${clean(topResult.artist)}` : ''}</small></span><b>Open</b></button></section>
        {#if songs.length}<section class="search-group"><h2>Songs <small>{songs.length}</small></h2><div class="search-list">{#each songs as item, index (key(item) || index)}<div class="search-row"><button class="search-main" on:click={() => play(item)} on:contextmenu={(event) => context(event, item)}><span class="search-image small">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span><strong>{clean(item.title)}</strong><small>{#if item.artist}<span class="entity" on:click|stopPropagation={() => onOpenArtistEntity(item.artistId || null, item.artist)}>{clean(item.artist)}</span>{/if}{#if item.album}<span class="muted"> · </span><span class="entity" on:click|stopPropagation={() => onOpenAlbumEntity(item.albumId || null, item.album, item.artist)}>{clean(item.album)}</span>{/if}</small></span><time>{clean(item.duration)}</time></button><TrackContextMenu track={item} onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} /></div>{/each}</div></section>{/if}
        {#if artists.length}<section class="search-group"><h2>Artists <small>{artists.length}</small></h2><div class="entity-grid">{#each artists as item, index (key(item) || index)}<button class="entity-card artist-card" on:click={() => onOpenArtistEntity(item.id, item.title)}><span class="artist-image">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♩{/if}</span><strong>{clean(item.title)}</strong><small>Artist</small></button>{/each}</div></section>{/if}
        {#if albums.length}<section class="search-group"><h2>Albums <small>{albums.length}</small></h2><div class="entity-grid">{#each albums as item, index (key(item) || index)}<button class="entity-card" on:click={() => onOpenAlbumEntity(item.id, item.title, item.artist)}><span class="search-image">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(item.title)}</strong><small>{clean(item.artist || 'Album')}</small></button>{/each}</div></section>{/if}
        {#if playlistsFound.length}<section class="search-group"><h2>Playlists <small>{playlistsFound.length}</small></h2><div class="entity-grid">{#each playlistsFound as item, index (key(item) || index)}<button class="entity-card" on:click={() => onOpenPlaylist({ id: item.id, title: item.title })}><span class="search-image">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(item.title)}</strong><small>Playlist</small></button>{/each}</div></section>{/if}
      {/if}
    </section>
  {:else if homeView === 'home'}
    <section class="home-feed" aria-label="Home feed">
      <section class="slim-hero" class:collapsed={!currentTrack} aria-label="Now playing">
        {#if currentTrack}<span class="hero-art">{#if currentTrack.thumbnail}<img src={currentTrack.thumbnail} alt="" />{:else}♫{/if}</span><span class="hero-copy"><strong>{trackTitle(currentTrack)}</strong><button on:click|stopPropagation={() => openArtist(currentTrack)}>{trackArtist(currentTrack)}</button><span class="hero-progress"><i style={`width:${duration ? Math.min(100, currentTime / duration * 100) : 0}%`}></i></span><small>{trackDuration(currentTime)} / {trackDuration(duration)}</small></span><button class="hero-icon" on:click={onToggle} aria-label={isPlaying ? 'Pause' : 'Play'}>{isPlaying ? 'Ⅱ' : '▶'}</button><button class="hero-icon" on:click={() => onPlayQueue(upNext, 0)} disabled={!upNext.length} aria-label="Skip to next">▶|</button><button class="hero-icon heart" on:click={(event) => toggleLike(event, currentTrack)} aria-label="Like current track">{likedIds.has(key(currentTrack)) ? '♥' : '♡'}</button>{/if}
      </section>
      <nav class="genre-strip" aria-label="Genres">{#each genres as genre}<button class:active={activeGenre === genre} on:click={() => genre === 'All' ? activeGenre = 'All' : loadGenre(genre)}>{genre}</button>{/each}</nav>
      <section class="home-section jump-back"><header><h2>Jump Back In</h2><span>{jumpBack.length} recent</span></header><div class="compact-row">{#each jumpBack as item, index (key(item) || index)}<article class="compact-card" on:click={() => play(item)} role="button" tabindex="0" on:contextmenu={(event) => context(event, item)}><div class="media-frame">{#if item.thumbnail}<img src={item.thumbnail} alt="" />{:else}♫{/if}<button class="heart-button" on:click={(event) => toggleLike(event, item)} aria-label="Like {trackTitle(item)}">{likedIds.has(key(item)) ? '♥' : '♡'}</button></div><strong>{trackTitle(item)}</strong><small>{relativeTime(item)}</small></article>{/each}</div></section>
      {#if baseTracks.length}<section class="home-section"><header><h2>{activeGenre === 'All' ? 'Quick Picks' : activeGenre}</h2><span>{baseTracks.length} tracks</span></header><div class="shelf-row">{#each baseTracks as item, index (key(item) || index)}<article class="media-card track-geometry" on:mouseenter={(event) => startPreview(item, event.currentTarget)} on:mouseleave={resetPreview} on:click={() => play(item, index, baseTracks)} on:contextmenu={(event) => context(event, item)} role="button" tabindex="0"><div class="media-frame widescreen"><span class="badge">TRACK</span>{#if item.thumbnail}<img src={item.thumbnail} alt="" />{:else}♫{/if}<button class="heart-button" on:click={(event) => toggleLike(event, item)} aria-label="Like {trackTitle(item)}">{likedIds.has(key(item)) ? '♥' : '♡'}</button><button class="avatar-badge" on:click|stopPropagation={() => openArtist(item)} aria-label="Open {trackArtist(item)}">{trackArtist(item).slice(0, 1).toUpperCase()}</button></div><strong>{trackTitle(item)}</strong><button class="artist-link" on:click|stopPropagation={() => openArtist(item)}>{trackArtist(item)}</button>{#if trackDuration(item.duration)}<time>{trackDuration(item.duration)}</time>{/if}</article>{/each}</div></section>{/if}
      {#each shelves as shelf (shelf.id || shelf.title)}<section class="home-section shelf-block"><header><h2>{clean(shelf.title)}</h2><div><span>{(shelf.items || []).length} items</span><button aria-label="Scroll shelf left" on:click={(event) => scrollShelf(event.currentTarget.closest('.home-section').querySelector('.shelf-row'), -1)}>‹</button><button aria-label="Scroll shelf right" on:click={(event) => scrollShelf(event.currentTarget.closest('.home-section').querySelector('.shelf-row'), 1)}>›</button></div></header><div class="shelf-row" on:scroll={onShelfScroll}>{#each shelf.items || [] as item, index (key(item) || index)}<article class="media-card" class:artist-geometry={item.type === 'artist'} on:mouseenter={(event) => isTrack(item) && startPreview(item, event.currentTarget)} on:mouseleave={resetPreview} on:click={() => item.type === 'album' ? onOpenAlbumEntity(item.id, item.title, item.artist) : item.type === 'artist' ? onOpenArtistEntity(item.id, item.title) : play(item)} role="button" tabindex="0"><div class:circle-frame={item.type === 'artist'} class="media-frame square"><span class="badge">{item.type === 'artist' ? 'ARTIST' : item.type === 'album' ? 'ALBUM' : 'TRACK'}</span>{#if item.thumbnail}<img src={item.thumbnail} alt="" />{:else}<span>{item.type === 'artist' ? '♩' : '♫'}</span>{/if}<button class="heart-button" on:click={(event) => toggleLike(event, item)} aria-label="Like {clean(item.title)}">{likedIds.has(key(item)) ? '♥' : '♡'}</button></div><strong>{clean(item.title)}</strong><small>{clean(item.subtitle || item.artist || item.year || '')}</small></article>{/each}</div></section>{/each}
      {#if !baseTracks.length && !shelvesLoading}<p class="empty">No recommendations yet</p>{/if}
      {#if shelvesLoading}<p class="feed-loading">Loading more shelves…</p>{/if}
    </section>
  {:else if homeView === 'recent'}
    <RecentlyPlayedView history={history} persistentHistory={persistentHistory} stats={stats} heavyRotation={stats.heavyRotation || rotationTracks} favoriteArtists={favoriteArtists} onPlay={(track) => play(track)} onOpenArtist={onOpenArtistEntity} onOpenAlbum={onOpenAlbumEntity} onAddToQueue={onAddToQueue} />
  {:else if homeView === 'discover'}
    <DiscoverView tracks={[...discoverTracks, ...quickPicks, ...smartMix]} favoriteArtists={favoriteArtists} history={history} persistentHistory={persistentHistory} stats={stats} loading={discoverLoading} onCompileMix={onCompileArtistMix} onPlay={(track) => play(track)} onOpenArtist={onOpenArtistEntity} onOpenAlbum={onOpenAlbumEntity} onAddToQueue={onAddToQueue} />
  {:else if homeView === 'stats'}
    <StatsView onPlayTrack={(track) => play(track)} onPlayTracks={onPlayTracks} onSavePlaylist={onSaveStatsPlaylist} onStartMix={onStartMix} />
  {:else if homeView === 'updates'}
    <UpdatesView />
  {:else if homeView === 'favorites'}
    <FavoritesView tracks={likedTracks} loading={likedLoading} error={likedError} onRetry={onRetryLiked} onPlay={onPlayQueue} onOpenArtist={onOpenArtistEntity} onOpenAlbum={onOpenAlbumEntity} onAddToQueue={onAddToQueue} />
  {/if}

  {#if menuTrack}<TrackContextMenu track={menuTrack} entityType={menuType} positioned x={menuX} y={menuY} autoOpen onPlayNext={menuType === 'artist' ? onOpenArtistEntity : onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} onOpenArtist={openMenuArtist} onOpenAlbum={openMenuAlbum} onFavorite={favoriteFromMenu} />{/if}
</div>

<style>
  .home-view{height:100%;min-height:0;box-sizing:border-box;overflow:auto;background:#000;color:#ededed;font-family:Inter,ui-sans-serif,system-ui,sans-serif}.notice{display:flex;align-items:center;gap:10px;margin:0 24px 10px;padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.07);color:#a1a1aa;font-size:.7rem}.notice button{border:1px solid rgba(255,255,255,.13);border-radius:6px;padding:5px 8px;color:#ededed;background:#08080a;cursor:pointer;font-size:.64rem}.notice .close{margin-left:auto;border:0;background:transparent;font-size:1rem}.home-feed{padding:14px clamp(14px,3vw,42px) 72px}.slim-hero{display:flex;align-items:center;gap:10px;max-height:72px;min-height:72px;overflow:hidden;border-bottom:1px solid #ffffff12;transition:max-height .25s ease,min-height .25s ease,opacity .25s ease}.slim-hero.collapsed{min-height:0;max-height:0;opacity:0;border:0}.hero-art{width:56px;height:56px;flex:0 0 auto;overflow:hidden;border-radius:8px;background:#111113}.hero-art img{width:100%;height:100%;object-fit:cover}.hero-copy{display:grid;min-width:0;flex:1;grid-template-columns:minmax(0,1fr) auto;gap:2px 8px}.hero-copy strong,.hero-copy button{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hero-copy button{width:max-content;max-width:100%;border:0;padding:0;color:#a1a1aa;background:transparent;cursor:pointer;font:inherit;font-size:.72rem}.hero-copy button:hover{text-decoration:underline;color:#fff}.hero-progress{grid-column:1/2;height:2px;background:#27272a}.hero-progress i{display:block;height:100%;background:#fff}.hero-copy small{grid-column:2/3;grid-row:2;color:#71717a;font:500 .58rem ui-monospace,monospace}.hero-icon{width:30px;height:30px;border:1px solid #ffffff1a;border-radius:50%;color:#ededed;background:#ffffff08;cursor:pointer}.hero-icon:hover{background:#fff;color:#000}.hero-icon:disabled{opacity:.3}.genre-strip{display:flex;gap:7px;overflow-x:auto;padding:12px 0;scrollbar-width:none}.genre-strip::-webkit-scrollbar,.shelf-row::-webkit-scrollbar,.compact-row::-webkit-scrollbar{display:none}.genre-strip button{flex:0 0 auto;padding:7px 12px;border:1px solid transparent;border-radius:999px;color:#a1a1aa;background:#ffffff08;cursor:pointer;font-size:.68rem}.genre-strip button:hover{color:#fff}.genre-strip button.active{color:#000;background:#fff}.home-section{margin:14px 0 26px}.home-section header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:9px}.home-section h2{margin:0;font-size:.92rem;letter-spacing:-.02em}.home-section header span{color:#71717a;font:500 .6rem ui-monospace,monospace}.home-section header div{display:flex;align-items:center;gap:6px}.home-section header button{width:26px;height:26px;border:1px solid #ffffff12;border-radius:50%;color:#aaa;background:#ffffff08;cursor:pointer}.compact-row,.shelf-row{display:flex;gap:12px;overflow-x:auto;scrollbar-width:none;padding:2px 1px 8px}.compact-card{width:120px;flex:0 0 120px;cursor:pointer}.media-frame{position:relative;overflow:hidden;border:1px solid #ffffff0f;border-radius:9px;background:#111113}.compact-card .media-frame{aspect-ratio:1}.media-frame img{display:block;width:100%;height:100%;object-fit:cover}.compact-card strong,.compact-card small,.media-card strong,.media-card small,.artist-link{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.compact-card strong{margin-top:6px;font-size:.72rem}.compact-card small{margin-top:3px;color:#71717a;font:500 .59rem ui-monospace,monospace}.media-card{position:relative;width:180px;flex:0 0 180px;cursor:pointer}.media-card:hover{filter:brightness(1.1)}.media-frame.widescreen{aspect-ratio:16/9}.media-frame.square{aspect-ratio:1}.circle-frame{border-radius:50%;aspect-ratio:1}.circle-frame img{border-radius:50%}.badge{position:absolute;z-index:3;top:6px;left:6px;padding:3px 5px;border-radius:4px;color:#fff;background:#000b;font:600 .48rem ui-monospace,monospace;letter-spacing:.08em}.heart-button{position:absolute;z-index:5;top:6px;right:6px;width:26px;height:26px;border:1px solid #ffffff2b;border-radius:50%;color:#fff;background:#0008;cursor:pointer;backdrop-filter:blur(5px)}.heart-button:hover{transform:scale(1.1)}.media-card strong{margin-top:7px;font-size:.76rem}.media-card small,.artist-link{margin-top:3px;color:#71717a;font-size:.64rem}.artist-link{border:0;padding:0;background:none;cursor:pointer;text-align:left}.artist-link:hover{text-decoration:underline;color:#fff}.media-card time{display:block;margin-top:3px;color:#71717a;font:500 .58rem ui-monospace,monospace}.hover-video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1}.avatar-badge{position:absolute;bottom:6px;left:6px;z-index:4;width:25px;height:25px;border:1px solid #fff8;border-radius:50%;color:#fff;background:#222;cursor:pointer;font-size:.6rem}.empty,.feed-loading{padding:28px 0;color:#71717a;font-size:.76rem}.search-page,.favorites-page{box-sizing:border-box;overflow:auto;padding:28px clamp(18px,4vw,48px) 48px}.search-head,.favorites-page header{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:24px}.eyebrow{margin:0 0 6px;color:#71717a;font:600 .62rem ui-monospace,SFMono-Regular,monospace;letter-spacing:.15em}.search-head h1,.favorites-page h1{margin:0;font-size:clamp(1.8rem,4vw,2.8rem);letter-spacing:-.06em}.searching{color:#71717a;font:500 .68rem ui-monospace,monospace}.search-group{margin:0 0 24px}.search-group h2{display:flex;align-items:baseline;gap:8px;margin:0 0 10px;font-size:.9rem}.search-group h2 small{color:#52525b;font:500 .62rem ui-monospace,monospace}.top-result{display:flex;align-items:center;gap:12px;width:100%;box-sizing:border-box;padding:10px;border:1px solid #ffffff12;border-radius:10px;color:#ededed;background:#08080a;text-align:left;cursor:pointer}.top-result>span:nth-child(2){display:flex;min-width:0;flex:1;flex-direction:column}.top-result strong,.top-result small,.entity-card strong,.entity-card small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.top-result small{color:#71717a;font-size:.68rem}.top-result b{color:#71717a;font:500 .62rem ui-monospace,monospace}.search-image{display:grid;place-items:center;width:58px;height:58px;flex:0 0 auto;overflow:hidden;border:1px solid #ffffff12;border-radius:9px;background:#121215;color:#71717a}.search-image.small{width:40px;height:40px}.search-image img,.artist-image img{width:100%;height:100%;object-fit:cover}.search-list{overflow:hidden;border:1px solid #ffffff12;border-radius:10px}.search-row{display:flex;align-items:center;border-bottom:1px solid #ffffff0c}.search-main{display:flex;align-items:center;gap:10px;flex:1;min-width:0;padding:8px 10px;border:0;color:#ededed;background:transparent;text-align:left;cursor:pointer}.search-main>span:nth-child(2){display:flex;min-width:0;flex:1;flex-direction:column}.search-main strong{font-size:.75rem}.search-main small{margin-top:3px;color:#71717a;font-size:.65rem}.search-main time{color:#71717a;font:500 .62rem ui-monospace,monospace}.entity{cursor:pointer}.entity:hover{color:#fff;text-decoration:underline}.entity-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:14px}.entity-card{min-width:0;padding:0;border:1px solid transparent;color:#ededed;background:transparent;text-align:left;cursor:pointer}.entity-card>span{display:grid;place-items:center;aspect-ratio:1;overflow:hidden;border-radius:10px;background:#121215}.artist-image{border-radius:50%!important}.entity-card strong,.entity-card small{display:block}.entity-card strong{margin-top:7px;font-size:.74rem}.entity-card small{margin-top:3px;color:#71717a;font-size:.62rem}.muted{color:#52525b}.error{color:#fca5a5}
</style>