<script>
  import TrackCard from '../components/TrackCard.svelte'

  export let history = []
  export let heavyRotation = []
  export let favoriteArtists = []
  export let onPlay = () => {}
  export let onOpenArtist = () => {}
  export let onOpenAlbum = () => {}
  export let onAddToQueue = () => {}

  let tab = 'tracks'
  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const formatTime = value => {
    const raw = String(value ?? '').trim()
    const parts = raw.split(':').map(Number)
    const seconds = parts.length > 1 && parts.every(Number.isFinite)
      ? parts.reduce((total, part) => total * 60 + part, 0)
      : Number(raw) || 0
    return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
  }
  const relativeTime = value => {
    const timestamp = new Date(value || 0).getTime()
    if (!timestamp) return 'recently'
    const minutes = Math.max(1, Math.floor((Date.now() - timestamp) / 60000))
    return minutes < 60 ? `${minutes}m ago` : `${Math.floor(minutes / 60)}h ago`
  }
  $: tape = history.slice(-10).reverse()
  $: rotation = heavyRotation.length ? heavyRotation.slice(0, 20) : history.slice(-20).reverse()
  $: albums = [...new Map(history.filter(item => item?.album).map(item => [item.album, item])).values()]
  $: artists = [...new Map(history.flatMap(item => Array.isArray(item?.artists) ? item.artists : [{ name: item?.artist }]).filter(item => item?.name).map(item => [item.name, item])).values()]
</script>

