import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CrewBuilder from '../../src/components/CrewBuilder.vue'
import { restoreMascot } from '../../src/mascot.js'
import { sent, serveApi } from '../helpers.js'

// Juli's own look is one shared setting: put it back after each test.
afterEach(() => {
  localStorage.clear()
  restoreMascot()
})

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

  it('adds an agent with the look chosen for it', async () => {
    const wrapper = open({ 'POST /api/settings/agents': {} })
    await wrapper.find('#new-name').setValue('Courier')
    await wrapper.find('#new-outfit').setValue('rider')
    await wrapper.find('#new-idle').setValue('ride')
    await wrapper.find('#new-pose').setValue('devops')
    expect(wrapper.findAll('form').at(-1).find('.juli-figure').classes()).toContain('juli-idle--ride') // the preview
    await wrapper.findAll('form').at(-1).trigger('submit')
    await flushPromises()
    expect(sent('POST', '/api/settings/agents')).toEqual([{ name: 'Courier', role: 'custom', model: 'ollama:qwen3:8b', outfit: 'rider', idle: 'ride', pose: 'devops' }])
    expect(wrapper.find('#new-outfit').element.value).toBe('default') // ready for the next one
  })

  it('shows why an agent could not be added', async () => {
    const wrapper = open({ 'POST /api/settings/agents': { status: 409, body: { detail: 'That agent exists' } } })
    await wrapper.find('#new-name').setValue('Coder')
    await wrapper.findAll('form').at(-1).trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe('That agent exists')
  })
})

describe('CrewBuilder looks', () => {
  const radio = (wrapper, group, name) => wrapper.find(`[role="radiogroup"][aria-label="${group}"]`).findAll('[role="radio"]').find(r => r.text().startsWith(name))
  async function looks(routes) {
    const wrapper = open(routes)
    await wrapper.findAll('[role="tab"]').find(t => t.text() === 'Looks').trigger('click')
    return wrapper
  }

  it("saves an agent's outfit, accessory, idle style and working pose", async () => {
    const wrapper = await looks({ 'PUT /api/settings/agents': {} })
    expect(wrapper.find('#model-Coder').exists()).toBe(false) // the Agents tab is away
    await radio(wrapper, 'Whose look to change', 'Coder').trigger('click')
    await radio(wrapper, 'Outfit', 'Motorcycle rider').trigger('click')
    await radio(wrapper, 'Accessory', 'Scarf').trigger('click')
    await radio(wrapper, 'Idle style', 'Ride').trigger('click')
    await radio(wrapper, 'Working pose', 'Fixing').trigger('click')
    await flushPromises()
    expect(sent('PUT', '/api/settings/agents')).toEqual([
      { Coder: { outfit: 'rider' } },
      { Coder: { accessory: 'scarf' } },
      { Coder: { idle: 'ride' } },
      { Coder: { pose: 'devops' } },
    ])
    expect(wrapper.find('[role="status"]').text()).toBe('Saved')
  })

  it("shows an agent's saved look, and previews it idle or working", async () => {
    const dressed = { ...settings, agents: { ...settings.agents, Coder: { ...settings.agents.Coder, outfit: 'hoodie', idle: 'dance', pose: 'analyst' } } }
    const wrapper = await looks()
    await wrapper.setProps({ settings: dressed })
    await radio(wrapper, 'Whose look to change', 'Coder').trigger('click')
    expect(radio(wrapper, 'Outfit', 'Hoodie').attributes('aria-checked')).toBe('true')
    expect(radio(wrapper, 'Accessory', 'Same as Juli').attributes('aria-checked')).toBe('true')
    const preview = () => wrapper.find('svg[width="152"] .juli-figure').classes()
    expect(preview()).toContain('juli-idle--dance')
    await wrapper.findAll('button').find(b => b.text() === 'Working').trigger('click')
    expect(preview()).toContain('juli--analyst')
  })

  it("keeps Juli's own look in this browser, with no working pose to choose", async () => {
    const wrapper = await looks()
    expect(wrapper.find('[role="radiogroup"][aria-label="Working pose"]').exists()).toBe(false)
    expect(radio(wrapper, 'Outfit', 'Same as Juli')).toBeUndefined()
    await radio(wrapper, 'Outfit', 'Space suit').trigger('click')
    await radio(wrapper, 'Idle style', 'Juggle').trigger('click')
    expect(JSON.parse(localStorage.getItem('juli-mascot'))).toEqual({ outfit: 'space-suit', accessory: 'none', idle: 'juggle' })
    expect(radio(wrapper, 'Outfit', 'Space suit').attributes('aria-checked')).toBe('true')
    expect(fetch).not.toHaveBeenCalled()
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
