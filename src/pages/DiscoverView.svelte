<script>
  import TrackCard from '../components/TrackCard.svelte'

  export let tracks = []
  export let favoriteArtists = []
  export let history = []
  export let persistentHistory = []
  export let stats = { monthly: [], heavyRotation: [] }
  export let onCompileMix = () => {}
  export let onPlay = () => {}
  export let onOpenArtist = () => {}
  export let onOpenAlbum = () => {}
  export let onAddToQueue = () => {}

  let selected = []
  let query = ''
  let compiling = false
  let tunesContainer

  function scrollTunes(direction) {
    if (!tunesContainer) return
    const offset = tunesContainer.clientWidth * 0.75
    tunesContainer.scrollBy({
      left: direction === 'left' ? -offset : offset,
      behavior: 'smooth',
    })
  }

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const entityName = item => typeof item === 'string' ? clean(item) : clean(item?.name || item?.title || item?.artist)
  const entityId = item => typeof item === 'object' ? item?.id || item?.browseId || null : null
  const entityKey = item => String(entityId(item) || entityName(item).toLowerCase())
  const artistEntries = item => {
    const value = item?.artists || item?.artist || item?.author
    return Array.isArray(value) ? value : value ? [value] : []
  }
  const trackKey = item => item?.videoId || item?.id || `${item?.title}-${item?.artist}`

  $: sourceArtists = Array.from(new Map([
    ...(Array.isArray(favoriteArtists) ? favoriteArtists : []),
    ...(Array.isArray(stats?.monthly) ? stats.monthly.flatMap(item => artistEntries(item)) : []),
    ...(Array.isArray(persistentHistory) ? persistentHistory.flatMap(item => artistEntries(item)) : []),
    ...(Array.isArray(history) ? history.flatMap(item => artistEntries(item)) : []),
  ].map(item => [entityKey(item), item]).filter(([key, item]) => entityName(item) && key !== '')).values())
  $: libraryArtists = sourceArtists.map(item => ({
    name: entityName(item),
    id: entityId(item),
    thumbnail: item?.thumbnail || item?.thumbnail_url || item?.thumbnails?.at?.(-1)?.url || null,
  }))
  $: filteredArtists = libraryArtists.filter(item => item.name.toLowerCase().includes(query.trim().toLowerCase()))
  $: allTracks = [...new Map([...(Array.isArray(tracks) ? tracks : []), ...(Array.isArray(persistentHistory) ? persistentHistory : [])].filter(item => trackKey(item)).map(item => [trackKey(item), item])).values()]
  $: freshDrops = allTracks.filter(item => item?.releaseDate || item?.releasedAt || item?.isNew).slice(0, 12)
  $: discoveryTracks = allTracks.slice(0, 12)

  function isSelected(artist) {
    return selected.some(item => entityKey(item) === entityKey(artist))
  }

  function toggleArtist(artist) {
    const key = entityKey(artist)
    if (selected.some(item => entityKey(item) === key)) {
      selected = selected.filter(item => entityKey(item) !== key)
    } else if (selected.length < 4) {
      selected = [...selected, artist]
    }
  }

  function removeArtist(artist) {
    selected = selected.filter(item => entityKey(item) !== entityKey(artist))
  }

  function addFirstAvailableArtist() {
    const artist = filteredArtists.find(item => !isSelected(item))
    if (artist) toggleArtist(artist)
  }

  async function compile() {
    if (selected.length < 2 || compiling) return
    compiling = true
    try {
      await onCompileMix(selected)
    } finally {
      compiling = false
    }
  }

  function openPerson(person) {
    onOpenArtist(entityId(person), entityName(person))
  }
</script>

