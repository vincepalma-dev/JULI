import { ref, onMounted, onUnmounted } from 'vue'
import { getToken } from '../api.js'

// Close codes sent by the server when it refuses a connection.
const AUTH_FAILED = 4401
const BAD_ORIGIN = 4403

/**
 * The live agent message stream at /ws.
 * Connects on the page's own origin (the Vite proxy in dev, FastAPI in
 * production), authenticates with the session token as its first message,
 * hands every message to `onMessage`, and reconnects with exponential
 * backoff unless the server refused the session. On every (re)connect the
 * server replays the current run's live view, so `onMessage` must tolerate
 * messages it has seen before.
 */
export function useWebSocket(onMessage) {
  const isConnected = ref(false)
  const status = ref('disconnected') // disconnected, connecting, connected, unauthorized
  let ws = null
  let reconnectTimeout = null
  let reconnectDelay = 1000

  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const wsUrl = `${scheme}://${window.location.host}/ws`

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return
    }
    if (!getToken()) {
      status.value = 'unauthorized'
      return
    }

    status.value = 'connecting'

    try {
      ws = new WebSocket(wsUrl)
    } catch (e) {
      console.error('WebSocket creation failed:', e)
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'auth', token: getToken() }))
    }

    ws.onmessage = (event) => {
      // The server accepted our auth: we're connected, and backoff resets.
      reconnectDelay = 1000
      isConnected.value = true
      status.value = 'connected'
      let data
      try {
        data = JSON.parse(event.data)
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
        return
      }
      onMessage(data)
    }

    ws.onclose = (event) => {
      isConnected.value = false
      if (event.code === AUTH_FAILED || event.code === BAD_ORIGIN) {
        status.value = 'unauthorized'
        return
      }
      status.value = 'disconnected'
      scheduleReconnect()
    }

    ws.onerror = () => {
      ws.close()
    }
  }

  function scheduleReconnect() {
    if (reconnectTimeout) clearTimeout(reconnectTimeout)
    reconnectTimeout = setTimeout(() => {
      connect()
      reconnectDelay = Math.min(reconnectDelay * 2, 10000) // Max 10s
    }, reconnectDelay)
  }

  function disconnect() {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout)
      reconnectTimeout = null
    }
    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }
  }

  onMounted(connect)
  onUnmounted(disconnect)

  return { isConnected, status, connect, disconnect }
}
