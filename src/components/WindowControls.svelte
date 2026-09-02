<script>
  // Renders only when running inside the Tauri webview (the frameless window has
  // no native chrome). Browser builds skip it entirely; the @tauri-apps/api module
  // is dynamically imported so it never loads outside Tauri.
  let isTauri = false
  let maxed = false
  let win = null

  async function detect() {
    if (typeof window === 'undefined' || !('__TAURI_INTERNALS__' in window)) return
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window')
      win = getCurrentWindow()
      maxed = await win.isMaximized()
      win.onResized(() => { win.isMaximized().then(value => { maxed = value }).catch(() => {}) })
      isTauri = true
    } catch { /* IPC unavailable — stay hidden */ }
  }
  detect()
</script>

{#if isTauri}
<div class="win-controls">
  <button class="wc" on:click={() => win?.minimize()} aria-label="Minimize">−</button>
  <button class="wc" on:click={() => win?.toggleMaximize()} aria-label={maxed ? 'Restore' : 'Maximize'}>{maxed ? '❐' : '□'}</button>
  <button class="wc close" on:click={() => win?.close()} aria-label="Close">✕</button>
</div>
{/if}

<style>
  .win-controls { display: flex; align-items: center; gap: 2px; margin-left: 10px; -webkit-app-region: no-drag; }
  .wc { width: 34px; height: 30px; display: grid; place-items: center; border: 0; border-radius: 7px; color: #c8c8d0; background: transparent; cursor: pointer; font-size: .8rem; line-height: 1; transition: background .15s ease, color .15s ease; }
  .wc:hover { background: #ffffff18; color: #fff; }
  .wc.close:hover { background: #e81123; color: #fff; }
</style>