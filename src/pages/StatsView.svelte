<script>
  import { apiFetch } from '../lib/api.js'
  import { onMount, onDestroy } from 'svelte'
  import StartMixButton from '../components/StartMixButton.svelte'

  export let onPlayTrack = () => {}
  export let onStartMix = () => {}

  const ranges = [
    { value: '7', label: '7 days' },
    { value: '30', label: '30 days' },
    { value: '180', label: '6 months' },
    { value: 'all', label: 'All time' },
  ]
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const hours = Array.from({ length: 24 }, (_, index) => index)
  const empty = { metrics: { totalSeconds: 0, totalTracks: 0, uniqueArtists: 0 }, topArtists: [], topTracks: [], trend: [], heatmap: [] }

  let range = '30'
  let data = empty
  let loading = true
  let error = ''
  let controller

  $: maxHeat = Math.max(1, ...(data.heatmap || []).map(item => Number(item.intensity) || 0))
  $: maxTrend = Math.max(1, ...(data.trend || []).map(item => Number(item.seconds) || 0))
  $: heat = new Map((data.heatmap || []).map(item => [`${item.day}-${item.hour}`, Number(item.intensity) || 0]))
  $: maxArtist = Math.max(1, ...(data.topArtists || []).map(item => Number(item.plays) || 0))

  const formatHours = seconds => {
    const hoursValue = (Number(seconds) || 0) / 3600
    return hoursValue >= 10 ? hoursValue.toFixed(0) : hoursValue.toFixed(1)
  }
  const formatDate = value => {
    if (!value) return ''
    const date = new Date(`${value}T00:00:00`)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }
  const formatTrackTime = seconds => {
    const total = Math.round(Number(seconds) || 0)
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
  }
  const heatOpacity = value => value ? 0.12 + (value / maxHeat) * 0.78 : 0.035

  async function loadStats() {
    controller?.abort()
    controller = new AbortController()
    loading = true
    error = ''
    try {
      const response = await apiFetch(`/api/stats/analytics?range=${range}`, { signal: controller.signal })
      const payload = await response.json()
      if (!response.ok || payload.error) throw Error(payload.error || 'Could not load listening stats.')
      data = { ...empty, ...payload }
    } catch (cause) {
      if (cause.name !== 'AbortError') {
        error = cause.message || 'Could not load listening stats.'
        data = empty
      }
    } finally {
      if (!controller.signal.aborted) loading = false
    }
  }
  function selectRange(value) {
    if (value !== range) {
      range = value
      loadStats()
    }
  }

  onMount(loadStats)
  onDestroy(() => controller?.abort())
</script>

