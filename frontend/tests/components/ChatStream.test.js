import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatStream from '../../src/components/ChatStream.vue'

const agents = { Planner: { color: '#6366f1' }, Coder: { color: '#06b6d4' } }
const at = s => `2026-11-10T00:00:${String(s).padStart(2, '0')}Z`
const msg = (key, type, agent, content, extra = {}) => ({ key, run_id: 1, message_type: type, agent_name: agent, content, timestamp: at(Number(key.slice(1))), ...extra })

const run = { id: 1, prompt: 'Build a calculator', mode: 'full', status: 'complete', started_at: at(0) }
const items = [
  msg('m1', 'agent', 'Planner', 'The plan.', { model: 'ollama:plan', tokens_in: 10, tokens_out: 5, cost_usd: 0 }),
  msg('m2', 'user', 'You', 'Use SQLite'),
  msg('m3', 'files', 'Coder', '', { data: { paths: ['calc.py'] } }),
  msg('m4', 'agent', 'Coder', 'Here is calc.py.', { model: 'ollama:code', tokens_in: 20, tokens_out: 8 }),
  msg('m5', 'warning', 'System', 'Running low on credit'),
]
const timeline = [{ run, items }]
const totals = () => ({ tokens_in: 30, tokens_out: 13, cost_usd: 0 })

const mountStream = (props = {}) => mount(ChatStream, { props: { timeline, agents, totals, activeRunId: 1, ...props } })

describe('ChatStream', () => {
  it('invites a first task when the project is empty', () => {
    expect(mountStream({ timeline: [] }).text()).toContain('Ready when you are')
  })

  it("shows each run's task with its mode and status, then the whole crew in order", () => {
    const wrapper = mountStream()
    const text = wrapper.text()
    expect(text).toContain('Build a calculator')
    expect(text).toContain('Run 1')
    expect(text).toContain('· Build')
    expect(wrapper.find('.badge').text()).toBe('complete')
    const order = ['The plan.', 'Use SQLite', 'calc.py', 'Here is calc.py.', 'Running low on credit'].map(t => text.indexOf(t))
    expect(order).toEqual([...order].sort((a, b) => a - b))
    expect(wrapper.find('details').exists()).toBe(false) // nothing folded
  })

  it('folds the crew\'s work away in "Juli only" and replies as Juli with the run totals', () => {
    const wrapper = mountStream({ view: 'juli' })
    const folded = wrapper.find('details')
    expect(folded.find('summary').text()).toContain('Show the crew\'s work')
    expect(folded.find('summary').text()).toContain('2 steps · Planner') // the plan and the files; the last reply is shown
    const reply = wrapper.findAll('article').filter(a => a.find('h3').exists() && a.find('h3').text() === 'Juli').at(-1)
    expect(reply.text()).toContain('Here is calc.py.')
    expect(reply.text()).toContain('from Coder')
    expect(reply.text()).toContain('run total 30 in · 13 out')
    // Your note stays in view before the reply, the warning after it.
    const text = wrapper.text()
    expect(text.indexOf('Use SQLite')).toBeLessThan(text.indexOf('Here is calc.py.'))
    expect(text.indexOf('Running low on credit')).toBeGreaterThan(text.indexOf('Here is calc.py.'))
    expect(folded.text()).not.toContain('Use SQLite')
  })

  it('folds tool calls with the rest of the crew work in "Juli only"', () => {
    const tool = msg('m3', 'tool', 'Coder', 'read_file calc.py', { data: { tool: 'read_file', status: 'ok', output: 'x' } })
    const wrapper = mountStream({ view: 'juli', timeline: [{ run, items: [items[0], tool, items[3]] }] })
    expect(wrapper.find('details summary').text()).toContain('2 steps')
    expect(wrapper.find('details').text()).toContain('read_file calc.py')
  })

  it('keeps an open question in view in "Juli only", and folds answered ones', () => {
    const decision = msg('m6', 'decision', 'System', 'Approve the plan?', { data: { kind: 'plan_approval' } })
    const answered = msg('m7', 'decision', 'System', 'Run pytest?', { data: { kind: 'command_approval', command: 'pytest' } })
    const live = [{ run: { ...run, status: 'paused' }, items: [...items, answered, decision] }]
    const wrapper = mountStream({ timeline: live, view: 'juli', status: 'paused', openDecisionKey: 'm6' })
    const folded = wrapper.find('details')
    expect(folded.text()).toContain('Run pytest?')
    expect(folded.text()).not.toContain('Approve the plan?')
    expect(wrapper.find('[data-decision="m6"]').exists()).toBe(true)
  })

  it('has no reply yet while the run is live', () => {
    const wrapper = mountStream({ view: 'juli', status: 'running', timeline: [{ run: { ...run, status: 'running' }, items }] })
    expect(wrapper.findAll('h3').some(h => h.text() === 'Juli')).toBe(false)
    expect(wrapper.find('details summary').text()).toContain('3 steps')
  })

  it("shows one agent's messages under a filter, and the whole crew again on request", async () => {
    const wrapper = mountStream({ filter: 'Coder', view: 'juli' })
    expect(wrapper.text()).toContain('Showing only')
    expect(wrapper.text()).toContain('Here is calc.py.')
    expect(wrapper.text()).not.toContain('The plan.')
    expect(wrapper.find('details').exists()).toBe(false) // a filter shows the whole crew's view
    await wrapper.findAll('button').find(b => b.text().includes('Show everyone')).trigger('click')
    expect(wrapper.emitted('clear-filter')).toHaveLength(1)
  })

  it('streams the draft under the agent name', () => {
    const wrapper = mountStream({ status: 'running', draft: { agent: 'Coder', text: 'Writing calc' } })
    const streaming = wrapper.find('[aria-busy="true"]')
    expect(streaming.text()).toContain('Coder')
    expect(streaming.text()).toContain('Writing calc')
    expect(mountStream({ status: 'running', view: 'juli', draft: { agent: 'Coder', text: 'Writing calc' } }).find('[aria-busy="true"]').exists()).toBe(false)
  })

  it('shows messages from before runs existed, and the live line after a run', () => {
    const wrapper = mountStream({ timeline: [{ run: null, items: [msg('m9', 'system', 'System', 'Old note')] }, ...timeline], status: 'complete' })
    expect(wrapper.text()).toContain('Earlier messages')
    expect(wrapper.text()).toContain('Old note')
    expect(wrapper.find('[role="status"]').text()).toContain('Done')
  })

  it('passes answers and file clicks up', async () => {
    const decision = msg('m6', 'decision', 'System', 'Approve?', { data: { kind: 'plan_approval' } })
    const wrapper = mountStream({ timeline: [{ run, items: [...items, decision] }] })
    await wrapper.findAll('button').find(b => b.text() === 'calc.py').trigger('click')
    expect(wrapper.emitted('open-file')).toEqual([['calc.py']])
    wrapper.findComponent({ name: 'DecisionCard' }).vm.$emit('answered', 'approve')
    expect(wrapper.emitted('answered')).toEqual([['m6', 'approve']])
  })
})
