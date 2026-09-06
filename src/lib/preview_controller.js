export function createHoverPreview({ fetcher, isPlaying }) {
  let timer = null
  let fadeTimer = null
  let fadeInterval = null
  let video = null
  let audio = null
  let generation = 0
  let activeId = ''

  const itemKey = item => item?.videoId || item?.id || item?.browseId || item?.title || ''
  const isPreviewable = item => !item?.type || item.type === 'song' || Boolean(item?.videoId)

  function clearTimers() {
    clearTimeout(timer)
    clearTimeout(fadeTimer)
    clearInterval(fadeInterval)
    timer = null
    fadeTimer = null
    fadeInterval = null
  }

  function stop() {
    generation += 1
    activeId = ''
    clearTimers()
    video?.pause()
    video?.remove()
    video = null
    audio?.pause()
    audio?.removeAttribute('src')
    audio = null
  }

  async function startAudio(item, id, request) {
    if (!id || request !== generation || activeId !== id) return
    try {
      const response = await fetcher(`/api/stream/${encodeURIComponent(id)}`)
      const data = await response.json().catch(() => ({}))
      if (request !== generation || activeId !== id || !response.ok || !data.url) return

      const element = new Audio(data.url)
      audio = element
      element.volume = isPlaying() ? 0 : 0.42
      element.currentTime = 0
      element.addEventListener('timeupdate', () => {
        if (audio === element && element.currentTime >= 30) stop()
      })
      element.play().catch(() => {})

      fadeTimer = setTimeout(() => {
        if (audio !== element) return
        const startVolume = element.volume
        const started = Date.now()
        fadeInterval = setInterval(() => {
          if (audio !== element) return
          element.volume = Math.max(0, startVolume * (1 - (Date.now() - started) / 700))
          if (element.volume <= 0) {
            clearInterval(fadeInterval)
            fadeInterval = null
          }
        }, 50)
      }, 29300)
    } catch {
      // Hover previews are optional and must never affect primary playback.
    }
  }

  function start(item, node) {
    if (!isPreviewable(item)) return
    stop()
    activeId = itemKey(item)
    if (!activeId) return
    const id = activeId
    const request = generation
    timer = setTimeout(() => {
      if (request !== generation || activeId !== id) return
      const element = document.createElement('video')
      video = element
      element.src = `/media/loops/${encodeURIComponent(id)}.mp4`
      element.muted = true
      element.loop = true
      element.autoplay = true
      element.playsInline = true
      element.className = 'hover-video'
      element.addEventListener('error', () => {
        if (request !== generation || video !== element) return
        element.remove()
        video = null
        startAudio(item, id, request)
      }, { once: true })
      element.addEventListener('playing', () => {
        if (request !== generation || video !== element) return
        if (!isPlaying()) startAudio(item, id, request)
      }, { once: true })
      node?.querySelector('.media-frame')?.appendChild(element)
      element.play().catch(() => {
        if (request === generation && video === element) startAudio(item, id, request)
      })
    }, 350)
  }

  return { start, stop, destroy: stop }
}
