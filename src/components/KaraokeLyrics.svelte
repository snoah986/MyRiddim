<script>
  import { onDestroy } from 'svelte'

  export let lines = []
  export let media = null
  export let currentTime = 0
  export let clock = null
  export let playing = false
  export let onSeek = () => {}
  export let onSync = () => {}

  let container
  let raf = 0
  const syncState = { lastLine: -1 }
  const lineElements = []
  const wordElements = new Map()

  function registerLine(node, index) {
    lineElements[index] = node
    return {
      update(nextIndex) {
        if (lineElements[index] === node) lineElements[index] = null
        lineElements[nextIndex] = node
        index = nextIndex
      },
      destroy() {
        if (lineElements[index] === node) lineElements[index] = null
      }
    }
  }

  function registerWord(node, key) {
    wordElements.set(key, node)
    return {
      update(nextKey) {
        if (wordElements.get(key) === node) wordElements.delete(key)
        wordElements.set(nextKey, node)
        key = nextKey
      },
      destroy() {
        if (wordElements.get(key) === node) wordElements.delete(key)
      }
    }
  }

  function time() {
    // An explicit clock function takes precedence so Theatre Mode can feed a
    // studio-referenced lyric time (VideoTime - introOffset) instead of raw
    // media currentTime during video playback.
    if (typeof clock === 'function') {
      const value = Number(clock())
      return Number.isFinite(value) ? value : 0
    }
    const value = Number(media?.currentTime)
    return Number.isFinite(value) ? value : Number(currentTime) || 0
  }

  function sync() {
    const now = time()
    let active = -1
    lineElements.forEach((node, index) => {
      if (!node) return
      const start = Number(node.dataset.start)
      const end = Number(node.dataset.end)
      const isActive = start <= now && now < end
      if (isActive) active = index
      node.classList.toggle('active', isActive)
      node.style.setProperty('--line-progress', isActive && end > start ? String(Math.max(0, Math.min(1, (now - start) / (end - start)))) : '0')
      node.style.setProperty('--line-distance', String(Math.min(1, Math.abs(now - start) / 3)))
      if (isActive && syncState.lastLine !== index) {
        node.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    })
    wordElements.forEach(node => {
      const start = Number(node.dataset.start)
      const end = Number(node.dataset.end)
      const progress = end > start ? Math.max(0, Math.min(1, (now - start) / (end - start))) : now >= start ? 1 : 0
      node.style.setProperty('--word-progress', String(progress))
      node.classList.toggle('past', now >= end)
      node.classList.toggle('current', now >= start && now < end)
    })
    syncState.lastLine = active
    if (playing || media && !media.paused) raf = requestAnimationFrame(sync)
  }

  $: if (lines || playing || media) {
    syncState.lastLine = -1
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(sync)
  }

  onDestroy(() => cancelAnimationFrame(raf))
</script>

<div class="karaoke-scroll" bind:this={container} aria-label="Syllable-synced lyrics">
  {#each lines as line, index}
    <button
      use:registerLine={index}
      class="karaoke-line"
      class:intro-line={line.isIntro}
      class:prompt-line={line.isPrompt}
      data-start={line.start}
      data-end={line.end}
      on:click={() => line.isPrompt ? onSync() : onSeek(Number(line.start))}
      aria-label={line.isPrompt ? 'Sync karaoke beat' : `Seek to ${line.text || 'lyric line'}`}>
      {#if line.words?.length}
        {#each line.words as word}
          <span use:registerWord={`${index}:${word.start}:${word.end}`} class="karaoke-word" data-start={word.start} data-end={word.end}>{word.text}</span>
        {/each}
      {:else}
        <span class="karaoke-plain">{line.text}</span>
      {/if}
    </button>
  {/each}
</div>

<style>
  .karaoke-scroll { flex:1; min-height:0; overflow-y:auto; padding:34vh 1rem 30vh; mask-image:linear-gradient(to bottom,transparent 0%,black 15%,black 85%,transparent 100%); }
  .karaoke-line { display:block; width:100%; padding:.62rem 0; border:0; color:#fff; background:none; text-align:center; font:650 clamp(1.35rem,3.3vw,2.7rem)/1.25 Inter,ui-sans-serif,sans-serif; letter-spacing:-.035em; opacity:.28; filter:blur(.8px); transform:scale(.96); cursor:pointer; transition:all .3s cubic-bezier(.2,0,0,1); }
  .karaoke-line:global(.active) { opacity:1; filter:blur(0); transform:scale(1.04); }
  .karaoke-line.intro-line { opacity:.9; }
  .karaoke-line.prompt-line { padding:.8rem 1rem; border:1px solid #ffffff2c; border-radius:14px; background:#ffffff10; opacity:.95; }
  .karaoke-word { --word-progress:0; display:inline-block; margin-right:.32em; color:rgba(255,255,255,.4); opacity:1; transition:transform .12s ease,color .12s ease,text-shadow .12s ease; white-space:pre-wrap; }
  .karaoke-word:global(.past) { color:#fff; }
  .karaoke-word:global(.current) { color:#fff; font-weight:700; transform:scale(1.14); text-shadow:0 0 20px rgba(255,255,255,.85),0 0 35px rgba(255,255,255,.4); }
  .karaoke-word:global(.current) + .karaoke-word { margin-left:.02em; }
  .karaoke-line:focus-visible { outline:2px solid #fff; outline-offset:4px; border-radius:8px; }
  @media (prefers-reduced-motion:reduce) { .karaoke-line,.karaoke-word { transition:none; } }
</style>
