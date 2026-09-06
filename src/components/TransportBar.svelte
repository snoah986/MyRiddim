<script>
  import TrackContextMenu from './TrackContextMenu.svelte'

  export let track = null
  export let isPlaying = false
  export let currentTime = 0
  export let duration = 0
  export let volume = 1
  export let shuffle = false
  export let repeat = 'off'
  export let loading = false
  export let onPrevious = () => {}
  export let onToggle = () => {}
  export let onNext = () => {}
  export let onShuffle = () => {}
  export let onRepeat = () => {}
  export let onSeek = () => {}
  export let onVolume = () => {}
  export let onQueue = () => {}
  export let onTheatre = () => {}
  export let onPartyOpen = () => {}
  export let onSleepTimer = () => {}
  export let onPip = () => {}
  export let onPlayNext = () => {}
  export let onAddToQueue = () => {}
  export let onAddToPlaylist = () => {}
  export let onStartMix = () => {}

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
  const formatTime = seconds => {
    const total = Math.max(0, Math.round(Number(seconds) || 0))
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
  }
  let moreOpen = false
  let sleepChoice = 30
</script>

{#if track}
  <section class="transport" aria-label="Now playing">
    <div class="now-playing">
      <div class="now-art">{#if track.thumbnail}<img src={track.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}</div>
      <div class="now-copy"><strong>{clean(track.title)}</strong><span>{clean(track.artist)}</span></div>
      <TrackContextMenu track={track} up onPlayNext={onPlayNext} onAddToQueue={onAddToQueue} onAddToPlaylist={onAddToPlaylist} onStartMix={onStartMix} />
    </div>

    <div class="transport-center">
      <div class="transport-buttons">
        <button class:active={shuffle} class="icon-button" on:click={onShuffle} aria-label="Toggle shuffle" title="Shuffle"><svg viewBox="0 0 24 24"><path d="M4 4h4l12 16h-4M4 20h4l3.2-4.3M16 4h4v4M14.2 8.3 16 4"></path></svg></button>
        <button class="icon-button" on:click={onPrevious} aria-label="Previous track" title="Previous"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zM20 6l-10 6 10 6z"></path></svg></button>
        <button class="play-button" on:pointerdown|preventDefault={onToggle} aria-label={isPlaying ? 'Pause' : 'Play'}>{#if isPlaying}<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"></path></svg>{:else}<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"></path></svg>{/if}</button>
        <button class="icon-button" on:click={onNext} aria-label="Next track" title="Next"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M16 6h2v12h-2zM4 6l10 6-10 6z"></path></svg></button>
        <button class:active={repeat !== 'off'} class="icon-button" on:click={onRepeat} aria-label={`Repeat: ${repeat}`} title={`Repeat: ${repeat}`}><svg viewBox="0 0 24 24"><path d="m17 2 4 4-4 4M3 11V9a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v2a4 4 0 0 1-4 4H3"></path></svg>{#if repeat === 'one'}<b>1</b>{/if}</button>
      </div>
      <div class="scrubber"><span>{formatTime(currentTime)}</span><input aria-label="Seek" type="range" min="0" max={duration || 0} step=".1" value={currentTime} on:change={onSeek} /><span>{formatTime(duration)}</span></div>
    </div>

    <div class="transport-actions">
      <label class="volume" aria-label="Volume"><svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6l-5 4H4zm12.5-2a6 6 0 0 1 0 8M19 5a10 10 0 0 1 0 14"></path></svg><input type="range" min="0" max="1" step=".01" value={volume} on:change={onVolume} /></label>
      <button class="icon-button" on:click={onQueue} aria-label="Open playback queue" title="Queue"><svg viewBox="0 0 24 24"><path d="M4 6h12M4 12h16M4 18h9"></path></svg></button>
      <button class="icon-button" on:click={onTheatre} aria-label="Open Theatre Mode" title="Theatre Mode"><svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="3"></rect><path d="m9 9 5 3-5 3z"></path></svg></button>
      <button class="more-button" on:click={() => moreOpen = !moreOpen} aria-label="More player actions" aria-expanded={moreOpen} title="More actions">···</button>
      {#if moreOpen}<div class="more-menu" role="menu">
        <button role="menuitem" on:click={() => { moreOpen = false; onPartyOpen() }}>Party Mode</button>
        <button role="menuitem" on:click={() => { moreOpen = false; onAddToPlaylist(track) }}>Add to Playlist</button>
        <button role="menuitem" on:click={() => { sleepChoice = sleepChoice === 30 ? 60 : sleepChoice === 60 ? 0 : 30; onSleepTimer(sleepChoice); moreOpen = false }}>{sleepChoice ? `Sleep Timer · ${sleepChoice}m` : 'Sleep Timer'}</button>
      </div>{/if}
      <button class="icon-button" on:click={onPip} aria-label="Open mini player" title="Mini player"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="3"></rect><rect x="12" y="12" width="7" height="6" rx="1.5"></rect></svg></button>
      {#if loading}<span class="loading">Loading…</span>{/if}
    </div>
  </section>
{/if}

<style>
  .transport { position:fixed; left:0; right:0; bottom:0; z-index:30; display:flex; align-items:center; gap:22px; min-height:76px; padding:12px 28px; border-top:1px solid #ffffff12; color:#f2ece4; background:#0a0908; box-shadow:0 -16px 34px #0007; font-family:'Manrope',ui-sans-serif,sans-serif; }
  .now-playing { display:flex; align-items:center; gap:11px; width:220px; min-width:0; }.now-art { display:grid; place-items:center; width:46px; height:46px; flex:none; overflow:hidden; border-radius:12px; color:#f2ece4; background:#221a16; }.now-art img { width:100%; height:100%; object-fit:cover; }.now-copy { display:flex; min-width:0; flex:1; flex-direction:column; }.now-copy strong,.now-copy span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.now-copy strong { font-size:.8rem; }.now-copy span { margin-top:3px; color:#a99b8f; font-size:.68rem; }
  .transport-center { display:flex; flex:1; min-width:220px; flex-direction:column; align-items:center; gap:8px; }.transport-buttons { display:flex; align-items:center; gap:18px; }.icon-button,.play-button { position:relative; display:grid; place-items:center; border:0; color:#f2ece4; background:none; cursor:pointer; }.icon-button { width:22px; height:22px; padding:0; opacity:.72; transition:transform .4s cubic-bezier(.2,.8,.2,1),color .35s ease,opacity .35s ease; }.icon-button:hover,.icon-button.active { color:#f2ece4; opacity:1; transform:translateY(-2px); }.icon-button svg { width:19px; height:19px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }.icon-button[title^="Repeat"] svg { width:18px; }.icon-button b { position:absolute; right:-4px; bottom:-5px; color:#f2ece4; font:600 .55rem 'Manrope',sans-serif; }.play-button { width:38px; height:38px; border-radius:999px; color:#1b1008; background:#f2ece4; transition:transform .4s cubic-bezier(.2,.8,.2,1),box-shadow .35s ease; }.play-button:hover { transform:translateY(-2px) scale(1.06); box-shadow:0 8px 20px #f2ece455; }.play-button svg { width:15px; height:15px; }.scrubber { display:flex; align-items:center; gap:10px; width:min(100%,480px); color:#7a6d64; font-size:.66rem; font-variant-numeric:tabular-nums; }.scrubber span { width:32px; }.scrubber span:last-child { text-align:right; }.scrubber input { flex:1; min-width:0; accent-color:#f2ece4; }
  .transport-actions { position:relative; display:flex; align-items:center; justify-content:flex-end; gap:13px; width:270px; min-width:0; }.more-button { width:24px; height:24px; border:0; color:#a99b8f; background:transparent; cursor:pointer; font-size:1.05rem; letter-spacing:.12em; line-height:1; }.more-button:hover,.more-button[aria-expanded="true"] { color:#fff; }.more-menu { position:absolute; right:0; bottom:calc(100% + 10px); z-index:50; display:flex; min-width:170px; flex-direction:column; gap:2px; padding:6px; border:1px solid #ffffff1c; border-radius:10px; background:#17171bf2; box-shadow:0 18px 50px #0009; }.more-menu button { border:0; border-radius:7px; padding:9px 10px; color:#eee; background:transparent; text-align:left; cursor:pointer; font:inherit; font-size:.72rem; }.more-menu button:hover { background:#ffffff12; }
  .volume { display:flex; align-items:center; gap:6px; color:#a99b8f; }.volume svg { width:17px; height:17px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }.volume input { width:70px; accent-color:#f2ece4; }.loading {color:#f2ece4;font-size:.68rem; white-space:nowrap; }
  :global(.transport .context-trigger) { color:#a99b8f; }
  @media (max-width:800px) { .transport { left:8px; right:8px; bottom:8px; flex-wrap:wrap; gap:8px; padding:9px 12px; border-radius:22px; border:1px solid #ffffff12; }.now-playing { width:calc(100% - 50px); }.transport-center { order:3; width:100%; }.transport-actions { position:absolute; top:15px; right:12px; width:auto; }.volume { display:none; }.transport-actions .icon-button { display:none; }.transport-actions .icon-button:first-of-type { display:grid; }.transport-actions .loading { position:absolute; right:0; top:31px; } }
</style>
