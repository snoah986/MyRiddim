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
  $: duration = formatDuration(track?.duration ?? track?.length ?? track?.duration_seconds)

  function formatDuration(value) {
    if (typeof value === 'string' && value.includes(':')) return value
    const seconds = Number(value)
    if (!Number.isFinite(seconds) || seconds <= 0) return ''
    return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
  }

  function play(event) {
    event?.stopPropagation()
    if (track) onPlay(track)
  }

  function handleCardKeydown(event) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      play(event)
    }
  }

  function openArtist(event, artist) {
    event.stopPropagation()
    onOpenArtist(artist?.id || null, artist?.name || '')
  }

  function openAlbum(event) {
    event.stopPropagation()
    onOpenAlbum(album?.id || null, album?.name || '', track?.artist || '')
  }
</script>

<article
  class:compact-card={compact}
  class:track-card={!compact}
  class:ranked={rank !== null}
  class="card-shell"
  role="button"
  tabindex="0"
  on:click={play}
  on:keydown={handleCardKeydown}
  aria-label="Play {title}"
>
  {#if rank !== null}<span class="rank">{String(rank).padStart(2, '0')}</span>{/if}
  <div class="card-main">
    <span class:compact-art={compact} class="art">
      {#if track?.thumbnail}<img src={track.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}
      {#if !compact}<span class="play-mark" aria-hidden="true">▶</span>{/if}
    </span>
    <span class:compact-copy={compact} class="card-copy">
      <strong>{title}</strong>
      <span class="metadata">
        {#each artists as artist, index}
          {#if index}<span class="separator">, </span>{/if}
          <button class="entity" type="button" on:click={(event) => openArtist(event, artist)}>{clean(artist.name)}</button>
        {/each}
        {#if album}<span class="separator"> · </span><button class="entity album-link" type="button" on:click={openAlbum}>{clean(album.name)}</button>{/if}
      </span>
    </span>
    {#if duration}<time>{duration}</time>{/if}
  </div>
  {#if onAdd}<button class="add-button" type="button" on:click|stopPropagation={() => onAdd(track)} aria-label="Add {title} to queue">＋</button>{/if}
</article>

<style>
  .card-shell { position:relative; min-width:0; color:#ededed; cursor:pointer; }
  .card-shell:focus-visible { outline:2px solid #fff; outline-offset:4px; }
  .card-shell:hover { filter:brightness(1.1); }
  .card-main { display:flex; align-items:center; gap:10px; min-width:0; }
  .track-card .card-main { display:block; }
  .art { position:relative; display:grid; place-items:center; aspect-ratio:1; overflow:hidden; border:1px solid rgba(255,255,255,.08); border-radius:12px; background:#111113; box-shadow:0 8px 24px rgba(0,0,0,.42); transition:transform .2s ease,box-shadow .2s ease; }
  .track-card .art { width:100%; }
  .compact-art { width:42px; height:42px; flex:0 0 auto; border-radius:8px; box-shadow:none; }
  .art img { display:block; width:100%; height:100%; object-fit:cover; }
  .track-card:hover .art { transform:scale(1.025); box-shadow:0 14px 30px rgba(0,0,0,.55); }
  .play-mark { position:absolute; right:10px; bottom:10px; display:grid; place-items:center; width:32px; height:32px; border-radius:50%; color:#09090b; background:#fff; opacity:0; transform:translateY(4px); transition:opacity .18s ease,transform .18s ease; font-size:.68rem; }
  .track-card:hover .play-mark,.track-card:focus-visible .play-mark { opacity:1; transform:none; }
  .card-copy { display:flex; min-width:0; flex:1; flex-direction:column; padding:9px 2px 0; }
  .compact-copy { padding:0; }
  .card-copy strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:.8rem; font-weight:650; }
  .compact-copy strong { font-size:.75rem; }
  .metadata { display:block; min-width:0; margin-top:4px; overflow:hidden; color:#71717a; font-size:.68rem; text-overflow:ellipsis; white-space:nowrap; }
  .entity { max-width:100%; overflow:hidden; border:0; padding:0; color:inherit; background:transparent; cursor:pointer; font:inherit; text-overflow:ellipsis; white-space:nowrap; }
  .entity:hover { color:#ededed; text-decoration:underline; }
  .separator { color:#52525b; }
  .card-main > time { margin-left:auto; color:#71717a; font:500 .66rem ui-monospace,SFMono-Regular,monospace; font-variant-numeric:tabular-nums; }
  .add-button { position:absolute; top:8px; right:8px; display:grid; place-items:center; width:28px; height:28px; border:1px solid rgba(255,255,255,.12); border-radius:50%; color:#fff; background:rgba(0,0,0,.7); cursor:pointer; opacity:0; transition:opacity .18s ease,background .18s ease; }
  .card-shell:hover .add-button,.card-shell:focus-within .add-button { opacity:1; }
  .add-button:hover { color:#09090b; background:#fff; }
  .compact-card { display:block; min-height:58px; border-bottom:1px solid rgba(255,255,255,.06); }
  .compact-card .card-main { padding:7px 0; }
  .compact-card .add-button { position:absolute; top:14px; right:0; opacity:1; background:transparent; }
  .rank { display:inline-block; width:25px; margin-right:7px; color:#71717a; font:500 .68rem ui-monospace,SFMono-Regular,monospace; }
</style>
