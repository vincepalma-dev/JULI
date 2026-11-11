import { describe, expect, it } from 'vitest'
import { ApiError, apiFetch, captureToken, getToken } from '../src/api.js'

function reply(status, body) {
  return { ok: status < 400, status, statusText: 'Status text', json: async () => body }
}

describe('session token', () => {
  it('moves the token from the URL into sessionStorage', () => {
    history.replaceState(null, '', '/#token=abc%2Fdef')
    captureToken()
    expect(getToken()).toBe('abc/def')
    expect(window.location.hash).toBe('')
  })
})

describe('apiFetch', () => {
  it('sends the token as a Bearer header and JSON bodies', async () => {
    sessionStorage.setItem('juli-token', 't')
    fetch.mockResolvedValueOnce(reply(200, { ok: true }))
    expect(await apiFetch('/api/x', { method: 'POST', body: { a: 1 } })).toEqual({ ok: true })
    const [path, init] = fetch.mock.calls[0]
    expect(path).toBe('/api/x')
    expect(init.headers).toEqual({ Authorization: 'Bearer t', 'Content-Type': 'application/json' })
    expect(init.body).toBe('{"a":1}')
  })

  it('returns null for 204', async () => {
    fetch.mockResolvedValueOnce(reply(204, null))
    expect(await apiFetch('/api/x', { method: 'DELETE' })).toBeNull()
  })

  it('keeps an object detail and shows its message', async () => {
    const detail = { message: 'Push to origin?', confirm: true }
    fetch.mockResolvedValueOnce(reply(409, { detail }))
    const error = await apiFetch('/api/runs/1/push').catch(e => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(409)
    expect(error.message).toBe('Push to origin?')
    expect(error.detail).toEqual(detail)
  })

  it('joins validation errors', async () => {
    fetch.mockResolvedValueOnce(reply(422, { detail: [{ msg: 'too long' }, { msg: 'required' }] }))
    expect((await apiFetch('/api/task').catch(e => e)).message).toBe('too long; required')
  })

  it('falls back to the status when the body is not JSON', async () => {
    fetch.mockResolvedValueOnce({ ok: false, status: 502, statusText: 'Bad Gateway', json: async () => { throw new SyntaxError() } })
    const error = await apiFetch('/api/x').catch(e => e)
    expect(error.message).toBe('502 Bad Gateway')
    expect(error.detail).toBeNull()
  })
})
