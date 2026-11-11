// The whole dashboard with a session: the wiring between the API, the live stream and the panels.
import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'
import { sent, serveApi } from './helpers.js'

const SETTINGS = {
  agents: { Planner: { role: 'planner', model: 'ollama:qwen3:8b' }, Coder: { role: 'coder', model: 'openai:gpt-6.1-sol' } },
  available_models: ['openai:gpt-6.1-sol', 'ollama:qwen3:8b'],
  run: {},
  mode: 'custom',
}
const PROVIDERS = [{ id: 'openai', label: 'OpenAI', local: false, needs_key: true }, { id: 'ollama', label: 'Ollama', local: true }]
const PROJECT = { id: 'p1', name: 'Calc', updated_at: null }
let clock = 0
const stamp = () => new Date(Date.UTC(2026, 10, 10, 0, 0, clock++)).toISOString()
const event = (type, fields = {}) => ({ run_id: 5, agent_name: 'System', content: '', message_type: type, timestamp: stamp(), ...fields })

function routes(extra = {}) {
  return {
    'GET /api/settings': SETTINGS,
    'GET /api/providers': PROVIDERS,
    'GET /api/local/models': { ollama: { running: true }, installed: [{ name: 'qwen3:8b' }] },
    'GET /api/status': { status: 'idle' },
    'GET /api/projects': [PROJECT],
    'PUT /api/projects/p1/activate': {},
    'GET /api/projects/p1': { messages: [] },
    'GET /api/projects/p1/runs': [],
    'GET /api/runs/resumable': [],
    'POST /api/task': { run_id: 5 },
    ...extra,
  }
}

async function start(extra) {
  sessionStorage.setItem('juli-token', 't')
  serveApi(routes(extra))
  const wrapper = mount(App, { attachTo: document.body })
  await flushPromises()
  const ws = window.WebSocket.instances[0]
  const push = async m => { ws.onmessage({ data: JSON.stringify(m) }); await flushPromises() }
  return { wrapper, push }
}

