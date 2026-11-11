import { describe, expect, it, vi } from 'vitest'
import { useRun } from '../src/composables/useRun.js'

let clock = 0
const msg = (type, fields = {}) => ({
  run_id: 1, agent_name: 'Coder', content: '', message_type: type,
  timestamp: new Date(Date.UTC(2026, 10, 10, 0, 0, clock++)).toISOString(), ...fields,
})
const status = (value, runId = 1) => msg('status', { run_id: runId, agent_name: 'System', data: { status: value } })

/** fetch replies for loadProject: the project's messages and its runs. */
function serve(messages, runs) {
  fetch.mockImplementation(async path => ({
    ok: true, status: 200, json: async () => (path.endsWith('/runs') ? runs : { messages }),
  }))
}

describe('useRun ingest', () => {
  it('drops a message it has seen, as a reconnect replays them', () => {
    const run = useRun()
    const m = msg('agent', { content: 'done' })
    run.ingest(m)
    run.ingest({ ...m })
    expect(run.messages.value).toHaveLength(1)
  })

  it('streams chunks into a draft until the final message lands', () => {
    const run = useRun()
    run.ingest(msg('turn_start', { data: { role: 'coder', activity: 'coding' } }))
    run.ingest(msg('chunk', { content: 'Hel' }))
    run.ingest(msg('chunk', { content: 'lo' }))
    expect(run.draft.value.text).toBe('Hello')
    expect(run.turn.value.role).toBe('coder')
    run.ingest(msg('agent', { content: 'Hello' }))
    expect(run.draft.value).toBeNull()
    expect(run.messages.value.map(m => m.message_type)).toEqual(['agent']) // turn_start isn't shown
  })

  it('ends the turn when the run ends, and calls onEnded except for idle', () => {
    const onEnded = vi.fn()
    const run = useRun({ onEnded })
    run.ingest(status('running'))
    run.ingest(msg('turn_start', { data: { role: 'coder' } }))
    run.ingest(status('complete'))
    expect(run.turn.value).toBeNull()
    expect(onEnded).toHaveBeenCalledTimes(1)
    run.ingest(status('idle'))
    expect(onEnded).toHaveBeenCalledTimes(1)
  })
})

describe('useRun openDecision', () => {
  it('is the latest decision of the active run while it is paused', () => {
    const run = useRun()
    run.ingest(status('running'))
    run.ingest(msg('decision', { content: 'Approve the plan?' }))
    expect(run.openDecision.value).toBeNull() // not paused yet
    run.ingest(status('paused'))
    const open = run.openDecision.value
    expect(open.content).toBe('Approve the plan?')
    run.answered[open.key] = 'approve'
    expect(run.openDecision.value).toBeNull()
  })

  it('ignores a decision from another run', () => {
    const run = useRun()
    run.ingest(msg('decision', { run_id: 1 }))
    run.ingest(status('paused', 2))
    expect(run.openDecision.value).toBeNull()
  })
})

describe('useRun timeline and totals', () => {
  it('groups messages by run in order, with messages from before runs first', () => {
    const run = useRun()
    run.started(2, 'second', 'full')
    run.ingest(msg('agent', { run_id: 2, content: 'b' }))
    run.ingest(msg('agent', { run_id: 1, content: 'a' })) // a run the list doesn't know yet
    run.ingest(msg('agent', { run_id: null, agent_name: 'Planner', content: 'p' }))
    const groups = run.timeline.value
    expect(groups.map(g => g.run?.id ?? null)).toEqual([null, 1, 2])
    expect(groups.map(g => g.items.length)).toEqual([1, 1, 1])
  })

  it('sums tokens and cost from the messages, unless the stored run has more', () => {
    const run = useRun()
    run.started(1, 'task', 'full')
    run.ingest(msg('agent', { tokens_in: 10, tokens_out: 5, cost_usd: 0.01 }))
    run.ingest(msg('answer', { agent_name: 'Tester', tokens_in: 1, tokens_out: 1, cost_usd: 0 }))
    expect(run.totals(1)).toEqual({ tokens_in: 11, tokens_out: 6, cost_usd: 0.01 })
    run.runs.value[0] = { ...run.runs.value[0], tokens_in: 100, tokens_out: 50, cost_usd: 0.5 }
    expect(run.totals(1)).toEqual({ tokens_in: 100, tokens_out: 50, cost_usd: 0.5 })
  })
})

