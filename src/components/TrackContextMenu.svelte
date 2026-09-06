<script>
  import { onMount, onDestroy } from 'svelte'
  import StartMixButton from './StartMixButton.svelte'

  export let track = {}
  export let entityType = 'track'
  export let owned = false
  export let up = false
  export let onPlayNext = () => {}
  export let onAddToQueue = () => {}
  export let onAddToPlaylist = () => {}
  export let onStartMix = () => {}
  export let onRemove = () => {}
  export let onOpenArtist = () => {}
  export let onOpenAlbum = () => {}
  export let onFavorite = () => {}
  export let positioned = false
  export let x = 0
  export let y = 0
  export let autoOpen = false

  let open = autoOpen
  let wrapper
  $: kind = String(entityType || track?.type || 'track').toLowerCase()
  $: menuLeft = positioned ? Math.max(6, Math.min(x, (typeof window !== 'undefined' ? window.innerWidth : 1200) - 208)) : 0
  $: menuUp = positioned && y > (typeof window !== 'undefined' ? window.innerHeight : 800) - 252
  $: menuBottom = positioned && typeof window !== 'undefined' ? window.innerHeight - y : 0

  function dismiss() { open = false }
  function onWindowClick(event) { if (wrapper && !wrapper.contains(event.target)) dismiss() }
  function onWindowKeydown(event) { if (event.key === 'Escape') dismiss() }
  function onWindowScroll() { dismiss() }
  onMount(() => {
    window.addEventListener('click', onWindowClick)
    window.addEventListener('keydown', onWindowKeydown)
    window.addEventListener('scroll', onWindowScroll, { passive: true })
  })
  onDestroy(() => {
    window.removeEventListener('click', onWindowClick)
    window.removeEventListener('keydown', onWindowKeydown)
    window.removeEventListener('scroll', onWindowScroll)
  })

  function toggle(event) {
    event.stopPropagation()
    open = !open
  }

  function openContextMenu(event) {
    event.preventDefault()
    event.stopPropagation()
    open = true
  }

  function act(fn) {
    return (event) => {
      event.preventDefault()
      event.stopPropagation()
      open = false
      fn(track)
    }
  }
</script>

{#if positioned}
  {#if open}
    <div class="fixed-menu" class:up={menuUp} style="left:{menuLeft}px;{menuUp ? `bottom:${menuBottom}px` : `top:${y}px`}" bind:this={wrapper} role="menu" on:contextmenu|preventDefault|stopPropagation>
      {#if kind === 'artist'}
        <button role="menuitem" on:click={act(onPlayNext)}>Play Top Tracks</button>
        <button role="menuitem" on:click={act(onStartMix)}>Start Artist Radio</button>
        <button role="menuitem" on:click={act(onFavorite)}>Favorite Artist</button>
      {:else if kind === 'album'}
        <button role="menuitem" on:click={act(onPlayNext)}>Play Album</button>
        <button role="menuitem" on:click={act(onAddToQueue)}>Add All to Queue</button>
        <button role="menuitem" on:click={act(onOpenArtist)}>Go to Artist</button>
        <button role="menuitem" on:click={act(onFavorite)}>Favorite Album</button>
      {:else}
        <button role="menuitem" on:click={act(onPlayNext)}>Play Next</button>
        <button role="menuitem" on:click={act(onAddToQueue)}>Add to Queue</button>
        <button role="menuitem" on:click={act(onStartMix)}>Start Radio</button>
        <button role="menuitem" on:click={act(onOpenArtist)}>Go to Artist</button>
        <button role="menuitem" on:click={act(onOpenAlbum)}>Go to Album</button>
        <button role="menuitem" on:click={act(onAddToPlaylist)}>Add to Playlist</button>
      {/if}
      {#if owned}<button role="menuitem" class="danger" on:click={act(onRemove)}>Remove from Playlist</button>{/if}
    </div>
  {/if}
{:else}
  <div class="track-menu" class:open class:up bind:this={wrapper} on:contextmenu={openContextMenu}>
    {#if kind === 'track'}<StartMixButton track={track} onStartMix={onStartMix} />{/if}
    <button class="dot-btn" aria-label="{kind} actions" aria-haspopup="menu" aria-expanded={open} on:click={toggle}>•••</button>
    {#if open}
      <div class="menu" role="menu">
        {#if kind === 'artist'}
          <button role="menuitem" on:click={act(onPlayNext)}>Play Top Tracks</button>
          <button role="menuitem" on:click={act(onStartMix)}>Start Artist Radio</button>
          <button role="menuitem" on:click={act(onFavorite)}>Favorite Artist</button>
        {:else if kind === 'album'}
          <button role="menuitem" on:click={act(onPlayNext)}>Play Album</button>
          <button role="menuitem" on:click={act(onAddToQueue)}>Add All to Queue</button>
          <button role="menuitem" on:click={act(onOpenArtist)}>Go to Artist</button>
          <button role="menuitem" on:click={act(onFavorite)}>Favorite Album</button>
        {:else}
          <button role="menuitem" on:click={act(onPlayNext)}>Play Next</button>
          <button role="menuitem" on:click={act(onAddToQueue)}>Add to Queue</button>
          <button role="menuitem" on:click={act(onStartMix)}>Start Radio</button>
          <button role="menuitem" on:click={act(onOpenArtist)}>Go to Artist</button>
          <button role="menuitem" on:click={act(onOpenAlbum)}>Go to Album</button>
          <button role="menuitem" on:click={act(onAddToPlaylist)}>Add to Playlist</button>
        {/if}
        {#if owned}<button role="menuitem" class="danger" on:click={act(onRemove)}>Remove from Playlist</button>{/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .track-menu { position: relative; display: inline-flex; flex: 0 0 auto; }
  .track-menu :global(.mix-trigger) { top: 0; right: 34px; }
  .dot-btn { border: 0; background: none; color: #71717a; cursor: pointer; font-size: 1.05rem; letter-spacing: 2px; padding: 4px 8px; border-radius: 8px; line-height: 1; }
  .dot-btn:hover, .track-menu.open .dot-btn { color: #f4f4f5; background: #ffffff12; }
  .menu, .fixed-menu { z-index: 999; min-width: 190px; padding: 6px; border: 1px solid #ffffff1c; border-radius: 12px; background: #17171bf2; box-shadow: 0 18px 50px #0009; backdrop-filter: blur(24px); }
  .menu { position: absolute; right: 0; top: calc(100% + 6px); }
  .track-menu.up .menu { top: auto; bottom: calc(100% + 6px); }
  .fixed-menu { position: fixed; }
  .menu button, .fixed-menu button { display: block; width: 100%; padding: 9px 12px; border: 0; border-radius: 8px; color: #eee; background: none; text-align: left; font: inherit; font-size: .78rem; cursor: pointer; }
  .menu button:hover, .fixed-menu button:hover { background: #ffffff14; }
  .menu button.danger, .fixed-menu button.danger { color: #fca5a5; }
</style>
