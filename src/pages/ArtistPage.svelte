<script>
  import { onMount, onDestroy } from 'svelte'
  import TrackContextMenu from '../components/TrackContextMenu.svelte'
  export let data = null
  export let track = null
  export let onPlay = () => {}
  export let onTrack = () => {}
  export let onOpenAlbum = () => {}
  export let onPlayNext = () => {}
  export let onAddToQueue = () => {}
  export let onAddToPlaylist = () => {}
  export let onStartMix = () => {}
  export let onClose = () => {}
  export let favorite = false
  export let onToggleFavorite = () => {}
  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  function onKeydown(event) { if (event.key === 'Escape') { event.preventDefault(); onClose() } }
  onMount(() => window.addEventListener('keydown', onKeydown))
  onDestroy(() => window.removeEventListener('keydown', onKeydown))
  let contextTrack = null
  let contextX = 0
  let contextY = 0
  let contextKey = 0
  function openContext(event, item) {
    event.preventDefault()
    event.stopPropagation()
    contextTrack = item
    contextX = event.clientX
    contextY = event.clientY
    contextKey += 1
  }
  const songs = () => data?.songs || []
  const albums = () => data?.albums || []
  const singles = () => data?.singles || []
</script>

<svelte:window on:keydown={onKeydown} />
<div class="artistpage" role="dialog" aria-modal="true" aria-label={data?.name ?? 'Artist'}>
  {#if contextTrack}<TrackContextMenu key={contextKey} track={contextTrack} entityType="track" positioned x={contextX} y={contextY} autoOpen onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} />{/if}
  <header class="topbar"><button class="icon-btn" on:click={onClose} aria-label="Back" title="Back (Esc)">←</button><div class="crumb">ARTIST</div><button class="fav-btn" class:active={favorite} on:click={onToggleFavorite} aria-label={favorite ? 'Remove from favorite artists' : 'Add to favorite artists'} title={favorite ? 'Remove from favorite artists' : 'Add to favorite artists'}>{favorite ? '♥' : '♡'}<span>{favorite ? 'Saved' : 'Save'}</span></button><button class="exit" on:click={onClose} aria-label="Exit" title="Exit (Esc)">Exit</button></header>
  <div class="layout">
    <aside class="details"><div class="cover">{#if data?.thumbnail}<img src={data.thumbnail} referrerpolicy="no-referrer" alt="{clean(data.name)} artwork" />{:else}<span>♫</span>{/if}</div><h1>{clean(data?.name) || 'Artist'}</h1><p class="summary">{#if data?.subscribers}<span class="count">{clean(data.subscribers)}</span>{/if}{#if data?.views}<span class="count">{clean(data.views)} views</span>{/if}</p>{#if songs().length}<button class="play" on:click={() => onPlay(songs())} aria-label="Play popular songs">▶ <span>Play</span></button>{/if}</aside>
    <section class="content" aria-label="Artist content">
      {#if songs().length}<section class="block"><h2>Popular</h2><div class="song-list">{#each songs() as t, i (t.videoId || i)}<div class="song-row" on:contextmenu|preventDefault|stopPropagation={(event) => openContext(event, t)}><button class="song-main" on:click={() => onTrack(songs(), i)}><span class="num">{track?.videoId === t.videoId ? '♪' : i + 1}</span><span class="song-art">{#if t.thumbnail}<img src={t.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</span><span class="song-meta"><strong>{clean(t.title)}</strong><small>{clean(t.artist)}</small></span><span class="song-dur">{t.duration || '—'}</span><span class="song-play">▶</span></button><TrackContextMenu track={t} onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} /></div>{/each}</div></section>{/if}
      {#if albums().length}<section class="block"><h2>Albums</h2><div class="card-row">{#each albums() as a (a.browseId)}<button class="release" on:click={() => onOpenAlbum(a.browseId)}><div class="card-art">{#if a.thumbnail}<img src={a.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</div><strong>{clean(a.title)}</strong><span>{clean(a.year) || clean(a.type) || 'Album'}</span></button>{/each}</div></section>{/if}
      {#if singles().length}<section class="block"><h2>Singles</h2><div class="card-row">{#each singles() as a (a.browseId)}<button class="release" on:click={() => onOpenAlbum(a.browseId)}><div class="card-art">{#if a.thumbnail}<img src={a.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</div><strong>{clean(a.title)}</strong><span>{clean(a.year) || clean(a.type) || 'Single'}</span></button>{/each}</div></section>{/if}
    </section>
  </div>
</div>

<style>
.artistpage{position:fixed;inset:0;z-index:10;display:flex;flex-direction:column;overflow:hidden;padding:22px 42px;color:#f4f4f5;background:radial-gradient(ellipse at 18% 18%,#302843 0%,transparent 38%),radial-gradient(ellipse at 88% 100%,#1f3034 0%,transparent 42%),#09090b;font-family:Inter,ui-sans-serif,system-ui,sans-serif}.topbar{display:flex;align-items:center;gap:18px;flex:0 0 auto;padding:0 0 18px;border-bottom:1px solid #ffffff14}.icon-btn,.exit,.fav-btn{color:#f4f4f5;background:#ffffff0b;border:1px solid #ffffff29;border-radius:10px;cursor:pointer;transition:.2s;backdrop-filter:blur(20px)}.fav-btn{display:flex;align-items:center;gap:7px;padding:9px 15px;font-weight:600}.fav-btn span{font-size:.8rem}.fav-btn.active{color:#ffd7e2;border-color:#f472b640;background:#f472b61a}.icon-btn{width:42px;height:42px;font-size:1.25rem}.exit{padding:9px 19px}.icon-btn:hover,.exit:hover{background:#ffffff1f}.crumb{flex:1;color:#a1a1aa;font-size:.7rem;font-weight:700;letter-spacing:.17em}.layout{display:grid;grid-template-columns:minmax(240px,30%) 1fr;gap:clamp(28px,5vw,70px);min-height:0;flex:1;margin:28px auto 0;width:min(1240px,100%)}.details{padding:10px 0;align-self:start}.cover{width:min(100%,310px);aspect-ratio:1;display:grid;place-items:center;border-radius:18px;overflow:hidden;background:linear-gradient(135deg,#252331,#4d3640);box-shadow:0 24px 70px #0007}.cover img{width:100%;height:100%;object-fit:cover}.cover span{color:#fff;font-size:8rem}h1{margin:14px 0 0;color:#fafafa;font-size:clamp(1.75rem,4vw,3.2rem);line-height:1.04;font-family:'Outfit',Inter,ui-sans-serif,sans-serif}.summary{margin:10px 0 22px;color:#a1a1aa;font-size:.9rem}.summary .count{margin-right:12px;color:#e4e4e7;font-weight:600}.play{border:0;cursor:pointer;padding:11px 20px;border-radius:22px;color:#161616;background:#fafafa;font-weight:700;transition:.2s}.play:hover{transform:translateY(-1px);box-shadow:0 8px 24px #0009}.content{min-height:0;overflow:auto;padding:3px 7px 20px 0;scrollbar-color:#45454f transparent}.block{margin-bottom:30px}.block h2{margin:0 0 12px;font-family:'Outfit',Inter,ui-sans-serif,sans-serif;font-size:1.3rem;letter-spacing:-.01em}.song-list{border:1px solid #ffffff10;border-radius:14px;overflow:hidden;background:#ffffff06}.song-row{display:flex;align-items:center;gap:6px;padding-right:8px}.song-row:hover{background:#ffffff0d}.song-main{display:flex;align-items:center;gap:12px;flex:1;min-width:0;border:0;padding:9px 12px;color:#eee;background:none;text-align:left;cursor:pointer}.num{width:22px;flex:0 0 auto;color:#71717a;font-variant-numeric:tabular-nums;font-size:.8rem;text-align:center}.song-art{width:40px;height:40px;flex:0 0 auto;display:grid;place-items:center;overflow:hidden;border-radius:8px;background:linear-gradient(135deg,#252331,#4d3640);font-size:1rem}.song-art img{width:100%;height:100%;object-fit:cover}.song-meta{min-width:0;flex:1;display:flex;flex-direction:column}.song-meta strong,.song-meta small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.song-meta strong{font-size:.9rem}.song-meta small{color:#a1a1aa;font-size:.78rem;margin-top:3px}.song-dur{color:#71717a;font-size:.8rem;font-variant-numeric:tabular-nums}.song-play{color:#a1a1aa;font-size:.8rem;margin:0 6px}.song-row:hover .song-play{color:var(--accent,#c4b5fd)}.card-row{display:flex;gap:16px;overflow-x:auto;padding:3px 4px 12px;scrollbar-width:none;-ms-overflow-style:none}.card-row::-webkit-scrollbar{display:none}.release{flex:0 0 150px;border:0;padding:0;color:#eee;background:none;text-align:left;cursor:pointer;transition:transform .2s ease}.release:hover{transform:translateY(-3px)}.card-art{aspect-ratio:1;display:grid;place-items:center;overflow:hidden;border-radius:14px;background:linear-gradient(135deg,#252331,#4d3640);font-size:2.5rem;margin-bottom:9px;transition:.2s}.release:hover .card-art{transform:scale(1.03);box-shadow:0 12px 30px #0009}.card-art img{width:100%;height:100%;object-fit:cover}.release strong,.release>span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.release strong{font-size:.86rem}.release>span{color:#a1a1aa;font-size:.76rem;margin-top:3px}@media(max-width:720px){.artistpage{padding:16px}.layout{display:block;overflow:auto;margin-top:18px}.details{padding:0 0 22px}.cover{width:150px}.content{overflow:visible}}
</style>