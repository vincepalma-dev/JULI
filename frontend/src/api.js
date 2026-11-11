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
 * `stale` marks a request the running backend didn't know (see staleBackend).
 */
export class ApiError extends Error {
  constructor(status, message, detail = null, stale = false) {
    super(message)
    this.status = status
    this.detail = detail
    this.stale = stale
  }
}

const STALE_BACKEND = "This dashboard is newer than the JULI backend that's running, so the backend didn't understand the request. Stop JULI and start it again."

/**
 * The page asked for something the running backend doesn't know: a field it
 * rejects, or a route it lacks (the framework's own 404 and 405; JULI's 404s
 * say what wasn't found). That happens when JULI keeps running while its code
 * is updated and the dashboard rebuilt.
 */
function staleBackend(status, detail) {
  if (status === 422) return Array.isArray(detail) && detail.some(d => d.type === 'extra_forbidden')
  return (status === 404 && detail === 'Not Found') || (status === 405 && detail === 'Method Not Allowed')
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
    if (staleBackend(res.status, detail)) throw new ApiError(res.status, STALE_BACKEND, detail, true)
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
  saveBlob(await (await request(path)).blob(), filename)
}

/** Save text the page already has as a file, e.g. a reply as Markdown. */
export function saveText(text, filename, type = 'text/plain') {
  saveBlob(new Blob([text], { type: `${type};charset=utf-8` }), filename)
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
