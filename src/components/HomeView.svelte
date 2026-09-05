<script>
  import TrackContextMenu from './TrackContextMenu.svelte'
  import StartMixButton from './StartMixButton.svelte'
  import StatsView from '../pages/StatsView.svelte'

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
  export let recommendationLoading = false
  export let likedTracks = []
  export let likedLoading = false
  export let likedError = ''
  export let onRetryLiked = () => {}
  export let onPlayQueue = () => {}
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
  function openArtist(event, track) { event.preventDefault(); event.stopPropagation(); onOpenArtistEntity(track?.artistId, track?.artist) }
  function openAlbum(event, track) { event.preventDefault(); event.stopPropagation(); onOpenAlbumEntity(track?.albumId, track?.album, track?.artist) }
  function feedTrack(item) {
    return { videoId: item?.id, id: item?.id, title: item?.title, artist: item?.subtitle, thumbnail: item?.thumbnail }
  }
  function openFeedItem(item) {
    if (item.type === 'song') {
      play([{ videoId: item.id, id: item.id, title: item.title, artist: item.subtitle, thumbnail: item.thumbnail }])
    } else if (item.type === 'album' && item.id) {
      onOpenAlbumEntity(item.id, item.title, item.subtitle)
    } else if (item.type === 'playlist' && item.id) {
      onOpenPlaylist({ id: item.id, title: item.title })
    } else {
      onOpenBrowse(item)
    }
  }

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  $: songResults = searchResults.filter(item => item.type === 'song')
  $: albumResults = searchResults.filter(item => item.type === 'album')
  $: artistResults = searchResults.filter(item => item.type === 'artist')
  $: playlistResults = searchResults.filter(item => item.type === 'playlist')
  $: browseResults = searchResults.filter(item => !['song', 'album', 'artist', 'playlist'].includes(item.type))
  $: heroTrack = currentTrack || stats.heavyRotation?.[0] || quickPicks?.[0] || null
  $: heroTitle = heroTrack?.title || 'Your music, your way'
  $: heroArtist = heroTrack?.artist || 'A library built around what you listen to'
  $: heroArt = heroTrack?.thumbnail || quickPicks?.[0]?.thumbnail || ''
  $: heavy = stats.heavyRotation || []
  $: because = recommendations || []
  let cardPalettes = {}
  const fallbackCardPalette = { a: '#3b2922', b: '#241a18' }
  const toRgb = (r, g, b) => `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`

  function play(tracks, index = 0) {
    if (tracks?.length) onPlayQueue(tracks, index)
  }
  function cardStyle(track) {
    const palette = cardPalettes[track?.videoId || track?.id] || fallbackCardPalette
    return `--card-a:${palette.a};--card-b:${palette.b}`
  }
  function artLoaded(event, track) {
    if (!track?.thumbnail) return
    const id = track.videoId || track.id || track.thumbnail
    const image = event?.currentTarget
    if (image && !cardPalettes[id]) {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = 32
        canvas.height = 32
        const context = canvas.getContext('2d', { willReadFrequently: true })
        context.drawImage(image, 0, 0, 32, 32)
        const pixels = context.getImageData(0, 0, 32, 32).data
        const buckets = new Map()
        for (let index = 0; index < pixels.length; index += 16) {
          const alpha = pixels[index + 3]
          if (alpha < 128) continue
          const red = pixels[index], green = pixels[index + 1], blue = pixels[index + 2]
          const luminance = .299 * red + .587 * green + .114 * blue
          const saturation = (Math.max(red, green, blue) - Math.min(red, green, blue)) / Math.max(1, Math.max(red, green, blue))
          if (luminance < 12 || luminance > 248 || saturation < .08) continue
          const key = [red, green, blue].map(value => Math.round(value / 24) * 24).join(',')
          const weight = 1 + saturation * 2 + (luminance > 35 && luminance < 225 ? .5 : 0)
          const bucket = buckets.get(key) || { red: 0, green: 0, blue: 0, weight: 0 }
          bucket.red += red * weight
          bucket.green += green * weight
          bucket.blue += blue * weight
          bucket.weight += weight
          buckets.set(key, bucket)
        }
        const dominant = [...buckets.values()].sort((left, right) => right.weight - left.weight)[0]
        if (dominant) {
          const red = dominant.red / dominant.weight
          const green = dominant.green / dominant.weight
          const blue = dominant.blue / dominant.weight
          cardPalettes = { ...cardPalettes, [id]: {
            a: toRgb(Math.min(255, red * 1.08), Math.min(255, green * 1.08), Math.min(255, blue * 1.08)),
            b: toRgb(red * .42, green * .42, blue * .42),
          }}
        }
      } catch { /* remote artwork without canvas access keeps its own neutral card */ }
    }
    const activeId = currentTrack?.videoId || currentTrack?.id || heroTrack?.videoId || heroTrack?.id
    if (id === activeId) onArtworkLoad(track, track.thumbnail)
  }
  function countText(value) {
    const count = Number(value)
    return Number.isFinite(count) ? `${count} ${count === 1 ? 'track' : 'tracks'}` : 'Playlist'
  }
  // Right-click context menus: the positioned TrackContextMenu instance is
  // keyed by a nonce so every right-click remounts it freshly opened.
  let contextMenuTrack = null
  let contextMenuX = 0
  let contextMenuY = 0
  let contextMenuNonce = 0
  function openContextMenu(event, track) {
    event.preventDefault()
    contextMenuTrack = track
    contextMenuX = event.clientX
    contextMenuY = event.clientY
    contextMenuNonce += 1
  }
</script>

