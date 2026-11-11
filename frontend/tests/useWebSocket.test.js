import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { useWebSocket } from '../src/composables/useWebSocket.js'

function host(onMessage = vi.fn()) {
  let api
  const wrapper = mount(defineComponent({
    setup() {
      api = useWebSocket(onMessage)
      return () => null
    },
  }))
  return { wrapper, api, onMessage }
}
const sockets = () => window.WebSocket.instances
// A real socket is CLOSED by the time its onclose runs.
function drop(ws, code) {
  ws.readyState = window.WebSocket.CLOSED
  ws.onclose({ code })
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('useWebSocket', () => {
  it("doesn't connect without a session token", () => {
    const { api } = host()
    expect(api.status.value).toBe('unauthorized')
    expect(sockets()).toHaveLength(0)
  })

  it('connects on the page origin and authenticates first', () => {
    sessionStorage.setItem('juli-token', 't')
    const { api } = host()
    const [ws] = sockets()
    expect(ws.url).toBe(`ws://${window.location.host}/ws`)
    expect(api.status.value).toBe('connecting')
    ws.onopen()
    expect(ws.sent.map(s => JSON.parse(s))).toEqual([{ type: 'auth', token: 't' }])
  })

  it('is connected once the server answers, and hands each message on', () => {
    sessionStorage.setItem('juli-token', 't')
    const { api, onMessage } = host()
    const [ws] = sockets()
    ws.onmessage({ data: JSON.stringify({ message_type: 'status' }) })
    expect(api.status.value).toBe('connected')
    expect(api.isConnected.value).toBe(true)
    expect(onMessage).toHaveBeenCalledWith({ message_type: 'status' })
  })

  it('skips a message that is not JSON', () => {
    sessionStorage.setItem('juli-token', 't')
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { onMessage } = host()
    sockets()[0].onmessage({ data: 'not json' })
    expect(onMessage).not.toHaveBeenCalled()
    expect(error).toHaveBeenCalled()
    error.mockRestore()
  })

  it('reconnects with a growing delay, reset once a message arrives', () => {
    sessionStorage.setItem('juli-token', 't')
    const { api } = host()
    drop(sockets()[0], 1006)
    expect(api.status.value).toBe('disconnected')
    vi.advanceTimersByTime(999)
    expect(sockets()).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(sockets()).toHaveLength(2) // after 1 s
    drop(sockets()[1], 1006)
    vi.advanceTimersByTime(1999)
    expect(sockets()).toHaveLength(2)
    vi.advanceTimersByTime(1)
    expect(sockets()).toHaveLength(3) // then after 2 s
    sockets()[2].onmessage({ data: '{}' }) // accepted: backoff resets
    drop(sockets()[2], 1006)
    vi.advanceTimersByTime(1000)
    expect(sockets()).toHaveLength(4)
  })

  it.each([4401, 4403])('stops reconnecting when the server refuses the session (%i)', code => {
    sessionStorage.setItem('juli-token', 't')
    const { api } = host()
    drop(sockets()[0], code)
    expect(api.status.value).toBe('unauthorized')
    vi.advanceTimersByTime(60000)
    expect(sockets()).toHaveLength(1)
  })

  it('closes on an error, and disconnects for good on unmount', () => {
    sessionStorage.setItem('juli-token', 't')
    const { wrapper } = host()
    const [ws] = sockets()
    ws.onerror()
    expect(ws.readyState).toBe(window.WebSocket.CLOSED)
    wrapper.unmount()
    vi.advanceTimersByTime(60000)
    expect(sockets()).toHaveLength(1)
  })

  it("doesn't open a second socket while one is connecting", () => {
    sessionStorage.setItem('juli-token', 't')
    const { api } = host()
    api.connect()
    expect(sockets()).toHaveLength(1)
  })
})
