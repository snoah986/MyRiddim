<script>
  import WindowControls from '../components/WindowControls.svelte'
  import SearchSuggestions from '../components/SearchSuggestions.svelte'
  export let homeView = 'home'
  export let searchQuery = ''
  export let onSearchChanged = () => {}
  export let searchSuggestions = []
  export let searchSuggestionIndex = -1
  export let onSearchSuggestion = () => {}
  export let onViewChange = () => {}
  export let onCreatePlaylist = () => {}
  export let onOpenSmartCreator = () => {}
  export let onOpenSettings = () => {}

  const navItems = [['home', 'Home'], ['recent', 'Recently played'], ['favorites', 'Favorites'], ['discover', 'Discover'], ['playlists', 'Playlists'], ['stats', 'Stats'], ['updates', 'Updates']]
</script>

<div class="shell topbar-shell">
  <header class="topbar" data-tauri-drag-region>
    <div class="brand"><span class="mark">♫</span><strong>myriddim</strong></div>
    <nav aria-label="Primary navigation">
      {#each navItems as item}<button style="-webkit-app-region: no-drag;" class:active={homeView === item[0]} on:click={() => onViewChange(item[0])}>{item[1]}</button>{/each}
    </nav>
    <label class="search" style="-webkit-app-region: no-drag;"><span aria-hidden="true">⌕</span><input style="-webkit-app-region: no-drag;" class="global-search" value={searchQuery} on:input={onSearchChanged} placeholder="Search music" aria-label="Search" /><kbd>⌘K</kbd>{#if searchQuery.trim()}<SearchSuggestions items={searchSuggestions} activeIndex={searchSuggestionIndex} onSelect={onSearchSuggestion} />{/if}</label>
    <div class="actions" style="-webkit-app-region: no-drag;"><button style="-webkit-app-region: no-drag;" on:click={onCreatePlaylist}>+ Playlist</button><button style="-webkit-app-region: no-drag;" on:click={onOpenSmartCreator}>Smart</button><button style="-webkit-app-region: no-drag;" class="settings" on:click={onOpenSettings} aria-label="Open settings">⚙</button><WindowControls /></div>
  </header>
  <main class="content"><slot /></main>
</div>

<style>
  .shell { display:flex; flex:1 1 auto; min-height:0; flex-direction:column; color:#f4f4f5; background:#09090b; font-family:Inter,ui-sans-serif,system-ui,sans-serif; }.topbar { position:sticky; top:0; z-index:30; display:flex; align-items:center; gap:22px; min-height:68px; box-sizing:border-box; padding:12px 28px; border-bottom:1px solid #ffffff0f; background:#09090bea; backdrop-filter:blur(24px); }.brand { display:flex; align-items:center; gap:9px; flex:0 0 auto; }.brand strong { font-size:.95rem; letter-spacing:-.03em; }.mark { display:grid; place-items:center; width:28px; height:28px; border-radius:8px; color:#09090b; background:#fff; }.topbar nav { display:flex; align-items:center; gap:3px; }.topbar nav button,.actions button { border:0; border-radius:8px; color:#ffffff70; background:transparent; cursor:pointer; font:600 .7rem Inter,sans-serif; }.topbar nav button { padding:8px 9px; }.topbar nav button:hover,.topbar nav button.active { color:#fff; background:#ffffff0b; }.topbar nav button.active { box-shadow:inset 0 -2px #fff; }.search { position:relative; display:flex; flex:1 1 auto; align-items:center; gap:8px; width:100%; max-width:min(640px,65vw); margin-left:auto; padding:9px 12px; border:1px solid rgba(255,255,255,.08); border-radius:10px; color:#ffffff66; background:rgba(255,255,255,.03); transition:background .2s ease,border-color .2s ease,box-shadow .2s ease; }.search:focus-within { border-color:rgba(255,255,255,.22); background:rgba(255,255,255,.06); outline:none; box-shadow:0 8px 24px rgba(0,0,0,.16); }.search input { width:100%; min-width:0; border:0; outline:0; color:#fff; background:transparent; font:inherit; font-size:.75rem; }.search input::placeholder { color:#ffffff52; }.search kbd { padding:2px 6px; border-radius:6px; color:rgba(255,255,255,.4); background:rgba(255,255,255,.06); font:500 .6rem ui-monospace,monospace; white-space:nowrap; }.actions { display:flex; align-items:center; gap:5px; }.actions button { padding:8px 9px; border:1px solid #ffffff0f; background:#ffffff06; }.actions button:hover { color:#fff; background:#ffffff10; }.actions .settings { border:0; background:transparent; font-size:.85rem; }  .content { flex:1 1 auto; min-width:0; min-height:0; overflow-y:auto; scrollbar-gutter:stable; }
  @media(max-width:1000px) { .topbar { gap:10px; padding-inline:16px; }.topbar nav { order:3; width:100%; justify-content:center; }.topbar { flex-wrap:wrap; }.search { max-width:min(640px,65vw); }.actions { margin-left:0; } }
  @media(max-width:600px) { .topbar { padding:10px 12px; }.brand strong,.topbar nav button:nth-child(n+4),.actions button:not(.settings) { display:none; }.search { flex:1 1 auto; width:auto; max-width:none; margin-left:0; }.topbar nav { justify-content:space-between; }.topbar nav button { flex:1; font-size:.62rem; }.content { padding-bottom:64px; } }
</style>
