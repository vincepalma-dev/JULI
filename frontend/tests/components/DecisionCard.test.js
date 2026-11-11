import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import DecisionCard from '../../src/components/DecisionCard.vue'
import { sent, serveApi } from '../helpers.js'

const plan = { key: 'k1', content: 'The planner has a plan.', data: { kind: 'plan_approval' } }
const command = {
  key: 'k2',
  content: 'Coder wants to run this command on this machine, outside any sandbox.\n\npytest -q; rm -rf build',
  data: { kind: 'command_approval', agent: 'Coder', command: 'pytest -q; rm -rf build', sandbox: false, reason: 'it contains shell metacharacters' },
}
const keyProblem = { key: 'k3', content: 'The key was rejected.', data: { kind: 'key_problem', agent: 'Coder' } }

const button = (wrapper, name) => wrapper.findAll('button').find(b => b.text().includes(name))

describe('DecisionCard: plan approval', () => {
  it('approves the plan', async () => {
    serveApi({ 'POST /api/task/decision': null })
    const wrapper = mount(DecisionCard, { props: { message: plan, open: true } })
    expect(wrapper.text()).toContain('Approve the plan?')
    await button(wrapper, 'Approve plan').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/task/decision')).toEqual([{ action: 'approve' }])
    expect(wrapper.emitted('answered')).toEqual([['approve']])
  })

  it('sends the requested changes to the planner, and only with text', async () => {
    serveApi({ 'POST /api/task/decision': null })
    const wrapper = mount(DecisionCard, { props: { message: plan, open: true } })
    await button(wrapper, 'Ask for changes').trigger('click')
    expect(button(wrapper, 'Send to planner').attributes('disabled')).toBeDefined()
    await wrapper.find('textarea').setValue('  Use SQLite  ')
    await button(wrapper, 'Send to planner').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/task/decision')).toEqual([{ action: 'revise', message: 'Use SQLite' }])
  })

  it('goes back from the change request, and stops the run', async () => {
    serveApi({ 'POST /api/task/decision': null })
    const wrapper = mount(DecisionCard, { props: { message: plan, open: true } })
    await button(wrapper, 'Ask for changes').trigger('click')
    await button(wrapper, 'Back').trigger('click')
    expect(button(wrapper, 'Approve plan')).toBeTruthy()
    await button(wrapper, 'Stop run').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/task/decision')).toEqual([{ action: 'stop' }])
  })

  it('shows the server error and stays answerable', async () => {
    serveApi({ 'POST /api/task/decision': { status: 409, body: { detail: 'No decision is pending' } } })
    const wrapper = mount(DecisionCard, { props: { message: plan, open: true } })
    await button(wrapper, 'Approve plan').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe('No decision is pending')
    expect(wrapper.emitted('answered')).toBeUndefined()
    expect(button(wrapper, 'Approve plan').attributes('disabled')).toBeUndefined()
  })

  it('shows the outcome once answered, without buttons', () => {
    const wrapper = mount(DecisionCard, { props: { message: plan, open: false, answeredWith: 'revise' } })
    expect(wrapper.text()).toContain('Changes sent to the planner')
    expect(wrapper.findAll('button')).toHaveLength(0)
    expect(mount(DecisionCard, { props: { message: plan } }).text()).toContain('No longer waiting for an answer')
  })
})

describe('DecisionCard: command approval', () => {
  it('shows the exact command, where it runs and why it asks', () => {
    const wrapper = mount(DecisionCard, { props: { message: command, open: true } })
    expect(wrapper.text()).toContain('Coder wants to run a command')
    expect(wrapper.find('pre').text()).toBe('pytest -q; rm -rf build')
    expect(wrapper.text()).toContain('On this machine, no sandbox')
    expect(wrapper.text()).toContain('Asks because it contains shell metacharacters.')
    // The intro is the first paragraph only; the command isn't repeated in it.
    expect(wrapper.find('.prose-msg').text()).not.toContain('rm -rf')
  })

  it('says when the command runs in the sandbox', () => {
    const message = { ...command, data: { ...command.data, sandbox: true } }
    expect(mount(DecisionCard, { props: { message, open: true } }).text()).toContain('Docker sandbox, no network')
  })

  it.each([['Run command', 'approve'], ['Deny', 'deny']])('%s sends %s', async (name, action) => {
    serveApi({ 'POST /api/task/decision': null })
    const wrapper = mount(DecisionCard, { props: { message: command, open: true } })
    await button(wrapper, name).trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/task/decision')).toEqual([{ action }])
    expect(wrapper.emitted('answered')).toEqual([[action]])
  })
})

describe('DecisionCard: key problem', () => {
  it('switches to the typed model and resumes, or stops', async () => {
    serveApi({ 'POST /api/task/decision': null })
    const wrapper = mount(DecisionCard, { props: { message: keyProblem, open: true, models: ['ollama:qwen3:8b'] } })
    expect(wrapper.text()).toContain("Coder can't continue")
    expect(wrapper.find('datalist option').attributes('value')).toBe('ollama:qwen3:8b')
    expect(button(wrapper, 'Switch and resume').attributes('disabled')).toBeDefined()
    await wrapper.find('input').setValue(' ollama:qwen3:8b ')
    await button(wrapper, 'Switch and resume').trigger('click')
    expect(button(wrapper, 'Stop run').attributes('disabled')).toBeDefined() // busy until the answer lands
    await flushPromises()
    await button(wrapper, 'Stop run').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/task/decision')).toEqual([{ action: 'switch', model: 'ollama:qwen3:8b' }, { action: 'stop' }])
  })
})
