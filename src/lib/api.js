const TAURI_API_BASE = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
  ? 'http://127.0.0.1:5178'
  : ''

export function apiFetch(path, options) {
  const normalizedPath = String(path).startsWith('/') ? path : `/${path}`
  return fetch(`${TAURI_API_BASE}${normalizedPath}`, options)
}
