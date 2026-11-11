/** Names, phrases and number formats shared by the dashboard. */

export const MASCOT_STATES = [
  'idle', 'waiting', 'done', 'stopped', 'error',
  'planner', 'coder', 'coder-thinking', 'coder-typing', 'reviewer', 'tester', 'docs',
  'devops', 'security', 'analyst',
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

/** The live line for a tool call, from its summary ("read_file src/app.py"). */
export function toolPhrase(summary) {
  const [name, ...rest] = String(summary || '').split(' ')
  const arg = rest.join(' ')
  switch (name) {
    case 'read_file': return `Reading ${arg}…`
    case 'list_files': return arg ? `Looking in ${arg}…` : 'Looking through the files…'
    case 'search_files': return `Searching for “${arg}”…`
    case 'handoff': return `Handing off to ${arg}…`
    default: {
      const mcp = /^mcp__(.+?)__(.+)$/.exec(name)
      return mcp ? `Using ${mcp[2]} from ${mcp[1]}…` : `Using ${name}…`
    }
  }
}

/** The icon for a tool call. */
export function toolIcon(tool) {
  if (tool === 'read_file' || tool === 'list_files') return 'file'
  if (tool === 'search_files') return 'search'
  if (tool === 'handoff') return 'arrows'
  return 'wrench'
}

/**
 * Which mascot pose fits a turn. `streaming`: text has started to arrive.
 * An agent's own working pose (its "pose" setting) comes before its role.
 */
export function turnMascot(turn, streaming, agents = {}) {
  if (turn.activity === 'discussing the plan') return 'discussion'
  const chosen = agents[turn.agent]?.pose
  const pose = WORK_POSES.includes(chosen) ? chosen : turn.role
  if (pose !== 'coder' && turn.activity !== 'fixing a failed command' && WORK_POSES.includes(pose)) return pose
  return streaming ? 'coder-typing' : 'coder-thinking'
}
const WORK_POSES = ['planner', 'coder', 'reviewer', 'tester', 'docs', 'devops', 'security', 'analyst']

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

/**
 * "npx -y 'a b'" -> ["npx", "-y", "a b"]: spaces split, quotes group, and
 * quoted parts join the text next to them. Single quotes are literal; inside
 * double quotes, \" and \\ are escapes. A bare backslash stays (Windows paths).
 */
export function splitArgs(text) {
  const s = String(text)
  const args = []
  let arg = null
  for (let i = 0; i < s.length; i++) {
    const c = s[i]
    if (/\s/.test(c)) {
      if (arg !== null) args.push(arg)
      arg = null
      continue
    }
    arg ??= ''
    if (c === "'") {
      const end = s.indexOf("'", i + 1)
      const stop = end < 0 ? s.length : end
      arg += s.slice(i + 1, stop)
      i = stop
    } else if (c === '"') {
      for (i++; i < s.length && s[i] !== '"'; i++) {
        if (s[i] === '\\' && (s[i + 1] === '"' || s[i + 1] === '\\')) i++
        arg += s[i]
      }
    } else {
      arg += c
    }
  }
  if (arg !== null) args.push(arg)
  return args
}

/** The reverse of splitArgs: an argument that's empty or has spaces or quotes is double-quoted, with \ and " escaped. */
export function joinArgs(args) {
  return args.map(a => (a === '' || /[\s"']/.test(a) ? `"${a.replace(/[\\"]/g, '\\$&')}"` : a)).join(' ')
}
