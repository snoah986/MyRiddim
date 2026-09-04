<script>
  import { onMount } from 'svelte'
  import { settings, updateSetting } from '../lib/settings.js'
  import { apiFetch } from '../lib/api.js'

  export let onClose = () => {}
  export let onDisconnect = () => {}
  export let onToast = () => {}
  export let onDataRefresh = () => {}

  const APP_VERSION = 'v1.2.0-production'
  const BACKEND_PORT = 5178

  let cacheInfo = { count: 0, sizeBytes: 0 }
  let backendOk = false
  let backendSession = 'ok'
  let clearing = false
  let cleared = false
  let savingLimit = false
  let limitSaved = false
  let authUploading = false
  let accountName = ''

  const formatBytes = bytes => {
    if (!Number.isFinite(bytes)) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB']
    let value = bytes
    let i = 0
    while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1 }
    return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
  }
  const cacheBytes = () => cacheInfo.size_bytes ?? cacheInfo.sizeBytes ?? 0
  const cachePct = () => $settings.cacheLimitMb > 0 ? Math.min(100, (cacheBytes() / ($settings.cacheLimitMb * 1024 * 1024)) * 100) : 0

  onMount(async () => {
    try {
      const [settingsRes, healthRes, accountRes] = await Promise.all([apiFetch('/api/settings'), apiFetch('/api/health'), apiFetch('/api/account')])
      try {
        const accountData = await accountRes.json()
        if (accountData.authenticated && accountData.account?.name) accountName = accountData.account.name
      } catch { /* account info is best-effort */ }
      if (settingsRes.ok) {
        const data = await settingsRes.json()
        if (data.cache) cacheInfo = data.cache
        if (data.cache_limit_bytes) updateSetting('cacheLimitMb', Math.max(16, Math.round(data.cache_limit_bytes / 1024 / 1024)))
        if (data.quality) updateSetting('quality', data.quality)
      }
      // "expired" still means the backend itself is reachable (it reports the
      // lapsed session honestly), so it counts as online.
      const healthData = await healthRes.json()
      backendOk = healthRes.ok && ['ok', 'expired'].includes(healthData.status)
      backendSession = healthData.session || healthData.status
    } catch { backendOk = false }
  })

  async function saveCacheLimit() {
    const mb = Number($settings.cacheLimitMb)
    if (!Number.isFinite(mb) || mb < 16 || mb > 65536) { onToast('Cache limit must be between 16 and 65536 MB'); return }
    savingLimit = true
    try {
      const response = await apiFetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cache_limit_bytes: Math.round(mb * 1024 * 1024) }) })
      if (!response.ok) throw Error()
      const data = await response.json()
      if (data.cache) cacheInfo = data.cache
      limitSaved = true
      setTimeout(() => { limitSaved = false }, 1800)
      onToast('Cache limit saved')
    } catch { onToast('Could not save cache limit') } finally { savingLimit = false }
  }

  async function clearCache() {
    clearing = true
    try {
      const response = await apiFetch('/api/settings/cache/clear', { method: 'POST' })
      if (!response.ok) throw Error()
      const data = await response.json()
      if (data.cache) cacheInfo = data.cache
      cleared = true
      setTimeout(() => { cleared = false }, 2000)
    } catch { onToast('Could not clear cache') } finally { clearing = false }
  }

  async function onAuthFile(event) {
    const file = event.currentTarget.files?.[0]
    if (!file) return
    authUploading = true
    try {
      const text = await file.text()
      const response = await apiFetch('/api/auth/setup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ auth: text }) })
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || 'Could not apply the new credentials')
      onToast('Credentials updated')
      onDataRefresh()
    } catch (error) { onToast(error.message || 'Could not update credentials') } finally { authUploading = false; event.currentTarget.value = '' }
  }

  async function exportStats() {
    try {
      const response = await apiFetch('/api/stats/export')
      if (!response.ok) throw Error()
      const data = await response.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ytm-listening-stats-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      onToast(`Exported ${data.count} listening events`)
    } catch { onToast('Could not export stats') }
  }

  function resetLocalData() {
    if (!confirm('Reset all local settings and reload the app?')) return
    localStorage.clear()
    location.reload()
  }
</script>

