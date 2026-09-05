<script>
  import { normalizeArtists, normalizeAlbum } from '../utils/navigation.js'

  export let track = null
  export let onPlay = () => {}
  export let onOpenArtist = () => {}
  export let onOpenAlbum = () => {}
  export let onAdd = null
  export let compact = false
  export let rank = null

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  $: artists = normalizeArtists(track)
  $: album = normalizeAlbum(track)
  $: title = clean(track?.title) || 'Untitled track'

  function play(event) {
    if (event) event.stopPropagation()
    if (track) onPlay(track)
  }

  function artistClick(event, artist) {
    event.stopPropagation()
    onOpenArtist(artist?.id || null, artist?.name || '')
  }

  function albumClick(event) {
    event.stopPropagation()
    onOpenAlbum(album?.id || null, album?.name || '', track?.artist || '')
  }
</script>

{#if compact}
  <article class="compact-card" class:ranked={rank !== null}>
    {#if rank !== null}<span class="rank">{String(rank).padStart(2, '0')}</span>{/if}
    <button class="compact-main" on:click={play} aria-label="Play {title}">
      <span class="art compact-art">{#if track?.thumbnail}<img src={track.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span>
      <span class="copy"><strong>{title}</strong><small>{#each artists as artist, index}{#if index}, {/if}<span class="entity" on:click|stopPropagation={(event) => artistClick(event, artist)}>{clean(artist.name)}</span>{/each}</small></span>
      {#if track?.duration}<time>{clean(track.duration)}</time>{/if}
    </button>
    {#if onAdd}<button class="add-button" on:click|stopPropagation={() => onAdd(track)} aria-label="Add {title} to queue">＋</button>{/if}
  </article>
{:else}
  <article class="track-card">
    <button class="card-main" on:click={play} aria-label="Play {title}">
      <span class="art">{#if track?.thumbnail}<img src={track.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}<span class="play-mark" aria-hidden="true">▶</span></span>
      <span class="card-copy"><strong>{title}</strong><small>{#each artists as artist, index}{#if index}, {/if}<span class="entity" on:click|stopPropagation={(event) => artistClick(event, artist)}>{clean(artist.name)}</span>{/each}{#if album}<span class="on-album"> · </span><span class="entity" on:click|stopPropagation={albumClick}>{clean(album.name)}</span>{/if}</small></span>
    </button>
    {#if onAdd}<button class="add-button" on:click|stopPropagation={() => onAdd(track)} aria-label="Add {title} to queue">＋</button>{/if}
  </article>
{/if}

<style>
  .track-card,.compact-card { position:relative; min-width:0; color:#ededed; }
  .card-main,.compact-main { width:100%; border:0; color:inherit; background:transparent; text-align:left; cursor:pointer; }
  .card-main { display:block; padding:0; }
  .art { position:relative; display:grid; place-items:center; aspect-ratio:1; overflow:hidden; border:1px solid rgba(255,255,255,.08); border-radius:12px; background:#111113; box-shadow:0 8px 24px rgba(0,0,0,.42); transition:transform .2s ease,box-shadow .2s ease; }
  .art img,.compact-art img { width:100%; height:100%; object-fit:cover; display:block; }
  .card-main:hover .art { transform:scale(1.025); box-shadow:0 14px 30px rgba(0,0,0,.55); }
  .play-mark { position:absolute; right:10px; bottom:10px; display:grid; place-items:center; width:32px; height:32px; border-radius:50%; color:#09090b; background:#fff; opacity:0; transform:translateY(4px); transition:opacity .18s ease,transform .18s ease; font-size:.68rem; }
  .card-main:hover .play-mark,.card-main:focus-visible .play-mark { opacity:1; transform:none; }
  .card-copy { display:flex; min-width:0; flex-direction:column; padding:9px 2px 0; }
  .card-copy strong,.card-copy small,.copy strong,.copy small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .card-copy strong { font-size:.8rem; font-weight:650; }.card-copy small { margin-top:4px; color:#71717a; font-size:.7rem; }.on-album { color:#52525b; }
  .entity { cursor:pointer; transition:color .15s ease; }.entity:hover { color:#ededed; text-decoration:underline; }
  .add-button { position:absolute; top:8px; right:8px; display:grid; place-items:center; width:28px; height:28px; border:1px solid rgba(255,255,255,.12); border-radius:50%; color:#fff; background:rgba(0,0,0,.7); cursor:pointer; opacity:0; transition:opacity .18s ease,background .18s ease; }.track-card:hover .add-button,.track-card:focus-within .add-button { opacity:1; }.add-button:hover { background:#fff;color:#09090b; }
  .compact-card { display:flex; align-items:center; min-height:58px; border-bottom:1px solid rgba(255,255,255,.06); }.compact-card:last-child { border-bottom:0; }.compact-main { display:flex; align-items:center; gap:10px; min-width:0; padding:7px 0; }.compact-art { width:42px; height:42px; flex:0 0 auto; border-radius:8px; box-shadow:none; }.copy { display:flex; min-width:0; flex:1; flex-direction:column; }.copy strong { font-size:.75rem; font-weight:600; }.copy small { margin-top:3px; color:#71717a; font-size:.66rem; }.compact-card time { margin-left:8px; color:#71717a; font:500 .66rem ui-monospace,SFMono-Regular,monospace; font-variant-numeric:tabular-nums; }.rank { width:25px; color:#71717a; font:500 .68rem ui-monospace,SFMono-Regular,monospace; }.ranked .compact-main { padding-left:0; }.compact-card .add-button { position:static; flex:0 0 auto; opacity:1; background:transparent; }.compact-card .add-button:hover { color:#09090b; background:#fff; }
</style>