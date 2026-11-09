/**
 * API access with the session token.
 *
 * The launcher opens the dashboard at /#token=<token>. captureToken() moves it
 * into sessionStorage and strips it from the URL, so it never lands in history
 * or bookmarks. Every API call sends it as a Bearer header.
 */

const TOKEN_KEY = 'juli-token'

export function captureToken() {
  const match = window.location.hash.match(/(?:^#|&)token=([^&]+)/)
  if (match) {
    try {
      sessionStorage.setItem(TOKEN_KEY, decodeURIComponent(match[1]))
    } catch { /* storage blocked: the session won't survive a reload */ }
    history.replaceState(null, '', window.location.pathname + window.location.search)
  }
}

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail)
    this.status = status
  }
}

function detailText(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(d => d.msg || JSON.stringify(d)).join('; ')
  return ''
}

/** fetch() for /api routes: adds auth and JSON, throws ApiError on !ok. */
export async function apiFetch(path, { body, headers, ...options } = {}) {
  const init = { ...options, headers: { ...headers, Authorization: `Bearer ${getToken()}` } }
  if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = ''
    try {
      detail = detailText((await res.json()).detail)
    } catch { /* not JSON */ }
    throw new ApiError(res.status, detail || `${res.status} ${res.statusText}`)
  }
  return res.status === 204 ? null : res.json()
}
