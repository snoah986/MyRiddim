<script>
  import StatsView from '../pages/StatsView.svelte'
  import TrackCard from './TrackCard.svelte'
  import HomeDashboard from './HomeDashboard.svelte'
  import RecentlyPlayedView from '../pages/RecentlyPlayedView.svelte'
  import DiscoverView from '../pages/DiscoverView.svelte'
  import TrackContextMenu from './TrackContextMenu.svelte'

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
  export let onCompileArtistMix = () => {}
  export let onToggle = () => {}
  export let onOpenQueue = () => {}
  export let onOpenTheatre = () => {}

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const key = item => item?.videoId || item?.id || item?.browseId || item?.title
  $: songs = searchResults.filter(item => item.type === 'song')
  $: artists = searchResults.filter(item => item.type === 'artist')
  $: albums = searchResults.filter(item => item.type === 'album')
  $: playlistsFound = searchResults.filter(item => item.type === 'playlist')
  $: topResult = searchResults[0]
  let menuTrack = null
  let menuX = 0
  let menuY = 0
  let menuKey = 0
  function play(track, index = 0, list = [track]) { if (track || list.length) onPlayQueue(list, index) }
  function context(event, track) { event.preventDefault(); menuTrack = track; menuX = event.clientX; menuY = event.clientY; menuKey += 1 }
  function openSearch(item) {
    if (item.type === 'song') play(item)
    else if (item.type === 'artist') onOpenArtistEntity(item.id, item.title)
    else if (item.type === 'album') onOpenAlbumEntity(item.id, item.title, item.artist)
    else if (item.type === 'playlist') onOpenPlaylist({ id: item.id, title: item.title })
    else onOpenBrowse(item)
  }
</script>

