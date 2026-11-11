// Fake API replies for component tests.
/**
 * Stub fetch with replies keyed by "METHOD /path" (the query string is
 * ignored unless the key has one). A reply is a body, a function
 * (body, path) => body, or { status, body } for an error.
 */
export function serveApi(routes) {
  fetch.mockImplementation(async (path, init = {}) => {
    const method = init.method || 'GET'
    const key = [`${method} ${path}`, `${method} ${path.split('?')[0]}`].find(k => k in routes)
    if (!key) return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({ detail: `no stub for ${method} ${path}` }) }
    let reply = routes[key]
    if (typeof reply === 'function') reply = reply(init.body ? JSON.parse(init.body) : undefined, path)
    if (reply && typeof reply === 'object' && 'status' in reply && reply.status >= 400) {
      return { ok: false, status: reply.status, statusText: 'Error', json: async () => reply.body }
    }
    return { ok: true, status: reply === null ? 204 : 200, json: async () => reply, blob: async () => new Blob(['zip']) }
  })
}

/** The calls made to one route: their parsed JSON bodies. */
export function sent(method, path) {
  return fetch.mock.calls
    .filter(([p, init = {}]) => (init.method || 'GET') === method && p.split('?')[0] === path)
    .map(([, init = {}]) => (init.body ? JSON.parse(init.body) : undefined))
}
