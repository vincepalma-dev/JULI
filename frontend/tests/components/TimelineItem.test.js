import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TimelineItem from '../../src/components/TimelineItem.vue'

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
