// jsdom lacks some browser APIs the components touch when they set up. They're
// stubbed here, so the components never need test-only guards.
import { afterEach, beforeEach, vi } from 'vitest'
import { enableAutoUnmount } from '@vue/test-utils'

enableAutoUnmount(afterEach) // each test's components are gone before the next one

// Sidebar, ParticleBackground and TerminalDock read media queries in setup.
window.matchMedia = query => ({
  matches: false,
  media: query,
  addEventListener() {},
  removeEventListener() {},
})

// ParticleBackground draws on a 2D canvas: every method is a no-op that
// returns the context, which also stands in for gradients.
const canvas2d = new Proxy({}, { get: (target, key) => target[key] ?? (() => canvas2d) })
HTMLCanvasElement.prototype.getContext = () => canvas2d

// TerminalDock mirrors xterm's <style> elements into constructed stylesheets
// and watches its host's size.
document.adoptedStyleSheets = []
CSSStyleSheet.prototype.replaceSync ??= function () {}
window.ResizeObserver ??= class {
  observe() {}
  disconnect() {}
}

// The side panels and modals use the native <dialog>.
HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
HTMLDialogElement.prototype.show = function () { this.setAttribute('open', '') }
HTMLDialogElement.prototype.close = function () {
  if (!this.hasAttribute('open')) return
  this.removeAttribute('open')
  this.dispatchEvent(new Event('close'))
}

// apiDownload saves a blob through an object URL.
URL.createObjectURL = () => 'blob:test'
URL.revokeObjectURL = () => {}

vi.mock('@xterm/xterm', () => ({
  Terminal: class {
    cols = 80
    rows = 24
    loadAddon() {}
    open() {}
    onData() {}
    focus() {}
    write() {}
    reset() {}
    dispose() {}
  },
}))
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }))

// No network: a test that needs the server stubs fetch with its replies, and
// sockets never connect.
class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 3
  static instances = []
  readyState = FakeWebSocket.CONNECTING
  sent = []
  constructor(url) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
  send(data) {
    this.sent.push(data)
  }
  close() {
    this.readyState = FakeWebSocket.CLOSED
  }
}
window.WebSocket = FakeWebSocket

beforeEach(() => {
  FakeWebSocket.instances = []
  sessionStorage.clear()
  window.fetch = vi.fn(async () => {
    throw new Error('fetch is not stubbed in this test')
  })
})
