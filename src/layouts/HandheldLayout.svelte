<script>
  export let homeView = 'home'
  export let searchQuery = ''
  export let onSearchChanged = () => {}
  export let onViewChange = () => {}
  export let onOpenSettings = () => {}
  const navItems = [['home', 'Home', '⌂'], ['discover', 'Discover', '✦'], ['favorites', 'Favorites', '♡'], ['stats', 'Stats', '◒']]
</script>

<div class="shell handheld-shell">
  <header class="mobile-head" data-tauri-drag-region><strong>myriddim</strong><button style="-webkit-app-region: no-drag;" on:click={onOpenSettings} aria-label="Open settings">⚙</button></header>
  <label class="search" style="-webkit-app-region: no-drag;"><span aria-hidden="true">⌕</span><input style="-webkit-app-region: no-drag;" class="global-search" value={searchQuery} on:input={onSearchChanged} placeholder="Search your music" aria-label="Search your music" /></label>
  <main class="content"><slot /></main>
  <nav class="thumb-bar" aria-label="Primary navigation">
    {#each navItems as item}<button class:active={homeView === item[0]} on:click={() => onViewChange(item[0])}><span>{item[2]}</span><small>{item[1]}</small></button>{/each}
  </nav>
</div>

<style>
  .shell { display:flex; flex:1 1 auto; min-height:0; flex-direction:column; color:#f4f4f5; background:#09090b; font-family:Inter,ui-sans-serif,system-ui,sans-serif; }.mobile-head { display:flex; align-items:center; justify-content:space-between; height:54px; padding:0 18px; border-bottom:1px solid #ffffff0f; background:#09090bea; }.mobile-head strong { font-size:1rem; letter-spacing:-.04em; }.mobile-head button { width:40px; height:40px; border:0; border-radius:50%; color:#fff; background:#ffffff0a; cursor:pointer; }.search { display:flex; align-items:center; gap:8px; margin:14px 16px 8px; padding:12px 14px; border:1px solid #ffffff10; border-radius:12px; color:#ffffff58; background:#ffffff06; }.search input { width:100%; border:0; outline:0; color:#fff; background:transparent; font:inherit; font-size:.82rem; }  .content { flex:1 1 auto; min-width:0; min-height:0; overflow-y:auto; padding-bottom:76px; scrollbar-gutter:stable; }.thumb-bar { position:fixed; inset:auto 0 0; z-index:40; display:flex; justify-content:space-around; height:68px; padding:4px 8px env(safe-area-inset-bottom); border-top:1px solid #ffffff12; background:#0c0c0de8; backdrop-filter:blur(24px); }.thumb-bar button { display:flex; flex:1; min-width:48px; flex-direction:column; align-items:center; justify-content:center; gap:3px; border:0; border-radius:10px; color:#ffffff58; background:transparent; cursor:pointer; }.thumb-bar button span { font-size:1.25rem; line-height:1; }.thumb-bar button small { font-size:.6rem; }.thumb-bar button.active,.thumb-bar button:hover { color:#fff; background:#ffffff0b; }
</style>