<div class="backdrop" on:click|self={onClose}>
  <div class="sheet" role="dialog" aria-modal="true" aria-label="Settings">
    <header class="sheet-head">
      <div>
        <p class="eyebrow">CONTROL CENTER</p>
        <h2>Settings</h2>
      </div>
      <button class="close" on:click={onClose} aria-label="Close settings">×</button>
    </header>

    <div class="scroll">
      <!-- Playback & Streaming -->
      <section class="group">
        <h3 class="group-title">Playback &amp; Streaming</h3>
        <div class="row">
          <div class="row-label"><strong>Playback quality</strong><small>High uses WebM Opus, Medium uses M4A AAC, Data Saver caps the bitrate. Applies to the next track.</small></div>
          <div class="seg" role="group" aria-label="Playback quality">
            <button class:active={$settings.quality === 'high'} on:click={() => updateSetting('quality', 'high')}>High</button>
            <button class:active={$settings.quality === 'medium'} on:click={() => updateSetting('quality', 'medium')}>Medium</button>
            <button class:active={$settings.quality === 'low'} on:click={() => updateSetting('quality', 'low')}>Data Saver</button>
          </div>
        </div>
        <div class="row">
          <div class="row-label"><strong>Gapless crossfade</strong><small>Smoothly fades the next track in before the current one ends.</small></div>
          <label class="switch"><input type="checkbox" checked={$settings.crossfade} on:change={event => updateSetting('crossfade', event.currentTarget.checked)} /><span></span></label>
        </div>
        <div class="row sub" class:disabled={!$settings.crossfade}>
          <div class="row-label"><strong>Crossfade duration</strong><small>{$settings.crossfadeDuration || 0}s overlap</small></div>
          <input class="slider" type="range" min="0" max="12" step="0.5" value={$settings.crossfadeDuration} disabled={!$settings.crossfade} on:input={event => updateSetting('crossfadeDuration', Number(event.currentTarget.value))} aria-label="Crossfade duration in seconds" />
        </div>
        <div class="row">
          <div class="row-label"><strong>Instant queue flush</strong><small>Use one click instead of holding the trash control for 0.8 seconds.</small></div>
          <label class="switch"><input type="checkbox" checked={$settings.instantQueueFlush} on:change={event => updateSetting('instantQueueFlush', event.currentTarget.checked)} /><span></span></label>
        </div>
        <div class="row">
          <div class="row-label"><strong>Report plays to YouTube Music</strong><small>Scrobbles each listen back to your account so Quick Picks and mixes learn from what you actually play.</small></div>
          <label class="switch"><input type="checkbox" checked={$settings.scrobble !== false} on:change={event => updateSetting('scrobble', event.currentTarget.checked)} /><span></span></label>
        </div>
        <div class="row">
          <div class="row-label"><strong>Volume normalization</strong><small>Levels track loudness automatically via Web Audio (ReplayGain-style).</small></div>
          <label class="switch"><input type="checkbox" checked={$settings.volumeNormalize} on:change={event => updateSetting('volumeNormalize', event.currentTarget.checked)} /><span></span></label>
        </div>
      </section>

      <!-- App Shell -->
      <section class="group">
        <h3 class="group-title">App Shell</h3>
        <div class="row">
          <div class="row-label"><strong>Workspace layout</strong><small>Choose the navigation density that fits your screen.</small></div>
          <div class="seg shell-seg" role="group" aria-label="Workspace layout">
            <button class:active={$settings.shellLayout === 'sidebar'} on:click={() => updateSetting('shellLayout', 'sidebar')}>Sidebar</button>
            <button class:active={$settings.shellLayout === 'topbar'} on:click={() => updateSetting('shellLayout', 'topbar')}>Topbar</button>
            <button class:active={$settings.shellLayout === 'handheld'} on:click={() => updateSetting('shellLayout', 'handheld')}>Handheld</button>
          </div>
        </div>
      </section>

      <!-- Visuals & Motion -->
      <section class="group">
        <h3 class="group-title">Visuals &amp; Motion</h3>
        <div class="row">
          <div class="row-label"><strong>Reduce motion</strong><small>Disables ambient drift, card tilt, and decorative animations.</small></div>
          <label class="switch"><input type="checkbox" checked={$settings.reduceMotion} on:change={event => updateSetting('reduceMotion', event.currentTarget.checked)} /><span></span></label>
        </div>
        <div class="row">
          <div class="row-label"><strong>Theatre dynamic ambient</strong><small>Blurred, drifting artwork backdrop in Theatre Mode. Off uses a clean dark canvas.</small></div>
          <label class="switch"><input type="checkbox" checked={$settings.dynamicAmbient !== false} on:change={event => updateSetting('dynamicAmbient', event.currentTarget.checked)} /><span></span></label>
        </div>
      </section>

      <!-- Storage & Caching -->
      <section class="group">
        <h3 class="group-title">Storage &amp; Caching</h3>
        <div class="row">
          <div class="row-label"><strong>Audio cache</strong><small>{cacheInfo.count} files · {formatBytes(cacheBytes())}</small></div>
          <div class="cache-vis">
            <div class="cache-bar"><i style="width: {cachePct()}%"></i></div>
            <span class="cache-copy">Using {formatBytes(cacheBytes())} of {$settings.cacheLimitMb} MB limit</span>
          </div>
        </div>
        <div class="row sub">
          <div class="row-label"><strong>Cache size limit</strong><small>LRU ceiling (16–65536 MB). Oldest files evict automatically.</small></div>
          <div class="limit-row">
            <input type="number" min="16" max="65536" value={$settings.cacheLimitMb} on:input={event => updateSetting('cacheLimitMb', Number(event.currentTarget.value) || 0)} aria-label="Cache size limit in megabytes" />
            <span class="unit">MB</span>
            <button class="ghost" on:click={saveCacheLimit} disabled={savingLimit}>{savingLimit ? 'Saving…' : (limitSaved ? 'Saved ✓' : 'Save')}</button>
          </div>
        </div>
        <div class="row sub">
          <div class="row-label"><strong>Clear cached audio</strong><small>Frees disk space; tracks re-download on next play.</small></div>
          <button class="ghost warn" on:click={clearCache} disabled={clearing}>{cleared ? 'Cleared!' : (clearing ? 'Clearing…' : 'Clear cache')}</button>
        </div>
      </section>

      <!-- Account & Session -->
      <section class="group">
        <h3 class="group-title">Account &amp; Session</h3>
        <div class="row">
          <div class="row-label"><strong>YouTube Music</strong><small>{backendSession === 'expired' ? 'Session credentials have lapsed — reconnect to restore library access.' : (accountName ? `Connected as ${accountName}` : 'Connected via session credentials in the private user-data directory.')}</small></div>
          <span class="badge" class:warn={backendSession === 'expired'}><i></i>{backendSession === 'expired' ? 'Session expired' : 'Connected'}</span>
        </div>
        <div class="row sub">
          <div class="row-label"><strong>Update credentials</strong><small>Replace the session by uploading a new <code>browser.json</code> file. No restart needed.</small></div>
          <label class="ghost file-btn">{authUploading ? 'Uploading…' : 'Choose file'}<input type="file" accept=".json,application/json" on:change={onAuthFile} disabled={authUploading} /></label>
        </div>
        <div class="row sub">
          <div class="row-label"><strong>Export listening stats</strong><small>Download every recorded listen from the local SQLite database as JSON.</small></div>
          <button class="ghost" on:click={exportStats}>Export JSON</button>
        </div>
        <div class="row sub">
          <div class="row-label"><strong>Re-authenticate</strong><small>Disconnects and returns to the setup screen to paste fresh credentials.</small></div>
          <button class="ghost warn" on:click={onDisconnect}>Disconnect</button>
        </div>
      </section>

      <!-- Advanced Diagnostics -->
      <section class="group">
        <h3 class="group-title">Advanced Diagnostics</h3>
        <div class="row">
          <div class="row-label"><strong>Backend</strong><small>Local Flask bridge · port {BACKEND_PORT}</small></div>
          <span class="badge" class:down={!backendOk}><i></i>{backendOk ? 'Online' : 'Offline'}</span>
        </div>
        <div class="row">
          <div class="row-label"><strong>App version</strong><small>{APP_VERSION}</small></div>
          <span class="version">{APP_VERSION}</span>
        </div>
        <div class="row sub">
          <div class="row-label"><strong>Reset local data</strong><small>Clears stored settings and reloads. Your YouTube account is unaffected.</small></div>
          <button class="ghost danger" on:click={resetLocalData}>Reset</button>
        </div>
      </section>
    </div>
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; z-index: 90; display: grid; place-items: center; background: #00000099; animation: fadeIn .18s ease; }
  @keyframes fadeIn { from { opacity: 0 } }
  .sheet { width: min(640px, 92vw); max-height: min(84vh, 780px); display: flex; flex-direction: column; overflow: hidden; border: 1px solid rgba(255,255,255,.08); border-radius: 20px; background: rgba(15,15,18,.85); box-shadow: 0 25px 50px rgba(0,0,0,.6); backdrop-filter: blur(30px); color: #f4f4f5; font-family: Inter, ui-sans-serif, system-ui, sans-serif; animation: rise .22s cubic-bezier(.22,1,.36,1); }
  @keyframes rise { from { opacity: 0; transform: translateY(14px) scale(.98) } }
  .sheet-head { display: flex; align-items: center; justify-content: space-between; padding: 22px 26px 16px; border-bottom: 1px solid #ffffff12; }
  .sheet-head h2 { margin: 0; font-size: 1.45rem; font-weight: 700; letter-spacing: -.02em; }
  .eyebrow { margin: 0 0 5px; color: #a1a1aa; font-size: .62rem; font-weight: 700; letter-spacing: .18em; }
  .close { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid #ffffff1c; border-radius: 50%; color: #ddd; background: #ffffff0a; cursor: pointer; font-size: 1.15rem; transition: .15s ease; }
  .close:hover { background: #ffffff18; color: #fff; }
  .scroll { overflow-y: auto; padding: 6px 26px 24px; scrollbar-width: thin; scrollbar-color: #ffffff2e transparent; }
  .group { padding: 18px 0; border-bottom: 1px solid #ffffff0d; }
  .group:last-of-type { border-bottom: 0; }
  .group-title { margin: 0 0 12px; color: #a1a1aa; font-size: .66rem; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 11px 4px; }
  .row.sub { padding-left: 14px; border-left: 2px solid #ffffff10; }
  .row-label { min-width: 0; }
  .row-label strong { display: block; font-size: .9rem; font-weight: 600; }
  .row-label small { display: block; margin-top: 3px; color: #71717a; font-size: .74rem; line-height: 1.45; }
  .row-label code { padding: 1px 5px; border-radius: 5px; color: #c4b5fd; background: #ffffff0c; font-size: .72rem; }
  .seg { display: flex; gap: 4px; flex: 0 0 auto; padding: 3px; border: 1px solid #ffffff14; border-radius: 999px; background: #ffffff08; }
  .seg button { padding: 7px 14px; border: 0; border-radius: 999px; color: #b8b8c0; background: transparent; cursor: pointer; font-size: .78rem; font-weight: 600; transition: all .18s ease; }
  .seg button:hover { color: #fff; }
  .seg button.active { color: #111; background: var(--accent, #c4b5fd); box-shadow: 0 2px 12px color-mix(in srgb, var(--accent, #c4b5fd) 45%, transparent); }
  .shell-seg button { padding-inline: 10px; }
  .switch { position: relative; display: inline-flex; align-items: center; cursor: pointer; flex: 0 0 auto; }
  .switch input { position: absolute; opacity: 0; }
  .switch span { width: 42px; height: 24px; border-radius: 999px; background: #3a3a44; transition: background .2s ease; }
  .switch span::after { content: ''; position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%; background: #fff; transition: transform .2s ease; }
  .switch input:checked + span { background: var(--accent, #c4b5fd); }
  .switch input:checked + span::after { transform: translateX(18px); }
  .row.disabled { opacity: .45; pointer-events: none; }
  .slider { width: 170px; accent-color: var(--accent, #c4b5fd); }
  .cache-vis { flex: 1; min-width: 0; max-width: 260px; }
  .cache-bar { height: 7px; overflow: hidden; border-radius: 999px; background: #ffffff10; }
  .cache-bar i { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--accent, #c4b5fd), color-mix(in srgb, var(--accent, #c4b5fd) 55%, #fff)); box-shadow: 0 0 12px color-mix(in srgb, var(--accent, #c4b5fd) 40%, transparent); transition: width .35s ease; }
  .cache-copy { display: block; margin-top: 7px; color: #a1a1aa; font-size: .72rem; }
  .limit-row { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
  .limit-row input { width: 86px; padding: 8px 10px; border: 1px solid #ffffff1c; border-radius: 10px; color: #fff; background: #0004; font-size: .82rem; }
  .limit-row .unit { color: #71717a; font-size: .74rem; }
  .ghost { padding: 8px 14px; border: 1px solid #ffffff1a; border-radius: 999px; color: #eee; background: #ffffff0d; cursor: pointer; font-size: .78rem; font-weight: 600; white-space: nowrap; transition: all .15s ease; }
  .ghost:hover:not(:disabled) { background: #ffffff1c; color: #fff; }
  .ghost:disabled { opacity: .5; cursor: default; }
  .ghost.warn { color: #fbbf24; border-color: #fbbf2433; background: #fbbf240f; }
  .ghost.warn:hover:not(:disabled) { background: #fbbf241f; }
  .ghost.danger { color: #fca5a5; border-color: #fca5a533; background: #fca5a50f; }
  .ghost.danger:hover:not(:disabled) { background: #fca5a520; }
  .file-btn { position: relative; overflow: hidden; display: inline-block; }
  .file-btn input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  .badge { display: inline-flex; align-items: center; gap: 7px; padding: 5px 12px; border-radius: 999px; color: #86efac; background: #86efac14; font-size: .74rem; font-weight: 600; flex: 0 0 auto; } .badge.warn { color: #fbbf24; background: #fbbf2414; }
  .badge i { width: 7px; height: 7px; border-radius: 50%; background: #4ade80; box-shadow: 0 0 8px #4ade80; }
  .badge.down { color: #fca5a5; background: #fca5a514; }
  .badge.down i { background: #f87171; box-shadow: 0 0 8px #f87171; }
  .version { padding: 4px 10px; border: 1px solid #ffffff14; border-radius: 8px; color: #a1a1aa; font-size: .72rem; font-family: ui-monospace, monospace; flex: 0 0 auto; }
  @media (max-width: 560px) {
    .sheet { max-height: 92vh; border-radius: 16px; }
    .row { flex-wrap: wrap; }
    .seg { width: 100%; }
    .seg button { flex: 1; }
    .slider { width: 100%; }
  }
</style>