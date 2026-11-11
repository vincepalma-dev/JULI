import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CrewBuilder from '../../src/components/CrewBuilder.vue'
import { sent, serveApi } from '../helpers.js'

const settings = {
  mode: 'privacy',
  agents: {
    Coder: { role: 'coder', model: 'ollama:qwen3:8b', color: '#06b6d4', icon: 'coder' },
    SecurityAuditor: { model: 'ollama:qwen3:8b', job_title: 'Auditor' },
  },
  available_models: ['openai:gpt-6.1-sol'],
}
const PICKS = {
  agents: { Coder: { model: 'ollama:qwen3:14b', tier: 'slow', installed: false, size_gb: 9.3 }, SecurityAuditor: null },
  shared: false, downloads: ['qwen3:14b'], download_gb: 9.3, licenses: [{ id: 'gemma', name: 'Gemma Terms of Use' }], fallback_model: 'ollama:qwen3:14b',
}

function open(routes = {}, props = {}) {
  serveApi(routes)
  return mount(CrewBuilder, { props: { open: true, settings, localModels: ['ollama:llama3:latest'], ...props }, attachTo: document.body })
}
const button = (wrapper, name) => wrapper.findAll('button').find(b => b.text().includes(name))

describe('CrewBuilder agents', () => {
  it('lists each agent with its label, role and model, and offers every known model', () => {
    const wrapper = open()
    expect(wrapper.text()).toContain('Coder')
    expect(wrapper.text()).toContain('Auditor') // the job title wins
    expect(wrapper.find('#role-SecurityAuditor').element.value).toBe('custom')
    expect(wrapper.find('#model-Coder').element.value).toBe('ollama:qwen3:8b')
    expect(wrapper.findAll('#crew-models option').map(o => o.attributes('value'))).toEqual(['ollama:llama3:latest', 'openai:gpt-6.1-sol'])
  })

  it('saves a model, role and output limit as they change', async () => {
    const wrapper = open({ 'PUT /api/settings/agents': {} })
    await wrapper.find('#model-Coder').setValue(' fake:fake ')
    await wrapper.find('#role-Coder').setValue('reviewer')
    await wrapper.find('#max-Coder').setValue('300')
    await flushPromises()
    expect(sent('PUT', '/api/settings/agents')).toEqual([
      { Coder: { model: 'fake:fake' } },
      { Coder: { role: 'reviewer' } },
      { Coder: { max_tokens: 300 } },
    ])
    expect(wrapper.find('[role="status"]').text()).toBe('Saved')
    expect(wrapper.emitted('saved')).toHaveLength(3)
  })

  it('keeps what is typed in one field while another save reloads the settings', async () => {
    const wrapper = open({ 'PUT /api/settings/agents': {} })
    const coder = wrapper.find('#model-Coder')
    coder.element.value = 'fake:fake'
    await coder.trigger('input') // typed, not saved yet (no change event)
    // Another agent's save reloads the settings: the typing must survive the re-render.
    const reloaded = { ...settings, agents: { ...settings.agents, SecurityAuditor: { ...settings.agents.SecurityAuditor, model: 'fake:other' } } }
    await wrapper.setProps({ settings: reloaded })
    expect(coder.element.value).toBe('fake:fake')
    // Once saved and reloaded, the field shows the saved value again.
    await wrapper.setProps({ settings: { ...reloaded, agents: { ...reloaded.agents, Coder: { ...reloaded.agents.Coder, model: 'fake:fake' } } } })
    await wrapper.setProps({ settings: { ...reloaded, agents: { ...reloaded.agents, Coder: { ...reloaded.agents.Coder, model: 'ollama:next' } } } })
    expect(coder.element.value).toBe('ollama:next')
  })

  it('clears a prompt draft that ends in whitespace once it is saved as typed', async () => {
    const wrapper = open({ 'PUT /api/settings/agents': {} })
    const prompt = wrapper.find('#prompt-Coder')
    prompt.element.value = 'Write tests first.\n'
    await prompt.trigger('input')
    const withPrompt = text => ({ ...settings, agents: { ...settings.agents, Coder: { ...settings.agents.Coder, prompt: text } } })
    await wrapper.setProps({ settings: withPrompt('Write tests first.\n') }) // saved exactly as typed: the draft goes
    await wrapper.setProps({ settings: withPrompt('Changed elsewhere.') })
    expect(prompt.element.value).toBe('Changed elsewhere.')
  })

  it('clears the output limit back to the model default', async () => {
    const wrapper = open({ 'PUT /api/settings/agents': {} })
    await wrapper.find('#max-Coder').setValue('')
    await flushPromises()
    expect(sent('PUT', '/api/settings/agents')).toEqual([{ Coder: { max_tokens: null } }])
  })

  it("saves and clears an agent's tool rounds", async () => {
    const wrapper = open({ 'PUT /api/settings/agents': {} })
    await wrapper.find('#rounds-Coder').setValue('7')
    await flushPromises()
    await wrapper.find('#rounds-Coder').setValue('')
    await flushPromises()
    expect(sent('PUT', '/api/settings/agents')).toEqual([{ Coder: { max_tool_rounds: 7 } }, { Coder: { max_tool_rounds: null } }])
  })

  it('refuses tool rounds outside 1 to 100 with a message, without saving', async () => {
    const wrapper = open({ 'PUT /api/settings/agents': {} })
    for (const value of ['0', '101', '2.5']) {
      await wrapper.find('#rounds-Coder').setValue(value)
      await flushPromises()
      expect(wrapper.find('#rounds-Coder').element.value).toBe(value)
      expect(wrapper.find('[role="status"]').text()).toBe('Tool rounds must be a whole number from 1 to 100')
    }
    expect(sent('PUT', '/api/settings/agents')).toEqual([])
  })

  it('saves the title, colour and prompt', async () => {
    const wrapper = open({ 'PUT /api/settings/agents': {} })
    await wrapper.find('#title-Coder').setValue(' Lead dev ')
    await wrapper.find('[aria-label="Colour #ef4444"]').trigger('click')
    await wrapper.find('#prompt-Coder').setValue('Code carefully.')
    await flushPromises()
    expect(sent('PUT', '/api/settings/agents')).toEqual([
      { Coder: { job_title: 'Lead dev' } },
      { Coder: { color: '#ef4444' } },
      { Coder: { prompt: 'Code carefully.' } },
    ])
  })

  it('shows a refused save next to the agent', async () => {
    const wrapper = open({ 'PUT /api/settings/agents': { status: 422, body: { detail: 'Unknown provider' } } })
    await wrapper.find('#model-Coder').setValue('nope:model')
    await flushPromises()
    expect(wrapper.find('[role="status"]').text()).toBe('Unknown provider')
  })

  it('asks before removing an agent', async () => {
    const wrapper = open({ 'DELETE /api/settings/agents/Coder': null })
    await wrapper.find('[aria-label="Remove Coder"]').trigger('click')
    await button(wrapper, 'Keep').trigger('click')
    expect(fetch).not.toHaveBeenCalled()
    await wrapper.find('[aria-label="Remove Coder"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text() === 'Remove').trigger('click')
    await flushPromises()
    expect(fetch.mock.calls.some(([p, init]) => p === '/api/settings/agents/Coder' && init.method === 'DELETE')).toBe(true)
  })

  it('adds an agent', async () => {
    const wrapper = open({ 'POST /api/settings/agents': {} })
    await wrapper.find('#new-name').setValue(' DatabaseArchitect ')
    await wrapper.find('#new-role').setValue('reviewer')
    await wrapper.findAll('form').at(-1).trigger('submit')
    await flushPromises()
    expect(sent('POST', '/api/settings/agents')).toEqual([{ name: 'DatabaseArchitect', role: 'reviewer', model: 'ollama:qwen3:8b' }])
    expect(wrapper.find('#new-name').element.value).toBe('')
  })

  it('shows why an agent could not be added', async () => {
    const wrapper = open({ 'POST /api/settings/agents': { status: 409, body: { detail: 'That agent exists' } } })
    await wrapper.find('#new-name').setValue('Coder')
    await wrapper.findAll('form').at(-1).trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe('That agent exists')
  })
})

describe('CrewBuilder Auto-Crew', () => {
  it('suggests models, preselecting the agents that have a pick', async () => {
    const wrapper = open({ 'POST /api/local/auto-crew': PICKS })
    await button(wrapper, 'Suggest models').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/local/auto-crew')).toEqual([{}])
    expect(wrapper.text()).toContain('ollama:qwen3:14b')
    expect(wrapper.text()).toContain('9.3 GB download')
    expect(wrapper.text()).toContain('Nothing fits this machine')
    expect(wrapper.text()).toContain('Downloads needed: qwen3:14b (9.3 GB)')
    expect(wrapper.text()).toContain('Gemma Terms of Use must be accepted before download.')
    const boxes = wrapper.findAll('li input[type="checkbox"]')
    expect(boxes.map(b => [b.element.checked, b.element.disabled])).toEqual([[true, false], [false, true]])
    expect(button(wrapper, 'Use for 1 agent')).toBeTruthy()
  })

  it('applies the chosen picks with the fallback choice', async () => {
    const wrapper = open({ 'POST /api/local/auto-crew': body => (body.apply ? {} : PICKS) })
    await button(wrapper, 'Suggest models').trigger('click')
    await flushPromises()
    await wrapper.findAll('label').find(l => l.text().includes('local fallback')).find('input').setValue(false)
    await button(wrapper, 'Use for 1 agent').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/local/auto-crew')[1]).toEqual({ agents: ['Coder'], apply: true, set_fallback: false })
    expect(wrapper.text()).not.toContain('Downloads needed')
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('dismisses the picks, and says when they share one model', async () => {
    const wrapper = open({ 'POST /api/local/auto-crew': { ...PICKS, shared: true, downloads: [], licenses: [] } })
    await button(wrapper, 'Suggest models').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('every agent shares one model')
    await button(wrapper, 'Dismiss').trigger('click')
    expect(wrapper.text()).not.toContain('every agent shares one model')
  })

  it('shows an Auto-Crew error', async () => {
    const wrapper = open({ 'POST /api/local/auto-crew': { status: 503, body: { detail: 'Ollama is not running' } } })
    await button(wrapper, 'Suggest models').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe('Ollama is not running')
  })

  it('passes a mode change on', async () => {
    const wrapper = open({ 'PUT /api/settings/mode': { mode: 'privacy' } }, { settings: { ...settings, mode: 'cloud' } })
    await wrapper.find('[aria-label="Privacy mode"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('mode-changed')).toEqual([[{ mode: 'privacy' }]])
  })
})
