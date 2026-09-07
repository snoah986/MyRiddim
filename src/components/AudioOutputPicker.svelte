<script>
  import { onDestroy, onMount } from 'svelte'
  import { audio, getAudioOutputs } from '../lib/audio.js'

  export let compact = false
  let outputs = []
  let selectedDevice = ''
  let supported = true
  let busy = false
  let deviceChangeHandler

  async function refreshOutputs() {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.enumerateDevices) {
      supported = false
      return
    }
    outputs = await getAudioOutputs()
    if (!outputs.some(device => device.deviceId === selectedDevice)) {
      selectedDevice = outputs[0]?.deviceId || ''
    }
  }

  async function chooseOutput(event) {
    const deviceId = event.currentTarget.value
    if (!deviceId || busy) return
    busy = true
    try {
      await audio.setOutputDevice(deviceId)
      selectedDevice = deviceId
    } catch {
      // Unsupported or permission-blocked webviews keep the current route.
      await refreshOutputs()
    } finally {
      busy = false
    }
  }

  onMount(() => {
    refreshOutputs()
    deviceChangeHandler = () => refreshOutputs()
    navigator.mediaDevices?.addEventListener?.('devicechange', deviceChangeHandler)
  })

  onDestroy(() => {
    navigator.mediaDevices?.removeEventListener?.('devicechange', deviceChangeHandler)
  })
</script>

{#if supported && outputs.length > 0}
  <label class:compact class="output-picker" aria-label="Audio output">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10v4h4l5 4V6l-5 4H4zM16 8a6 6 0 0 1 0 8M19 5a10 10 0 0 1 0 14" /></svg>
    <select value={selectedDevice} on:change={chooseOutput} disabled={busy} aria-label="Audio output device">
      {#each outputs as device, index}
        <option value={device.deviceId}>{device.label || `Output ${index + 1}`}</option>
      {/each}
    </select>
  </label>
{/if}

<style>
  .output-picker { display:flex; align-items:center; gap:6px; min-width:0; color:#a99b8f; }
  .output-picker svg { width:17px; height:17px; flex:0 0 auto; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
  .output-picker select { min-width:92px; max-width:150px; border:1px solid #ffffff16; border-radius:7px; padding:5px 7px; color:#eee; background:#17171bf2; outline:none; cursor:pointer; font:500 .62rem Inter,ui-sans-serif,sans-serif; }
  .output-picker select:focus-visible { outline:2px solid #fff; outline-offset:2px; }
  .output-picker select:disabled { cursor:wait; opacity:.6; }
  .output-picker.compact select { width:28px; min-width:28px; padding:0; color:transparent; background:#ffffff08; }
  .output-picker.compact select option { color:#111; }
</style>