describe('useRun loadProject', () => {
  it('replaces the shown project, keeping the live run it is ahead on', async () => {
    const run = useRun()
    run.ingest(status('running', 7))
    run.ingest(msg('agent', { run_id: 7, content: 'live only' }))
    const stored = msg('agent', { run_id: 6, content: 'stored' })
    serve([stored], [{ id: 6 }, { id: 7 }])
    await run.loadProject(1)
    expect(run.messages.value.map(m => m.content)).toEqual(['stored', 'live only'])
    expect(run.status.value).toBe('running') // a live run's status stays
  })

  it("drops another project's messages and the live run's when it isn't in this project", async () => {
    const run = useRun()
    run.ingest(status('running', 7))
    run.ingest(msg('agent', { run_id: 7, content: 'live' }))
    serve([msg('agent', { run_id: 3, content: 'other project' })], [{ id: 3 }])
    await run.loadProject(2)
    expect(run.messages.value.map(m => m.content)).toEqual(['other project'])
  })

  it("rebuilds the Agent tab from a project's stored commands", async () => {
    const run = useRun()
    const command = msg('command', { data: { command: 'pytest', status: 'passed', exit_code: 0, output: 'ok' } })
    serve([command], [{ id: 1 }])
    await run.loadProject(1)
    expect(run.commands.value.map(c => [c.command, c.status])).toEqual([['pytest', 'passed']])
    serve([], [{ id: 9 }])
    await run.loadProject(2)
    expect(run.commands.value).toEqual([])
  })
})

describe('useRun follow-ups and refresh', () => {
  it('asks an agent about a finished run and shows the answer', async () => {
    const run = useRun()
    run.started(1, 'task', 'full')
    fetch.mockImplementation(async () => ({ ok: true, status: 200, json: async () => ({ agent: 'Coder', reply: 'Because SQLite is simple.', model: 'ollama:code', tokens_in: 5, tokens_out: 4, cost_usd: 0 }) }))
    const pending = run.ask(1, 'Coder', 'Why SQLite?')
    expect(run.asking.value).toEqual({ agent: 'Coder', run_id: 1 })
    await pending
    expect(run.asking.value).toBeNull()
    expect(run.messages.value.map(m => [m.message_type, m.content])).toEqual([['question', 'Why SQLite?'], ['answer', 'Because SQLite is simple.']])
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ agent: 'Coder', message: 'Why SQLite?' })
  })

  it('drops an answer that arrives after another project is shown', async () => {
    const run = useRun()
    run.started(1, 'task', 'full')
    let reply
    fetch.mockImplementation(() => new Promise(resolve => { reply = resolve }))
    const pending = run.ask(1, 'Coder', 'Why?')
    run.reset()
    reply({ ok: true, status: 200, json: async () => ({ agent: 'Coder', reply: 'late' }) })
    await pending
    expect(run.messages.value.some(m => m.content === 'late')).toBe(false)
  })

  it('updates known runs and adds new ones on refresh', async () => {
    const run = useRun()
    run.started(1, 'task', 'full')
    fetch.mockImplementation(async () => ({ ok: true, status: 200, json: async () => [{ id: 1, status: 'complete' }, { id: 2, status: 'running' }] }))
    await run.refreshRuns('p')
    expect(run.runs.value.map(r => [r.id, r.status])).toEqual([[1, 'complete'], [2, 'running']])
    expect(run.runs.value[0].prompt).toBe('task') // the rest of the row stays
  })

  it('toasts only recent warnings, and records pull progress', () => {
    const onWarning = vi.fn()
    const run = useRun({ onWarning })
    run.ingest(msg('warning', { content: 'old', timestamp: '2020-01-01T00:00:00Z' }))
    run.ingest(msg('limit_reached', { content: 'now', timestamp: new Date().toISOString() }))
    expect(onWarning.mock.calls.map(([m]) => m.content)).toEqual(['now'])
    run.ingest(msg('pull_progress', { data: { model: 'qwen3:8b', status: 'pulling', completed: 1, total: 2 } }))
    expect(run.pulls['qwen3:8b'].completed).toBe(1)
  })

  it("streams a command's output into the Agent tab and settles it", () => {
    const run = useRun()
    run.ingest(msg('turn_start', { data: { role: 'coder' } }))
    run.ingest(msg('command_start', { content: 'pytest -q', data: { command: 'pytest -q', sandbox: true } }))
    expect(run.turn.value.command).toBe('pytest -q')
    run.ingest(msg('command_output', { content: '1 passed\n', data: { command: 'pytest -q' } }))
    run.ingest(msg('command', { content: '$ pytest -q', data: { command: 'pytest -q', status: 'passed', exit_code: 0, seconds: 1 } }))
    expect(run.commands.value).toMatchObject([{ command: 'pytest -q', sandbox: true, output: '1 passed\n', status: 'passed', exit_code: 0 }])
    expect(run.turn.value.command).toBeNull()
  })
})

