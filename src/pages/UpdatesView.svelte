<script>
  const updates = [
    {
      tag: 'v1.4.0', title: 'Theatre, Lyrics, and Remote Control', date: '2026-09-05', commit: '7f0bd81', latest: true,
      items: [
        ['AUDIO/VISUAL', 'Kinetic Lyrics', 'Apple Music style word pop, line scaling, timing sync, and dark readability scrims.'],
        ['AUDIO/VISUAL', 'Smart Media', 'Companion video, max resolution artwork fallback, and non blocking media errors.'],
        ['CONTROLS', 'Theatre Deck', 'Play, seek, skip, shuffle, repeat, queue, lyrics, video, and volume controls.'],
        ['REMOTE', 'Mobile Remote', 'Zero config web controller served on the local network at /remote.'],
        ['FIXES', 'Playback Safety', 'Audio source changes now load cleanly and rejected play promises are handled.']
      ]
    },
    {
      tag: 'v1.3.0', title: 'Search and Entity Navigation', date: '2026-09-05', commit: '137655e',
      items: [
        ['CONTROLS', 'Instant Search', 'The first keystroke opens Search while focus stays in the input.'],
        ['AUDIO/VISUAL', 'Categorized Results', 'Top Result, Songs, Artists, Albums, and Playlists render in one result surface.'],
        ['REMOTE', 'Entity Links', 'Artist and album metadata opens the correct catalog or scoped fallback search.'],
        ['FIXES', 'Event Isolation', 'Nested actions stop propagation so likes and entity links do not start playback.']
      ]
    },
    {
      tag: 'v1.2.0', title: 'Home Feed and Smart Discovery', date: '2026-09-05', commit: '78cd376',
      items: [
        ['AUDIO/VISUAL', 'Hover Previews', '16:9 track cards use silent video first with an audio preview fallback.'],
        ['CONTROLS', 'Mixer Desk', 'Four artist slots, first free slot assignment, and alternating artist mixes.'],
        ['REMOTE', 'Sub Genre Routing', 'UK Real Rap, UK Drill, US Trap, Pluggnb, Afroswing, R&B, and Wave seed feeds.'],
        ['FIXES', 'Shelf Loading', 'Horizontal shelves scroll smoothly and vertical feed pages load on demand.'],
        ['FIXES', 'Artist Data', 'Mixer artists now carry stable IDs, names, thumbnails, and accessible pressed state.']
      ]
    },
    {
      tag: 'v1.1.0', title: 'Obsidian UI and Media Pipeline', date: '2026-09-05', commit: 'b13a354',
      items: [
        ['AUDIO/VISUAL', 'Obsidian Surface', 'OLED black surfaces, high contrast type, restrained borders, and compact telemetry.'],
        ['AUDIO/VISUAL', 'Media Engine', 'Direct track loop extraction with 1080p and 720p quality fallbacks.'],
        ['REMOTE', 'Desktop Shell', 'Frameless Tauri shell and universal 0.0.0.0 backend binding.'],
        ['FIXES', 'Media Resilience', 'Missing ffmpeg and autoplay failures produce safe fallbacks instead of crashes.']
      ]
    },
    {
      tag: 'v1.0.0', title: 'Party Mode and Local Sync', date: '2026-09-05', commit: '2bad46b',
      items: [
        ['REMOTE', 'Party Rooms', 'Host rooms support guest requests, approvals, roles, voting, and queue reconciliation.'],
        ['CONTROLS', 'Shared Queue', 'Persistent history, manual queue management, radio continuation, and playlist saving.'],
        ['REMOTE', 'Mobile Access', 'LAN address resolution, public URL support, Vite host access, and QR invites.'],
        ['FIXES', 'Lifecycle Cleanup', 'Party polling, tunnel processes, queue state, and browser lifecycle events clean up safely.']
      ]
    },
    {
      tag: 'v0.9.0', title: 'Lyrics Timing and Release Automation', date: '2026-09-04', commit: 'e2d5178',
      items: [
        ['AUDIO/VISUAL', 'Lyrics Engine', 'Word spacing, cadence conversion, line timing estimates, and duration gates.'],
        ['REMOTE', 'Provider Fallbacks', 'Sanitized metadata supports LRCLIB and native YouTube Music lyric paths.'],
        ['CONTROLS', 'Release Automation', 'GitHub Actions workflows package cloud and desktop builds repeatably.'],
        ['FIXES', 'Timing Repair', 'Enhanced lyric tokens no longer collapse into unreadable words.']
      ]
    },
    {
      tag: 'FOUNDATION', title: 'Tauri Shell and Security Hardening', date: '2026-09-03', commit: '3fca309',
      items: [
        ['REMOTE', 'Desktop Runtime', 'Tauri provides the native shell and packaged frontend.'],
        ['FIXES', 'Bridge Boundaries', 'The packaged frontend and local Flask service have a constrained integration boundary.'],
        ['CONTROLS', 'CI Packaging', 'Initial continuous integration workflows establish reproducible release artifacts.']
      ]
    }
  ]

  let expanded = new Set(['v1.4.0', 'v1.3.0'])

  function toggleDetails(tag) {
    const next = new Set(expanded)
    if (next.has(tag)) next.delete(tag)
    else next.add(tag)
    expanded = next
  }
