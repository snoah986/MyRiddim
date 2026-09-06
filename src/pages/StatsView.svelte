<script>
  import { onMount } from 'svelte'
  import { apiFetch } from '../lib/api.js'

  export let onPlayTrack = () => {}
  export let onPlayTracks = tracks => onPlayTrack(tracks?.[0])
  export let onStartMix = () => {}
  export let onSavePlaylist = async () => {}

  const ranges = [
    { value: '7', label: '7 days' },
    { value: '30', label: '30 days' },
    { value: '180', label: '6 months' },
    { value: 'all', label: 'All time' },
  ]
  const empty = {
    range: '30',
    metrics: { totalSeconds: 0, totalTracks: 0, uniqueArtists: 0 },
    recap: { obsession: null, clockDensity: null, heavyweight: null, marathon: null },
    leaderboards: { tracks: [], artists: [], albums: [] },
  }

  let range = '30'
  let data = empty
  let activeBoard = 'tracks'
  let loading = true
  let error = ''
  let gemsLoading = false
  let saveLoading = false
  let toast = ''
  let controller

  $: rows = data.leaderboards?.[activeBoard] || []
  $: totalHours = ((Number(data.metrics?.totalSeconds) || 0) / 3600).toFixed(1)
  $: boardLabel = activeBoard[0].toUpperCase() + activeBoard.slice(1)

  const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim()
  const formatTime = seconds => {
    const total = Math.max(0, Math.round(Number(seconds) || 0))
    if (total >= 3600) return `${(total / 3600).toFixed(1)}h`
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
  }
  const formatHours = seconds => {
    const total = Number(seconds) || 0
    return total >= 3600 ? `${(total / 3600).toFixed(1)} hrs` : `${Math.round(total / 60)} min`
  }
  const hourLabel = hour => {
    const start = Number(hour) || 0
    const end = (start + 3) % 24
    const label = value => `${String(value).padStart(2, '0')}:00`
    return `${label(start)} – ${label(end)}`
  }
  const movementLabel = movement => {
    if (movement === 'new') return 'NEW'
    if (Number(movement) > 0) return `▲ ${movement}`
    if (Number(movement) < 0) return `▼ ${Math.abs(movement)}`
    return '='
  }
  const movementClass = movement => movement === 'new' ? 'new' : Number(movement) > 0 ? 'up' : Number(movement) < 0 ? 'down' : 'flat'
  const rowTitle = row => activeBoard === 'tracks' ? row.title : activeBoard === 'artists' ? row.artist : row.album
  const rowSubtitle = row => activeBoard === 'tracks' ? row.artist : activeBoard === 'artists' ? `${row.plays || 0} plays` : `${row.artist || 'Various artists'} · ${row.plays || 0} plays`
  const rowArtwork = row => row.thumbnail || ''
  const playable = row => activeBoard === 'tracks' && row.videoId
    ? { ...row, id: row.videoId, title: row.title, artist: row.artist, thumbnail: row.thumbnail }
    : null

  async function loadStats() {
    controller?.abort()
    controller = new AbortController()
    loading = true
    error = ''
    try {
      const response = await apiFetch(`/api/stats/recap?range=${range}`, { signal: controller.signal })
      const payload = await response.json()
      if (!response.ok || payload.error) throw Error(payload.error || 'Could not load listening recap.')
      data = { ...empty, ...payload, recap: { ...empty.recap, ...(payload.recap || {}) }, leaderboards: { ...empty.leaderboards, ...(payload.leaderboards || {}) } }
    } catch (cause) {
      if (cause.name !== 'AbortError') {
        error = cause.message || 'Could not load listening recap.'
        data = empty
      }
    } finally {
      if (!controller.signal.aborted) loading = false
    }
  }
  function selectRange(value) {
    if (value === range) return
    range = value
    loadStats()
  }
  function playRow(row) {
    const track = playable(row)
    if (track) onPlayTrack(track)
  }
  function playTop25() {
    const tracks = (data.leaderboards?.tracks || []).map(playable).filter(Boolean)
    if (tracks.length) onPlayTracks(tracks)
    else showToast('No tracks in this range yet')
  }
  async function playForgottenGems() {
    gemsLoading = true
    try {
      const response = await apiFetch('/api/stats/forgotten-gems')
      const payload = await response.json()
      if (!response.ok || payload.error) throw Error(payload.error || 'Could not find forgotten gems')
      const tracks = (payload.tracks || []).filter(track => track?.videoId)
      if (!tracks.length) showToast('No forgotten gems yet')
      else { onPlayTracks(tracks); showToast(`${tracks.length} forgotten gems queued`) }
    } catch (cause) { showToast(cause.message || 'Could not find forgotten gems') }
    finally { gemsLoading = false }
  }
  async function saveCurrentLeaderboard() {
    const tracks = (data.leaderboards?.tracks || []).map(playable).filter(Boolean)
    if (!tracks.length) { showToast('There are no tracks to save'); return }
    const suffix = ranges.find(item => item.value === range)?.label || range
    saveLoading = true
    try {
      const result = await onSavePlaylist(`Wrapped Top Tracks · ${suffix}`, tracks)
      if (result) showToast(`Saved ${tracks.length} tracks as a playlist`)
    } catch (cause) { showToast(cause.message || 'Could not save playlist') }
    finally { saveLoading = false }
  }
  function showToast(message) { toast = message; setTimeout(() => { if (toast === message) toast = '' }, 3500) }

  onMount(loadStats)