<section class="stats-page" aria-labelledby="stats-title">
  <header class="stats-header">
    <div>
      <p class="eyebrow">YOUR LISTENING</p>
      <h2 id="stats-title">Listening stats</h2>
      <p class="subtitle">A private view of how your music habits change over time.</p>
    </div>
    <div class="range-picker" role="tablist" aria-label="Stats date range">
      {#each ranges as item}
        <button class:active={range === item.value} role="tab" aria-selected={range === item.value} on:click={() => selectRange(item.value)}>{item.label}</button>
      {/each}
    </div>
  </header>

  {#if loading}
    <div class="stats-state"><span class="spinner"></span><span>Crunching your listening history…</span></div>
  {:else if error}
    <div class="stats-state error-state"><strong>Stats are unavailable</strong><span>{error}</span><button on:click={loadStats}>Retry</button></div>
  {:else}
    <div class="metric-grid">
      <article class="metric-card"><span class="metric-label">Listening time</span><strong>{formatHours(data.metrics.totalSeconds)}<small> hrs</small></strong><span class="metric-note">Across {data.metrics.totalTracks} plays</span></article>
      <article class="metric-card"><span class="metric-label">Tracks played</span><strong>{data.metrics.totalTracks.toLocaleString()}</strong><span class="metric-note">Unique listens in this range</span></article>
      <article class="metric-card"><span class="metric-label">Artists explored</span><strong>{data.metrics.uniqueArtists.toLocaleString()}</strong><span class="metric-note">Distinct artists heard</span></article>
    </div>

    <div class="stats-grid">
      <section class="panel trend-panel">
        <div class="panel-heading"><div><h3>Listening trend</h3><p>Minutes listened per day</p></div><span>{ranges.find(item => item.value === range)?.label}</span></div>
        {#if data.trend.length}
          <div class="trend-chart" aria-label="Daily listening trend">
            {#each data.trend as item}
              <div class="trend-column" title={`${formatDate(item.date)} · ${Math.round(item.seconds / 60)} min`}><div class="trend-bar" style={`height: ${Math.max(5, (item.seconds / maxTrend) * 100)}%`}></div><span>{formatDate(item.date)}</span></div>
            {/each}
          </div>
        {:else}<p class="empty">No listening data in this range.</p>{/if}
      </section>

      <section class="panel heat-panel">
        <div class="panel-heading"><div><h3>When you listen</h3><p>Play density by day and hour</p></div></div>
        <div class="heatmap-wrap"><div class="heat-hours">{#each hours as hour}<span>{hour % 4 === 0 ? hour : ''}</span>{/each}</div><div class="heatmap"><div class="heat-days">{#each days as day}<span>{day}</span>{/each}</div><div class="heat-grid">{#each days as _, day}{#each hours as hour}<span class="heat-cell" title={`${days[day]}, ${String(hour).padStart(2, '0')}:00 · ${heat.get(`${day}-${hour}`) || 0} plays`} style={`opacity: ${heatOpacity(heat.get(`${day}-${hour}`) || 0)}`}></span>{/each}{/each}</div></div></div>
        <div class="heat-legend"><span>Less</span><i></i><i></i><i></i><i></i><span>More</span></div>
      </section>
    </div>

    <div class="rank-grid">
      <section class="panel ranking"><div class="panel-heading"><div><h3>Top artists</h3><p>Most played in this range</p></div></div>{#if data.topArtists.length}<ol>{#each data.topArtists as artist, index}<li><b>{String(index + 1).padStart(2, '0')}</b><span class="rank-name">{artist.artist}</span><span class="rank-count">{artist.plays} plays</span><span class="rank-fill" style={`width: ${(artist.plays / maxArtist) * 100}%`}></span></li>{/each}</ol>{:else}<p class="empty">No artists to rank yet.</p>{/if}</section>
      <section class="panel ranking"><div class="panel-heading"><div><h3>Top tracks</h3><p>Your most replayed songs</p></div></div>{#if data.topTracks.length}<ol>{#each data.topTracks as track, index}<li class="track-rank mixable-track"><b>{String(index + 1).padStart(2, '0')}</b><button on:click={() => onPlayTrack(track)}><span class="track-art">{#if track.thumbnail}<img src={track.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}♫{/if}</span><span class="rank-name"><strong>{track.title || 'Unknown title'}</strong><small>{track.artist || 'Unknown artist'}</small></span><span class="rank-count">{track.plays} plays</span></button><StartMixButton track={track} onStartMix={onStartMix} /></li>{/each}</ol>{:else}<p class="empty">No tracks to rank yet.</p>{/if}</section>
    </div>
  {/if}
</section>

<style>
  .stats-page { position: relative; z-index: 1; max-width: 1180px; margin: 0 auto; padding: 8px 0 44px; color: #f4f4f5; font-family: 'Inter', ui-sans-serif, system-ui, sans-serif; }
  .stats-header { display: flex; justify-content: space-between; align-items: end; gap: 24px; margin: 18px 0 26px; }
  .eyebrow { margin: 0 0 8px; color: #9d9da8; font-size: .68rem; font-weight: 700; letter-spacing: .16em; }
  h2, h3, p { margin: 0; }
  h2 { font-family: 'Outfit', Inter, sans-serif; font-size: clamp(1.8rem, 3vw, 2.5rem); letter-spacing: -.03em; }
  .subtitle, .panel-heading p, .metric-note { color: #92929d; font-size: .82rem; }
  .subtitle { margin-top: 7px; }
  .range-picker { display: flex; gap: 4px; padding: 4px; border: 1px solid #ffffff12; border-radius: 12px; background: #ffffff08; }
  .range-picker button { border: 0; border-radius: 8px; padding: 8px 12px; color: #a1a1aa; background: transparent; cursor: pointer; font-size: .76rem; font-weight: 600; transition: .18s ease; }
  .range-picker button:hover { color: #fff; background: #ffffff0b; }
  .range-picker button.active { color: #111; background: var(--accent, #c4b5fd); box-shadow: 0 3px 14px color-mix(in srgb, var(--accent, #c4b5fd) 28%, transparent); }
  .metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 14px; }
  .metric-card, .panel { border: 1px solid #ffffff0d; border-radius: 16px; background: linear-gradient(135deg, #ffffff0b, #ffffff04); backdrop-filter: blur(18px); }
  .metric-card { display: flex; flex-direction: column; gap: 8px; padding: 19px 20px; }
  .metric-label { color: #a1a1aa; font-size: .78rem; font-weight: 600; }
  .metric-card strong { font-family: 'Outfit', Inter, sans-serif; font-size: 2rem; letter-spacing: -.04em; }
  .metric-card strong small { color: #a1a1aa; font-family: Inter, sans-serif; font-size: .9rem; font-weight: 500; letter-spacing: 0; }
  .stats-grid, .rank-grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 14px; margin-bottom: 14px; }
  .panel { padding: 18px; min-width: 0; }
  .panel-heading { display: flex; justify-content: space-between; align-items: start; gap: 12px; margin-bottom: 20px; }
  .panel-heading h3 { font-family: 'Outfit', Inter, sans-serif; font-size: 1.08rem; }
  .panel-heading span { color: #71717a; font-size: .72rem; }
  .trend-chart { display: flex; align-items: end; gap: 5px; height: 170px; overflow-x: auto; padding-top: 8px; }
  .trend-column { display: flex; flex: 1 0 17px; flex-direction: column; justify-content: end; align-items: center; gap: 7px; height: 100%; color: #71717a; font-size: .59rem; }
  .trend-column span { max-width: 36px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .trend-bar { width: 100%; min-height: 4px; border-radius: 5px 5px 2px 2px; background: linear-gradient(to top, var(--accent, #c4b5fd), color-mix(in srgb, var(--accent, #c4b5fd) 40%, #fff)); transition: height .35s ease; }
  .heat-panel { overflow: hidden; }
  .heatmap-wrap { overflow-x: auto; padding-bottom: 4px; }
  .heat-hours { display: grid; grid-template-columns: repeat(24, 18px); gap: 4px; margin: 0 0 5px 38px; color: #71717a; font-size: .58rem; }
  .heat-hours span { text-align: center; }
  .heatmap { display: flex; gap: 5px; }
  .heat-days { display: grid; grid-template-rows: repeat(7, 18px); gap: 4px; width: 33px; color: #71717a; font-size: .63rem; }
  .heat-days span { display: flex; align-items: center; }
  .heat-grid { display: grid; grid-template-columns: repeat(24, 18px); grid-template-rows: repeat(7, 18px); grid-auto-flow: row; gap: 4px; }
  .heat-cell { display: block; border-radius: 4px; background: var(--accent, #c4b5fd); transition: opacity .2s ease, transform .2s ease; }
  .heat-cell:hover { transform: scale(1.18); }
  .heat-legend { display: flex; justify-content: end; align-items: center; gap: 5px; margin-top: 12px; color: #71717a; font-size: .6rem; }
  .heat-legend i { width: 11px; height: 11px; border-radius: 3px; background: var(--accent, #c4b5fd); opacity: .18; }.heat-legend i:nth-of-type(2){opacity:.38}.heat-legend i:nth-of-type(3){opacity:.62}.heat-legend i:nth-of-type(4){opacity:.9}
  .ranking ol { display: flex; flex-direction: column; gap: 4px; margin: 0; padding: 0; list-style: none; }
  .ranking li { position: relative; display: flex; align-items: center; gap: 12px; min-height: 38px; padding: 4px 2px; overflow: hidden; border-radius: 8px; }
  .ranking li:hover { background: #ffffff08; }
  .ranking li > b { width: 23px; color: #71717a; font-size: .7rem; font-variant-numeric: tabular-nums; }
  .rank-name { position: relative; z-index: 1; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: .82rem; }
  .rank-count { position: relative; z-index: 1; color: #92929d; font-size: .7rem; white-space: nowrap; }
  .rank-fill { position: absolute; left: 35px; bottom: 0; height: 1px; background: var(--accent, #c4b5fd); opacity: .35; transition: width .35s ease; }
  .track-rank button { display: flex; align-items: center; flex: 1; gap: 10px; min-width: 0; border: 0; padding: 0; color: inherit; background: none; text-align: left; cursor: pointer; }
  .track-art { display: grid; place-items: center; width: 34px; height: 34px; flex: 0 0 auto; overflow: hidden; border-radius: 6px; color: #bbb; background: #ffffff0d; }
  .track-art img { width: 100%; height: 100%; object-fit: cover; }
  .track-rank .rank-name { display: flex; flex-direction: column; gap: 2px; }
  .track-rank .rank-name strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: .8rem; }
  .track-rank .rank-name small { overflow: hidden; color: #92929d; text-overflow: ellipsis; white-space: nowrap; font-size: .7rem; }
  .empty { color: #71717a; font-size: .8rem; }
  .stats-state { display: flex; min-height: 300px; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: #92929d; font-size: .85rem; }
  .spinner { width: 22px; height: 22px; border: 2px solid #ffffff1c; border-top-color: var(--accent, #c4b5fd); border-radius: 50%; animation: spin .8s linear infinite; }
  .error-state strong { color: #fca5a5; }.error-state button { margin-top: 4px; border: 0; border-radius: 999px; padding: 8px 14px; color: #111; background: var(--accent, #c4b5fd); cursor: pointer; font-weight: 700; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 800px) { .stats-header { align-items: start; flex-direction: column; }.range-picker { width: 100%; }.range-picker button { flex: 1; padding: 8px 5px; }.stats-grid, .rank-grid { grid-template-columns: 1fr; }.metric-card { padding: 15px; }.metric-card strong { font-size: 1.65rem; } }
  @media (prefers-reduced-motion: reduce) { .trend-bar, .heat-cell { transition: none; } }
</style>
