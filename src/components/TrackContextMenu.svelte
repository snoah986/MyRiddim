<script>
  import { onMount, onDestroy } from 'svelte'
  import StartMixButton from './StartMixButton.svelte'
  export let track = {}
  export let owned = false
  export let up = false
  export let onPlayNext = () => {}
  export let onAddToQueue = () => {}
  export let onAddToPlaylist = () => {}
  export let onStartMix = () => {}
  export let onRemove = () => {}
  // Positioned mode: rendered at cursor coordinates on right-click instead of
  // being anchored to a "•••" trigger button.
  export let positioned = false
  export let x = 0
  export let y = 0
  export let autoOpen = false

  let open = autoOpen
  let wrapper
  $: menuLeft = positioned ? Math.min(x, (typeof window !== 'undefined' ? window.innerWidth : 1200) - 208) : 0
  $: menuUp = positioned && y > (typeof window !== 'undefined' ? window.innerHeight : 800) - 252
  $: menuBottom = positioned && typeof window !== 'undefined' ? window.innerHeight - y : 0
  function onWindowClick(event) { if (wrapper && !wrapper.contains(event.target)) open = false }
  function onKeydown(event) { if (event.key === 'Escape') open = false }
  onMount(() => { window.addEventListener('click', onWindowClick); window.addEventListener('keydown', onKeydown) })
  onDestroy(() => { window.removeEventListener('click', onWindowClick); window.removeEventListener('keydown', onKeydown) })
  function toggle(event) { event.stopPropagation(); open = !open }
  function act(fn) { return (event) => { event.stopPropagation(); open = false; fn() } }
</script>

{#if positioned}
  {#if open}<div class="fixed-menu" class:up={menuUp} style="left:{menuLeft}px;{menuUp ? `bottom:${menuBottom}px` : `top:${y}px`}" bind:this={wrapper} role="menu">
    <button role="menuitem" on:click={act(() => onPlayNext(track))}>Play Next</button>
    <button role="menuitem" on:click={act(() => onAddToQueue(track))}>Add to Queue</button>
    <button role="menuitem" on:click={act(() => onAddToPlaylist(track))}>Add to Playlist</button>
    {#if owned}<button role="menuitem" class="danger" on:click={act(() => onRemove(track))}>Remove from Playlist</button>{/if}
  </div>{/if}
{:else}
<div class="track-menu" class:open class:up bind:this={wrapper}>
  <StartMixButton track={track} onStartMix={onStartMix} />
  <button class="dot-btn" aria-label="Track actions" aria-haspopup="menu" aria-expanded={open} on:click={toggle}>•••</button>
  {#if open}<div class="menu" role="menu">
    <button role="menuitem" on:click={act(() => onPlayNext(track))}>Play Next</button>
    <button role="menuitem" on:click={act(() => onAddToQueue(track))}>Add to Queue</button>
    <button role="menuitem" on:click={act(() => onAddToPlaylist(track))}>Add to Playlist</button>
    {#if owned}<button role="menuitem" class="danger" on:click={act(() => onRemove(track))}>Remove from Playlist</button>{/if}
  </div>{/if}
</div>
{/if}

<style>
  .track-menu { position: relative; display: inline-flex; flex: 0 0 auto; }
  .track-menu :global(.mix-trigger) { top: 0; right: 34px; }
  .dot-btn { border: 0; background: none; color: #71717a; cursor: pointer; font-size: 1.05rem; letter-spacing: 2px; padding: 4px 8px; border-radius: 8px; line-height: 1; }
  .dot-btn:hover, .track-menu.open .dot-btn { color: #f4f4f5; background: #ffffff12; }
  .menu { position: absolute; right: 0; top: calc(100% + 6px); z-index: 60; min-width: 180px; padding: 6px; border: 1px solid #ffffff1c; border-radius: 12px; background: #24242bf2; box-shadow: 0 18px 50px #0009; backdrop-filter: blur(24px); }
  .track-menu.up .menu { top: auto; bottom: calc(100% + 6px); }
  .fixed-menu { position: fixed; z-index: 999; min-width: 190px; padding: 6px; border: 1px solid #ffffff1c; border-radius: 12px; background: #24242bf2; box-shadow: 0 18px 50px #0009; backdrop-filter: blur(24px); }
  .menu button, .fixed-menu button { display: block; width: 100%; padding: 9px 12px; border: 0; border-radius: 8px; color: #eee; background: none; text-align: left; font: inherit; font-size: .85rem; cursor: pointer; }
  .menu button:hover, .fixed-menu button:hover { background: #ffffff14; }
  .menu button.danger, .fixed-menu button.danger { color: #fca5a5; }
  .menu button.danger:hover, .fixed-menu button.danger:hover { background: #fca5a51f; }
</style>