async function startTask(wrapper, text = 'Build a calculator') {
  await wrapper.find('#composer-text').setValue(text)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

describe('App with a session', () => {
  it('loads settings and the project, and warns that cloud agents send code to third parties', async () => {
    const { wrapper } = await start()
    expect(wrapper.text()).not.toContain('No session.')
    expect(sent('PUT', '/api/projects/p1/activate')).toHaveLength(1)
    expect(wrapper.text()).toContain('Calc')
    expect(wrapper.text()).toContain('Prompts and code for Coder go to openai, third-party providers with their own terms.')
  })

  it('creates a first project when there is none', async () => {
    const { wrapper } = await start({ 'GET /api/projects': [], 'POST /api/projects': PROJECT })
    expect(sent('POST', '/api/projects')).toEqual([{ name: 'My first project' }])
    expect(wrapper.text()).toContain('Calc')
  })

  it('reopens a run that is going on in a project', async () => {
    const { wrapper } = await start({ 'GET /api/status': { status: 'paused', project_id: 'p1', run_id: 5 } })
    expect(wrapper.find('[role="status"][aria-label^="Run status"]').attributes('aria-label')).toBe('Run status: Waiting for you')
  })

  it('starts a task in the project and streams the run', async () => {
    const { wrapper, push } = await start()
    await startTask(wrapper)
    expect(sent('POST', '/api/task')).toEqual([{ prompt: 'Build a calculator', mode: 'full', approve_plan: false, project_id: 'p1', ignore_allowance: false }])
    expect(wrapper.text()).toContain('Build a calculator')
    await push(event('status', { data: { status: 'running' } }))
    await push(event('turn_start', { agent_name: 'Coder', model: 'openai:gpt-6.1-sol', data: { role: 'coder', activity: 'coding' } }))
    await push(event('chunk', { agent_name: 'Coder', content: 'def add' }))
    expect(wrapper.text()).toContain('def add')
    expect(wrapper.text()).toContain('Deliberation of the Coder…')
    await push(event('agent', { agent_name: 'Coder', content: 'def add(a, b): ...', model: 'openai:gpt-6.1-sol', tokens_in: 100, tokens_out: 20, cost_usd: 0.002 }))
    expect(wrapper.text()).toContain('100 in · 20 out')
    await push(event('status', { data: { status: 'complete' } }))
    expect(wrapper.text()).toContain('Done')
  })

  it('stops a live run', async () => {
    const { wrapper, push } = await start({ 'POST /api/task/stop': {} })
    await startTask(wrapper)
    await push(event('status', { data: { status: 'running' } }))
    await wrapper.find('[aria-label="Stop the run"]').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/task/stop')).toHaveLength(1)
  })

  it('sends a note to the running crew', async () => {
    const { wrapper, push } = await start({ 'POST /api/task/message': {} })
    await startTask(wrapper)
    await push(event('status', { data: { status: 'running' } }))
    await wrapper.find('#composer-text').setValue('Use SQLite')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(sent('POST', '/api/task/message')).toEqual([{ content: 'Use SQLite' }])
  })

  it('brings a command approval up as a modal and sends the answer', async () => {
    const { wrapper, push } = await start({ 'POST /api/task/decision': {} })
    await startTask(wrapper)
    await push(event('status', { data: { status: 'running' } }))
    await push(event('decision', { content: 'Coder wants to run this command.\n\npytest -q', data: { kind: 'command_approval', agent: 'Coder', command: 'pytest -q', sandbox: false, reason: 'the Docker sandbox is off' } }))
    await push(event('status', { data: { status: 'paused' } }))
    const modal = wrapper.find('dialog.modal[open]')
    expect(modal.exists()).toBe(true)
    expect(modal.find('pre').text()).toBe('pytest -q')
    await modal.findAll('button').find(b => b.text().includes('Deny')).trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/task/decision')).toEqual([{ action: 'deny' }])
    expect(wrapper.find('dialog.modal[open]').exists()).toBe(false)
  })

  it('brings an MCP tool approval up as a modal too', async () => {
    const { wrapper, push } = await start({ 'POST /api/task/decision': {} })
    await startTask(wrapper)
    await push(event('status', { data: { status: 'running' } }))
    await push(event('decision', { content: 'Tester wants to use echo.\n\n{}', data: { kind: 'tool_approval', agent: 'Tester', tool: 'echo', server: 'fake', args: { text: 'hi' }, sandbox: false, reason: 'its server runs on this machine, outside the sandbox' } }))
    await push(event('status', { data: { status: 'paused' } }))
    const modal = wrapper.find('dialog.modal[open]')
    expect(modal.find('pre').text()).toBe('{\n  "text": "hi"\n}')
    await modal.findAll('button').find(b => b.text().includes('Allow this call')).trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/task/decision')).toEqual([{ action: 'approve' }])
  })

  it('refreshes projects in place after a partial "delete all data", keeping what is left in view', async () => {
    let deleted = false
    const { wrapper } = await start({
      'GET /api/projects': () => (deleted ? [] : [PROJECT]),
      'POST /api/data/delete-all': () => {
        deleted = true
        return { status: 'partly deleted', problems: ["Some workspace files couldn't be deleted (in use)."] }
      },
      'POST /api/projects': { id: 'p2', name: 'My first project', updated_at: null },
      'PUT /api/projects/p2/activate': {},
      'GET /api/projects/p2': { messages: [] },
      'GET /api/projects/p2/runs': [],
    })
    await wrapper.findAll('nav button').filter(b => b.text() === 'Settings').at(-1).trigger('click')
    await flushPromises()
    await wrapper.findAll('[role="tab"]').find(t => t.text() === 'Data').trigger('click')
    await wrapper.find('#delete-confirm').setValue('delete all data')
    await wrapper.findAll('form').filter(f => f.text().includes('Delete everything')).at(0).trigger('submit')
    await flushPromises()

    expect(sent('POST', '/api/projects')).toEqual([{ name: 'My first project' }])
    expect(sent('PUT', '/api/projects/p2/activate')).toHaveLength(1)
    expect(wrapper.text()).toContain("Mostly deleted. Some workspace files couldn't be deleted (in use).")
  })

  it('drops the old resume banner after a partial delete, even when the fresh project fails', async () => {
    let deleted = false
    const { wrapper } = await start({
      'GET /api/runs/resumable': [{ id: 3, status: 'error', prompt: 'Old task', mode: 'full' }],
      'GET /api/projects': () => (deleted ? [] : [PROJECT]),
      'POST /api/data/delete-all': () => {
        deleted = true
        return { status: 'partly deleted', problems: ['Some files stayed.'] }
      },
      'POST /api/projects': { status: 500, body: { detail: 'disk full' } },
    })
    expect(wrapper.find('[aria-label="Dismiss run 3"]').exists()).toBe(true)
    await wrapper.findAll('nav button').filter(b => b.text() === 'Settings').at(-1).trigger('click')
    await flushPromises()
    await wrapper.findAll('[role="tab"]').find(t => t.text() === 'Data').trigger('click')
    await wrapper.find('#delete-confirm').setValue('delete all data')
    await wrapper.findAll('form').filter(f => f.text().includes('Delete everything')).at(0).trigger('submit')
    await flushPromises()
    expect(wrapper.find('[aria-label="Dismiss run 3"]').exists()).toBe(false)
  })

  it('shows a key problem as a banner, with a way to stop', async () => {
    const { wrapper, push } = await start({ 'POST /api/task/stop': {} })
    await startTask(wrapper)
    await push(event('decision', { content: 'Key rejected', data: { kind: 'key_problem', agent: 'Coder', model: 'openai:gpt-6.1-sol', problem: 'out_of_credit' } }))
    await push(event('status', { data: { status: 'paused' } }))
    const banner = wrapper.findAll('[role="alert"]').find(a => a.text().includes('is out of credit'))
    expect(banner.text()).toContain('openai is out of credit: Coder paused on openai:gpt-6.1-sol.')
    await banner.findAll('button').find(b => b.text() === 'Stop run').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/task/stop')).toHaveLength(1)
  })

  it('offers to start anyway when a monthly allowance blocks the task', async () => {
    const { wrapper } = await start({
      'POST /api/task': body => (body.ignore_allowance ? { run_id: 6 } : { status: 409, body: { detail: 'Monthly allowance reached for openai' } }),
    })
    await startTask(wrapper)
    const toast = wrapper.findAll('[role="status"]').find(t => t.text().includes('Monthly allowance reached'))
    expect(wrapper.find('#composer-text').element.value).toBe('Build a calculator') // kept
    await toast.findAll('button').find(b => b.text() === 'Start anyway').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/task').map(b => b.ignore_allowance)).toEqual([false, true])
  })

  it('shows a failed request as an error toast that can be dismissed', async () => {
    const { wrapper } = await start({ 'POST /api/task': { status: 500, body: { detail: 'The engine broke' } } })
    await startTask(wrapper)
    const toast = wrapper.findAll('[role="alert"]').find(a => a.text().includes('The engine broke'))
    await toast.find('[aria-label="Dismiss"]').trigger('click')
    expect(wrapper.text()).not.toContain('The engine broke')
  })

  it('offers to resume a run that was cut short', async () => {
    const { wrapper } = await start({
      'GET /api/runs/resumable': [{ id: 3, status: 'error', prompt: 'Old task', mode: 'full' }],
      'POST /api/runs/3/resume': {},
    })
    expect(wrapper.text()).toContain('Run 3 was cut short (an error).')
    await wrapper.findAll('button').find(b => b.text() === 'Resume run 3').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/runs/3/resume')).toEqual([{ ignore_allowance: false }])
    expect(wrapper.text()).not.toContain('was cut short')
  })

  it('opens panels from the sidebar, and remembers the "Juli only" view', async () => {
    const { wrapper } = await start()
    await wrapper.findAll('nav[aria-label="Panels"] button').find(b => b.text().includes('Projects')).trigger('click')
    expect(wrapper.findAll('dialog[open]').some(d => d.text().includes('Your projects'))).toBe(true)
    await wrapper.find('[role="switch"][aria-label="Juli only"]').trigger('click')
    expect(localStorage.getItem('juli-view')).toBe('juli')
    localStorage.clear()
  })

  it('deletes the open project and moves to another', async () => {
    const other = { id: 'p2', name: 'Todo', updated_at: null }
    const { wrapper } = await start({
      'GET /api/projects': [PROJECT, other],
      'DELETE /api/projects/p1': null,
      'PUT /api/projects/p2/activate': {},
      'GET /api/projects/p2': { messages: [] },
      'GET /api/projects/p2/runs': [],
    })
    await wrapper.findAll('nav[aria-label="Panels"] button').find(b => b.text().includes('Projects')).trigger('click')
    await wrapper.find('[aria-label="Delete Calc"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text() === 'Delete').trigger('click')
    await flushPromises()
    expect(sent('PUT', '/api/projects/p2/activate')).toHaveLength(1)
  })
})
