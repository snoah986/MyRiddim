<script>
  import { createEventDispatcher } from 'svelte'
  import { apiFetch } from '../lib/api.js'

  export let isOpen = false
  const dispatch = createEventDispatcher()

  const fields = [
    { id: 'artist', label: 'Artist name', operator: 'contains', type: 'text', defaultOp: 'LIKE' },
    { id: 'play_count', label: 'Play count', operator: 'at least', type: 'number', defaultOp: '>=' },
    { id: 'last_played', label: 'Last played', operator: 'older than', type: 'date', defaultOp: '<' },
    { id: 'skips', label: 'Skip count', operator: 'at most', type: 'number', defaultOp: '<=' },
  ]
  const dates = [
    { value: '-7 days', label: '7 days' },
    { value: '-30 days', label: '30 days' },
    { value: '-60 days', label: '60 days' },
    { value: '-180 days', label: '6 months' },
  ]

  let playlistName = 'My Smart Mix'
  let limit = 50
  let rules = [{ field: 'play_count', op: '>=', val: '3' }]
  let isSubmitting = false
  let errorMessage = ''

  function configFor(field) { return fields.find(item => item.id === field) || fields[0] }
  function addRule() { rules = [...rules, { field: 'artist', op: 'LIKE', val: '' }] }
  function removeRule(index) { rules = rules.filter((_, current) => current !== index) }
  function handleFieldChange(index, field) {
    const config = configFor(field)
    rules[index] = { field, op: config.defaultOp, val: config.type === 'date' ? '-60 days' : '' }
    rules = [...rules]
  }
  function close() {
    if (!isSubmitting) {
      isOpen = false
      dispatch('close')
    }
  }
  async function handleCreate() {
    if (!playlistName.trim()) { errorMessage = 'Please enter a playlist name.'; return }
    const validRules = rules.filter(rule => String(rule.val ?? '').trim() !== '')
    if (!validRules.length) { errorMessage = 'Add at least one condition with a value.'; return }
    isSubmitting = true
    errorMessage = ''
    try {
      const response = await apiFetch('/api/playlists/smart/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: playlistName.trim(), rules: validRules, limit: Number(limit) }),
      })
      const data = await response.json()
      if (!response.ok || data.error) throw Error(data.error || `Server returned ${response.status}`)
      dispatch('saved', data)
      isOpen = false
    } catch (error) {
      errorMessage = `Failed to save recipe: ${error.message}`
    } finally { isSubmitting = false }
  }
</script>

