import { ref, onMounted, onUnmounted } from 'vue'
import { getToken } from '../api.js'

// Close codes sent by the server when it refuses a connection.
const AUTH_FAILED = 4401
const BAD_ORIGIN = 4403

/**
 * WebSocket composable for real-time agent message streaming.
 * Connects on the page's own origin (the Vite proxy in dev), authenticates
 * with the session token as its first message, and auto-reconnects with
 * exponential backoff unless the server refused the session.
 */
export function useWebSocket(url = null) {
  const messages = ref([])
  const isConnected = ref(false)
  const status = ref('disconnected') // disconnected, connecting, connected, unauthorized
  let ws = null
  let reconnectTimeout = null
  let reconnectDelay = 1000

  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const wsUrl = url || `${scheme}://${window.location.host}/ws`

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
      isConnected.value = true
      status.value = 'connected'
    }

    ws.onmessage = (event) => {
      reconnectDelay = 1000 // The server accepted our auth: reset backoff
      try {
        const data = JSON.parse(event.data)
        // Streamed chunks are followed by the agent's full message; live
        // streaming display comes with the dashboard rework.
        if (data.message_type === 'chunk') return
        messages.value.push({
          agent_name: data.agent_name || 'Unknown',
          content: data.content || '',
          timestamp: data.timestamp || new Date().toISOString(),
          message_type: data.message_type || 'agent',
        })
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
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

  function clearMessages() {
    messages.value = []
  }

  onMounted(() => {
    connect()
  })

  onUnmounted(() => {
    disconnect()
  })

  return {
    messages,
    isConnected,
    status,
    connect,
    disconnect,
    clearMessages,
  }
}
