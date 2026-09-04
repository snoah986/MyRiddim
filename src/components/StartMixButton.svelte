<script>
  export let track = null
  export let onStartMix = () => {}

  function activate(event) {
    event.preventDefault()
    event.stopPropagation()
    onStartMix(track)
  }

  function keydown(event) {
    if (event.key === 'Enter' || event.key === ' ') activate(event)
  }
</script>

<button
  type="button"
  class="mix-trigger"
  aria-label="Start a radio mix from {track?.title || 'this track'}"
  title="Start Mix"
  on:pointerdown|preventDefault={activate}
  on:keydown={keydown}
>
  <span class="mix-icon" aria-hidden="true">✦</span>
  <span class="mix-label">Start Mix</span>
</button>

<style>
  :global(.mixable-track) { position: relative; }
  .mix-trigger {
    position: absolute;
    top: 9px;
    right: 9px;
    z-index: 6;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    min-height: 28px;
    padding: 5px 9px;
    border: 1px solid #ffffff2b;
    border-radius: 999px;
    color: #18120f;
    background: #f2ece4;
    box-shadow: 0 8px 22px #0008;
    cursor: pointer;
    font: 700 .65rem 'Manrope', ui-sans-serif, sans-serif;
    opacity: 0;
    pointer-events: none;
    transform: translateY(3px) scale(.96);
    transition: opacity .18s ease, transform .18s ease, background .18s ease;
  }
  :global(.mixable-track:hover) .mix-trigger,
  :global(.mixable-track:focus-within) .mix-trigger,
  :global(.rowcard:hover) .mix-trigger,
  :global(.song-row:hover) .mix-trigger,
  :global(.search-row:hover) .mix-trigger,
  :global(.track:hover) .mix-trigger,
  :global(.quick-card:hover) .mix-trigger,
  :global(.tile:hover) .mix-trigger,
  :global(.browse-card:hover) .mix-trigger,
  :global(.queue-row:hover) .mix-trigger,
  :global(.queue-recommendation-row:hover) .mix-trigger,
  :global(.track-menu:hover) .mix-trigger,
  :global(.now-playing:hover) .mix-trigger,
  :global(.recommendation-chip-wrap:hover) .mix-trigger,
  :global(.mix-trigger:focus-visible) {
    opacity: 1;
    pointer-events: auto;
    transform: translateY(0) scale(1);
  }
  .mix-trigger:hover { background: #fff; }
  .mix-trigger:active { transform: scale(.94); }
  @media (hover: none) {
    .mix-trigger { opacity: 1; pointer-events: auto; transform: translateY(0) scale(1); }
  }
  .mix-icon { font-size: .75rem; line-height: 1; }
  .mix-label { white-space: nowrap; }
  @media (prefers-reduced-motion: reduce) {
    .mix-trigger { transition: none; }
  }
</style>