{#if isOpen}
  <div class="backdrop" role="presentation" on:click|self={close}>
    <section class="sheet" role="dialog" aria-modal="true" aria-labelledby="smart-title">
      <header class="sheet-head">
        <div><p class="eyebrow">LOCAL AUTOMATION</p><h2 id="smart-title">New Smart Playlist</h2><p class="subtitle">A living collection built from your listening history.</p></div>
        <button class="close" type="button" on:click={close} aria-label="Close smart playlist builder">×</button>
      </header>

      <label class="field-label" for="smart-name">Playlist name</label>
      <input id="smart-name" class="text-input" bind:value={playlistName} placeholder="e.g. Forgotten favorites" />

      <div class="criteria-head"><span class="field-label">Matching criteria</span><span class="and-pill">ALL conditions</span><button type="button" class="add-rule" on:click={addRule}>＋ Add condition</button></div>
      <div class="rules" aria-label="Smart playlist conditions">
        {#each rules as rule, index}
          {@const config = configFor(rule.field)}
          <div class="rule-row">
            <select aria-label="Condition field" value={rule.field} on:change={(event) => handleFieldChange(index, event.currentTarget.value)}>
              {#each fields as field}<option value={field.id}>{field.label}</option>{/each}
            </select>
            <span class="operator">{config.operator}</span>
            {#if config.type === 'date'}
              <select aria-label="Condition value" bind:value={rule.val}>{#each dates as date}<option value={date.value}>{date.label}</option>{/each}</select>
            {:else}
              <input aria-label="Condition value" type={config.type} min={config.type === 'number' ? 0 : undefined} placeholder={config.type === 'text' ? 'Artist name' : '0'} bind:value={rule.val} />
            {/if}
            {#if rules.length > 1}<button type="button" class="remove-rule" on:click={() => removeRule(index)} aria-label="Remove condition">×</button>{/if}
          </div>
        {/each}
      </div>

      <div class="options"><label class="field-label" for="smart-limit">Maximum tracks</label><input id="smart-limit" class="limit-input" type="number" min="1" max="200" bind:value={limit} /><span class="option-help">Results are re-evaluated whenever you open the collection.</span></div>
      {#if errorMessage}<p class="error" role="alert">{errorMessage}</p>{/if}
      <footer class="sheet-foot"><button type="button" class="cancel" on:click={close}>Cancel</button><button type="button" class="save" disabled={isSubmitting} on:click={handleCreate}>{isSubmitting ? 'Saving…' : 'Save Smart Playlist'}</button></footer>
    </section>
  </div>
{/if}

<style>
  .backdrop { position: fixed; inset: 0; z-index: 100; display: grid; place-items: center; padding: 18px; background: #000b; backdrop-filter: blur(12px); }
  .sheet { width: min(560px, 100%); max-height: min(88vh, 720px); overflow: auto; box-sizing: border-box; padding: 26px; border: 1px solid #ffffff18; border-radius: 20px; color: #f4f4f5; background: rgba(18, 18, 23, .96); box-shadow: 0 28px 80px #000b; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
  .sheet-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding-bottom: 18px; border-bottom: 1px solid #ffffff0d; }
  .eyebrow { margin: 0 0 6px; color: var(--accent, #c4b5fd); font-size: .65rem; font-weight: 700; letter-spacing: .15em; }.sheet h2 { margin: 0; font-family: Outfit, Inter, sans-serif; font-size: 1.45rem; letter-spacing: -.025em; }.subtitle { margin: 5px 0 0; color: #92929d; font-size: .78rem; }.close { width: 30px; height: 30px; border: 0; border-radius: 50%; color: #a1a1aa; background: #ffffff0b; cursor: pointer; font-size: 1.2rem; }.close:hover { color: #fff; background: #ffffff18; }
  .field-label { display: block; color: #c4c4cc; font-size: .73rem; font-weight: 600; }.sheet > .field-label { margin-top: 20px; }.text-input, .rule-row input, .rule-row select, .limit-input { box-sizing: border-box; border: 1px solid #ffffff16; border-radius: 9px; color: #eee; background: #08080b; outline: none; font: inherit; font-size: .78rem; transition: border-color .18s ease, background .18s ease; }.text-input { width: 100%; margin-top: 7px; padding: 11px 12px; }.text-input:focus, .rule-row input:focus, .rule-row select:focus, .limit-input:focus { border-color: color-mix(in srgb, var(--accent, #c4b5fd) 70%, transparent); background: #101016; }
  .criteria-head { display: flex; align-items: center; gap: 8px; margin: 22px 0 9px; }.and-pill { padding: 3px 7px; border-radius: 999px; color: #b9aaff; background: #9b87ff1a; font-size: .59rem; font-weight: 700; letter-spacing: .04em; }.add-rule { margin-left: auto; padding: 5px 8px; border: 0; border-radius: 7px; color: var(--accent, #c4b5fd); background: #ffffff08; cursor: pointer; font-size: .7rem; }.add-rule:hover { background: #ffffff12; }
  .rules { display: flex; flex-direction: column; gap: 7px; max-height: 270px; overflow-y: auto; padding: 2px 4px 2px 0; scrollbar-width: thin; scrollbar-color: #ffffff2b transparent; }.rules::-webkit-scrollbar { width: 5px; }.rules::-webkit-scrollbar-thumb { border-radius: 9px; background: #ffffff2b; }.rule-row { display: flex; align-items: center; gap: 7px; padding: 7px; border: 1px solid #ffffff0d; border-radius: 11px; background: #ffffff06; }.rule-row select:first-child { width: 132px; }.rule-row select, .rule-row input { min-width: 0; padding: 8px; }.rule-row input { flex: 1; }.rule-row select:not(:first-child) { flex: 1; }.operator { flex: 0 0 auto; color: #858593; font-size: .68rem; white-space: nowrap; }.remove-rule { width: 25px; height: 25px; flex: 0 0 auto; border: 0; border-radius: 50%; color: #92929d; background: none; cursor: pointer; font-size: 1.05rem; }.remove-rule:hover { color: #fca5a5; background: #fca5a51a; }
  .options { display: flex; align-items: center; gap: 10px; margin-top: 18px; padding-top: 16px; border-top: 1px solid #ffffff0d; }.limit-input { width: 70px; padding: 8px; }.option-help { color: #71717a; font-size: .68rem; }.error { margin: 14px 0 0; color: #fca5a5; font-size: .76rem; }.sheet-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 22px; padding-top: 16px; border-top: 1px solid #ffffff0d; }.cancel, .save { padding: 9px 14px; border: 0; border-radius: 9px; cursor: pointer; font: inherit; font-size: .76rem; font-weight: 600; }.cancel { color: #a1a1aa; background: #ffffff08; }.cancel:hover { color: #fff; background: #ffffff12; }.save { color: #111; background: var(--accent, #c4b5fd); }.save:hover { filter: brightness(1.08); }.save:disabled { cursor: wait; opacity: .55; }
  @media (max-width: 560px) { .sheet { padding: 20px; }.rule-row { flex-wrap: wrap; }.rule-row select:first-child { flex: 1 1 45%; width: auto; }.operator { order: 3; }.rule-row input, .rule-row select:not(:first-child) { flex: 1 1 55%; }.options { align-items: flex-start; flex-wrap: wrap; }.option-help { flex-basis: 100%; margin-left: 80px; } }
</style>
