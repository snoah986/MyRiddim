<script>
  export let items = []
  export let activeIndex = -1
  export let onSelect = () => {}

  const label = item => item?.title || item?.name || 'Untitled'
  const kind = item => item?.type === 'song' ? 'Song' : item?.type ? item.type[0].toUpperCase() + item.type.slice(1) : 'Result'
</script>

{#if items.length}
  <div class="suggestions" role="listbox" aria-label="Search suggestions">
    {#each items.slice(0, 6) as item, index (item.id || item.title || index)}
      <button
        type="button"
        class:active={index === activeIndex}
        class="suggestion"
        data-search-suggestion-index={index}
        role="option"
        aria-selected={index === activeIndex}
        tabindex={index === activeIndex ? 0 : -1}
        on:click={() => onSelect(item)}
        on:focus={() => activeIndex = index}
      >
        <span class="art">{#if item.thumbnail}<img src={item.thumbnail} alt="" referrerpolicy="no-referrer" />{:else}♫{/if}</span>
        <span class="copy"><strong>{label(item)}</strong><small>{kind(item)}{#if item.artist} · {item.artist}{/if}</small></span>
      </button>
    {/each}
  </div>
{/if}

<style>
  .suggestions { position:absolute; top:calc(100% + 6px); left:0; right:0; z-index:60; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:4px; padding:6px; border:1px solid #ffffff16; border-radius:12px; background:#111114f5; box-shadow:0 18px 40px #000b; backdrop-filter:blur(18px); }
  .suggestion { display:flex; align-items:center; gap:8px; min-width:0; padding:6px; border:1px solid transparent; border-radius:8px; color:#ededed; background:transparent; text-align:left; cursor:pointer; }
  .suggestion:hover,.suggestion.active { border-color:#ffffff18; background:#ffffff0d; }
  .art { display:grid; place-items:center; width:34px; height:34px; flex:0 0 auto; overflow:hidden; border-radius:6px; color:#71717a; background:#202024; font-size:.8rem; }.art img { width:100%; height:100%; object-fit:cover; }
  .copy { display:flex; min-width:0; flex-direction:column; }.copy strong,.copy small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.copy strong { font-size:.68rem; }.copy small { margin-top:2px; color:#71717a; font-size:.58rem; }
  @media(max-width:560px) { .suggestions { grid-template-columns:1fr; } }
</style>
