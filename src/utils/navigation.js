import { apiFetch } from '../lib/api.js'

const isEntity = value =>
  value &&
  (typeof value === 'object' || typeof value === 'string') &&
  Boolean(
    value.id != null ||
    value.browseId != null ||
    value.vid != null ||
    value.videoId != null ||
    value.id1 != null ||
    (typeof value === 'string' && value.trim().length > 0)
  )

const entityId = entity =>
  entity?.id != null ? entity.id :
  entity?.browseId != null ? entity.browseId :
  entity?.vid != null ? entity.vid :
  entity?.videoId != null ? entity.videoId :
  entity?.id1 != null ? entity.id1 :
  null

const entityName = entity =>
  typeof entity === 'string'
    ? entity.trim() || null
    : (
      entity?.name != null ? entity.name :
      entity?.title != null ? entity.title :
      entity?.label != null ? entity.label :
      null
    )

export function normalizeArtists(track) {
  if (!track) return []
  const artists = track.artists ?? track.artist ?? track.author ?? []
  return Array.isArray(artists)
    ? artists
        .map(item => {
          if (typeof item === 'string') return { name: item.trim(), id: null }
          if (!item || typeof item !== 'object') return { name: null, id: null }
          return {
            name: entityName(item),
            id: entityId(item),
          }
        })
        .filter(item => item.name)
    : artists
        ? [{ name: entityName(artists), id: entityId(artists) }].filter(item => item.name)
        : []
}

export function normalizeAlbum(track) {
  if (!track) return null
  const album = track.album ?? track.albumTitle ?? track.album_name ?? null
  if (!album) return null
  if (typeof album === 'string') return { name: album.trim(), id: null }
  if (!album || typeof album !== 'object') return null
  const id = entityId(album) != null ? entityId(album) : album.id
  const name = entityName(album) ?? ''
  return name ? { name, id: id ?? null } : null
}

export function openArtist(artist, router) {
  const name = entityName(artist)
  const id = entityId(artist)
  if (!name) return
  if (typeof router === 'function') router(`/artist/${encodeURIComponent(id ?? name)}`)
}

export function openAlbum(album, router) {
  const name = entityName(album)
  const id = entityId(album)
  if (!name) return
  if (id) {
    if (typeof router === 'function') router(`/album/${encodeURIComponent(id)}`)
    else if (typeof window !== 'undefined') window.location.hash = `#/album/${encodeURIComponent(id)}`
  } else if (typeof router === 'function') {
    router(`/search?q=${encodeURIComponent(name)}&type=album`)
  } else if (typeof window !== 'undefined') {
    window.location.hash = `#/search?q=${encodeURIComponent(name)}&type=album`
  }
}

export async function resolveLiveArtist(params, setEntityData) {
  if (!params) return
  const query = params.id ?? params.name ?? ''
  if (!query) return
  try {
    const response = await apiFetch(`/api/artist/resolve?q=${encodeURIComponent(query)}`)
    const data = await response.json()
    if (response.ok && data && !data.error) {
      setEntityData?.({ type: 'artist', data })
    }
  } catch {
    /* live resolve is best-effort */
  }
}

export async function resolveLiveAlbum(params, setEntityData) {
  if (params?.id) {
    const paramsObj = new URLSearchParams({ title: params.id })
    const response = await apiFetch(`/api/album/resolve?${paramsObj}`)
    const data = await response.json()
    if (response.ok && data && !data.error) setEntityData?.({ type: 'album', data })
  } else if (params?.title) {
    const paramsObj = new URLSearchParams()
    paramsObj.set('title', params.title)
    if (params.artist) paramsObj.set('artist', params.artist)
    const response = await apiFetch(`/api/album/resolve?${paramsObj}`)
    const data = await response.json()
    if (response.ok && data && !data.error) setEntityData?.({ type: 'album', data })
  }
}