<div class="home-view">
  {#if sessionState === 'expired' && !sessionBannerDismissed}<div class="notice" role="alert"><span>Your YouTube Music session has expired.</span><button on:click={onReconnect}>Reconnect</button><button class="close" on:click={onDismissSession} aria-label="Dismiss">×</button></div>{/if}
  {#if libraryCached}<div class="notice" role="status"><span>Showing your cached library.</span><button class="close" on:click={onDismissOffline} aria-label="Dismiss">×</button></div>{/if}

  {#if searchQuery.trim()}
    <section class="search-page" aria-label="Search results" aria-busy={searching}>
      <header class="search-head"><div><p class="eyebrow">SEARCH</p><h1>{clean(searchQuery)}</h1></div>{#if searching}<span class="searching">Searching…</span>{/if}</header>
      {#if searchError}<p class="error" role="alert">{searchError}</p>{/if}
      {#if searching && !searchResults.length}<p class="empty">Looking across songs, artists, albums, and playlists…</p>{:else if !searchResults.length}<p class="empty">No results for “{clean(searchQuery)}”.</p>{:else}
        <section class="search-group"><h2>Top Result</h2><button class="top-result" on:click={() => openSearch(topResult)}><span class="search-image">{#if topResult.thumbnail}<img src={topResult.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span><strong>{clean(topResult.title)}</strong><small>{clean(topResult.type || 'Result')} {topResult.artist ? `· ${clean(topResult.artist)}` : ''}</small></span><b>Open</b></button></section>
        {#if songs.length}<section class="search-group"><h2>Songs <small>{songs.length}</small></h2><div class="search-list">{#each songs as item, index (key(item) || index)}<div class="search-row"><button class="search-main" on:click={() => play(item)} on:contextmenu={(event) => context(event, item)}><span class="search-image small">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span><strong>{clean(item.title)}</strong><small>{#if item.artist}<span class="entity" on:click|stopPropagation={() => onOpenArtistEntity(item.artistId || null, item.artist)}>{clean(item.artist)}</span>{/if}{#if item.album}<span class="muted"> · </span><span class="entity" on:click|stopPropagation={() => onOpenAlbumEntity(item.albumId || null, item.album, item.artist)}>{clean(item.album)}</span>{/if}</small></span><time>{clean(item.duration)}</time></button><TrackContextMenu track={item} onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} /></div>{/each}</div></section>{/if}
        {#if artists.length}<section class="search-group"><h2>Artists <small>{artists.length}</small></h2><div class="entity-grid">{#each artists as item, index (key(item) || index)}<button class="entity-card" on:click={() => onOpenArtistEntity(item.id, item.title)}><span class="artist-image">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♩{/if}</span><strong>{clean(item.title)}</strong><small>Artist</small></button>{/each}</div></section>{/if}
        {#if albums.length}<section class="search-group"><h2>Albums <small>{albums.length}</small></h2><div class="entity-grid">{#each albums as item, index (key(item) || index)}<button class="entity-card" on:click={() => onOpenAlbumEntity(item.id, item.title, item.artist)}><span class="search-image">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(item.title)}</strong><small>{clean(item.artist || 'Album')}</small></button>{/each}</div></section>{/if}
        {#if playlistsFound.length}<section class="search-group"><h2>Playlists <small>{playlistsFound.length}</small></h2><div class="entity-grid">{#each playlistsFound as item, index (key(item) || index)}<button class="entity-card" on:click={() => onOpenPlaylist({ id: item.id, title: item.title })}><span class="search-image">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(item.title)}</strong><small>Playlist</small></button>{/each}</div></section>{/if}
      {/if}
    </section>
  {:else if homeView === 'home'}
    <HomeDashboard currentTrack={currentTrack} quickPicks={quickPicks} upNext={upNext} playlists={playlists} heavyRotation={stats.heavyRotation || rotationTracks} currentTime={currentTime} duration={duration} isPlaying={isPlaying} volume={volume} loading={loading} onPlayQueue={onPlayQueue} onToggle={onToggle} onOpenPlaylist={onOpenPlaylist} onOpenQueue={onOpenQueue} onOpenTheatre={onOpenTheatre} onCreatePlaylist={onCreatePlaylist} />
  {:else if homeView === 'recent'}
    <RecentlyPlayedView history={history} heavyRotation={stats.heavyRotation || rotationTracks} favoriteArtists={favoriteArtists} onPlay={(track) => play(track)} onOpenArtist={onOpenArtistEntity} onOpenAlbum={onOpenAlbumEntity} onAddToQueue={onAddToQueue} />
  {:else if homeView === 'discover'}
    <DiscoverView tracks={[...discoverTracks, ...quickPicks, ...smartMix]} favoriteArtists={favoriteArtists} history={history} loading={discoverLoading} onCompileMix={onCompileArtistMix} onPlay={(track) => play(track)} onOpenArtist={onOpenArtistEntity} onOpenAlbum={onOpenAlbumEntity} onAddToQueue={onAddToQueue} />
  {:else if homeView === 'stats'}
    <StatsView onPlayTrack={(track) => play(track)} onStartMix={onStartMix} />
  {:else if homeView === 'favorites'}
    <section class="favorites-page"><header><p class="eyebrow">LIBRARY</p><h1>Favorites</h1><p>Your saved tracks, kept close.</p></header>{#if likedLoading}<p class="empty">Loading favorites…</p>{:else if likedError}<div class="empty"><strong>{likedError}</strong><button class="action" on:click={onRetryLiked}>Retry</button></div>{:else if likedTracks.length}<div class="track-grid">{#each likedTracks as item, index (key(item) || index)}<TrackCard track={item} onPlay={track => play(track, index, likedTracks)} onOpenArtist={onOpenArtistEntity} onOpenAlbum={onOpenAlbumEntity} onAdd={onAddToQueue} />{/each}</div>{:else}<p class="empty">No favorites yet.</p>{/if}</section>
  {/if}

  {#if menuTrack}<TrackContextMenu key={menuKey} track={menuTrack} positioned x={menuX} y={menuY} autoOpen onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} />{/if}
</div>

<style>
  .home-view{height:100%;min-height:0;box-sizing:border-box;background:#000;color:#ededed;font-family:Inter,ui-sans-serif,system-ui,sans-serif}.notice{display:flex;align-items:center;gap:10px;margin:0 24px 10px;padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.07);color:#a1a1aa;font-size:.7rem}.notice button{border:1px solid rgba(255,255,255,.13);border-radius:6px;padding:5px 8px;color:#ededed;background:#08080a;cursor:pointer;font-size:.64rem}.notice .close{margin-left:auto;border:0;background:transparent;font-size:1rem}.search-page,.favorites-page{height:100%;box-sizing:border-box;overflow:auto;padding:28px clamp(18px,4vw,48px) 48px}.search-head,.favorites-page header{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:24px}.eyebrow{margin:0 0 6px;color:#71717a;font:600 .62rem ui-monospace,SFMono-Regular,monospace;letter-spacing:.15em}.search-head h1,.favorites-page h1{margin:0;font-size:clamp(1.8rem,4vw,2.8rem);letter-spacing:-.06em}.searching{color:#71717a;font:500 .68rem ui-monospace,monospace}.search-group{margin:0 0 24px}.search-group h2{display:flex;align-items:baseline;gap:8px;margin:0 0 10px;font-size:.9rem;letter-spacing:-.02em}.search-group h2 small{color:#52525b;font:500 .62rem ui-monospace,monospace}.top-result{display:flex;align-items:center;gap:12px;width:100%;box-sizing:border-box;padding:10px;border:1px solid rgba(255,255,255,.07);border-radius:10px;color:#ededed;background:#08080a;text-align:left;cursor:pointer}.top-result:hover,.entity-card:hover,.search-row:hover{border-color:rgba(255,255,255,.2);background:#101014}.top-result>span:nth-child(2){display:flex;min-width:0;flex:1;flex-direction:column}.top-result strong,.top-result small,.entity-card strong,.entity-card small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.top-result small{margin-top:3px;color:#71717a;font-size:.68rem}.top-result b{color:#71717a;font:500 .62rem ui-monospace,monospace}.search-image{display:grid;place-items:center;width:58px;height:58px;flex:0 0 auto;overflow:hidden;border:1px solid rgba(255,255,255,.07);border-radius:9px;background:#121215;color:#71717a}.search-image.small{width:40px;height:40px;border-radius:7px}.search-image img,.artist-image img{width:100%;height:100%;object-fit:cover}.search-list{overflow:hidden;border:1px solid rgba(255,255,255,.07);border-radius:10px}.search-row{display:flex;align-items:center;border-bottom:1px solid rgba(255,255,255,.05)}.search-row:last-child{border-bottom:0}.search-main{display:flex;align-items:center;gap:10px;flex:1;min-width:0;padding:8px 10px;border:0;color:#ededed;background:transparent;text-align:left;cursor:pointer}.search-main>span:nth-child(2){display:flex;min-width:0;flex:1;flex-direction:column}.search-main strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.75rem}.search-main small{display:block;margin-top:3px;color:#71717a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.65rem}.search-main time{color:#71717a;font:500 .62rem ui-monospace,monospace}.entity{cursor:pointer}.entity:hover{color:#ededed;text-decoration:underline}.muted{color:#52525b}.entity-grid,.track-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:14px}.entity-card{min-width:0;padding:0;border:1px solid transparent;color:#ededed;background:transparent;text-align:left;cursor:pointer}.entity-card>span{display:grid;place-items:center;aspect-ratio:1;overflow:hidden;border:1px solid rgba(255,255,255,.07);border-radius:10px;background:#121215}.entity-card .artist-image{border-radius:50%}.entity-card strong,.entity-card small{display:block}.entity-card strong{margin-top:7px;font-size:.74rem}.entity-card small{margin-top:3px;color:#71717a;font:500 .62rem ui-monospace,monospace}.empty{color:#71717a;font-size:.75rem}.empty strong{display:block;color:#a1a1aa;margin-bottom:8px}.action{border:1px solid rgba(255,255,255,.12);border-radius:7px;padding:7px 10px;color:#ededed;background:#111113;cursor:pointer;font-size:.68rem}.track-grid{padding-top:10px}
</style>