<div class="home-page">
  <div class="ambient-glow" aria-hidden="true"></div>

  {#if !embedded}<header class="topbar" data-tauri-drag-region>
    <label class="search">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m21 21-4.3-4.3"></path></svg>
      <input bind:value={searchQuery} on:input={onSearchChanged} placeholder="Search YouTube Music" aria-label="Search YouTube Music" />
      <kbd>Ctrl K</kbd>
    </label>
    <h1 class="wordmark">myriddim</h1>
    <div class="actions">
      {#if sessionState === 'expired'}<button class="expired" on:click={onReconnect}>Reconnect</button>{/if}
      <button class="btn primary" on:click={onCreatePlaylist}>+ New playlist</button>
      <button class="btn ghost" on:click={onOpenSmartCreator}>Smart playlist</button>
      <button class="settings" on:click={onOpenSettings} aria-label="Open settings" title="Settings">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.14.36.22.75.22 1.15V9a2 2 0 0 1 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
      </button>
      <WindowControls />
    </div>
  </header>{/if}

  {#if sessionState === 'expired' && !sessionBannerDismissed}<div class="notice expired-notice" role="alert"><span>Your YouTube Music session has expired.</span><button on:click={onReconnect}>Reconnect in settings</button><button class="notice-close" on:click={onDismissSession} aria-label="Dismiss">×</button></div>{/if}
  {#if libraryCached}<div class="notice offline-notice" role="status"><span>Showing your cached library. Reconnect to sync changes.</span><button class="notice-close" on:click={onDismissOffline} aria-label="Dismiss">×</button></div>{/if}

  {#if !embedded}<nav class="pills" aria-label="Browse your library">
    <button class:active={homeView === 'home'} on:click={() => onViewChange('home')}>Home</button>
    <button class:active={homeView === 'recent'} on:click={() => onViewChange('recent')}>Recently played</button>
    <button class:active={homeView === 'favorites'} on:click={() => onViewChange('favorites')}>Favorites</button>
    <button class:active={homeView === 'discover'} on:click={() => onViewChange('discover')}>Discover</button>
    <button class:active={homeView === 'stats'} on:click={() => onViewChange('stats')}>Listening stats</button>
  </nav>{/if}

  {#if searchQuery.trim()}
    <section class="search-results" aria-label="Search results" aria-busy={searching}>
      <div class="search-heading"><div><p class="search-kicker">Search results</p><h2 class="display">{searchQuery}</h2></div>{#if searching}<span class="search-state">Searching…</span>{/if}</div>
      {#if searchError}<div class="search-error" role="alert"><strong>Search unavailable</strong><span>{searchError}</span></div>
      {:else if searching && !searchResults.length}<div class="search-empty">Looking across songs, artists, and albums…</div>
      {:else if !searchResults.length}<div class="search-empty">No results for “{searchQuery}”. Try another artist, track, or album.</div>
      {:else}
        {#if songResults.length}<section class="result-group"><div class="result-group-head"><h3>Songs</h3><span>{songResults.length} results</span></div><div class="search-list">{#each songResults as item, index (item.videoId || index)}<div class="search-row"><button on:click={() => play([item])} on:contextmenu={(event) => openContextMenu(event, item)}><span class="search-art">{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span class="search-copy"><strong>{clean(item.title)}</strong><small><span class="entity-link" on:click={(event) => openArtist(event, item)}>{clean(item.artist)}</span>{#if item.album}<i> on </i><span class="entity-link" on:click={(event) => openAlbum(event, item)}>{clean(item.album)}</span>{/if}</small></span><span class="search-type">Song</span></button><TrackContextMenu track={item} onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} /></div>{/each}</div></section>{/if}
        {#if artistResults.length}<section class="result-group"><div class="result-group-head"><h3>Artists</h3><span>{artistResults.length} results</span></div><div class="browse-row">{#each artistResults as item, index (item.id || index)}<button class="browse-card artist-card" on:click={() => onOpenBrowse(item)}>{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}<span>♩</span>{/if}<strong>{clean(item.title)}</strong><small>Artist</small></button>{/each}</div></section>{/if}
        {#if albumResults.length}<section class="result-group"><div class="result-group-head"><h3>Albums</h3><span>{albumResults.length} results</span></div><div class="browse-row">{#each albumResults as item, index (item.id || index)}<button class="browse-card" on:click={() => onOpenBrowse(item)}>{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}<strong>{clean(item.title)}</strong><small>{clean(item.artist || 'Album')}</small></button>{/each}</div></section>{/if}
        {#if playlistResults.length}<section class="result-group"><div class="result-group-head"><h3>Playlists</h3><span>{playlistResults.length} results</span></div><div class="browse-row">{#each playlistResults as item, index (item.id || index)}<button class="browse-card" on:click={() => onOpenBrowse(item)}>{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}<strong>{clean(item.title)}</strong><small>Playlist</small></button>{/each}</div></section>{/if}
        {#if browseResults.length}<section class="result-group"><div class="result-group-head"><h3>More results</h3><span>{browseResults.length} results</span></div><div class="browse-row">{#each browseResults as item, index (item.id || item.title || index)}<button class="browse-card" on:click={() => onOpenBrowse(item)}>{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}<strong>{clean(item.title)}</strong><small>{clean(item.type || 'Result')}</small></button>{/each}</div></section>{/if}
      {/if}
    </section>
  {/if}

  {#if homeView === 'stats'}
    <StatsView onPlayTrack={(track) => play([track])} onStartMix={onStartMix} />
  {:else if homeView === 'favorites'}
    <section class="section list-section"><div class="section-head"><div><h2 class="display">Favorites</h2><p>Your songs, kept close.</p></div></div>{#if likedLoading}<p class="empty">Loading favorites…</p>{:else if likedError}<div class="empty"><strong>Could not load favorites</strong><span>{likedError}</span><button class="pill-button" on:click={onRetryLiked}>Retry</button></div>{:else if likedTracks.length}<div class="row">{#each likedTracks.slice(0, 12) as item, index (item.videoId || index)}<article class="rowcard"><button class="row-main" on:click={() => play(likedTracks, index)} on:contextmenu={(event) => openContextMenu(event, item)}><span class="art">{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(item.title)}</strong><small class="entity-line"><span class="entity-link" on:click={(event) => openArtist(event, item)}>{clean(item.artist)}</span></small></button><TrackContextMenu track={item} onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} /></article>{/each}</div>{:else}<p class="empty">No favorites yet.</p>{/if}</section>
  {:else if homeView === 'home' || homeView === 'recent' || homeView === 'discover'}
    {#if heroTrack}<section class="hero mixable-track" aria-label="Now playing">
      {#if heroArt}<img class="hero-image" src={heroArt} on:load={(event) => artLoaded(event, heroTrack)} referrerpolicy="no-referrer" alt="" aria-hidden="true" />{/if}
      <div class="hero-content">
        <div class="hero-context"><span class="hero-live-dot" aria-hidden="true"></span><span>{currentTrack ? 'Now Playing' : 'From Your Library'}</span></div>
        <h2 class="hero-title">{clean(heroTitle)}</h2>
        <p class="hero-sub">{clean(heroArtist)}</p>
        {#if heroTrack?.album}<p class="hero-album"><span class="entity-link" on:click={(event) => openAlbum(event, heroTrack)}>{clean(heroTrack.album)}</span></p>{/if}
        <div class="hero-actions"><button class="hero-play" on:pointerdown|preventDefault={() => play([heroTrack])} on:keydown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); play([heroTrack]) } }} aria-label="Play {clean(heroTitle)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"></path></svg><span>Play</span></button></div>
      </div>
      {#if heroArt}<div class="hero-art"><img src={heroArt} on:load={(event) => artLoaded(event, heroTrack)} referrerpolicy="no-referrer" alt="{clean(heroTitle)} artwork" /></div>{/if}
      <StartMixButton track={heroTrack} onStartMix={onStartMix} />
    </section>{/if}

    {#if homeView === 'home' || homeView === 'discover'}
      {#if favoriteArtists.length}<section class="section favorites-section"><div class="section-head"><div><h2 class="display">Favorite artists</h2><p>The artists you pinned to your library.</p></div><span>{favoriteArtists.length} artists</span></div><div class="browse-row">{#each favoriteArtists as item, index (item.id)}<button class="browse-card artist-card" on:click={() => onOpenArtistEntity(item.id, item.name)} on:contextmenu={(event) => openContextMenu(event, item)}>{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}<span>♩</span>{/if}<strong>{clean(item.name)}</strong><small>Artist</small></button>{/each}</div></section>{/if}

      {#if quickPicks.length}<section class="section"><div class="section-head"><div><h2 class="display">Quick picks</h2><p>Fresh from your listening habits.</p></div><span>{quickPicks.length} tracks</span></div><div class="row">{#each quickPicks.slice(0, 8) as item, index (item.videoId || index)}<article class="rowcard mixable-track"><button class="row-main" on:click={() => play(quickPicks, index)} on:contextmenu={(event) => openContextMenu(event, item)}><span class="art">{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(item.title)}</strong><small class="entity-line"><span class="entity-link" on:click={(event) => openArtist(event, item)}>{clean(item.artist)}</span></small></button><StartMixButton track={item} onStartMix={onStartMix} /></article>{/each}</div></section>{/if}

      {#if discoverLoading || discoverTracks.length}<section class="section discover-section"><div class="section-head"><div><h2 class="display">Fresh Discoveries</h2><p>New artists and unheard tracks around what you play.</p></div><span>{discoverTracks.length} tracks</span></div>{#if discoverLoading && !discoverTracks.length}<p class="empty">Finding new tracks…</p>{:else}<div class="browse-row">{#each discoverTracks as item, index (item.videoId || index)}<div class="browse-card-wrap mixable-track"><button class="browse-card discover-card" on:click={() => play([item])} on:contextmenu={(event) => openContextMenu(event, item)}>{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}<strong>{clean(item.title)}</strong><small class="entity-line"><span class="entity-link" on:click={(event) => openArtist(event, item)}>{clean(item.artist)}</span></small><em class="discover-tag">{item.discovery_source === 'familiar_deep_cut' ? 'Deep cut' : item.related_to ? `Similar to ${clean(item.related_to)}` : 'New to you'}</em></button><StartMixButton track={item} onStartMix={onStartMix} /></div>{/each}</div>{/if}</section>{/if}
    {/if}

    {#if homeView === 'home' || homeView === 'recent'}
      <section class="section"><div class="section-head"><div><h2 class="display">Heavy rotation</h2><p>The tracks you keep coming back to.</p></div><span>{heavy.length} tracks</span></div><div class="row">{#each heavy.slice(0, 4) as item, index (item.videoId || index)}<article class="rowcard"><button class="row-main" on:click={() => play(heavy, index)} on:contextmenu={(event) => openContextMenu(event, item)}><span class="art">{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(item.title)}</strong><small class="entity-line"><span class="entity-link" on:click={(event) => openArtist(event, item)}>{clean(item.artist)}</span></small></button><TrackContextMenu track={item} onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} /></article>{/each}</div>{#if !heavy.length}<p class="empty">Your listening history will shape this section.</p>{/if}</section>

      {#if rotationTracks.length}<section class="section"><div class="section-head"><div><h2 class="display">In rotation this month</h2><p>Your most-completed tracks over the last 30 days.</p></div><span>{rotationTracks.length} tracks</span></div><div class="row">{#each rotationTracks.slice(0, 4) as item, index (item.videoId || index)}<article class="rowcard"><button class="row-main" on:click={() => play(rotationTracks, index)} on:contextmenu={(event) => openContextMenu(event, item)}><span class="art">{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(item.title)}</strong><small class="entity-line"><span class="entity-link" on:click={(event) => openArtist(event, item)}>{clean(item.artist)}</span></small></button><TrackContextMenu track={item} onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} /></article>{/each}</div></section>{/if}
    {/if}

    {#if homeView !== 'stats' && (recommendationLoading || because.length)}<section class="section"><div class="section-head"><div><h2 class="display">Because you’re playing this</h2><p>{currentTrack ? clean(currentTrack.title) : 'Pick a track to get started.'}</p></div><span>{because.length} tracks</span></div>{#if recommendationLoading}<p class="empty">Finding a good follow-up…</p>{:else}<div class="row">{#each because.slice(0, 4) as item, index (item.videoId || index)}<article class="rowcard mixable-track"><button class="row-main" on:click={() => play(because, index)} on:contextmenu={(event) => openContextMenu(event, item)}><span class="art">{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(item.title)}</strong><small class="entity-line"><span class="entity-link" on:click={(event) => openArtist(event, item)}>{clean(item.artist)}</span></small>{#if item.available_sources?.length}<span class="source-badges">{#each item.available_sources as source}<em>{source === 'soundcloud' ? 'SoundCloud' : 'YouTube'}</em>{/each}</span>{/if}</button><button class="add" on:click={() => onAddToQueue(item)} aria-label="Add {clean(item.title)} to queue">＋</button><StartMixButton track={item} onStartMix={onStartMix} /></article>{/each}</div>{/if}</section>{/if}

    {#if smartMix.length}<section class="section"><div class="section-head"><div><h2 class="display">Personal mix</h2><p>Built locally from what you actually play.</p></div><span>{smartMix.length} tracks</span></div><div class="row">{#each smartMix.slice(0, 4) as item, index (item.videoId || index)}<article class="rowcard mixable-track"><button class="row-main" on:click={() => play(smartMix, index)} on:contextmenu={(event) => openContextMenu(event, item)}><span class="art">{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(item.title)}</strong><small class="entity-line"><span class="entity-link" on:click={(event) => openArtist(event, item)}>{clean(item.artist)}</span></small>{#if item.available_sources?.length}<span class="source-badges">{#each item.available_sources as source}<em>{source === 'soundcloud' ? 'SoundCloud' : 'YouTube'}</em>{/each}</span>{/if}</button><StartMixButton track={item} onStartMix={onStartMix} /></article>{/each}</div></section>{/if}

    {#if ytmShelves.length || ytmFeedLoading}<section class="section ytm-feed-section"><div class="section-head"><div><h2 class="display">From YouTube Music</h2><p>Your personalized home feed, straight from the source.</p></div>{#if ytmFeedLoading}<span>Loading…</span>{/if}</div>{#if ytmFeedLoading && !ytmShelves.length}<p class="empty">Loading your feed…</p>{:else}{#each ytmShelves as shelf}<div class="ytm-shelf"><div class="shelf-head"><h3>{shelf.title}</h3>{#if shelf.strapline}<small>{shelf.strapline}</small>{/if}</div><div class="browse-row">{#each shelf.items as item, index (item.id || index)}{#if item.type === 'song'}<div class="browse-card-wrap mixable-track"><button class="browse-card" on:click={() => openFeedItem(item)} on:contextmenu={(event) => openContextMenu(event, feedTrack(item))}>{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}<strong>{clean(item.title)}</strong><small>{clean(item.subtitle || item.type)}</small></button><StartMixButton track={feedTrack(item)} onStartMix={onStartMix} /></div>{:else}<button class="browse-card" on:click={() => openFeedItem(item)} on:contextmenu={(event) => openContextMenu(event, item)}>{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}<strong>{clean(item.title)}</strong><small>{clean(item.subtitle || item.type)}</small></button>{/if}{/each}</div></div>{/each}{#if !ytmShelves.length}<p class="empty">Your feed is unavailable right now.<button class="pill-button" on:click={onRetryYtmFeed}>Retry</button></p>{/if}{/if}</section>{/if}

    {#if homeView === 'discover' && moods.length}<section class="section mood-section"><div class="section-head"><div><h2 class="display">Moods and genres</h2><p>Choose a direction for the next listen.</p></div></div>{#each moods as mood (mood.title)}<div class="mood-group"><h3>{mood.title}</h3><div class="mood-pills">{#each mood.categories as category (category.title)}<button class:active={activeMood === category.title} on:click={() => onOpenMood(category)}>{category.title}</button>{/each}</div></div>{/each}{#if moodLoading}<p class="empty">Loading playlists…</p>{:else if activeMood && moodPlaylists.length}<div class="browse-row">{#each moodPlaylists as item, index (item.browseId || index)}<button class="browse-card" on:click={() => onOpenMoodPlaylist(item)}>{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}<strong>{clean(item.title)}</strong><small>{clean(item.count || 'Mood playlist')}</small></button>{/each}</div>{:else if activeMood}<p class="empty">No playlists for this mood yet.</p>{/if}</section>{/if}

    {#if homeView === 'home'}
      {#if recentPlaylists.length}<section class="section"><div class="section-head"><div><h2 class="display">Recently played playlists</h2><p>Pick up where you left off.</p></div><span>{recentPlaylists.length} playlists</span></div><div class="playlist-row">{#each recentPlaylists as item, index (item.id)}<button class="playlist-card" on:click={() => onOpenRecentPlaylist(item)}><span class="playlist-art">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span><strong>{clean(item.title)}</strong><small>{item.count ?? 0} tracks</small></span></button>{/each}</div></section>{/if}
      {#if smartPlaylists.length || smartPlaylistsLoading || smartPlaylistsError}<section class="section smart-section"><div class="section-head"><div><h2 class="display">Smart collections</h2><p>Rules that stay fresh as your history changes.</p></div><button class="pill-button" on:click={onRefreshSmart} disabled={smartPlaylistsLoading}>{smartPlaylistsLoading ? 'Loading…' : 'Refresh'}</button></div>{#if smartPlaylistsError}<p class="empty">{smartPlaylistsError}</p>{:else if smartPlaylistsLoading && !smartPlaylists.length}<p class="empty">Loading saved collections…</p>{:else}<div class="smart-list">{#each smartPlaylists as item (item.id)}<button class="smart-item" on:click={() => onOpenSmartPlaylist(item)}><span class="smart-symbol">⚡</span><span><strong>{clean(item.name)}</strong><small>{item.limit || 50} tracks, updates from listening history</small></span><b>Live</b></button>{/each}</div>{/if}</section>{/if}
      {#if playlistsError}<div class="empty library-empty"><strong>Could not load your library</strong><span>{playlistsError}</span><button class="pill-button" on:click={onRetryPlaylists}>Retry</button></div>{:else if playlists.length}<section class="section library-section"><div class="section-head"><div><h2 class="display">Your playlists</h2><p>Everything you have made in one place.</p></div><span>{playlists.length} playlists</span></div><div class="playlist-row">{#each playlists as item, index (item.id)}<button class="playlist-card" style={cardStyle(item)} class:playlist-feature={index === 0 && item.count > 0} class:playlist-empty={item.count === 0} on:click={() => onOpenPlaylist(item)}><span class="playlist-art">{#if item.thumbnail}<img src={item.thumbnail} on:load={(event) => artLoaded(event, item)} loading="lazy" referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span><strong>{clean(item.title)}</strong><small>{item.count === 0 ? 'Empty' : countText(item.count)}</small></span></button>{/each}</div></section>{:else if playlistsLoaded}<div class="empty library-empty"><strong>No playlists yet</strong><span>Create your first playlist with the button above.</span></div>{/if}
    {/if}
  {/if}

  {#each contextMenuTrack ? [1] : [] as _ (contextMenuNonce)}
    <TrackContextMenu track={contextMenuTrack} positioned x={contextMenuX} y={contextMenuY} autoOpen onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} />
  {/each}
</div>

<style>
  .home-page { --bg-0:#0d0b0a; --bg-1:#17110f; --glow-a:var(--accent,#f2ece4); --glow-b:var(--ambient,#5c2a4a); --glow-c:var(--shadow,#8a3a2e); --paper:#f2ece4; --muted:#a99b8f; --muted-2:#7a6d64; --bar:#0a0908; --card:#1c1512; --card-2:#221a16; position:relative; z-index:1; max-width:1180px; margin:0 auto; padding:28px 32px 150px; color:var(--paper); font-family:'Manrope',ui-sans-serif,sans-serif; }
  .ambient-glow { position:fixed; inset:0; z-index:-1; background:radial-gradient(1100px 700px at 18% -8%,var(--glow-a) 0%,transparent 55%),radial-gradient(900px 900px at 100% 10%,var(--glow-b) 0%,transparent 60%),radial-gradient(800px 800px at 40% 100%,var(--glow-c) 0%,transparent 55%),var(--bg-0); opacity:.18; mix-blend-mode:soft-light; animation:drift 26s ease-in-out infinite alternate; pointer-events:none; }
  @keyframes drift { from { filter:hue-rotate(0deg) saturate(1); } to { filter:hue-rotate(-8deg) saturate(1.08); } }
  .topbar { display:flex; align-items:center; justify-content:space-between; gap:20px; margin-bottom:24px; }
  .search { display:flex; align-items:center; gap:10px; width:260px; padding:11px 18px; border:1px solid #ffffff14; border-radius:999px; background:#ffffff0d; backdrop-filter:blur(8px); }
  .search svg { width:15px; height:15px; flex:0 0 auto; fill:none; stroke:currentColor; stroke-width:2; color:var(--muted); }.search input { width:100%; min-width:0; border:0; outline:0; color:var(--paper); background:transparent; font:inherit; font-size:.82rem; }.search input::placeholder { color:var(--muted); }.search kbd { margin-left:auto; color:var(--muted-2); font-size:.68rem; white-space:nowrap; }
  .wordmark { margin:0; font-family:'Anton',Impact,sans-serif; font-size:2rem; font-weight:400; letter-spacing:.02em; }
  .actions { display:flex; align-items:center; gap:10px; }.btn,.expired { display:flex; align-items:center; gap:8px; border-radius:999px; padding:11px 20px; border:1px solid transparent; color:var(--paper); background:transparent; font:600 .82rem 'Manrope',sans-serif; cursor:pointer; transition:transform .4s cubic-bezier(.2,.8,.2,1),background .4s ease,border-color .4s ease; }.btn:hover { transform:translateY(-2px); }  .btn.primary { color:#1b1008; background:var(--paper); }.btn.ghost { border-color:#ffffff29; }.btn.ghost:hover { background:#ffffff0d; }.settings { display:flex; align-items:center; justify-content:center; width:38px; height:38px; margin-left:2px; border:0; color:var(--paper); background:none; cursor:pointer; }.settings svg { width:18px; height:18px; }.settings:hover { color:var(--glow-a); }
  .expired { padding:8px 12px; border-color:#d9a53f55; color:#f0c979; font-size:.72rem; }.pills { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:34px; }.pills button,.pill-button { border:1px solid #ffffff14; border-radius:999px; padding:8px 16px; color:var(--muted); background:#ffffff08; font:600 .76rem 'Manrope',sans-serif; cursor:pointer; transition:color .35s ease,border-color .35s ease,background .35s ease,transform .35s cubic-bezier(.2,.8,.2,1); }.pills button:hover,.pill-button:hover { color:var(--paper); border-color:#ffffff40; transform:translateY(-1px); }.pills button.active { color:#1b1008; border-color:var(--paper); background:var(--paper); }
  .notice { display:flex; align-items:center; gap:12px; margin:-16px 0 20px; padding:11px 14px; border:1px solid #ffffff1a; border-radius:16px; font-size:.78rem; }.notice button:not(.notice-close) { border:0; border-radius:999px; padding:6px 10px; color:var(--paper); background:#ffffff14; cursor:pointer; font:600 .72rem 'Manrope',sans-serif; }.expired-notice { color:#f0c979; border-color:#d9a53f45; background:#d9a53f0d; }.offline-notice { color:#c2dce2; border-color:#62a8b044; background:#62a8b00d; }.notice-close { margin-left:auto; border:0; color:inherit; background:none; cursor:pointer; font-size:1.2rem; }
  .display { font-family:'Anton',Impact,sans-serif; font-weight:400; letter-spacing:.01em; }  .hero { position:relative; display:flex; align-items:center; justify-content:space-between; gap:28px; min-height:300px; margin-bottom:44px; overflow:hidden; border:1px solid #ffffff12; border-radius:32px; background:#121110; isolation:isolate; }.hero-image { position:absolute; inset:-9%; z-index:-1; width:118%; height:118%; object-fit:cover; filter:blur(34px); opacity:.22; transform:scale(1.08); }.hero::before { content:''; position:absolute; inset:0; z-index:0; background:linear-gradient(90deg,#121110f5 0%,#121110c9 48%,#12111052 100%); pointer-events:none; }.hero-content { position:relative; z-index:2; display:flex; flex:1; min-width:0; flex-direction:column; justify-content:center; padding:34px 0 34px 40px; }.hero-context { display:flex; align-items:center; gap:8px; margin:0 0 10px; color:#fbbf24e6; font:700 .66rem/1 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:.16em; text-transform:uppercase; }.hero-live-dot { width:7px; height:7px; border-radius:50%; background:#fbbf24; box-shadow:0 0 14px #fbbf24; animation:hero-pulse 1.5s ease-in-out infinite; }.hero-title { max-width:100%; margin:0 0 7px; overflow:hidden; color:#fff; font-family:'Manrope',ui-sans-serif,sans-serif; font-size:clamp(1.9rem,4vw,3rem); font-weight:800; letter-spacing:-.045em; line-height:1.05; text-overflow:ellipsis; white-space:nowrap; }.hero-sub { margin:0; overflow:hidden; color:#ffffff99; font-family:'Manrope',ui-sans-serif,sans-serif; font-size:clamp(.9rem,1.7vw,1rem); font-weight:600; text-overflow:ellipsis; white-space:nowrap; }.hero-actions { display:flex; align-items:center; gap:10px; margin-top:22px; }.hero-play { display:inline-flex; align-items:center; justify-content:center; gap:8px; height:40px; padding:0 19px; border:0; border-radius:999px; color:#11100f; background:#fff; box-shadow:0 10px 28px #0005; cursor:pointer; font:700 .75rem 'Manrope',ui-sans-serif,sans-serif; transition:transform .25s ease,box-shadow .25s ease,background .25s ease; }.hero-play:hover { background:#fffdf9; transform:translateY(-2px) scale(1.03); box-shadow:0 14px 32px #0008; }.hero-play:active { transform:scale(.97); }.hero-play:focus-visible { outline:2px solid #fbbf24; outline-offset:4px; }.hero-play svg { width:15px; height:15px; fill:currentColor; }.hero-art { position:relative; z-index:2; flex:0 0 auto; width:180px; height:180px; margin:0 38px 0 0; overflow:hidden; border:1px solid #ffffff1c; border-radius:22px; background:#0006; box-shadow:0 20px 48px #000b; }.hero-art img { display:block; width:100%; height:100%; object-fit:cover; user-select:none; } @keyframes hero-pulse { 50% { opacity:.45; transform:scale(.8); } }
  .section { margin-bottom:46px; }.section-head { display:flex; align-items:baseline; justify-content:space-between; gap:16px; margin-bottom:16px; }.section-head h2 { margin:0; font-size:1.65rem; }.section-head p { margin:5px 0 0; color:var(--muted); font-size:.78rem; }.section-head > span { color:var(--muted-2); font-size:.72rem; white-space:nowrap; }
  .row { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); align-items:start; gap:20px; }.rowcard { position:relative; min-width:0; padding:8px; border:0; border-radius:14px; background:transparent; transition:background .2s ease; }.rowcard:hover { background:rgba(255,255,255,.05); }.row-main { display:block; width:100%; min-width:0; padding:0; border:0; color:var(--paper); background:none; text-align:left; cursor:pointer; }  .art { position:relative; display:grid; place-items:center; width:100%; aspect-ratio:1; margin-bottom:10px; overflow:hidden; border:1px solid rgba(255,255,255,.08); border-radius:14px; background:#141414; box-shadow:0 8px 24px rgba(0,0,0,.45); transition:transform .2s ease; }.rowcard:hover .art { transform:scale(1.03); }.art img { width:100%; height:100%; object-fit:cover; display:block; }.row-main strong,.row-main small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.row-main strong { font-size:.8rem; }.row-main small { margin-top:3px; color:var(--muted); font-size:.72rem; }.source-badges { display:flex; gap:4px; margin-top:6px; }.source-badges em { padding:2px 5px; border:1px solid #ffffff18; border-radius:999px; color:var(--muted-2); background:#ffffff08; font-size:.57rem; font-style:normal; }.rowcard :global(.context-menu),.rowcard .add { position:absolute; right:9px; top:9px; }.add { width:28px; height:28px; border:0; border-radius:50%; color:var(--paper); background:#0008; cursor:pointer; }
  .playlist-row { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; align-items:start; }.playlist-card { display:flex; flex-direction:column; min-width:0; padding:14px; border:1px solid #ffffff0f; border-radius:22px; color:var(--paper); background:var(--card-2); text-align:left; cursor:pointer; transition:transform .4s cubic-bezier(.2,.8,.2,1),border-color .4s ease; }.playlist-card:nth-child(2) { margin-top:22px; }.playlist-card:nth-child(4) { margin-top:38px; }.playlist-card:hover { transform:translateY(-3px); border-color:#ffffff2b; }  .playlist-art { position:relative; display:grid; place-items:center; width:100%; aspect-ratio:1; overflow:hidden; border-radius:16px; background:#1c1512; font-size:3rem; }.playlist-art img { width:100%; height:100%; object-fit:cover; }.playlist-card strong,.playlist-card small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.playlist-card strong { margin-top:10px; font-size:.8rem; }.playlist-card small { margin-top:3px; color:var(--muted); font-size:.7rem; }.playlist-feature { grid-column:span 2; display:grid; grid-template-columns:120px 1fr; align-items:center; gap:16px; }.playlist-feature .playlist-art { width:120px; }.playlist-empty { background:transparent; border-style:dashed; }.playlist-empty .playlist-art { width:58px; aspect-ratio:1; }.playlist-empty { flex-direction:row; align-items:center; gap:12px; }.playlist-empty strong { margin-top:0; }
  .smart-section { padding:20px; border:1px solid #ffffff12; border-radius:22px; background:linear-gradient(135deg,#ffffff0b,#ffffff03); }.smart-list { display:grid; grid-template-columns:repeat(2,1fr); gap:8px; }.smart-item { display:flex; align-items:center; gap:10px; min-width:0; padding:11px; border:1px solid #ffffff0d; border-radius:14px; color:var(--paper); background:#ffffff08; text-align:left; cursor:pointer; }.smart-item:hover { background:#ffffff12; }  .smart-symbol { display:grid; place-items:center; width:30px; height:30px; border-radius:50%; color:var(--paper); background:#ffffff12; }.smart-item > span:nth-child(2) { display:flex; flex:1; min-width:0; flex-direction:column; }.smart-item strong,.smart-item small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.smart-item strong { font-size:.78rem; }.smart-item small { margin-top:3px; color:var(--muted); font-size:.67rem; }.smart-item b { color:var(--muted-2); font-size:.66rem; font-weight:500; }
  .mood-group h3 { margin:0 0 8px; color:var(--muted); font-size:.75rem; font-weight:600; }.mood-pills { display:flex; flex-wrap:wrap; gap:7px; }.mood-pills button { border:1px solid #ffffff16; border-radius:999px; padding:7px 12px; color:var(--muted); background:#ffffff08; cursor:pointer; font:500 .72rem 'Manrope',sans-serif; }.mood-pills button.active,.mood-pills button:hover { color:#1b1008; background:var(--paper); }
  .entity-link { cursor:pointer; }.entity-link:hover { color:var(--paper); text-decoration:underline; }.entity-line { display:block; margin-top:3px; color:var(--muted); font-size:.72rem; }.hero-album { margin:8px 0 0; color:var(--muted); font-size:.78rem; }.hero-album .entity-link:hover { color:var(--paper); }
  .ytm-feed-section { padding:22px; border:1px solid #ffffff10; border-radius:26px; background:linear-gradient(150deg,#ffffff0a,#ffffff02); }.ytm-shelf { margin-bottom:28px; }.ytm-shelf:last-child { margin-bottom:0; }.shelf-head { display:flex; align-items:baseline; gap:10px; margin-bottom:12px; }.shelf-head h3 { margin:0; color:var(--paper); font-family:'Anton',Impact,sans-serif; font-size:1.2rem; font-weight:400; letter-spacing:.01em; }.shelf-head small { color:var(--muted-2); font-size:.68rem; }.ytm-feed-section .empty { padding:8px 2px; }.ytm-feed-section .empty .pill-button { margin-left:10px; }
  .discover-tag { align-self:flex-start; margin-top:5px; padding:2px 8px; border:1px solid #ffffff18; border-radius:999px; color:var(--muted-2); background:#ffffff08; font-size:.6rem; font-style:normal; }
  .discover-card:hover .discover-tag { color:var(--paper); border-color:#ffffff30; }
  .search-results { margin:0 0 42px; padding:22px; border:1px solid #ffffff12; border-radius:26px; background:linear-gradient(145deg,#1c1512ee,#120f0dca); box-shadow:0 20px 60px #0004; }.search-heading { display:flex; align-items:end; justify-content:space-between; gap:16px; margin-bottom:24px; }.search-kicker { margin:0 0 6px; color:var(--muted-2); font-size:.72rem; }.search-heading h2 { margin:0; font-size:2rem; }.search-state { color:#d8cbbf; font-size:.74rem; }.result-group { margin-top:26px; }.result-group:first-of-type { margin-top:0; }.result-group-head { display:flex; align-items:baseline; justify-content:space-between; margin-bottom:10px; }.result-group-head h3 { margin:0; color:var(--paper); font-family:'Anton',Impact,sans-serif; font-size:1.25rem; font-weight:400; }.result-group-head span { color:var(--muted-2); font-size:.7rem; }.search-list { overflow:hidden; border:1px solid #ffffff12; border-radius:18px; background:#0d0b0acc; }.search-row { display:flex; align-items:center; gap:8px; padding-right:8px; border-bottom:1px solid #ffffff0a; }.search-row:last-child { border-bottom:0; }.search-row:hover { background:#f2ece40a; }.search-row > button { display:flex; align-items:center; flex:1; gap:12px; min-width:0; padding:10px 12px; border:0; color:var(--paper); background:none; text-align:left; cursor:pointer; }.search-art { display:grid; place-items:center; width:46px; height:46px; flex:none; overflow:hidden; border:1px solid #ffffff14; border-radius:12px; color:#d8cbbf; background:#221a16; }.search-art img { width:100%; height:100%; object-fit:cover; }.search-copy { display:flex; min-width:0; flex:1; flex-direction:column; }.search-row strong,.search-row small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.search-row strong { font-size:.82rem; }.search-row small { margin-top:3px; color:var(--muted); font-size:.7rem; }.search-row small i { color:var(--muted-2); font-style:normal; }.search-type { color:var(--muted-2); font-size:.67rem; }  .browse-row { display:flex; gap:14px; overflow-x:auto; padding:3px 3px 12px; scrollbar-width:thin; scrollbar-color:#f2ece433 transparent; }.browse-card-wrap { position:relative; flex:0 0 150px; min-width:0; }.browse-card-wrap .browse-card { width:100%; }.browse-row::-webkit-scrollbar { height:5px; }.browse-row::-webkit-scrollbar-thumb { border-radius:999px; background:#f2ece433; }.browse-card { display:flex; flex:0 0 150px; flex-direction:column; min-width:0; border:0; color:var(--paper); background:none; text-align:left; cursor:pointer; transition:transform .35s cubic-bezier(.2,.8,.2,1); }.browse-card:hover { transform:translateY(-3px); }.browse-card img,.browse-card > span { display:grid; place-items:center; width:150px; aspect-ratio:1; overflow:hidden; border-radius:18px; color:var(--paper); background:#221a16; object-fit:cover; }.artist-card img,.artist-card > span { border-radius:50%; border:1px solid #ffffff18; }.browse-card strong,.browse-card small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.browse-card strong { margin-top:9px; font-size:.78rem; }.browse-card small { margin-top:3px; color:var(--muted); font-size:.68rem; }.search-empty,.search-error { padding:24px 4px; color:var(--muted); font-size:.82rem; }.search-error { display:flex; flex-direction:column; gap:5px; }.search-error strong { color:#e5aaa0; }
  .empty,.library-empty { color:var(--muted); font-size:.8rem; }.empty strong,.empty span { display:block; }.empty span { margin-top:5px; }.empty .pill-button { margin-top:12px; }.library-empty { padding:20px 0; }
  @media (max-width:800px) { .home-page { padding:20px 16px 140px; }.topbar { flex-wrap:wrap; }.wordmark { order:-1; width:100%; }.search { flex:1; width:auto; }.actions { margin-left:auto; }.btn { padding:9px 13px; }.row,.playlist-row { grid-template-columns:repeat(2,1fr); }.playlist-card:nth-child(2) { margin-top:18px; }.playlist-card:nth-child(4) { margin-top:28px; }.playlist-feature { grid-column:span 2; }.smart-list { grid-template-columns:1fr; }.hero { min-height:260px; gap:14px; }.hero-content { padding:28px 0 28px 26px; }.hero-title { max-width:100%; font-size:clamp(1.55rem,6vw,2.5rem); }.hero-art { width:138px; height:138px; margin-right:22px; border-radius:18px; } }
  @media (max-width:520px) { .actions .ghost,.expired { display:none; }.settings { width:32px; }.pills { margin-bottom:24px; }.hero { min-height:240px; align-items:flex-end; gap:8px; }.hero-content { padding:26px 0 25px 20px; }.hero-context { font-size:.57rem; letter-spacing:.12em; }.hero-title { font-size:1.55rem; }.hero-sub { max-width:calc(100vw - 190px); font-size:.78rem; }.hero-album { display:none; }.hero-actions { margin-top:16px; }.hero-play { height:36px; padding:0 15px; font-size:.7rem; }.hero-art { width:112px; height:112px; margin:0 16px 20px 0; border-radius:15px; } .row,.playlist-row { gap:9px; }.rowcard,.playlist-card { padding:10px; border-radius:18px; }.playlist-card:nth-child(2) { margin-top:12px; }.playlist-card:nth-child(4) { margin-top:20px; } }
  @media (prefers-reduced-motion: reduce) { .ambient-glow,.hero-live-dot { animation:none; }.rowcard,.playlist-card,.btn,.hero-play { transition:none; } }
</style>
