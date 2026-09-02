import { writable } from 'svelte/store'
// openPlaylist: null | {id,title}; closes when set back to null
export const openPlaylist = writable(null)