</script>

<section class="updates-page" aria-labelledby="updates-title">
  <header class="updates-header">
    <div>
      <span class="eyebrow">PRODUCT HISTORY</span>
      <h1 id="updates-title">Updates</h1>
    </div>
    <span class="entry-count">{updates.length} milestones</span>
  </header>

  <div class="timeline">
    {#each updates as update, index (update.commit)}
      <article class="update-entry">
        <div class:latest={update.latest} class="timeline-node" aria-hidden="true"><span>{String(index + 1).padStart(2, '0')}</span></div>
        <div class="update-card">
          <header class="entry-header">
            <div class="entry-title">
              <div class="version-line"><h2>{update.tag}</h2>{#if update.latest}<span class="latest-tag">LATEST</span>{/if}</div>
              <h3>{update.title}</h3>
              <time datetime={update.date}>{update.date}</time>
            </div>
            <code class="commit-pill">{update.commit}</code>
          </header>

          {#if expanded.has(update.tag)}
            <div class="entry-body">
              {#each update.items as item}
                <div class="update-item">
                  <span class="category">[{item[0]}]</span>
                  <p><strong>{item[1]}:</strong> {item[2]}</p>
                </div>
              {/each}
            </div>
          {/if}

          {#if !update.latest && update.tag !== 'v1.3.0'}
            <button type="button" class="details-toggle" on:click={() => toggleDetails(update.tag)} aria-expanded={expanded.has(update.tag)}>
              {expanded.has(update.tag) ? 'Hide details' : 'Show details'}
              <span class:open={expanded.has(update.tag)} aria-hidden="true">⌄</span>
            </button>
          {/if}
        </div>
      </article>
    {/each}
  </div>
</section>

<style>
  .updates-page { min-height:100%; box-sizing:border-box; padding:32px 24px 64px; color:#ededed; background:#000; font-family:Inter,ui-sans-serif,system-ui,sans-serif; }
  .updates-header,.timeline { width:min(896px,100%); margin-inline:auto; }
  .updates-header { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; margin-bottom:32px; }
  .eyebrow { display:block; margin-bottom:9px; color:#71717a; font:700 10px ui-monospace,SFMono-Regular,monospace; letter-spacing:.16em; }
  h1 { margin:0; color:#fff; font-size:clamp(2.3rem,6vw,4rem); font-weight:800; letter-spacing:-.07em; line-height:.95; }
  .entry-count { color:#71717a; font:500 10px ui-monospace,SFMono-Regular,monospace; letter-spacing:.12em; text-transform:uppercase; }
  .timeline { position:relative; padding-left:16px; border-left:1px solid rgba(255,255,255,.1); }
  .update-entry { position:relative; margin:0 0 48px; padding-left:32px; }
  .timeline-node { position:absolute; z-index:1; top:8px; left:-17px; display:grid; place-items:center; width:32px; height:32px; border:1px solid rgba(255,255,255,.14); border-radius:50%; color:#71717a; background:#000; font:600 9px ui-monospace,SFMono-Regular,monospace; transition:border-color .2s ease,background .2s ease; }
  .timeline-node.latest { border-color:rgba(52,211,153,.65); color:#a7f3d0; box-shadow:0 0 0 4px rgba(16,185,129,.08); }
  .timeline-node.latest::after { content:''; position:absolute; width:8px; height:8px; border-radius:50%; background:#6ee7b7; }
  .timeline-node.latest span { opacity:0; }
  .update-card { padding:24px; border:1px solid rgba(255,255,255,.1); border-radius:12px; background:rgba(23,23,23,.4); backdrop-filter:blur(12px); transition:border-color .2s ease,background .2s ease,transform .2s ease; }
  .update-card:hover { border-color:rgba(255,255,255,.2); background:rgba(255,255,255,.05); transform:translateY(-1px); }
  .entry-header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
  .entry-title { min-width:0; }
  .version-line { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
  .version-line h2 { margin:0; color:#fff; font-size:1.25rem; font-weight:800; letter-spacing:-.04em; }
  .latest-tag { padding:4px 8px; border:1px solid rgba(52,211,153,.28); border-radius:6px; color:#a7f3d0; background:rgba(52,211,153,.08); font:700 9px ui-monospace,SFMono-Regular,monospace; letter-spacing:.08em; transition:background .2s ease,border-color .2s ease; }
  .entry-title h3 { margin:8px 0 4px; color:#d4d4d8; font-size:.85rem; font-weight:600; }
  .entry-title time { color:#71717a; font:500 10px ui-monospace,SFMono-Regular,monospace; }
  .commit-pill { flex:0 0 auto; padding:4px 8px; border:1px solid rgba(255,255,255,.1); border-radius:6px; color:#a1a1aa; background:rgba(255,255,255,.05); font:500 10px ui-monospace,SFMono-Regular,monospace; transition:color .2s ease,border-color .2s ease,background .2s ease; }
  .commit-pill:hover { border-color:rgba(255,255,255,.2); color:#fff; background:rgba(255,255,255,.1); }
  .entry-body { display:grid; gap:8px; margin-top:24px; padding-top:16px; border-top:1px solid rgba(255,255,255,.07); }
  .update-item { display:grid; grid-template-columns:max-content minmax(0,1fr); align-items:baseline; gap:12px; }
  .category { color:#a1a1aa; font:700 9px ui-monospace,SFMono-Regular,monospace; letter-spacing:.04em; white-space:nowrap; }
  .update-item p { margin:0; color:#a1a1aa; font-size:.74rem; line-height:1.5; }
  .update-item strong { color:#f4f4f5; font-weight:700; }
  .details-toggle { display:flex; align-items:center; gap:8px; margin-top:16px; padding:4px 0; border:0; color:#71717a; background:transparent; cursor:pointer; font:600 10px ui-monospace,SFMono-Regular,monospace; transition:color .2s ease,transform .2s ease; }
  .details-toggle:hover { color:#fff; }.details-toggle:active { transform:scale(.99); }
  .details-toggle span { display:inline-block; font-size:14px; line-height:.7; transition:transform .2s ease; }
  .details-toggle span.open { transform:rotate(180deg); }
  @media(max-width:600px) {
    .updates-page { padding:24px 16px 48px; }
    .updates-header { align-items:flex-start; flex-direction:column; gap:16px; margin-bottom:24px; }
    .entry-count { align-self:flex-end; }
    .timeline { padding-left:16px; }
    .update-entry { padding-left:24px; }
    .timeline-node { left:-17px; width:32px; height:32px; }
    .update-card { padding:16px; }
    .entry-header { gap:12px; }
    .commit-pill { padding:4px 8px; }
    .update-item { grid-template-columns:1fr; gap:4px; }
  }
</style>
