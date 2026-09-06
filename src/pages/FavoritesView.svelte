<script>
  import TrackCard from '../components/TrackCard.svelte'

  export let tracks = []
  export let loading = false
  export let error = ''
  export let onRetry = () => {}
  export let onPlay = () => {}
  export let onOpenArtist = () => {}
  export let onOpenAlbum = () => {}
  export let onAddToQueue = () => {}

  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
</script>

<section class="favorites-page" aria-label="Favorites">
  <header class="page-head">
    <div><p class="eyebrow">LIBRARY</p><h1>Favorites</h1></div>
    {#if tracks.length}<span class="count">{tracks.length} TRACKS</span>{/if}
  </header>

  {#if loading}
    <p class="empty">Loading favorites…</p>
  {:else if error}
    <div class="empty error-state"><strong>{error}</strong><button on:click={onRetry}>Retry</button></div>
  {:else if tracks.length}
    <div class="track-grid">
      {#each tracks as track, index (track.videoId || track.id || index)}
        <TrackCard track={track} onPlay={onPlay} onOpenArtist={onOpenArtist} onOpenAlbum={onOpenAlbum} onAdd={onAddToQueue} />
      {/each}
    </div>
  {:else}
    <p class="empty">No favorites yet.</p>
  {/if}
</section>

<style>
  .favorites-page{min-height:100%;box-sizing:border-box;padding:28px clamp(18px,4vw,48px) 48px;color:#ededed;background:#000}
  .page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:24px}.eyebrow,.count{margin:0 0 7px;color:#71717a;font:600 .62rem ui-monospace,SFMono-Regular,monospace;letter-spacing:.14em}.page-head h1{margin:0;font-size:clamp(1.8rem,4vw,2.8rem);letter-spacing:-.06em}.count{font-weight:500}.track-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:14px}.empty{color:#71717a;font-size:.78rem}.error-state strong{display:block;color:#fca5a5;margin-bottom:10px}.error-state button{border:1px solid rgba(255,255,255,.13);border-radius:7px;padding:7px 10px;color:#ededed;background:#111113;cursor:pointer;font-size:.68rem}
</style>
