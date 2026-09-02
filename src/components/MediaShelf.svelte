<script>
  export let eyebrow = ''
  export let title = ''
  export let tracks = []
  export let onPlayTrack = () => {}
  const clean = value => String(value ?? '').replace(/[\\\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim()
</script>

<section class="tile-shelf">
  <div class="section-head"><div><p class="eyebrow">{eyebrow}</p><h2>{title}</h2></div></div>
  <div class="tile-grid">
    {#each tracks as t, i (t.videoId || i)}
    <button class="tile" on:click={() => onPlayTrack(t, i)}>
      <div class="tile-art">{#if t.thumbnail}<img src={t.thumbnail} referrerpolicy="no-referrer" alt="" />{:else}<span>♫</span>{/if}<i>▶</i></div>
      <strong>{clean(t.title)}</strong><span>{clean(t.artist)}</span>
    </button>
    {/each}
  </div>
</section>

<style>
  .tile-shelf { margin: 28px 0 34px; }
  .section-head { display: flex; justify-content: space-between; align-items: end; margin-bottom: 14px; }
  .section-head h2 { margin: 0; font-size: 1.45rem; }
  .eyebrow { margin: 0 0 8px; color: #a1a1aa; font-size: .68rem; font-weight: 700; letter-spacing: .16em; }
  .tile-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 18px; }
  .tile { border: 0; padding: 0; color: #eee; background: none; text-align: left; cursor: pointer; transition: transform .22s ease; }
  .tile:hover { transform: translateY(-4px) scale(1.02); }
  .tile-art { position: relative; display: grid; place-items: center; aspect-ratio: 1; overflow: hidden; border-radius: 12px; background: linear-gradient(135deg, #252331, #4d3640); font-size: 2.2rem; margin-bottom: 10px; border: 1px solid rgba(255,255,255,.06); transition: box-shadow .22s ease; }
  .tile-art img { width: 100%; height: 100%; object-fit: cover; }
  .tile-art::after { content: ''; position: absolute; inset: 0; z-index: 0; background: linear-gradient(to top, rgba(0,0,0,.4), transparent 42%); pointer-events: none; }
  .tile-art i { position: absolute; right: 10px; bottom: 10px; z-index: 1; display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; color: #111; background: #fff; font-style: normal; opacity: 0; transition: .2s; }
  .tile:hover .tile-art i { opacity: 1; }
  .tile:hover .tile-art { box-shadow: 0 12px 30px rgba(0,0,0,.6); }
  .tile strong, .tile > span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tile strong { font-size: .88rem; }
  .tile > span { color: #a1a1aa; font-size: .78rem; margin-top: 3px; }
</style>