describe('useRun tool calls', () => {
  const start = (fields = {}) => msg('tool_start', { content: 'read_file app.py', data: { tool: 'read_file', call_id: 'c1', args: { path: 'app.py' } }, ...fields })
  const done = (fields = {}) => msg('tool', {
    content: 'read_file app.py',
    data: { tool: 'read_file', call_id: 'c1', args: { path: 'app.py' }, status: 'ok', output: 'def add', seconds: 0.1, server: null },
    ...fields,
  })

  it('shows a running tool in the live line and the Agent tab, then settles it in the timeline', () => {
    const run = useRun()
    run.ingest(msg('turn_start', { data: { role: 'coder', activity: 'coding' } }))
    run.ingest(start())
    expect(run.turn.value.tool).toBe('read_file app.py')
    expect(run.commands.value).toMatchObject([{ kind: 'tool', command: 'read_file app.py', status: 'running', agent: 'Coder' }])
    expect(run.messages.value.some(m => m.message_type === 'tool_start')).toBe(false)

    run.ingest(done())
    expect(run.turn.value.tool).toBe(null)
    expect(run.commands.value).toMatchObject([{ kind: 'tool', status: 'ok', output: 'def add', seconds: 0.1 }])
    expect(run.messages.value.filter(m => m.message_type === 'tool')).toHaveLength(1)
  })

  it("keeps a tool's result apart from a command with the same text", () => {
    const run = useRun()
    run.ingest(msg('command_start', { content: 'pytest', data: { command: 'pytest' } }))
    run.ingest(start({ content: 'pytest' }))
    run.ingest(msg('command', { content: '$ pytest', data: { command: 'pytest', status: 'passed', exit_code: 0 } }))
    expect(run.commands.value.map(c => [c.kind ?? 'command', c.status])).toEqual([['command', 'passed'], ['tool', 'running']])
  })

  it('keeps two tool calls by one agent in the same instant, and settles each by its call id', () => {
    const run = useRun()
    const ts = '2026-11-10T09:00:00.000000+00:00'
    run.ingest(start({ timestamp: ts }))
    run.ingest(start({ timestamp: ts, content: 'list_files', data: { tool: 'list_files', call_id: 'c2', args: {} } }))
    run.ingest(done({ timestamp: ts, data: { tool: 'list_files', call_id: 'c2', status: 'ok', output: 'a.py' } }))
    run.ingest(done({ timestamp: ts }))
    expect(run.commands.value.map(c => [c.command, c.status])).toEqual([['read_file app.py', 'ok'], ['list_files', 'ok']])
    expect(run.messages.value.filter(m => m.message_type === 'tool')).toHaveLength(2)
  })

  it("doesn't settle a running tool with a result that has no call id", () => {
    const run = useRun()
    run.ingest(start({ data: { tool: 'read_file', call_id: undefined } }))
    run.ingest(done({ data: { tool: 'read_file', status: 'ok', output: 'x' } }))
    expect(run.commands.value.map(c => c.status)).toEqual(['running', 'ok'])
  })

  it('records a finished tool it never saw start', () => {
    const run = useRun()
    run.ingest(done({ data: { tool: 'mcp__gh__search', call_id: 'x', status: 'error', output: 'boom', server: 'gh' } }))
    expect(run.commands.value).toMatchObject([{ kind: 'tool', status: 'error', server: 'gh', output: 'boom' }])
  })

  it('hides a reply that only called tools, but counts its tokens', () => {
    const run = useRun()
    run.started(1, 'task', 'code')
    run.ingest(msg('agent', { content: '  ', tokens_in: 10, tokens_out: 2 }))
    run.ingest(msg('agent', { content: 'Done.', tokens_in: 5, tokens_out: 1 }))
    expect(run.timeline.value[0].items.map(m => m.content)).toEqual(['Done.'])
    expect(run.totals(1).tokens_in).toBe(15)
  })

  it("rebuilds the Agent tab from a project's stored tool calls", async () => {
    serve([done({ run_id: 3 })], [{ id: 3, prompt: 'p', status: 'complete' }])
    const run = useRun()
    await run.loadProject('p1')
    expect(run.commands.value).toMatchObject([{ kind: 'tool', command: 'read_file app.py', status: 'ok' }])
  })
})
