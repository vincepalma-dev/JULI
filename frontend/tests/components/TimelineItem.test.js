import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TimelineItem from '../../src/components/TimelineItem.vue'
import { serveApi, watchSaves } from '../helpers.js'

afterEach(() => vi.restoreAllMocks())

const agents = { SecurityAuditor: { color: '#ef4444', job_title: 'Auditor' } }
const item = (m, props = {}) => mount(TimelineItem, { props: { m: { key: 'k', timestamp: '2026-11-10T00:00:00Z', ...m }, agents, ...props } })

describe('TimelineItem', () => {
  it("shows an agent's reply with its model, tokens and cost", () => {
    const wrapper = item({ message_type: 'agent', agent_name: 'SecurityAuditor', content: 'All good.', model: 'openai:gpt-6.1-sol', tokens_in: 1200, tokens_out: 300, cost_usd: 0.0123 })
    const text = wrapper.text()
    expect(wrapper.find('h3').text()).toBe('Auditor')
    expect(text).toContain('All good.')
    expect(text).toContain('openai:gpt-6.1-sol')
    expect(text).toContain('1,200 in · 300 out')
    expect(text).toContain('$0.01')
  })

  it('says when a model has no known price', () => {
    expect(item({ message_type: 'agent', agent_name: 'X', content: 'Hi', model: 'fake:fake', tokens_in: 1, tokens_out: 1, cost_usd: null }).text()).toContain('no price')
  })

  it('speaks as Juli in "Juli only", naming who answered a follow-up', () => {
    const wrapper = item({ message_type: 'answer', agent_name: 'SecurityAuditor', content: 'Because.' }, { asJuli: true })
    expect(wrapper.find('h3').text()).toContain('Juli')
    expect(wrapper.find('h3').text()).toContain('follow-up from Auditor')
  })

  it('copies a reply and downloads it as a Markdown file named for the run and the agent', async () => {
    vi.useFakeTimers()
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const saved = watchSaves()
    const wrapper = item({ message_type: 'agent', agent_name: 'SecurityAuditor', content: '# Audit\nAll good.', run_id: 12 })
    const button = label => wrapper.findAll('button').find(b => b.text() === label)

    await button('Copy').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('# Audit\nAll good.')
    expect(button('Copied')).toBeTruthy()
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(button('Copy')).toBeTruthy()

    await button('Download').trigger('click')
    expect(saved.map(s => s.name)).toEqual(['juli-run-12-SecurityAuditor.md'])
    expect(await saved[0].blob.text()).toBe('# Audit\nAll good.')
    expect(button('Download files')).toBeUndefined() // only at the end of a run that wrote files
    vi.useRealTimers()
  })

  it('names a follow-up answer and a reply from before runs existed', async () => {
    const saved = watchSaves()
    const download = async m => item(m).findAll('button').find(b => b.text() === 'Download').trigger('click')
    await download({ message_type: 'answer', agent_name: 'Coder', content: 'Because.', run_id: 3 })
    await download({ message_type: 'agent', agent_name: 'Coder', content: 'Old.' })
    expect(saved.map(s => s.name)).toEqual(['juli-run-3-Coder-follow-up.md', 'juli-Coder.md'])
  })

  it("offers the project's files on the reply that ends a run, and says why a download failed", async () => {
    const saved = watchSaves()
    serveApi({ 'GET /api/projects/abcdef123456/workspace/zip': new Blob(['zip']) })
    const wrapper = item({ message_type: 'agent', agent_name: 'Coder', content: 'Done.', run_id: 1 }, { zipProject: 'abcdef123456' })
    const files = () => wrapper.findAll('button').find(b => b.text() === 'Download files')
    await files().trigger('click')
    await flushPromises()
    expect(saved.map(s => s.name)).toEqual(['juli-abcdef12.zip'])
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)

    serveApi({ 'GET /api/projects/abcdef123456/workspace/zip': { status: 404, body: { detail: 'Project not found' } } })
    await files().trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe('Project not found')
    expect(saved).toHaveLength(1)
  })

  it('shows your note and your question', () => {
    expect(item({ message_type: 'user', content: 'Use SQLite' }).text()).toContain('Note to the crew')
    expect(item({ message_type: 'question', content: 'Why?' }).text()).toContain('Your question')
  })

  it('lists the files written, each one opening it', async () => {
    const wrapper = item({ message_type: 'files', agent_name: 'Coder', data: { paths: ['a.py', 'b.py'] } })
    expect(wrapper.text()).toContain('Coder wrote')
    await wrapper.findAll('button')[1].trigger('click')
    expect(wrapper.emitted('open-file')).toEqual([['b.py']])
  })

  it.each([
    [{ status: 'passed', exit_code: 0, seconds: 2.04 }, 'passed · exit 0 · 2.0 s', 'text-emerald-300'],
    [{ status: 'denied' }, 'denied', 'text-slate-300'],
    [{ status: 'failed', exit_code: 1 }, 'failed · exit 1', 'text-red-300'],
  ])('shows a command result %#', (data, label, tone) => {
    const wrapper = item({ message_type: 'command', data: { command: 'pytest -q', output: '\x1b[31mboom\x1b[0m', ...data } })
    expect(wrapper.find('code').text()).toBe('pytest -q')
    expect(wrapper.find('.badge').text()).toBe(label)
    expect(wrapper.find('.badge').classes()).toContain(tone)
    expect(wrapper.find('pre').text()).toBe('boom')
  })

  it('says when a command printed nothing', () => {
    expect(item({ message_type: 'command', data: { command: 'true', status: 'passed' } }).find('pre').text()).toBe('No output.')
  })

  it('shows warnings, limits, errors and system lines', () => {
    expect(item({ message_type: 'limit_reached', content: 'Limit reached' }).text()).toBe('Limit reached')
    expect(item({ message_type: 'error', content: 'It broke' }).find('[role="alert"]').text()).toBe('It broke')
    expect(item({ message_type: 'system', content: 'Crew for this run' }).find('p').text()).toBe('Crew for this run')
  })

  it('shows a decision as its card, open or answered', () => {
    const m = { message_type: 'decision', content: 'Approve?', data: { kind: 'plan_approval' } }
    expect(item(m, { openDecisionKey: 'k' }).text()).toContain('Approve plan')
    expect(item(m, { answered: { k: 'approve' } }).text()).toContain('Approved')
  })
})

