import { ref, reactive, computed } from 'vue'
import { apiFetch } from '../api.js'

// Message types that drive state but aren't shown as timeline entries.
const NOT_IN_TIMELINE = new Set(['status', 'turn_start', 'command_start', 'tool_start'])
const ENDED = new Set(['complete', 'stopped', 'error', 'idle'])
const MAX_COMMANDS = 30
const MAX_OUTPUT_CHARS = 200_000
// Warnings older than this (replayed on connect) don't pop a toast again.
const TOAST_WINDOW_MS = 30_000

/**
 * The project's runs as one timeline, fed by the stored history (REST) and
 * the live stream (WebSocket). Messages are de-duplicated by run, time, type
 * and agent, because a reconnect replays the current run's live view.
 *
 * - status messages carry data.status; turn_start drives the "now working" line
 * - chunks build the streaming draft until the agent's final message lands
 * - command_start / command_output / command feed the terminal's Agent tab
 * - tool_start / tool do too, and a finished tool call is a timeline entry
 */
export function useRun({ onWarning = () => {}, onEnded = () => {} } = {}) {
  const status = ref('idle') // idle, running, paused, complete, stopped, error
  const activeRunId = ref(null)
  const runs = ref([])
  const messages = ref([])
  const draft = ref(null) // { agent, model, text, run_id }
  const turn = ref(null) // { agent, role, activity, model, since, command, tool }
  const asking = ref(null) // { agent, run_id }: a follow-up question waiting for its answer
  // The Agent tab: commands { key, agent, command, sandbox, output, status, exit_code, seconds },
  // and tool calls, which also have kind 'tool', call_id and server.
  const commands = ref([])
  const pulls = reactive({}) // model -> latest pull_progress data
  const answered = reactive({}) // decision key -> the action the user chose
  const lastSpeed = ref(null) // { model, tokPerSec } of the latest finished turn
  const seen = new Set()
  let commandsProject = null // the project the Agent tab's commands belong to

  // Tool calls also carry their call id: one agent can start two in the same clock tick.
  const keyOf = m => `${m.run_id ?? ''}|${m.timestamp}|${m.message_type}|${m.agent_name}${m.data?.call_id != null ? `|${m.data.call_id}` : ''}`

  function add(m) {
    const key = keyOf(m)
    if (seen.has(key)) return false
    seen.add(key)
    if (!NOT_IN_TIMELINE.has(m.message_type)) messages.value.push({ ...m, key })
    return true
  }

  function isRecent(m) {
    return Date.now() - Date.parse(m.timestamp) < TOAST_WINDOW_MS
  }

  function setRunStatus(runId, value) {
    const row = runs.value.find(r => r.id === runId)
    if (row) row.status = value
  }

  /** One message from the WebSocket. */
  function ingest(m) {
    switch (m.message_type) {
      case 'status': {
        const value = m.data?.status
        if (!value) return
        status.value = value
        if (m.run_id != null) {
          activeRunId.value = m.run_id
          setRunStatus(m.run_id, value)
        }
        if (ENDED.has(value)) {
          turn.value = null
          draft.value = null
          if (value !== 'idle') onEnded()
        }
        return
      }
      case 'turn_start':
        add(m)
        turn.value = {
          agent: m.agent_name,
          role: m.data?.role,
          activity: m.data?.activity,
          model: m.model,
          since: Date.parse(m.timestamp) || Date.now(),
          command: null,
          tool: null,
        }
        draft.value = { agent: m.agent_name, model: m.model, text: '', run_id: m.run_id }
        return
      case 'chunk':
        if (!draft.value || draft.value.agent !== m.agent_name) {
          draft.value = { agent: m.agent_name, model: m.model, text: '', run_id: m.run_id }
        }
        draft.value.text += m.content
        return
      case 'command_start':
        if (!add(m)) return
        pushEntry({
          key: keyOf(m), agent: m.agent_name, command: m.data?.command ?? m.content,
          sandbox: Boolean(m.data?.sandbox), output: '', status: 'running', exit_code: null, seconds: null,
        })
        if (turn.value) turn.value.command = m.data?.command ?? m.content
        return
      case 'command_output': {
        const cmd = findRunning(m.data?.command)
        if (cmd && cmd.output.length < MAX_OUTPUT_CHARS) cmd.output += m.content
        return
      }
      case 'command': {
        if (!add(m)) return
        const d = m.data || {}
        const cmd = findRunning(d.command)
        if (cmd) {
          Object.assign(cmd, { status: d.status, exit_code: d.exit_code, seconds: d.seconds })
          if (!cmd.output && d.output) cmd.output = d.output
        } else {
          recordCommand(m)
        }
        if (turn.value) turn.value.command = null
        return
      }
      case 'tool_start':
        if (!add(m)) return
        pushEntry({
          key: keyOf(m), kind: 'tool', agent: m.agent_name, command: m.content, call_id: m.data?.call_id,
          server: null, sandbox: null, output: '', status: 'running', exit_code: null, seconds: null,
        })
        if (turn.value) turn.value.tool = m.content
        return
      case 'tool': {
        if (!add(m)) return
        const d = m.data || {}
        const entry = d.call_id == null ? null : commands.value.find(c => c.kind === 'tool' && c.status === 'running' && c.call_id === d.call_id)
        if (entry) Object.assign(entry, { status: d.status, output: d.output || '', seconds: d.seconds, server: d.server })
        else recordTool(m)
        if (turn.value) turn.value.tool = null
        return
      }
      case 'pull_progress':
        if (m.data?.model) pulls[m.data.model] = m.data
        return
      case 'agent':
        // Clear the draft even for a replayed message: a reconnect replays turn_start too.
        if (draft.value?.agent === m.agent_name) draft.value = null
        if (!add(m)) return
        if (turn.value?.agent === m.agent_name && m.tokens_out) {
          const seconds = (Date.parse(m.timestamp) - turn.value.since) / 1000
          if (seconds > 0) lastSpeed.value = { model: m.model, tokPerSec: m.tokens_out / seconds }
        }
        return
      case 'warning':
      case 'limit_reached':
        if (add(m) && isRecent(m)) onWarning(m)
        return
      default:
        add(m)
    }
  }

  function pushEntry(entry) {
    commands.value.push(entry)
    if (commands.value.length > MAX_COMMANDS) commands.value.shift()
  }

  /** A finished command (its result message) as an Agent tab entry. */
  function recordCommand(m) {
    const d = m.data || {}
    pushEntry({
      key: keyOf(m), agent: m.agent_name, command: d.command, sandbox: Boolean(d.sandbox),
      output: d.output || '', status: d.status, exit_code: d.exit_code, seconds: d.seconds,
    })
  }

  /** A finished tool call (its result message) as an Agent tab entry. */
  function recordTool(m) {
    const d = m.data || {}
    pushEntry({
      key: keyOf(m), kind: 'tool', agent: m.agent_name, command: m.content, call_id: d.call_id, server: d.server,
      sandbox: null, output: d.output || '', status: d.status, exit_code: null, seconds: d.seconds,
    })
  }

  function findRunning(command) {
    for (let i = commands.value.length - 1; i >= 0; i--) {
      const c = commands.value[i]
      if (c.kind !== 'tool' && c.status === 'running' && (command == null || c.command === command)) return c
    }
    return null
  }

  /** Show a project: its stored runs and messages, keeping what the live stream already gave us. */
  async function loadProject(projectId) {
    const [project, rows] = await Promise.all([
      apiFetch(`/api/projects/${projectId}`),
      apiFetch(`/api/projects/${projectId}/runs`),
    ])
    const live = messages.value.filter(m => m.run_id != null && m.run_id === activeRunId.value)
    reset()
    runs.value = rows
    // A live run's commands stay only when reloading their own project; otherwise
    // the Agent tab shows this project's latest commands from the store.
    if (commandsProject !== projectId) commands.value = []
    commandsProject = projectId
    const rebuild = commands.value.length === 0
    for (const m of project.messages || []) {
      if (!add(m) || !rebuild) continue
      if (m.message_type === 'command') recordCommand(m)
      else if (m.message_type === 'tool') recordTool(m)
    }
    // The live view may be ahead of the store (a run in progress here).
    if (rows.some(r => r.id === activeRunId.value)) for (const m of live) add(m)
  }

  async function refreshRuns(projectId) {
    const rows = await apiFetch(`/api/projects/${projectId}/runs`)
    for (const row of rows) {
      const known = runs.value.find(r => r.id === row.id)
      if (known) Object.assign(known, row)
      else runs.value.push(row)
    }
  }

  /** Clear the shown project. A live run's status, turn and commands stay (it's in this project). */
  function reset() {
    messages.value = []
    runs.value = []
    seen.clear()
    draft.value = null
    lastSpeed.value = null
    asking.value = null
    for (const k of Object.keys(answered)) delete answered[k]
    if (status.value !== 'running' && status.value !== 'paused') {
      status.value = 'idle'
      turn.value = null
      commands.value = []
    }
  }

  /** A task the user just started: show its run at once, before any message. */
  function started(runId, prompt, mode) {
    activeRunId.value = runId
    status.value = 'running'
    turn.value = null
    if (!runs.value.some(r => r.id === runId)) {
      runs.value.push({ id: runId, prompt, mode, status: 'running', tokens_in: 0, tokens_out: 0, cost_usd: 0, started_at: new Date().toISOString(), ended_at: null })
    }
  }

  /** Ask one agent about a finished run. The answer isn't streamed: the line shows who's answering. */
  async function ask(runId, agent, question) {
    // Each entry gets its own instant: entries are de-duplicated by time, type and agent.
    let tick = 0
    const now = () => new Date(Date.now() + tick++).toISOString()
    add({ run_id: runId, agent_name: 'You', content: question, message_type: 'question', timestamp: now() })
    asking.value = { agent, run_id: runId }
    try {
      const reply = await apiFetch(`/api/runs/${runId}/chat`, { method: 'POST', body: { agent, message: question } })
      if (!runs.value.some(r => r.id === runId)) return // another project is shown now
      add({
        run_id: runId, agent_name: reply.agent, content: reply.reply, message_type: 'answer', timestamp: now(),
        model: reply.model, tokens_in: reply.tokens_in, tokens_out: reply.tokens_out, cost_usd: reply.cost_usd,
      })
      // What a run says live: its warnings, then a cap that cut the answer short. They go the
      // same way (a toast too), under the agent's name so its filter keeps them with the answer.
      const notes = [...(reply.warnings || []).map(content => ({ content, message_type: 'warning' }))]
      if (reply.notice) notes.push({ content: reply.notice, message_type: 'limit_reached' })
      for (const note of notes) ingest({ run_id: runId, agent_name: reply.agent, timestamp: now(), ...note })
    } finally {
      if (asking.value?.run_id === runId) asking.value = null
    }
  }

  /** The decision waiting for an answer: the latest one in the active run, while it's paused. */
  const openDecision = computed(() => {
    if (status.value !== 'paused') return null
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i]
      if (m.message_type === 'decision') return m.run_id === activeRunId.value && !answered[m.key] ? m : null
    }
    return null
  })

  /** Runs in order, each with its timeline entries. Messages from before runs existed come first.
   * A reply that only called tools has no text: its tokens count, but it isn't shown. */
  const timeline = computed(() => {
    const groups = new Map(runs.value.map(r => [r.id, { run: r, items: [] }]))
    const loose = []
    for (const m of messages.value) {
      if (m.message_type === 'agent' && !String(m.content || '').trim()) continue
      if (m.run_id == null) {
        loose.push(m)
        continue
      }
      if (!groups.has(m.run_id)) groups.set(m.run_id, { run: { id: m.run_id, prompt: '', status: '' }, items: [] })
      groups.get(m.run_id).items.push(m)
    }
    const list = [...groups.values()].sort((a, b) => a.run.id - b.run.id)
    return loose.length ? [{ run: null, items: loose }, ...list] : list
  })

  /** Tokens and cost of one run, from its messages (live) or its row (stored totals). */
  function totals(runId) {
    const sum = { tokens_in: 0, tokens_out: 0, cost_usd: 0 }
    for (const m of messages.value) {
      if (m.run_id !== runId || (m.message_type !== 'agent' && m.message_type !== 'answer')) continue
      sum.tokens_in += m.tokens_in || 0
      sum.tokens_out += m.tokens_out || 0
      sum.cost_usd += m.cost_usd || 0
    }
    const row = runs.value.find(r => r.id === runId)
    if (row && row.tokens_in + row.tokens_out > sum.tokens_in + sum.tokens_out) {
      return { tokens_in: row.tokens_in, tokens_out: row.tokens_out, cost_usd: row.cost_usd }
    }
    return sum
  }

  return {
    status, activeRunId, runs, messages, draft, turn, asking, commands, pulls, answered, lastSpeed,
    timeline, openDecision,
    ingest, loadProject, refreshRuns, reset, started, ask, totals,
  }
}
