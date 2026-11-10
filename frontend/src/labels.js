/** Names, phrases and number formats shared by the dashboard. */

export const MASCOT_STATES = [
  'idle', 'waiting', 'done', 'stopped', 'error',
  'planner', 'coder', 'coder-thinking', 'coder-typing', 'reviewer', 'tester', 'docs',
  'discussion', 'follow-up',
]

/** "ReviewerSecurity" -> "Reviewer Security", unless the agent has a job title. */
export function agentLabel(name, agents = {}) {
  if (name === 'You' || name === 'System') return name
  const title = agents[name]?.job_title
  return title || String(name).replace(/([a-z])([A-Z])/g, '$1 $2')
}

/** The "now working" line for a turn_start (data: role, activity). */
export function workingPhrase(turn, agents = {}) {
  const who = agentLabel(turn.agent, agents)
  if (turn.activity === 'discussing the plan') return 'The crew is discussing the plan…'
  if (turn.activity === 'revising the plan') return 'Revising the plan…'
  if (turn.activity === 'fixing a failed command') return `${who} is fixing a failed command…`
  switch (turn.role) {
    case 'planner': return 'Planning the build…'
    case 'coder': return 'Deliberation of the Coder…'
    case 'reviewer': return 'Checking of the Checker…'
    case 'tester': return 'Testing…'
    case 'docs': return 'Writing the docs…'
    default: return `${who} is ${turn.activity || 'working'}…`
  }
}

/** Which mascot loop fits a turn. `streaming`: text has started to arrive. */
export function turnMascot(turn, streaming) {
  if (turn.activity === 'discussing the plan') return 'discussion'
  if (turn.role === 'coder' || turn.activity === 'fixing a failed command') {
    return streaming ? 'coder-typing' : 'coder-thinking'
  }
  if (['planner', 'reviewer', 'tester', 'docs'].includes(turn.role)) return turn.role
  return streaming ? 'coder-typing' : 'coder-thinking'
}

export const RUN_MODES = [
  { id: 'full', label: 'Build', hint: 'Plan, code and review, then tests and docs' },
  { id: 'plan', label: 'Plan only', hint: 'The planner, then the docs writer' },
  { id: 'code', label: 'Plan and code', hint: 'Plan, then code and review' },
  { id: 'review', label: 'Review', hint: "Review this project's latest run" },
]

export const ROLES = ['planner', 'coder', 'reviewer', 'tester', 'docs', 'custom']

const tokens = new Intl.NumberFormat('en-PH')
const compact = new Intl.NumberFormat('en-PH', { notation: 'compact', maximumFractionDigits: 1 })

export function formatTokens(n) {
  if (n == null) return '0'
  return n >= 100000 ? compact.format(n) : tokens.format(n)
}

/** USD with enough digits that small runs don't show as $0.00. */
export function formatCost(usd) {
  if (!usd) return '$0.00'
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(2)}`
}

export function formatBytes(bytes) {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function formatTime(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString('en-PH', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

/** "ollama:qwen3:8b" -> { provider: "ollama", model: "qwen3:8b" } */
export function splitRef(ref) {
  const i = String(ref || '').indexOf(':')
  return i < 0 ? { provider: '', model: ref || '' } : { provider: ref.slice(0, i), model: ref.slice(i + 1) }
}

// Terminal colour and cursor codes, for showing command output as plain text.
const ANSI = /\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]/g // eslint-disable-line no-control-regex
export function stripAnsi(text) {
  return String(text || '').replace(ANSI, '')
}
