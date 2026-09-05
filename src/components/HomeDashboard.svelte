<script>
  export let currentTrack = null
  export let quickPicks = []
  export let upNext = []
  export let playlists = []
  export let heavyRotation = []
  export let currentTime = 0
  export let duration = 0
  export let isPlaying = false
  export let loading = false
  export let volume = 1
  export let onPlayQueue = () => {}
  export let onToggle = () => {}
  export let onOpenPlaylist = () => {}
  export let onOpenQueue = () => {}
  export let onOpenTheatre = () => {}
  export let onCreatePlaylist = () => {}

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const trackTitle = item => clean(item?.title || item?.name) || 'Untitled'
  const trackArtist = item => clean(item?.artist || item?.artists?.[0]?.name || item?.artists?.[0]) || 'Various Artists'
  const durationValue = item => item?.duration ?? item?.duration_seconds ?? item?.length
  const asSeconds = value => {
    if (typeof value === 'number' && Number.isFinite(value)) return value
    const raw = String(value ?? '').trim()
    if (!raw) return 0
    const parts = raw.split(':').map(Number)
    if (parts.length > 1 && parts.every(Number.isFinite)) {
      return parts.reduce((total, part) => total * 60 + part, 0)
    }
    const seconds = Number(raw)
    return Number.isFinite(seconds) ? seconds : 0
  }
  const formatTime = value => {
    const seconds = Math.max(0, Math.round(asSeconds(value)))
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
  }
  const optionalTime = value => asSeconds(value) > 0 ? formatTime(value) : ''
  const formatQueue = items => formatTime(items.reduce((sum, item) => sum + asSeconds(durationValue(item)), 0))
  const trackKey = item => item?.videoId || item?.id || item?.browseId
  const playedAt = item => item?.playedAt || item?.played_at || item?.lastPlayed || item?.last_played || item?.timestamp
  const relativePlayed = item => {
    const raw = playedAt(item)
    if (!raw) return `${Number(item?.count || item?.plays || 0)} plays this week`
    const timestamp = typeof raw === 'number' && raw < 10000000000 ? raw * 1000 : new Date(raw).getTime()
    if (!Number.isFinite(timestamp)) return `${Number(item?.count || item?.plays || 0)} plays this week`
    const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000))
    if (minutes < 1) return 'Played just now'
    if (minutes < 60) return `Played ${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `Played ${hours}h ago`
    return `Played ${Math.floor(hours / 24)}d ago`
  }
  const playlistCount = item => item?.count ?? item?.trackCount ?? item?.track_count ?? item?.songCount ?? item?.song_count
  const launcherContext = item => item.launchType === 'playlist'
    ? `${playlistCount(item) ?? 0} tracks · ${clean(item.type || 'playlist')}`
    : relativePlayed(item)

  $: active = currentTrack || quickPicks[0] || null
  $: nextTracks = upNext.slice(0, 3)
  $: pins = playlists.filter(item => item?.id).slice(0, 3)
  $: velocity = (heavyRotation.length ? heavyRotation : quickPicks).slice(0, 3)
  $: launchers = [
    ...pins.map(item => ({ ...item, launchType: 'playlist', launchLabel: 'Pinned' })),
    ...velocity.map(item => ({ ...item, launchType: 'track', launchLabel: 'Velocity' })),
  ]
  $: progress = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0

  function play(item, index = 0) {
    if (item?.launchType === 'playlist') onOpenPlaylist(item)
    else if (item) onPlayQueue([item], index)
  }
</script>

<section class="dashboard" aria-labelledby="dashboard-title">
  <header class="dashboard-head"><div><p class="eyebrow">STUDIO DASHBOARD</p><h1 id="dashboard-title">Home</h1><p class="subtitle">Your listening surface, tuned to the room.</p></div><div class="head-actions"><button on:click={onCreatePlaylist}>+ Playlist</button><button on:click={onOpenQueue}>Queue <span>{upNext.length}</span></button></div></header>

  <section class="session-grid" aria-label="Live session monitor">
    <article class="session-deck">
      <div class="session-art">{#if active?.thumbnail}<img src={active.thumbnail} referrerpolicy="no-referrer" alt="{trackTitle(active)} artwork" />{:else}<span>♫</span>{/if}<span class="live-mark" class:active={isPlaying}>{isPlaying ? 'LIVE' : 'READY'}</span></div>
      <div class="session-copy"><p class="eyebrow">ACTIVE SESSION</p><h2>{trackTitle(active) === 'Untitled' && !active ? 'Nothing playing' : trackTitle(active)}</h2><p class="artist">{active ? trackArtist(active) : 'Select a track to start your session'}</p>{#if active?.album}<p class="album">{clean(active.album)}</p>{/if}<div class="progress"><span style={`width:${progress}%`}></span></div><div class="timecode"><span>{formatTime(currentTime)}</span><span>{formatTime(duration || durationValue(active))}</span></div></div>
      <div class="session-actions"><button class="play-toggle" on:click={onToggle} disabled={!active} aria-label={isPlaying ? 'Pause active track' : 'Play active track'}>{isPlaying ? 'Ⅱ' : '▶'}</button><button class="stage-button" on:click={onOpenTheatre} disabled={!active}>Stage</button></div>
    </article>
    <aside class="up-next"><div class="section-label"><h2>Up next</h2><span>PEEK ONLY</span></div>{#if nextTracks.length}<div class="next-list">{#each nextTracks as item, index (trackKey(item) || index)}<div class="next-item"><span class="next-number">{String(index + 1).padStart(2, '0')}</span><span class="next-art">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span class="next-copy"><strong>{trackTitle(item)}</strong><small>{trackArtist(item)}</small></span>{#if optionalTime(durationValue(item))}<time>{optionalTime(durationValue(item))}</time>{/if}</div>{/each}</div>{:else}<p class="empty">Your next tracks will appear here.</p>{/if}</aside>
  </section>

  <section class="launch-section" aria-labelledby="launch-title"><div class="section-label"><div><p class="eyebrow">QUICK LAUNCH</p><h2 id="launch-title">Your signal board</h2></div><span>{launchers.length}/6 TILES</span></div>{#if launchers.length}<div class="launcher-grid">{#each launchers as item, index (trackKey(item) || index)}<button class="launcher" class:pinned={item.launchType === 'playlist'} on:click={() => play(item)} aria-label={`${item.launchType === 'playlist' ? 'Open' : 'Play'} ${trackTitle(item)}`}><span class="launcher-art">{#if item.thumbnail}<img src={item.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span class="launcher-copy"><small>{item.launchType === 'playlist' ? 'PINNED' : '7-DAY VELOCITY'}</small><strong>{trackTitle(item)}</strong><span>{launcherContext(item)}</span></span>{#if item.launchType === 'playlist'}<span class="pin" aria-label="Pinned">⌖</span>{/if}<span class="launcher-index">{String(index + 1).padStart(2, '0')}</span></button>{/each}{#each Array(Math.max(0, 6 - launchers.length)) as _, index}<button class="launcher empty-launcher" on:click={onCreatePlaylist} aria-label="Create a quick launch tile"><span class="empty-plus">＋</span><span><small>OPEN SLOT</small><strong>Create a collection</strong></span></button>{/each}</div>{:else}<div class="empty-board"><p>No launch data yet.</p><button on:click={onCreatePlaylist}>Create a playlist</button></div>{/if}</section>

  <footer class="hardware-strip" aria-label="Hardware status"><div><span class="status-dot"></span><strong>ENGINE ONLINE</strong></div><span class="mono">{active ? 'AAC / HIGH' : 'IDLE / —'}</span><span class="mono">QUEUE {formatQueue(upNext)}</span><span class="mono">VOL {Math.round(volume * 100)}%</span><div class="hardware-actions"><button on:click={onOpenQueue}>Manage queue</button><button on:click={onOpenTheatre}>Open stage</button>{#if loading}<span class="loading">BUFFERING</span>{/if}</div></footer>
</section>

<style>
  .dashboard{height:100%;min-height:0;box-sizing:border-box;display:grid;grid-template-rows:auto minmax(190px,40%) minmax(200px,45%) auto;gap:14px;padding:24px clamp(18px,3vw,42px) 14px;color:#ededed;background:#000;font-family:Inter,ui-sans-serif,system-ui,sans-serif;overflow:hidden}.dashboard-head,.section-label{display:flex;align-items:flex-end;justify-content:space-between;gap:16px}.dashboard-head{min-height:46px}.eyebrow{margin:0 0 6px;color:#71717a;font:600 .61rem ui-monospace,SFMono-Regular,monospace;letter-spacing:.15em}.dashboard h1{margin:0;font-size:clamp(1.8rem,3vw,2.5rem);letter-spacing:-.06em}.subtitle,.section-label p{margin:5px 0 0;color:#71717a;font-size:.73rem}.head-actions{display:flex;gap:6px}.head-actions button,.hardware-actions button,.empty-board button{border:1px solid rgba(255,255,255,.1);border-radius:7px;padding:7px 10px;color:#a1a1aa;background:#08080a;cursor:pointer;font:600 .66rem Inter,sans-serif}.head-actions button:hover,.hardware-actions button:hover,.empty-board button:hover{color:#ededed;border-color:rgba(255,255,255,.28)}.head-actions span{margin-left:3px;color:#71717a;font:500 .6rem ui-monospace,monospace}.session-grid{display:grid;grid-template-columns:3fr 2fr;gap:10px;min-height:0}.session-deck,.up-next,.launch-section{border:1px solid rgba(255,255,255,.07);background:#050507}.session-deck{position:relative;display:grid;grid-template-columns:minmax(150px,34%) 1fr auto;align-items:center;gap:18px;min-width:0;padding:16px}.session-art{position:relative;display:grid;place-items:center;aspect-ratio:1;max-height:calc(100% - 4px);overflow:hidden;border:1px solid rgba(255,255,255,.08);border-radius:10px;color:#71717a;background:#111113;font-size:2.5rem}.session-art img{width:100%;height:100%;object-fit:cover}.live-mark{position:absolute;left:8px;top:8px;padding:4px 6px;border:1px solid rgba(255,255,255,.2);border-radius:4px;color:#a1a1aa;background:#000c;font:600 .54rem ui-monospace,monospace;letter-spacing:.08em}.live-mark.active{color:#ededed;border-color:#ededed}.session-copy{min-width:0}.session-copy h2{margin:5px 0 4px;overflow:hidden;font-size:clamp(1rem,2vw,1.7rem);letter-spacing:-.045em;text-overflow:ellipsis;white-space:nowrap}.artist{margin:0;overflow:hidden;color:#a1a1aa;font-size:.78rem;text-overflow:ellipsis;white-space:nowrap}.album{margin:5px 0 0;color:#52525b;font-size:.68rem}.progress{height:2px;margin-top:18px;background:#27272a}.progress span{display:block;height:100%;background:#ededed;transition:width .18s linear}.timecode{display:flex;justify-content:space-between;margin-top:6px;color:#71717a;font:500 .59rem ui-monospace,SFMono-Regular,monospace;font-variant-numeric:tabular-nums}.session-actions{display:flex;flex-direction:column;align-items:center;gap:9px}.play-toggle{display:grid;place-items:center;width:46px;height:46px;border:1px solid #ededed;border-radius:50%;color:#09090b;background:#ededed;cursor:pointer;font-size:.9rem}.play-toggle:hover{background:#fff}.play-toggle:disabled,.stage-button:disabled{opacity:.3;cursor:not-allowed}.stage-button{border:1px solid rgba(255,255,255,.14);border-radius:6px;padding:5px 8px;color:#a1a1aa;background:transparent;cursor:pointer;font:600 .59rem Inter,sans-serif}.stage-button:hover{color:#ededed;border-color:#ededed}.up-next{min-width:0;padding:15px;overflow:hidden}.section-label h2{margin:0;font-size:.85rem;letter-spacing:-.025em}.section-label>span{color:#52525b;font:500 .56rem ui-monospace,monospace;letter-spacing:.1em}.next-list{margin-top:10px}.next-item{display:flex;align-items:center;gap:8px;min-width:0;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05)}.next-item:last-child{border:0}.next-number{width:20px;color:#52525b;font:500 .6rem ui-monospace,monospace}.next-art{width:34px;height:34px;flex:0 0 auto;overflow:hidden;border-radius:6px;background:#111113}.next-art img{width:100%;height:100%;object-fit:cover}.next-copy{display:flex;min-width:0;flex:1;flex-direction:column}.next-copy strong,.next-copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.next-copy strong{font-size:.69rem}.next-copy small{margin-top:3px;color:#71717a;font-size:.61rem}.next-item time{color:#71717a;font:500 .6rem ui-monospace,monospace;font-variant-numeric:tabular-nums}.empty{color:#52525b;font-size:.7rem}.launch-section{min-height:0;padding:15px;overflow:hidden}.launcher-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:8px;height:calc(100% - 36px);margin-top:11px}.launcher{position:relative;display:flex;align-items:center;gap:10px;min-width:0;padding:9px;border:1px solid rgba(255,255,255,.07);border-radius:9px;color:#ededed;background:#08080a;text-align:left;cursor:pointer;overflow:hidden;transition:border-color .16s ease,background .16s ease,transform .16s ease}.launcher:hover{border-color:rgba(255,255,255,.28);background:#101014;transform:translateY(-1px)}.launcher-art{width:60px;height:60px;flex:0 0 auto;display:grid;place-items:center;overflow:hidden;border-radius:8px;border:1px solid rgba(255,255,255,.08);background:#151518;color:#71717a}.launcher-art img{width:100%;height:100%;object-fit:cover}.launcher-copy{display:flex;min-width:0;flex:1;flex-direction:column}.launcher-copy small{color:#71717a;font:600 .52rem ui-monospace,monospace;letter-spacing:.08em}.launcher-copy strong,.launcher-copy span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.launcher-copy strong{margin:4px 0 2px;font-size:.75rem}.launcher-copy>span{color:#71717a;font-size:.63rem}.pin{position:absolute;right:9px;top:7px;color:#ededed;font-size:.7rem}.launcher-index{position:absolute;right:9px;bottom:7px;color:#3f3f46;font:500 .56rem ui-monospace,monospace}.empty-launcher{justify-content:center}.empty-launcher .empty-plus{font-size:1.5rem;color:#52525b}.empty-launcher span:last-child{display:flex;flex-direction:column;gap:4px}.empty-launcher small{color:#52525b;font:600 .52rem ui-monospace,monospace}.empty-launcher strong{font-size:.7rem;font-weight:500}.empty-board{display:grid;place-items:center;height:calc(100% - 30px);color:#71717a;font-size:.72rem}.empty-board button{margin-left:8px}.hardware-strip{display:flex;align-items:center;gap:18px;min-height:28px;padding-top:9px;border-top:1px solid rgba(255,255,255,.1);color:#71717a;font:500 .59rem ui-monospace,SFMono-Regular,monospace;letter-spacing:.03em}.hardware-strip>div:first-child{display:flex;align-items:center;gap:6px;color:#a1a1aa}.status-dot{width:6px;height:6px;border-radius:50%;background:#ededed}.mono{font-variant-numeric:tabular-nums}.hardware-actions{display:flex;align-items:center;gap:6px;margin-left:auto}.hardware-actions button{padding:5px 7px;font:500 .58rem ui-monospace,monospace}.loading{color:#ededed;letter-spacing:.1em}@media(max-width:850px){.dashboard{height:auto;min-height:100%;overflow:visible}.session-grid{grid-template-columns:1fr}.up-next{min-height:150px}.launch-section{min-height:350px}.launcher-grid{height:300px}}@media(max-width:560px){.dashboard{padding:20px 14px 24px}.dashboard-head{align-items:flex-start;flex-direction:column}.head-actions{width:100%}.head-actions button{flex:1}.session-deck{grid-template-columns:92px 1fr;gap:12px}.session-art{width:92px}.session-actions{position:absolute;right:12px;top:12px}.session-copy{padding-right:42px}.launcher-grid{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(3,minmax(0,1fr));height:380px}.hardware-strip{flex-wrap:wrap;gap:9px}.hardware-actions{width:100%;margin-left:0}}
</style>