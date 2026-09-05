<script>
  import TrackCard from '../components/TrackCard.svelte'

  export let tracks = []
  export let favoriteArtists = []
  export let history = []
  export let loading = false
  export let onCompileMix = () => {}
  export let onPlay = () => {}
  export let onOpenArtist = () => {}
  export let onOpenAlbum = () => {}
  export let onAddToQueue = () => {}

  let selected = []
  let query = ''

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const entityKey = item => item?.id || item?.browseId || clean(item?.name).toLowerCase()
  const entityName = item => typeof item === 'string' ? item : item?.name || item?.title || ''

  $: libraryArtists = [...new Map([
    ...favoriteArtists,
    ...history.flatMap(item => Array.isArray(item?.artists) ? item.artists : [{ name: item?.artist }]),
  ].filter(item => entityName(item)).map(item => [entityKey(item), item])).values()]
  $: filteredArtists = libraryArtists.filter(item => clean(entityName(item)).toLowerCase().includes(query.trim().toLowerCase()))
  $: targetArtist = selected[0] || libraryArtists[0] || null
  $: targetName = clean(entityName(targetArtist))
  $: artistTracks = targetName ? tracks.filter(item => clean(item?.artist).toLowerCase().includes(targetName.toLowerCase())) : []
  $: architects = [...new Map(artistTracks.flatMap(item => {
    const value = item?.producers || item?.producer || []
    return Array.isArray(value) ? value : [value]
  }).filter(Boolean).map(item => [entityKey(item), item])).values()]
  $: collaborators = [...new Map(artistTracks.flatMap(item => {
    const value = item?.features || item?.collaborators || []
    return Array.isArray(value) ? value : [value]
  }).filter(Boolean).map(item => [entityKey(item), item])).values()]
  $: freshDrops = tracks.filter(item => item?.releaseDate || item?.releasedAt || item?.isNew).slice(0, 12)

  function toggleArtist(artist) {
    const key = entityKey(artist)
    if (selected.some(item => entityKey(item) === key)) {
      selected = selected.filter(item => entityKey(item) !== key)
      return
    }
    if (selected.length < 4) selected = [...selected, artist]
  }

  function compile() {
    if (selected.length < 2) return
    onCompileMix(selected)
  }

  function openPerson(person) {
    onOpenArtist(person?.id || person?.browseId || null, entityName(person))
  }
</script>