<section class="recent-page" aria-labelledby="recent-title">
  <header class="page-header"><div><p class="eyebrow">PLAYBACK ARCHIVE</p><h1 id="recent-title">Recently played</h1><p class="lede">A clean tape of what actually moved through your decks.</p></div><span class="data-tag">LAST 10 / CHRONOLOGICAL</span></header>

  <section class="tape" aria-label="Last ten tracks played">
    <div class="section-label"><h2>Session tape</h2><span>{tape.length}/10 tracks</span></div>
    {#if tape.length}<div class="tape-row">{#each tape as item (item.videoId)}<article class="tape-card"><span class="tape-art">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span class="tape-copy"><strong>{clean(item.title)}</strong><small>{clean(item.artist)}</small><time>{relativeTime(item.playedAt || item.played_at || item.timestamp)}</time></span><button on:click={() => onPlay(item)} aria-label="Play {clean(item.title)}">▶</button></article>{/each}</div>{:else}<p class="empty">Play a few tracks and your session tape will appear here.</p>{/if}
  </section>

  <nav class="segment" aria-label="Recently played sections" role="tablist">{#each [['tracks','Heavy Rotation'],['albums','Albums'],['artists','Artists']] as item}<button role="tab" aria-selected={tab === item[0]} class:active={tab === item[0]} on:click={() => tab = item[0]}>{item[1]}</button>{/each}</nav>

  {#if tab === 'tracks'}
    <section class="panel rotation-panel"><div class="section-label"><div><h2>Heavy Rotation</h2><p>Your most replayed tracks this week.</p></div><span class="data-tag">TOP {rotation.length}</span></div><div class="rotation-list">{#each rotation as item, index}<TrackCard track={item} compact rank={index + 1} onPlay={onPlay} onOpenArtist={onOpenArtist} onOpenAlbum={onOpenAlbum} onAdd={onAddToQueue} />{:else}<p class="empty">Your leaderboard will build as you listen.</p>{/each}</div></section>
  {:else if tab === 'albums'}
    <section class="panel"><div class="section-label"><div><h2>Albums</h2><p>Projects your recent plays touched.</p></div></div><div class="album-grid">{#each albums as album}<button class="album-card" on:click={() => onOpenAlbum(null, album.album)}><span>{#if album.thumbnail}<img src={album.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><strong>{clean(album.album)}</strong><small>{clean(album.year) || 'Recent play'} · {history.filter(item => item.album === album.album).length} plays</small></button>{:else}<p class="empty">No album history yet.</p>{/each}</div></section>
  {:else}
    <section class="panel"><div class="section-label"><div><h2>Artists</h2><p>Artists in your current listening rotation.</p></div></div><div class="artist-grid">{#each artists as artist}<button class="artist-card" on:click={() => onOpenArtist(artist.id || null, artist.name)}><span>{#if artist.thumbnail}<img src={artist.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♩{/if}</span><strong>{clean(artist.name)}</strong><small>{history.filter(item => item.artist === artist.name).length} plays this month</small></button>{:else}<p class="empty">No artists to show yet.</p>{/each}</div></section>
  {/if}
</section>

<style>
  .recent-page { min-height:100%; box-sizing:border-box; padding:30px clamp(18px,4vw,48px) 46px; color:#ededed; font-family:Inter,ui-sans-serif,system-ui,sans-serif; }
  .page-header,.section-label { display:flex; align-items:flex-end; justify-content:space-between; gap:18px; }.page-header { margin-bottom:28px; }.eyebrow,.data-tag { margin:0 0 8px; color:#71717a; font:600 .64rem ui-monospace,SFMono-Regular,monospace; letter-spacing:.14em; }.page-header h1 { margin:0; color:#ededed; font-size:clamp(2rem,4vw,3rem); letter-spacing:-.055em; }.lede,.section-label p { margin:7px 0 0; color:#71717a; font-size:.78rem; }.section-label h2 { margin:0; font-size:1rem; letter-spacing:-.025em; }.section-label > span { color:#71717a; font:500 .66rem ui-monospace,SFMono-Regular,monospace; }
  .tape { padding:18px 0 22px; border-top:1px solid rgba(255,255,255,.07); border-bottom:1px solid rgba(255,255,255,.07); }.tape-row { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:8px; margin-top:14px; }.tape-card { display:flex; align-items:center; gap:9px; min-width:0; padding:7px; border:1px solid rgba(255,255,255,.06); border-radius:10px; background:#0a0a0c; }.tape-art { display:grid; place-items:center; width:48px; height:48px; flex:0 0 auto; overflow:hidden; border-radius:7px; background:#151518; }.tape-art img { width:100%; height:100%; object-fit:cover; }.tape-copy { display:flex; min-width:0; flex:1; flex-direction:column; }.tape-copy strong,.tape-copy small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.tape-copy strong { font-size:.69rem; }.tape-copy small { margin-top:3px; color:#71717a; font-size:.62rem; }.tape-copy time { margin-top:4px; color:#52525b; font:500 .58rem ui-monospace,SFMono-Regular,monospace; }.tape-card button { width:24px; height:24px; border:0; border-radius:50%; color:#a1a1aa; background:#fff0; cursor:pointer; }.tape-card button:hover { color:#09090b; background:#fff; }.segment { display:flex; gap:4px; width:max-content; margin:24px 0 16px; padding:4px; border:1px solid rgba(255,255,255,.06); border-radius:10px; background:#0a0a0c; }.segment button { border:0; border-radius:7px; padding:8px 13px; color:#71717a; background:transparent; cursor:pointer; font:600 .68rem Inter,sans-serif; }.segment button:hover,.segment button.active { color:#ededed; background:#17171a; }.panel { padding:18px; border:1px solid rgba(255,255,255,.07); border-radius:12px; background:#09090b; }.rotation-list { margin-top:13px; border-top:1px solid rgba(255,255,255,.06); }.album-grid,.artist-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(145px,1fr)); gap:16px; margin-top:17px; }.album-card,.artist-card { min-width:0; border:0; padding:0; color:#ededed; background:transparent; text-align:left; cursor:pointer; }.album-card > span,.artist-card > span { display:grid; place-items:center; aspect-ratio:1; overflow:hidden; border:1px solid rgba(255,255,255,.07); border-radius:10px; background:#121215; }.artist-card > span { border-radius:50%; }.album-card img,.artist-card img { width:100%; height:100%; object-fit:cover; }.album-card strong,.album-card small,.artist-card strong,.artist-card small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.album-card strong,.artist-card strong { margin-top:8px; font-size:.76rem; }.album-card small,.artist-card small { margin-top:4px; color:#71717a; font:500 .62rem ui-monospace,SFMono-Regular,monospace; }.album-card:hover > span,.artist-card:hover > span { border-color:rgba(255,255,255,.23); transform:translateY(-2px); }.empty { color:#71717a; font-size:.78rem; }
  @media(max-width:900px){.tape-row{grid-template-columns:repeat(2,minmax(0,1fr))}.page-header{align-items:flex-start;flex-direction:column}} @media(max-width:520px){.tape-row{display:flex;overflow-x:auto}.tape-card{flex:0 0 220px}.recent-page{padding:22px 16px 36px}}
</style>