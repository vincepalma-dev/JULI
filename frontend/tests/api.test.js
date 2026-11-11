import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiDownload, apiFetch, captureToken, getToken, saveText } from '../src/api.js'
import { watchSaves } from './helpers.js'

afterEach(() => vi.restoreAllMocks())

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

  it.each([
    [422, [{ type: 'extra_forbidden', loc: ['body', 'choose_fixes'], msg: 'Extra inputs are not permitted' }]],
    [404, 'Not Found'],
    [405, 'Method Not Allowed'],
  ])('says the backend is older than the dashboard when it does not know the request (%i)', async (status, detail) => {
    fetch.mockResolvedValueOnce(reply(status, { detail }))
    const error = await apiFetch('/api/task', { method: 'POST', body: {} }).catch(e => e)
    expect(error.message).toBe("This dashboard is newer than the JULI backend that's running, so the backend didn't understand the request. Stop JULI and start it again.")
    expect(error.stale).toBe(true)
    expect(error.status).toBe(status)
  })

  it("keeps the API's own 404s and validation errors as they are", async () => {
    fetch.mockResolvedValueOnce(reply(404, { detail: 'Project not found' }))
    const missing = await apiFetch('/api/projects/x').catch(e => e)
    expect([missing.message, missing.stale]).toEqual(['Project not found', false])
    fetch.mockResolvedValueOnce(reply(422, { detail: [{ type: 'string_too_long', msg: 'too long' }] }))
    expect((await apiFetch('/api/task').catch(e => e)).stale).toBe(false)
  })

  it('falls back to the status when the body is not JSON', async () => {
    fetch.mockResolvedValueOnce({ ok: false, status: 502, statusText: 'Bad Gateway', json: async () => { throw new SyntaxError() } })
    const error = await apiFetch('/api/x').catch(e => e)
    expect(error.message).toBe('502 Bad Gateway')
    expect(error.detail).toBeNull()
  })
})

describe('saving files', () => {
  it('saves text under a name, as UTF-8', async () => {
    const saved = watchSaves()
    saveText('# Plan\n', 'juli-run-1.md', 'text/markdown')
    expect(saved).toHaveLength(1)
    expect(saved[0].name).toBe('juli-run-1.md')
    expect(saved[0].blob.type).toBe('text/markdown;charset=utf-8')
    expect(await saved[0].blob.text()).toBe('# Plan\n')
  })

  it('downloads a file from the API with the token', async () => {
    const saved = watchSaves()
    sessionStorage.setItem('juli-token', 't')
    fetch.mockResolvedValueOnce({ ok: true, status: 200, blob: async () => new Blob(['zip']) })
    await apiDownload('/api/projects/p/workspace/zip', 'juli-p.zip')
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer t')
    expect(saved.map(s => s.name)).toEqual(['juli-p.zip'])
  })
})
