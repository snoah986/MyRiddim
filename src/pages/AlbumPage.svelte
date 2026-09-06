<script>
  import { onMount, onDestroy } from 'svelte'
  import TrackContextMenu from '../components/TrackContextMenu.svelte'
  export let data = null
  export let track = null
  export let onPlay = () => {}
  export let onTrack = () => {}
  export let onOpenArtist = () => {}
  export let onPlayNext = () => {}
  export let onAddToQueue = () => {}
  export let onAddToPlaylist = () => {}
  export let onStartMix = () => {}
  export let onClose = () => {}
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
  const tracks = () => data?.tracks || []
  const formatDuration = seconds => {
    if (!Number.isFinite(seconds) || seconds <= 0) return ''
    const minutes = Math.floor(seconds / 60)
    return `${minutes}:${String(Math.round(seconds % 60)).padStart(2, '0')}`
  }
</script>

<svelte:window on:keydown={onKeydown} />
<div class="albumpage" role="dialog" aria-modal="true" aria-label={data?.title ?? 'Album'}>
  {#if contextTrack}<TrackContextMenu key={contextKey} track={contextTrack} positioned x={contextX} y={contextY} autoOpen onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} />{/if}
  <header class="topbar"><button class="icon-btn" on:click={onClose} aria-label="Back" title="Back (Esc)">←</button><div class="crumb">{clean(data?.type) || 'ALBUM'}</div><button class="exit" on:click={onClose} aria-label="Exit" title="Exit (Esc)">Exit</button></header>
  <div class="layout">
    <aside class="details"><div class="cover">{#if data?.thumbnail}<img src={data.thumbnail} referrerpolicy="no-referrer" alt="{clean(data.title)} artwork" />{:else}<span>♫</span>{/if}</div><h1>{clean(data?.title) || 'Album'}</h1>{#if data?.artist}<button class="artist" on:click={onOpenArtist}>{clean(data.artist)}</button>{/if}<p class="summary">{#if data?.year}<span class="count">{clean(data.year)}</span>{/if}<span>{data?.trackCount ?? tracks().length} songs</span>{#if data?.durationSeconds}<span>· {formatDuration(data.durationSeconds)}</span>{/if}</p>{#if tracks().length}<button class="play" on:click={() => onPlay(tracks())} aria-label="Play album">▶ <span>Play</span></button>{/if}</aside>
    <section class="tracks" aria-label="Album tracks"><div class="track-head"><span>#</span><span>Title</span><span>Artist</span><span>Time</span><span></span></div>{#each tracks() as t, i (t.videoId)}<div class="track" role="button" tabindex="0" class:active={track && track.videoId === t.videoId} on:click={() => onTrack(tracks(), i)} on:contextmenu={(event) => openContext(event, t)} on:keydown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onTrack(tracks(), i) } }}><span class="num">{track && track.videoId === t.videoId ? '♪' : i + 1}</span><span class="meta"><span class="title">{clean(t.title)}</span><span class="sub">{clean(t.album)}</span></span><span class="artist">{clean(t.artist) || '—'}</span><span class="dur">{t.duration || '—'}</span><TrackContextMenu track={t} onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} /></div>{/each}</section>
  </div>
</div>

<style>
.albumpage{position:fixed;inset:0;z-index:10;display:flex;flex-direction:column;overflow:hidden;padding:22px 42px;color:#f4f4f5;background:radial-gradient(ellipse at 18% 18%,#302843 0%,transparent 38%),radial-gradient(ellipse at 88% 100%,#1f3034 0%,transparent 42%),#09090b;font-family:Inter,ui-sans-serif,system-ui,sans-serif}.topbar{display:flex;align-items:center;gap:18px;flex:0 0 auto;padding:0 0 18px;border-bottom:1px solid #ffffff14}.icon-btn,.exit{color:#f4f4f5;background:#ffffff0b;border:1px solid #ffffff29;border-radius:10px;cursor:pointer;transition:.2s;backdrop-filter:blur(20px)}.icon-btn{width:42px;height:42px;font-size:1.25rem}.exit{padding:9px 19px}.icon-btn:hover,.exit:hover{background:#ffffff1f}.crumb{flex:1;color:#a1a1aa;font-size:.7rem;font-weight:700;letter-spacing:.17em}.layout{display:grid;grid-template-columns:minmax(240px,30%) 1fr;gap:clamp(28px,5vw,70px);min-height:0;flex:1;margin:28px auto 0;width:min(1240px,100%)}.details{padding:10px 0;align-self:start}.cover{width:min(100%,310px);aspect-ratio:1;display:grid;place-items:center;border-radius:18px;overflow:hidden;background:linear-gradient(135deg,#252331,#4d3640);box-shadow:0 24px 70px #0007}.cover img{width:100%;height:100%;object-fit:cover}.cover span{color:#fff;font-size:8rem}h1{margin:14px 0 6px;color:#fafafa;font-size:clamp(1.75rem,4vw,3.2rem);line-height:1.04;font-family:'Outfit',Inter,ui-sans-serif,sans-serif}.artist{border:0;background:none;padding:0;color:var(--accent,#c4b5fd);cursor:pointer;font:inherit;font-size:.95rem;font-weight:600}.artist:hover{text-decoration:underline}.summary{margin:10px 0 22px;color:#a1a1aa;font-size:.9rem}.summary span{margin-right:12px}.summary .count{color:#e4e4e7;font-weight:600}.play{border:0;cursor:pointer;padding:11px 20px;border-radius:22px;color:#161616;background:#fafafa;font-weight:700;transition:.2s}.play:hover{transform:translateY(-1px);box-shadow:0 8px 24px #0009}.tracks{min-height:0;overflow:auto;padding:3px 7px 20px 0;scrollbar-color:#45454f transparent}.track-head,.track{display:grid;grid-template-columns:38px minmax(160px,1.6fr) minmax(130px,1fr) 58px 44px;gap:14px;align-items:center}.track-head{padding:12px 14px;border-bottom:1px solid #ffffff1a;color:#71717a;font-size:.68rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase}.track{width:100%;box-sizing:border-box;padding:13px 14px;border:0;border-radius:10px;color:#e4e4e7;background:transparent;text-align:left;font:inherit;cursor:pointer}.track:nth-child(odd){background:#ffffff05}.track:hover{background:#ffffff12}.track.active{background:#ab8bff29}.num{color:#71717a;font-variant-numeric:tabular-nums}.meta{display:flex;min-width:0;flex-direction:column}.title{overflow:hidden;color:#f4f4f5;font-size:.94rem;font-weight:600;text-overflow:ellipsis;white-space:nowrap}.sub{overflow:hidden;color:#71717a;font-size:.76rem;text-overflow:ellipsis;white-space:nowrap}.artist,.dur{color:#a1a1aa;font-size:.83rem}.dur{text-align:right;font-variant-numeric:tabular-nums}@media(max-width:720px){.albumpage{padding:16px}.layout{display:block;overflow:auto;margin-top:18px}.details{padding:0 0 22px}.cover{width:150px}.tracks{overflow:visible}.track-head,.track{grid-template-columns:28px minmax(140px,1fr) 58px 44px}.track-head span:nth-child(3){display:block}}
</style>