</script>

<section class="stats-page" aria-labelledby="stats-title">
  <header class="stats-header">
    <div>
      <p class="eyebrow">YOUR LISTENING / WRAPPED</p>
      <h1 id="stats-title">The numbers behind the noise.</h1>
      <p class="subtitle">A private recap of what you played, when you played it, and what deserves another spin.</p>
    </div>
    <div class="range-picker" role="tablist" aria-label="Stats date range">
      {#each ranges as item}
        <button class:active={range === item.value} role="tab" aria-selected={range === item.value} on:click={() => selectRange(item.value)}>{item.label}</button>
      {/each}
    </div>
  </header>

  {#if loading}
    <div class="state"><span class="spinner"></span><span>Compiling your listening story…</span></div>
  {:else if error}
    <div class="state error"><strong>Recap unavailable</strong><span>{error}</span><button on:click={loadStats}>Retry</button></div>
  {:else}
    <section class="metric-strip" aria-label="Listening totals">
      <div><span>LISTENING TIME</span><strong>{totalHours}<small> hrs</small></strong></div>
      <div><span>PLAYS</span><strong>{(data.metrics?.totalTracks || 0).toLocaleString()}</strong></div>
      <div><span>ARTISTS</span><strong>{(data.metrics?.uniqueArtists || 0).toLocaleString()}</strong></div>
    </section>

    <section class="recap-grid" aria-label="Listening highlights">
      <article class="highlight obsession"><span class="card-kicker">THE OBSESSION</span>{#if data.recap?.obsession}<strong>{clean(data.recap.obsession.title)}</strong><p>{clean(data.recap.obsession.artist)} · {data.recap.obsession.plays} plays on {clean(data.recap.obsession.day)}</p>{:else}<strong>No repeat offender yet.</strong><p>Keep listening to reveal your fixation.</p>{/if}</article>
      <article class="highlight clock"><span class="card-kicker">CLOCK DENSITY</span>{#if data.recap?.clockDensity}<strong>Night Owl</strong><p>{hourLabel(data.recap.clockDensity.hour)} · {data.recap.clockDensity.plays} plays</p>{:else}<strong>Waiting for a pattern.</strong><p>Your listening hours will appear here.</p>{/if}</article>
      <article class="highlight heavyweight"><span class="card-kicker">HEAVYWEIGHT ARTIST</span>{#if data.recap?.heavyweight}<strong>{clean(data.recap.heavyweight.artist)}</strong><p>{data.recap.heavyweight.share}% of your total plays · {data.recap.heavyweight.plays} plays</p>{:else}<strong>No heavyweight yet.</strong><p>Play a few artists to build the split.</p>{/if}</article>
      <article class="highlight marathon"><span class="card-kicker">MARATHON RUN</span>{#if data.recap?.marathon}<strong>{formatHours(data.recap.marathon.seconds)}</strong><p>{clean(data.recap.marathon.day)} · {data.recap.marathon.plays} plays in one day</p>{:else}<strong>No marathon yet.</strong><p>Your longest listening day lands here.</p>{/if}</article>
    </section>

    <section class="leaderboard-panel" aria-label="Listening leaderboard">
      <header class="panel-head"><div><p class="eyebrow">THE RANKINGS</p><h2>Top 10 / {boardLabel}</h2><p>Rank movement compares this window with the preceding identical window.</p></div><div class="board-tabs" role="tablist">{#each ['tracks', 'artists', 'albums'] as board}<button class:active={activeBoard === board} role="tab" aria-selected={activeBoard === board} on:click={() => activeBoard = board}>{board}</button>{/each}</div></header>
      {#if rows.length}
        <div class="leaderboard-head"><span>#</span><span>{boardLabel}</span><span>PLAYS</span><span>TIME</span><span></span></div>
        <ol class="leaderboard">
          {#each rows as row (row.videoId || row.artist || row.album)}
            <li>
              <span class="rank">{String(row.rank).padStart(2, '0')}</span>
              {#if activeBoard === 'tracks'}<button class="row-main" on:click={() => playRow(row)}><span class="art">{#if rowArtwork(row)}<img src={rowArtwork(row)} alt="" referrerpolicy="no-referrer" />{:else}♫{/if}</span><span class="row-copy"><strong>{clean(rowTitle(row))}</strong><small>{clean(rowSubtitle(row))}</small></span></button>{:else}<div class="row-main"><span class="art">{#if rowArtwork(row)}<img src={rowArtwork(row)} alt="" referrerpolicy="no-referrer" />{:else}♫{/if}</span><span class="row-copy"><strong>{clean(rowTitle(row))}</strong><small>{clean(rowSubtitle(row))}</small></span></div>{/if}
              <span class="plays">{row.plays || 0}</span><span class="time">{formatTime(row.seconds)}</span><span class={`movement ${movementClass(row.movement)}`}>{movementLabel(row.movement)}</span>
            </li>
          {/each}
        </ol>
      {:else}<p class="empty">No listening data in this range.</p>{/if}
    </section>

    <section class="utility-panel" aria-label="Listening utilities">
      <div><p class="eyebrow">MAKE IT USEFUL</p><h2>Turn the recap into a queue.</h2><p>Keep the best of this window close, or resurrect tracks you have not heard in a while.</p></div>
      <div class="utility-actions"><button on:click={playTop25}>▶ Spin Top 25</button><button on:click={playForgottenGems} disabled={gemsLoading}>{gemsLoading ? 'Searching…' : '↺ Forgotten Gems'}</button><button on:click={saveCurrentLeaderboard} disabled={saveLoading}>{saveLoading ? 'Saving…' : '＋ Save as Playlist'}</button></div>
    </section>
  {/if}
  {#if toast}<div class="toast" role="status">{toast}</div>{/if}
</section>

<style>
  :global(body) { background: #000; }
  .stats-page { min-height: 100%; box-sizing: border-box; overflow-y: auto; padding: 28px clamp(18px, 4vw, 56px) 64px; color: #ededed; background: #000; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
  .stats-header { display: flex; align-items: end; justify-content: space-between; gap: 28px; max-width: 1280px; margin: 0 auto 30px; }
  h1, h2, p { margin: 0; }
  h1 { max-width: 700px; font-size: clamp(2rem, 5vw, 4.5rem); line-height: .95; letter-spacing: -.075em; }
  h2 { font-size: 1.15rem; letter-spacing: -.035em; }
  .subtitle { max-width: 560px; margin-top: 12px; color: #71717a; font-size: .82rem; line-height: 1.5; }
  .eyebrow, .card-kicker { color: #71717a; font: 600 .62rem ui-monospace, SFMono-Regular, monospace; letter-spacing: .16em; text-transform: uppercase; }
  .eyebrow { margin-bottom: 8px; }
  .range-picker, .board-tabs { display: flex; gap: 3px; padding: 3px; border: 1px solid rgba(255,255,255,.07); border-radius: 9px; background: #080808; }
  .range-picker button, .board-tabs button { border: 0; border-radius: 6px; padding: 8px 11px; color: #71717a; background: transparent; cursor: pointer; font-size: .68rem; white-space: nowrap; }
  .range-picker button.active, .board-tabs button.active { color: #000; background: #ededed; }
  .metric-strip, .recap-grid, .leaderboard-panel, .utility-panel { max-width: 1280px; margin-right: auto; margin-left: auto; }
  .metric-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; margin-bottom: 14px; border: 1px solid rgba(255,255,255,.07); background: rgba(255,255,255,.07); }
  .metric-strip > div { padding: 18px 20px; background: #050505; }.metric-strip span { display: block; color: #71717a; font: 600 .6rem ui-monospace, monospace; letter-spacing: .12em; }.metric-strip strong { display: block; margin-top: 8px; font-size: 1.9rem; letter-spacing: -.05em; }.metric-strip small { color: #71717a; font-size: .72rem; letter-spacing: 0; }
  .recap-grid { display: grid; grid-template-columns: 1.35fr 1fr 1fr 1fr; gap: 8px; margin-bottom: 14px; }.highlight { min-height: 142px; box-sizing: border-box; padding: 17px; border: 1px solid rgba(255,255,255,.07); border-radius: 10px; background: #050505; }.highlight strong { display: block; margin-top: 35px; overflow: hidden; font-size: clamp(1rem, 2vw, 1.45rem); letter-spacing: -.045em; text-overflow: ellipsis; white-space: nowrap; }.highlight p { margin-top: 6px; overflow: hidden; color: #71717a; font-size: .68rem; text-overflow: ellipsis; white-space: nowrap; }.obsession { background: linear-gradient(135deg, #15100b, #050505 75%); }.clock { background: linear-gradient(135deg, #0a1012, #050505 75%); }.heavyweight { background: linear-gradient(135deg, #100b15, #050505 75%); }.marathon { background: linear-gradient(135deg, #111109, #050505 75%); }
  .leaderboard-panel, .utility-panel { border: 1px solid rgba(255,255,255,.07); background: #050505; }.leaderboard-panel { padding: 20px; }.panel-head { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin-bottom: 20px; }.panel-head > div:first-child p:last-child, .utility-panel > div:first-child p:last-child { color: #71717a; font-size: .7rem; }.board-tabs button { text-transform: capitalize; }.leaderboard-head, .leaderboard li { display: grid; grid-template-columns: 42px minmax(0, 1fr) 70px 70px 54px; align-items: center; gap: 10px; }.leaderboard-head { padding: 0 10px 8px; color: #52525b; font: 600 .58rem ui-monospace, monospace; letter-spacing: .1em; text-transform: uppercase; }.leaderboard { margin: 0; padding: 0; list-style: none; }.leaderboard li { min-height: 58px; padding: 6px 10px; border-top: 1px solid rgba(255,255,255,.05); }.leaderboard li:hover { background: rgba(255,255,255,.03); }.rank, .plays, .time, .movement { color: #71717a; font: 600 .68rem ui-monospace, monospace; }.row-main { display: flex; align-items: center; gap: 11px; min-width: 0; border: 0; padding: 0; color: #ededed; background: transparent; text-align: left; cursor: pointer; }.art { display: grid; place-items: center; width: 42px; height: 42px; flex: 0 0 auto; overflow: hidden; border: 1px solid rgba(255,255,255,.07); border-radius: 7px; color: #52525b; background: #101010; }.art img { width: 100%; height: 100%; object-fit: cover; }.row-copy { display: flex; min-width: 0; flex-direction: column; gap: 4px; }.row-copy strong, .row-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.row-copy strong { font-size: .78rem; }.row-copy small { color: #71717a; font-size: .66rem; }.movement { text-align: right; }.movement.up { color: #86efac; }.movement.down { color: #fca5a5; }.movement.new { color: #facc15; }.movement.flat { color: #52525b; }.empty { padding: 22px 10px; color: #71717a; font-size: .76rem; }
  .utility-panel { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-top: 14px; padding: 20px; }.utility-panel h2 { margin-bottom: 6px; }.utility-actions { display: flex; flex-wrap: wrap; justify-content: end; gap: 7px; }.utility-actions button, .state button { border: 1px solid rgba(255,255,255,.14); border-radius: 7px; padding: 10px 12px; color: #ededed; background: #0e0e0e; cursor: pointer; font-size: .68rem; }.utility-actions button:hover { background: #191919; }.utility-actions button:disabled { cursor: wait; opacity: .5; }.state { display: flex; min-height: 420px; align-items: center; justify-content: center; gap: 10px; color: #71717a; font-size: .8rem; }.state.error { flex-direction: column; }.state.error strong { color: #fca5a5; }.spinner { width: 20px; height: 20px; border: 2px solid #ffffff22; border-top-color: #ededed; border-radius: 50%; animation: spin .8s linear infinite; }.toast { position: fixed; right: 24px; bottom: 24px; z-index: 10; padding: 11px 14px; border: 1px solid rgba(255,255,255,.12); border-radius: 8px; color: #ededed; background: #111; box-shadow: 0 12px 40px #000; font-size: .72rem; }@keyframes spin{to{transform:rotate(360deg)}}
  @media (max-width: 800px) { .stats-header, .panel-head, .utility-panel { align-items: stretch; flex-direction: column; }.range-picker, .board-tabs { width: max-content; max-width: 100%; overflow-x: auto; }.recap-grid { grid-template-columns: repeat(2, 1fr); }.leaderboard-head, .leaderboard li { grid-template-columns: 30px minmax(0, 1fr) 44px 0 45px; }.leaderboard-head span:nth-child(4), .leaderboard li .time { display: none; }.utility-actions { justify-content: start; }.metric-strip strong { font-size: 1.35rem; } }
</style>
