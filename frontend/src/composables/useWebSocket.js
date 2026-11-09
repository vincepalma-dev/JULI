import { ref, onMounted, onUnmounted } from 'vue'

/**
 * WebSocket composable for real-time agent message streaming.
 * Auto-reconnects on disconnect with exponential backoff.
 */
export function useWebSocket(url = null) {
  const messages = ref([])
  const isConnected = ref(false)
  const status = ref('disconnected') // disconnected, connecting, connected
  let ws = null
  let reconnectTimeout = null
  let reconnectDelay = 1000

  // Default to current host
  const wsUrl = url || `ws://${window.location.hostname}:8000/ws`

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
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
      isConnected.value = true
      status.value = 'connected'
      reconnectDelay = 1000 // Reset backoff
      console.log('🟢 WebSocket connected')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
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

    ws.onclose = () => {
      isConnected.value = false
      status.value = 'disconnected'
      console.log('🔴 WebSocket disconnected')
      scheduleReconnect()
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      ws.close()
    }
  }

  function scheduleReconnect() {
    if (reconnectTimeout) clearTimeout(reconnectTimeout)
    reconnectTimeout = setTimeout(() => {
      console.log(`🔄 Reconnecting in ${reconnectDelay}ms...`)
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
      ws.close()
      ws = null
    }
  }

  function sendMessage(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
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
    sendMessage,
    clearMessages,
  }
}
