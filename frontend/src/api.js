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

/**
 * A failed API call. `detail` is the server's detail as sent: usually a
 * string, but some 409s carry an object, e.g. {message, confirm} before a push
 * or {message, license} before a download that needs a licence accepted.
 */
export class ApiError extends Error {
  constructor(status, message, detail = null) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

function detailText(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(d => d.msg || JSON.stringify(d)).join('; ')
  if (detail && typeof detail.message === 'string') return detail.message
  return ''
}

async function request(path, { body, headers, ...options } = {}) {
  const init = { ...options, headers: { ...headers, Authorization: `Bearer ${getToken()}` } }
  if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = null
    try {
      detail = (await res.json()).detail ?? null
    } catch { /* not JSON */ }
    throw new ApiError(res.status, detailText(detail) || `${res.status} ${res.statusText}`, detail)
  }
  return res
}

/** fetch() for /api routes: adds auth and JSON, throws ApiError on !ok. */
export async function apiFetch(path, options) {
  const res = await request(path, options)
  return res.status === 204 ? null : res.json()
}

/** Download an authenticated file (e.g. the workspace zip) and save it. */
export async function apiDownload(path, filename) {
  const blob = await (await request(path)).blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
