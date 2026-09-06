<script>
  import WindowControls from '../components/WindowControls.svelte'

  export let homeView = 'home'
  export let searchQuery = ''
  export let onSearchChanged = () => {}
  export let onViewChange = () => {}
  export let onCreatePlaylist = () => {}
  export let onOpenSmartCreator = () => {}
  export let onOpenSettings = () => {}
  export let playlists = []
  export let onOpenPlaylist = () => {}
  export let onOpenTheatre = () => {}

  const navItems = [
    ['home', 'Home'],
    ['recent', 'Recently played'],
    ['favorites', 'Favorites'],
    ['discover', 'Discover'],
    ['stats', 'Listening stats'],
    ['updates', 'Updates'],
  ]
</script>

<div class="shell sidebar-shell">
  <aside class="rail" aria-label="Primary navigation">
    <div class="brand"><span class="brand-mark">♫</span><span>myriddim</span></div>
    <nav class="nav-list" aria-label="Library">
      {#each navItems as item}
        <button class:active={homeView === item[0]} on:click={() => onViewChange(item[0])}>{item[1]}</button>
      {/each}
    </nav>
    <div class="rail-section">
      <div class="rail-section-head"><span>Pinned playlists</span><button on:click={onCreatePlaylist} aria-label="Create playlist">+</button></div>
      <div class="playlist-links">
        {#each playlists.slice(0, 8) as playlist (playlist.id)}
          <button on:click={() => onOpenPlaylist(playlist)} title={playlist.title}>{playlist.title}</button>
        {/each}
        {#if !playlists.length}<span class="muted">No playlists yet</span>{/if}
      </div>
    </div>
    <div class="rail-footer">
      <button class="dsp" on:click={onOpenSettings}><span class="dsp-dot"></span><span>Legion Go DSP</span><small>Settings</small></button>
    </div>
  </aside>
  <div class="shell-main">
    <header class="shell-topbar" data-tauri-drag-region>
      <label class="shell-search" style="-webkit-app-region: no-drag;"><span aria-hidden="true">⌕</span><input style="-webkit-app-region: no-drag;" class="global-search" value={searchQuery} on:input={onSearchChanged} placeholder="Search your library" aria-label="Search your library" /><kbd>Ctrl K</kbd></label>
      <div class="shell-actions" style="-webkit-app-region: no-drag;"><button style="-webkit-app-region: no-drag;" on:click={onCreatePlaylist}>+ Playlist</button><button style="-webkit-app-region: no-drag;" on:click={onOpenSmartCreator}>Smart</button><button style="-webkit-app-region: no-drag;" class="settings" on:click={onOpenSettings} aria-label="Open settings">⚙</button><WindowControls /></div>
    </header>
    <main class="shell-content"><slot /></main>
  </div>
</div>

<style>
  .shell { display:flex; flex:1 1 auto; min-height:0; color:#f4f4f5; background:#09090b; font-family:Inter,ui-sans-serif,system-ui,sans-serif; }
  .sidebar-shell { display:grid; grid-template-columns:240px minmax(0,1fr); }
  .rail { position:sticky; top:0; display:flex; flex:0 0 240px; height:100%; box-sizing:border-box; flex-direction:column; padding:24px 16px 18px; border-right:1px solid #ffffff0f; background:#0b0b0d; }
  .brand { display:flex; align-items:center; gap:10px; padding:0 10px 30px; color:#fff; font-size:1.05rem; font-weight:750; letter-spacing:-.03em; }.brand-mark { display:grid; place-items:center; width:30px; height:30px; border:1px solid #ffffff18; border-radius:9px; color:#09090b; background:#fff; }
  .nav-list { display:flex; flex-direction:column; gap:4px; }.nav-list button,.playlist-links button,.rail-section-head button,.dsp { border:0; color:#ffffff85; background:none; cursor:pointer; text-align:left; font:inherit; }.nav-list button { padding:11px 12px; border-radius:10px; font-size:.8rem; transition:color .18s ease,background .18s ease; }.nav-list button:hover,.nav-list button.active { color:#fff; background:#ffffff0b; }.nav-list button.active { box-shadow:inset 2px 0 #fff; }
  .rail-section { min-height:0; margin-top:34px; }.rail-section-head { display:flex; align-items:center; justify-content:space-between; padding:0 10px 9px; color:#ffffff42; font:700 .6rem/1 Inter,sans-serif; letter-spacing:.14em; text-transform:uppercase; }.rail-section-head button { width:22px; height:22px; border-radius:6px; color:#ffffff90; text-align:center; }.rail-section-head button:hover { color:#fff; background:#ffffff12; }.playlist-links { display:flex; max-height:40vh; flex-direction:column; gap:2px; overflow:auto; }.playlist-links button { overflow:hidden; padding:8px 10px; border-radius:8px; color:#ffffff70; font-size:.74rem; text-overflow:ellipsis; white-space:nowrap; }.playlist-links button:hover { color:#fff; background:#ffffff08; }.muted { padding:8px 10px; color:#ffffff35; font-size:.72rem; }.rail-footer { margin-top:auto; }.dsp { display:grid; grid-template-columns:10px 1fr auto; align-items:center; gap:8px; width:100%; padding:10px; border:1px solid #ffffff0d; border-radius:12px; background:#ffffff06; font-size:.68rem; }.dsp:hover { background:#ffffff0b; }.dsp small { color:#ffffff35; font-size:.6rem; }.dsp-dot { width:7px; height:7px; border-radius:50%; background:#a78bfa; box-shadow:0 0 10px #a78bfa; }
  .shell-main { display:flex; flex:1 1 auto; min-width:0; min-height:0; flex-direction:column; }.shell-topbar { position:sticky; top:0; z-index:20; display:flex; align-items:center; justify-content:space-between; gap:20px; min-height:72px; box-sizing:border-box; padding:15px 32px; border-bottom:1px solid #ffffff0b; background:#09090be6; backdrop-filter:blur(20px); }.shell-search { display:flex; align-items:center; gap:10px; width:min(430px,55vw); padding:10px 14px; border:1px solid #ffffff0e; border-radius:12px; color:#ffffff55; background:#ffffff06; }.shell-search input { width:100%; min-width:0; border:0; outline:0; color:#fff; background:transparent; font:inherit; font-size:.8rem; }.shell-search kbd { color:#ffffff32; font:500 .6rem ui-monospace,monospace; white-space:nowrap; }.shell-actions { display:flex; align-items:center; gap:7px; }.shell-actions button { padding:8px 11px; border:1px solid #ffffff10; border-radius:8px; color:#ffffff70; background:#ffffff06; cursor:pointer; font:600 .68rem Inter,sans-serif; }.shell-actions button:hover { color:#fff; background:#ffffff10; }.shell-actions .settings { border:0; background:none; font-size:.9rem; }  .shell-content { flex:1 1 auto; min-width:0; min-height:0; overflow-y:auto; scrollbar-gutter:stable; }
  @media(max-width:900px) { .sidebar-shell { grid-template-columns:76px minmax(0,1fr); }.rail { padding:18px 10px; }.brand { justify-content:center; padding-inline:0; }.brand > span:last-child,.nav-list button,.rail-section,.rail-footer { font-size:0; }.brand > span:last-child { display:none; }.nav-list button { height:42px; padding:0; text-align:center; }.nav-list button::first-letter { font-size:1rem; }.shell-topbar { padding-inline:20px; }.shell-search { width:min(360px,60vw); } }
  @media(max-width:560px) { .sidebar-shell { display:block; padding-bottom:70px; }.rail { position:fixed; inset:auto 0 0; z-index:40; display:flex; height:62px; flex-direction:row; align-items:center; justify-content:space-around; padding:6px 8px; border-top:1px solid #ffffff12; border-right:0; }.brand,.rail-section,.rail-footer { display:none; }.nav-list { display:flex; width:100%; flex-direction:row; justify-content:space-around; }.nav-list button { flex:1; height:48px; font-size:.58rem; }.nav-list button::after { content:attr(aria-label); }.shell-topbar { min-height:62px; padding:10px 14px; }.shell-search { width:100%; }.shell-actions { display:none; } }
</style>