describe('TimelineItem tool calls', () => {
  it('shows a tool call compactly, with its result inside', () => {
    const wrapper = item({
      message_type: 'tool', agent_name: 'SecurityAuditor', content: 'read_file app.py',
      data: { tool: 'read_file', status: 'ok', output: 'def add(a, b):', seconds: 0.25, server: null },
    })
    expect(wrapper.find('summary').text()).toContain('Auditor')
    expect(wrapper.find('summary').text()).toContain('read_file app.py')
    expect(wrapper.find('.badge').text()).toBe('done · 0.3 s')
    expect(wrapper.find('pre').text()).toBe('def add(a, b):')
  })

  it("names an MCP tool's server and shows a denial", () => {
    const wrapper = item({ message_type: 'tool', agent_name: 'X', content: 'mcp__gh__search', data: { tool: 'mcp__gh__search', status: 'denied', output: '', server: 'gh' } })
    expect(wrapper.text()).toContain('MCP · gh')
    expect(wrapper.find('.badge').text()).toBe('denied')
    expect(wrapper.find('pre').text()).toBe('No output.')
  })

  it('marks a failed tool call', () => {
    const wrapper = item({ message_type: 'tool', agent_name: 'X', content: 'search_files x', data: { tool: 'search_files', status: 'error' } })
    expect(wrapper.find('.badge').classes()).toContain('text-red-300')
  })
})