<section class="discover-page" aria-labelledby="discover-title">
  <header class="page-header">
    <div>
      <p class="eyebrow">DISCOVERY WORKSPACE</p>
      <h1 id="discover-title">Discover</h1>
      <p class="lede">Build a deliberate next listen from the artists already shaping your library.</p>
    </div>
    <span class="data-tag">{tracks.length} TRACKS IN FIELD</span>
  </header>

  <section class="compile-bar" aria-label="Compile a mix">
    <div>
      <p class="eyebrow">STATION MATRIX</p>
      <h2>Compile a mix</h2>
      <p>Choose 2–4 artists. The queue will alternate between their catalogs.</p>
    </div>
    <button class="compile-button" disabled={selected.length < 2 || loading} on:click={compile}>
      {#if loading}<span class="spinner" aria-hidden="true"></span>Compiling…{:else}Compile Mix <span>{selected.length}/4</span>{/if}
    </button>
  </section>

  <section class="artist-picker" aria-labelledby="signal-title">
    <div class="picker-head">
      <div>
        <h2 id="signal-title">Signal sources</h2>
        <p>{selected.length === 0 ? 'Select at least two artists' : `${selected.length} selected`}</p>
      </div>
      <input bind:value={query} type="search" placeholder="Filter artists" aria-label="Filter artists" />
    </div>
    <div class="artist-chips">
      {#each filteredArtists as artist (entityKey(artist))}
        <button class:selected={selected.some(item => entityKey(item) === entityKey(artist))} on:click={() => toggleArtist(artist)}>
          <span aria-hidden="true">♩</span>
          {clean(entityName(artist))}
          {#if selected.some(item => entityKey(item) === entityKey(artist))}<b aria-hidden="true">✓</b>{/if}
        </button>
      {:else}
        <p class="empty">No artists from your listening history match that search.</p>
      {/each}
    </div>
    {#if selected.length === 1}
      <p class="validation">Choose one more artist to compile a balanced mix.</p>
    {:else if selected.length >= 4}
      <p class="validation">Four artists selected — remove one before choosing another.</p>
    {/if}
  </section>

  <section class="node-workspace" aria-labelledby="nodes-title">
    <div class="node-header">
      <div>
        <p class="eyebrow">CONNECTION NODES</p>
        <h2 id="nodes-title">{targetArtist ? `The network around ${targetName}` : 'Choose a target artist'}</h2>
      </div>
      <span class="data-tag">{targetArtist ? 'ACTIVE TARGET' : 'NO TARGET'}</span>
    </div>
    <div class="node-grid">
      <section class="node-panel" aria-labelledby="architects-title">
        <header>
          <span class="node-index">01</span>
          <div><h3 id="architects-title">Architects</h3><p>Producers and beatmakers</p></div>
        </header>
        {#if architects.length}
          <ul>
            {#each architects as person (entityKey(person))}
              <li><button on:click={() => openPerson(person)}>{clean(entityName(person))}</button><span>producer</span></li>
            {/each}
          </ul>
        {:else}
          <p class="empty">Producer credits will appear when the provider returns them for this catalog.</p>
        {/if}
      </section>

      <section class="node-panel" aria-labelledby="collaborators-title">
        <header>
          <span class="node-index">02</span>
          <div><h3 id="collaborators-title">Collaborators</h3><p>Features and scene peers</p></div>
        </header>
        {#if collaborators.length}
          <ul>
            {#each collaborators as person (entityKey(person))}
              <li><button on:click={() => openPerson(person)}>{clean(entityName(person))}</button><span>collaborator</span></li>
            {/each}
          </ul>
        {:else}
          <p class="empty">Collaborator data will populate from enriched artist metadata.</p>
        {/if}
      </section>
    </div>
  </section>

  <section class="drops" aria-labelledby="drops-title">
    <div class="section-label">
      <div><p class="eyebrow">FRESH DROPS</p><h2 id="drops-title">New in your orbit</h2></div>
      <span class="data-tag">LAST 30 DAYS</span>
    </div>
    {#if freshDrops.length}
      <div class="drop-grid">
        {#each freshDrops as item (item.videoId || item.id)}
          <TrackCard track={item} onPlay={onPlay} onOpenArtist={onOpenArtist} onOpenAlbum={onOpenAlbum} onAdd={onAddToQueue} />
        {/each}
      </div>
    {:else}
      <p class="empty">New releases from artists in your library will land here as the feed supplies release dates.</p>
    {/if}
  </section>
</section>

<style>
  .discover-page{min-height:100%;box-sizing:border-box;padding:30px clamp(18px,4vw,48px) 46px;color:#ededed;font-family:Inter,ui-sans-serif,system-ui,sans-serif}
  .page-header,.picker-head,.node-header,.section-label{display:flex;align-items:flex-end;justify-content:space-between;gap:18px}.page-header{margin-bottom:26px}.eyebrow,.data-tag{margin:0 0 8px;color:#71717a;font:600 .64rem ui-monospace,SFMono-Regular,monospace;letter-spacing:.14em}.page-header h1{margin:0;font-size:clamp(2rem,4vw,3rem);letter-spacing:-.055em}.lede{margin:7px 0 0;color:#71717a;font-size:.78rem}.compile-bar,.artist-picker,.node-workspace,.drops{border:1px solid rgba(255,255,255,.07);background:#09090b;border-radius:12px}.compile-bar{display:flex;align-items:center;justify-content:space-between;gap:22px;padding:20px;margin-bottom:14px}.compile-bar h2,.node-header h2,.section-label h2{margin:0;font-size:1.08rem;letter-spacing:-.03em}.compile-bar p:not(.eyebrow),.picker-head p,.node-panel header p{margin:6px 0 0;color:#71717a;font-size:.74rem}.compile-button{display:inline-flex;align-items:center;gap:8px;border:1px solid #ededed;border-radius:999px;padding:10px 16px;color:#09090b;background:#ededed;cursor:pointer;font-weight:700;white-space:nowrap}.compile-button:disabled{opacity:.38;cursor:not-allowed}.compile-button span{font:500 .64rem ui-monospace,SFMono-Regular,monospace}.spinner{width:12px;height:12px;border:2px solid #09090b33;border-top-color:#09090b;border-radius:50%;animation:spin .7s linear infinite}.artist-picker{padding:17px;margin-bottom:14px}.picker-head h2{margin:0;font-size:.95rem}.picker-head input{width:min(220px,44vw);border:1px solid rgba(255,255,255,.09);border-radius:8px;padding:9px 11px;color:#ededed;background:#111113;outline:none}.picker-head input:focus{border-color:#ededed}.artist-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:15px}.artist-chips button{display:inline-flex;align-items:center;gap:7px;border:1px solid rgba(255,255,255,.08);border-radius:999px;padding:8px 11px;color:#a1a1aa;background:#111113;cursor:pointer;font-size:.72rem}.artist-chips button:hover,.artist-chips button.selected{color:#ededed;border-color:rgba(255,255,255,.28)}.artist-chips button.selected{background:#ededed;color:#09090b}.artist-chips b{font-size:.68rem}.validation{margin:12px 0 0;color:#a1a1aa;font-size:.7rem}.node-workspace{padding:18px;margin-bottom:14px}.node-header{margin-bottom:16px}.node-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.node-panel{min-height:170px;padding:15px;border:1px solid rgba(255,255,255,.06);border-radius:10px;background:#0c0c0f}.node-panel header{display:flex;align-items:center;gap:10px;padding-bottom:12px;border-bottom:1px solid rgba(255,255,255,.06)}.node-index{color:#71717a;font:500 .65rem ui-monospace,SFMono-Regular,monospace}.node-panel h3{margin:0;font-size:.85rem}.node-panel ul{margin:12px 0 0;padding:0;list-style:none}.node-panel li{display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.04)}.node-panel li:last-child{border-bottom:0}.node-panel li button{border:0;padding:0;color:#ededed;background:none;cursor:pointer;font:inherit;font-size:.75rem}.node-panel li button:hover{text-decoration:underline}.node-panel li span{color:#52525b;font:500 .6rem ui-monospace,SFMono-Regular,monospace}.drops{padding:18px}.section-label{align-items:center}.drop-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(145px,1fr));gap:16px;margin-top:16px}.empty{color:#71717a;font-size:.76rem}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:700px){.page-header,.compile-bar,.picker-head,.node-header{align-items:flex-start;flex-direction:column}.compile-button{width:100%;justify-content:center}.picker-head input{width:100%}.node-grid{grid-template-columns:1fr}.discover-page{padding:22px 16px 36px}}
</style>