<section class="discover-page" aria-labelledby="discover-title">
  <section class="tunes-panel" aria-labelledby="tunes-title">
    <header class="section-head">
      <h1 id="tunes-title">Tunes to Discover</h1>
      {#if discoveryTracks.length}
        <div class="tunes-navigation">
          <span class="data-tag">{discoveryTracks.length} TRACKS</span>
          <div class="carousel-arrows">
            <button type="button" class="carousel-arrow" on:click={() => scrollTunes('left')} aria-label="Scroll left">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m15 19-7-7 7-7" /></svg>
            </button>
            <button type="button" class="carousel-arrow" on:click={() => scrollTunes('right')} aria-label="Scroll right">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
            </button>
          </div>
        </div>
      {/if}
    </header>
    {#if freshDrops.length}
      <div class="drop-strip" aria-label="Fresh drops">
        {#each freshDrops.slice(0, 4) as item, index (`${trackKey(item)}-${index}`)}
          <TrackCard track={item} compact onPlay={onPlay} onOpenArtist={onOpenArtist} onOpenAlbum={onOpenAlbum} onAdd={onAddToQueue} />
        {/each}
      </div>
    {/if}
    {#if discoveryTracks.length}
      <div class="track-grid" bind:this={tunesContainer}>
        {#each discoveryTracks as item, index (`${trackKey(item)}-${index}`)}
          <div class="tune-card">
            <TrackCard track={item} onPlay={onPlay} onOpenArtist={onOpenArtist} onOpenAlbum={onOpenAlbum} onAdd={onAddToQueue} />
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <section class="mixer-panel" aria-labelledby="mixer-title">
    <header class="mixer-head">
      <h2 id="mixer-title">Multi-Artist Mixer Desk</h2>
      <button class="compile-button" disabled={selected.length < 2 || compiling} on:click={compile} aria-label="Compile selected artists">
        {#if compiling}<span class="spinner" aria-hidden="true"></span>{/if}
        <span class="mixer-glyph" aria-hidden="true">⧉</span>
        <span>{compiling ? 'Compiling…' : 'Compile Mix'}</span>
      </button>
    </header>

    <div class="mix-slots" aria-label="Selected artists">
      {#each Array(4) as _, index}
        {#if selected[index]}
          <button class="mix-slot filled" on:click={() => removeArtist(selected[index])} aria-label="Remove {selected[index].name} from mix">
            {#if selected[index].thumbnail}<img src={selected[index].thumbnail} alt="" referrerpolicy="no-referrer" />{/if}
            <span>{selected[index].name}</span><b aria-hidden="true">×</b>
          </button>
        {:else}
          <button class="mix-slot empty-slot" on:click={addFirstAvailableArtist} aria-label="Add an artist to slot {index + 1}"><span aria-hidden="true">＋</span></button>
        {/if}
      {/each}
    </div>

    <div class="artist-source">
      <div class="source-head"><h3>Artists</h3><input bind:value={query} type="search" placeholder="Search artists" aria-label="Search library artists" /></div>
      <div class="artist-strip">
        {#each filteredArtists as artist, index (`${entityKey(artist)}-${index}`)}
          <button class:selected={isSelected(artist)} class="artist-avatar" on:click={() => toggleArtist(artist)} aria-pressed={isSelected(artist)} title={artist.name}>
            {#if artist.thumbnail}
              <img src={artist.thumbnail} alt={artist.name} referrerpolicy="no-referrer" on:error={(event) => event.currentTarget.hidden = true} />
            {/if}
            <span class="avatar-fallback" aria-hidden="true">{clean(artist.name).charAt(0).toUpperCase() || '♩'}</span>
            <small>{artist.name}</small>
          </button>
        {:else}<span class="no-results">No results</span>{/each}
      </div>
    </div>

    {#if selected.length >= 2}
      <div class="selected-summary"><span>{selected.length}/4 selected</span><span>Round-robin queue ready</span></div>
    {/if}
  </section>
</section>

<style>
  .discover-page{display:flex;flex-direction:column;gap:12px;min-height:100%;box-sizing:border-box;padding:18px clamp(16px,3vw,42px) 34px;color:#ededed;background:#000;font-family:Inter,ui-sans-serif,system-ui,sans-serif}.tunes-panel,.mixer-panel{min-height:0;border:1px solid rgba(255,255,255,.07);border-radius:10px;background:#050505;padding:16px}.tunes-panel{flex:1 1 50%;overflow:hidden}.mixer-panel{flex:1 1 50%}.section-head,.mixer-head,.source-head{display:flex;align-items:center;justify-content:space-between;gap:14px}.section-head h1,.mixer-head h2{margin:0;font-size:1.1rem;letter-spacing:-.045em}.tunes-navigation{display:flex;align-items:center;gap:12px}.data-tag{color:#71717a;font:600 .6rem ui-monospace,SFMono-Regular,monospace;letter-spacing:.12em}.carousel-arrows{display:flex;align-items:center;gap:4px}.carousel-arrow{display:grid;place-items:center;width:28px;height:28px;border:0;border-radius:50%;color:#d4d4d8;background:rgba(255,255,255,.05);cursor:pointer;transition:background .18s ease,color .18s ease}.carousel-arrow:hover{color:#fff;background:rgba(255,255,255,.15)}.carousel-arrow svg{width:16px;height:16px;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:2}.drop-strip{display:flex;gap:8px;overflow-x:auto;margin-top:14px;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,.06);scrollbar-width:none}.drop-strip::-webkit-scrollbar{display:none}.drop-strip :global(.compact-card){min-width:215px}.track-grid{display:flex;flex-wrap:nowrap;gap:16px;margin-top:14px;overflow-x:auto;scroll-behavior:smooth;scrollbar-width:none;-ms-overflow-style:none;user-select:none;padding:2px 2px 12px}.track-grid::-webkit-scrollbar{display:none}.tune-card{flex:0 0 9rem;width:9rem}.compile-button{display:inline-flex;align-items:center;gap:7px;border:1px solid #ededed;border-radius:999px;padding:8px 13px;color:#080808;background:#ededed;cursor:pointer;font-size:.7rem;font-weight:750}.compile-button:disabled{opacity:.34;cursor:not-allowed}.mixer-glyph{font-size:1rem;line-height:1}.spinner{width:11px;height:11px;border:2px solid #0004;border-top-color:#000;border-radius:50%;animation:spin .7s linear infinite}.mix-slots{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:18px}.mix-slot{display:flex;align-items:center;justify-content:center;gap:7px;min-width:0;min-height:42px;padding:7px 9px;border:1px dashed rgba(255,255,255,.22);border-radius:9px;color:#71717a;background:transparent;cursor:pointer}.mix-slot.filled{border-style:solid;border-color:rgba(255,255,255,.25);color:#ededed;background:#111113}.mix-slot img{width:24px;height:24px;flex:0 0 auto;object-fit:cover;border-radius:50%}.mix-slot span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.68rem}.mix-slot b{color:#71717a;font-size:1rem;font-weight:400}.empty-slot span{font-size:1rem}.artist-source{margin-top:18px;padding-top:14px;border-top:1px solid rgba(255,255,255,.07)}.source-head h3{margin:0;color:#a1a1aa;font-size:.76rem}.source-head input{width:min(240px,48%);padding:8px 10px;border:1px solid rgba(255,255,255,.09);border-radius:7px;outline:0;color:#ededed;background:#111113;font-size:.7rem}.source-head input:focus{border-color:#ededed}.artist-strip{display:flex;gap:14px;overflow-x:auto;margin-top:13px;padding:2px 2px 8px;scrollbar-width:none}.artist-strip::-webkit-scrollbar{display:none}.artist-avatar{display:flex;flex:0 0 58px;flex-direction:column;align-items:center;gap:5px;border:0;padding:0;color:#71717a;background:transparent;cursor:pointer}.artist-avatar{position:relative}.artist-avatar img,.artist-avatar .avatar-fallback{display:grid;place-items:center;width:52px;height:52px;overflow:hidden;border:1px solid rgba(255,255,255,.1);border-radius:50%;color:#a1a1aa;background:#17171a;object-fit:cover}.artist-avatar img{position:relative;z-index:1}.artist-avatar .avatar-fallback{position:absolute;top:0;left:50%;transform:translateX(-50%);font-size:1rem;font-weight:700}.artist-avatar.selected img,.artist-avatar.selected .avatar-fallback{border-color:#ededed;box-shadow:0 0 0 2px #000,0 0 0 3px #ededed}.artist-avatar small{width:58px;overflow:hidden;color:#71717a;text-overflow:ellipsis;white-space:nowrap;text-align:center;font-size:.58rem}.artist-avatar.selected small{color:#ededed}.no-results{color:#71717a;font:500 .68rem ui-monospace,SFMono-Regular,monospace}.selected-summary{display:flex;justify-content:space-between;margin-top:14px;color:#71717a;font:500 .62rem ui-monospace,SFMono-Regular,monospace}.selected-summary span:last-child{color:#a1a1aa}@keyframes spin{to{transform:rotate(360deg)}}@media(min-width:640px){.tune-card{flex-basis:10rem;width:10rem}}@media(max-width:700px){.discover-page{padding-inline:12px}.tunes-panel,.mixer-panel{flex-basis:auto}.tunes-panel{min-height:48vh}.mixer-panel{min-height:48vh}.mix-slots{gap:5px}.mix-slot{padding-inline:4px}.source-head input{width:52%}}
</style>
