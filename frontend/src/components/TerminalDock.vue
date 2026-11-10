<template>
  <section v-show="open" class="flex shrink-0 flex-col border-t border-juli-border bg-[#0b0f19]" :class="tall ? 'h-[60dvh]' : 'h-[42dvh] md:h-72'" aria-label="Terminal">
    <div class="flex flex-wrap items-center gap-1 border-b border-juli-border px-2">
      <div class="flex" role="tablist" aria-label="Terminal views">
        <button type="button" role="tab" class="tab !py-2" :aria-selected="tab === 'shell'" @click="tab = 'shell'">Terminal</button>
        <button type="button" role="tab" class="tab !py-2" :aria-selected="tab === 'agent'" @click="tab = 'agent'">
          Agent
          <span v-if="running" class="badge ml-1 bg-cyan-500/15 text-cyan-200">running</span>
        </button>
      </div>
      <span v-if="tab === 'shell' && note" class="ml-2 min-w-0 text-xs text-slate-400" role="status">{{ note }}</span>
      <div class="ml-auto flex items-center">
        <button v-if="tab === 'shell' && state !== 'open'" type="button" class="btn btn-secondary !min-h-0 !py-1 text-xs" @click="restart"><Icon name="refresh" class="h-3.5 w-3.5" />New session</button>
        <button type="button" class="icon-btn" :aria-label="tall ? 'Make the terminal shorter' : 'Make the terminal taller'" @click="tall = !tall">
          <Icon :name="tall ? 'chevron-down' : 'chevron-up'" class="h-4 w-4" />
        </button>
        <button type="button" class="icon-btn" aria-label="Hide the terminal" @click="$emit('close')">
          <Icon name="x" class="h-4 w-4" />
        </button>
      </div>
    </div>

    <!-- The user's shell, in the project's workspace -->
    <div v-show="tab === 'shell'" ref="host" class="min-h-0 flex-1 px-2 py-1"></div>

    <!-- Live agent commands -->
    <div v-show="tab === 'agent'" ref="agentLog" class="min-h-0 flex-1 overflow-y-auto px-3 py-2 font-mono text-xs" aria-live="polite">
      <p v-if="!commands.length" class="py-2 font-sans text-sm text-slate-400">Commands the agents run (tests, linters) stream here. Each one that isn't safe to run on its own asks you first.</p>
      <div v-for="c in commands" :key="c.key" class="mb-3">
        <p class="flex flex-wrap items-center gap-2 text-slate-200">
          <span class="text-cyan-300">$</span>
          <span class="break-all">{{ c.command }}</span>
          <span class="font-sans text-slate-500">{{ c.agent }}</span>
          <span class="badge font-sans" :class="c.sandbox ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-200'">{{ c.sandbox ? 'sandbox' : 'this machine' }}</span>
          <span class="badge font-sans" :class="c.status === 'running' ? 'bg-cyan-500/15 text-cyan-200' : c.status === 'passed' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'">
            {{ c.status }}<template v-if="c.exit_code != null"> · exit {{ c.exit_code }}</template><template v-if="c.seconds != null"> · {{ Number(c.seconds).toFixed(1) }} s</template>
          </span>
        </p>
        <pre v-if="c.output" class="mt-1 whitespace-pre-wrap break-all text-slate-300">{{ stripAnsi(c.output) }}</pre>
      </div>
    </div>
  </section>
</template>

<script setup>
// The bottom dock. Terminal: the user's own shell in the project's workspace
// over /ws/terminal (xterm.js). Agent: the agents' commands as they run.
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import Icon from './Icon.vue'
import { getToken } from '../api.js'
import { stripAnsi } from '../labels.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  projectId: { type: String, default: null },
  commands: { type: Array, default: () => [] },
  showAgent: { type: Number, default: 0 }, // bump to switch to the Agent tab
})
defineEmits(['close'])

// Why the server closed the terminal, by close code.
const CONNECTING = 'Connecting…'
const CLOSED = {
  4400: 'The terminal request was malformed.',
  4401: 'The session token was refused. Reopen JULI from its launch link.',
  4403: 'This page is not an allowed origin for the terminal.',
  4404: 'This project no longer exists.',
  4429: 'Too many terminals are open, or they opened too quickly. Wait a moment, then start a new session.',
  4503: "This machine can't open a terminal",
}

const tab = ref('shell')
const tall = ref(false)
const state = ref('idle') // idle, connecting, open, closed
const note = ref('')
const host = ref(null)
const agentLog = ref(null)
let term = null
let fit = null
let socket = null
let observer = null
let unadopt = null

const running = computed(() => props.commands.some(c => c.status === 'running'))

function start() {
  if (!props.projectId || !host.value || state.value === 'connecting' || state.value === 'open') return
  if (!term) {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    term = new Terminal({
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: 13,
      cursorBlink: !reduce,
      scrollback: 5000,
      theme: { background: '#0b0f19', foreground: '#e2e8f0', cursor: '#67e8f9', selectionBackground: '#155e75' },
    })
    fit = new FitAddon()
    term.loadAddon(fit)
    term.open(host.value)
    unadopt = adoptStyles(host.value)
    term.onData(data => send({ type: 'input', data }))
    observer = new ResizeObserver(() => resize())
    observer.observe(host.value)
  }
  fit.fit()
  state.value = 'connecting'
  note.value = CONNECTING
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  socket = new WebSocket(`${scheme}://${window.location.host}/ws/terminal`)
  socket.onopen = () => {
    socket.send(JSON.stringify({ token: getToken(), project_id: props.projectId, cols: term.cols, rows: term.rows }))
    state.value = 'open'
    note.value = ''
    term.focus()
  }
  socket.onmessage = event => {
    let msg
    try {
      msg = JSON.parse(event.data)
    } catch {
      return
    }
    if (msg.type === 'output') term.write(msg.data)
    else if (msg.type === 'exit') note.value = 'The shell ended.'
  }
  socket.onclose = event => {
    state.value = 'closed'
    socket = null
    if (CLOSED[event.code]) note.value = event.code === 4503 && event.reason ? `${CLOSED[4503]}: ${event.reason}` : CLOSED[event.code]
    else if (!note.value || note.value === CONNECTING) note.value = 'The terminal disconnected.'
  }
}

/**
 * xterm writes its renderer CSS (font, colours, cell sizes) into <style>
 * elements, which the dashboard's CSP (style-src 'self') refuses to apply.
 * Constructed stylesheets aren't inline styles, so mirror each <style> into
 * one and keep it in sync as xterm rewrites it (on resize and theme changes).
 */
function adoptStyles(root) {
  const sheets = new Map()
  const sync = () => {
    for (const el of root.querySelectorAll('style')) {
      let sheet = sheets.get(el)
      if (!sheet) {
        sheet = new CSSStyleSheet()
        sheets.set(el, sheet)
        document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet]
      }
      sheet.replaceSync(el.textContent || '')
    }
  }
  sync()
  // xterm rewrites its rows on every output chunk; only a change to a <style>
  // element (a new one, or new text in one) needs the sheets synced.
  const isStyle = node => node?.nodeName === 'STYLE'
  const touchesStyle = r => isStyle(r.target) || isStyle(r.target.parentNode) || [...r.addedNodes].some(isStyle)
  const watcher = new MutationObserver(records => {
    if (records.some(touchesStyle)) sync()
  })
  watcher.observe(root, { subtree: true, childList: true, characterData: true })
  return () => {
    watcher.disconnect()
    const mine = new Set(sheets.values())
    document.adoptedStyleSheets = document.adoptedStyleSheets.filter(sheet => !mine.has(sheet))
  }
}

function send(msg) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(msg))
}

let lastSize = ''
function resize() {
  if (!fit || !host.value || host.value.offsetParent === null) return // hidden
  fit.fit()
  const size = `${term.cols}x${term.rows}`
  if (size !== lastSize) {
    lastSize = size
    send({ type: 'resize', cols: term.cols, rows: term.rows })
  }
}

function stop() {
  if (socket) {
    socket.onclose = null
    socket.close()
    socket = null
  }
  state.value = 'idle'
}

function restart() {
  stop()
  term?.reset()
  note.value = ''
  start()
}

// Connect when the shell is first shown; a new project gets a new shell.
watch(() => [props.open, tab.value], async ([open, t]) => {
  if (!open) return
  await nextTick()
  if (t === 'shell') {
    if (state.value === 'idle') start()
    else resize()
  }
})
// The dock may open before the project has loaded: start once it has.
watch(() => props.projectId, () => {
  if (state.value !== 'idle') {
    stop()
    term?.reset()
  }
  if (props.open && tab.value === 'shell') nextTick(start)
})
watch(() => props.showAgent, () => { tab.value = 'agent' })

// Follow the agent log.
watch(() => props.commands.map(c => c.output.length + c.status).join(), () => {
  nextTick(() => { if (agentLog.value) agentLog.value.scrollTop = agentLog.value.scrollHeight })
})

onUnmounted(() => {
  stop()
  observer?.disconnect()
  unadopt?.()
  term?.dispose()
})
</script>
