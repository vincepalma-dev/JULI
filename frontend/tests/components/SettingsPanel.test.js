import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import SettingsPanel from '../../src/components/SettingsPanel.vue'
import { restoreTheme, savedThemeId } from '../../src/theme.js'
import { sent, serveApi } from '../helpers.js'

const settings = { run: { budget_usd: null, token_cap: 5000, discussion_rounds: 0, allowances: { openai: 20 } } }
const providers = [
  { id: 'openai', label: 'OpenAI', needs_key: true, key_hint: '••••abcd' },
  { id: 'anthropic', label: 'Anthropic', needs_key: true, key_hint: null },
  { id: 'ollama', label: 'Ollama', needs_key: false },
]
const SANDBOX_OFF = { active: false, problem: 'the Docker sandbox is off', settings: { enabled: false, image: 'python:3.12-slim', timeout: 120 } }

async function open(routes = {}) {
  serveApi(routes)
  const wrapper = mount(SettingsPanel, { props: { open: false, settings, providers, localModels: ['ollama:qwen3:8b'] }, attachTo: document.body })
  await wrapper.setProps({ open: true })
  await flushPromises()
  return wrapper
}
const tab = (wrapper, name) => wrapper.findAll('[role="tab"]').find(t => t.text() === name).trigger('click')
const button = (wrapper, name) => wrapper.findAll('button').find(b => b.text().includes(name))

describe('SettingsPanel run limits', () => {
  it('shows empty limits as "No limit" and saves them as null', async () => {
    const wrapper = await open({ 'PUT /api/settings/run': {} })
    expect(wrapper.find('#budget').element.value).toBe('')
    expect(wrapper.find('#budget').attributes('placeholder')).toBe('No limit')
    expect(wrapper.find('#tokencap').element.value).toBe('5000')
    await wrapper.find('#tokencap').setValue('')
    await wrapper.find('#budget').setValue('1.5')
    await wrapper.find('#discuss').setValue('2')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(sent('PUT', '/api/settings/run')).toEqual([{
      budget_usd: 1.5, token_cap: null, privacy_mode: false, auto_fallback: false, fallback_model: null, discussion_rounds: 2, allowances: { openai: 20 },
    }])
    expect(wrapper.find('[role="status"]').text()).toBe('Limits saved')
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('shows a refused save', async () => {
    const wrapper = await open({ 'PUT /api/settings/run': { status: 422, body: { detail: [{ msg: 'too large' }] } } })
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="status"]').text()).toBe('too large')
    expect(wrapper.emitted('saved')).toBeUndefined()
  })
})

describe('SettingsPanel API keys', () => {
  it('only ever shows a saved key as its hint', async () => {
    const wrapper = await open()
    await tab(wrapper, 'API keys')
    expect(wrapper.text()).toContain('OpenAI')
    expect(wrapper.text()).not.toContain('Ollama') // no key needed
    expect(wrapper.text()).toContain('••••abcd')
    const input = wrapper.find('#key-openai')
    expect(input.element.value).toBe('') // the saved key is never loaded into the page
    expect(input.attributes('type')).toBe('password')
    expect(input.attributes('placeholder')).toBe('Saved')
    expect(wrapper.text()).toContain('Not checked')
    expect(wrapper.text()).toContain('No key')
  })

  it('shows and hides a typed key', async () => {
    const wrapper = await open()
    await tab(wrapper, 'API keys')
    await wrapper.find('[aria-label="Show key"]').trigger('click')
    expect(wrapper.find('#key-openai').attributes('type')).toBe('text')
    await wrapper.find('[aria-label="Hide key"]').trigger('click')
    expect(wrapper.find('#key-openai').attributes('type')).toBe('password')
  })

  it('saves typed keys and allowances, then clears the typed keys', async () => {
    const wrapper = await open({ 'PUT /api/settings/keys': { health: { anthropic: { status: 'invalid', detail: 'rejected' } } }, 'PUT /api/settings/run': {} })
    await tab(wrapper, 'API keys')
    await wrapper.find('#key-anthropic').setValue(' k ')
    await wrapper.find('#allow-anthropic').setValue('5')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(sent('PUT', '/api/settings/keys')).toEqual([{ anthropic: ' k ' }])
    expect(sent('PUT', '/api/settings/run')[0].allowances).toEqual({ openai: 20, anthropic: 5 })
    expect(wrapper.find('#key-anthropic').element.value).toBe('')
    expect(wrapper.text()).toContain('Invalid')
    expect(wrapper.find('[role="status"]').text()).toBe('Saved')
  })

  it("doesn't send keys when none were typed", async () => {
    const wrapper = await open({ 'PUT /api/settings/run': {} })
    await tab(wrapper, 'API keys')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(sent('PUT', '/api/settings/keys')).toEqual([])
    expect(sent('PUT', '/api/settings/run')).toHaveLength(1)
  })

  it('checks a key and shows its health', async () => {
    const wrapper = await open({ 'POST /api/providers/openai/check': { status: 'out_of_credit', detail: 'no credit' } })
    await tab(wrapper, 'API keys')
    expect(button(wrapper, 'Check').attributes('disabled')).toBeUndefined() // openai has a key
    await button(wrapper, 'Check').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Out of credit')
  })

  it('removes a key from the keychain', async () => {
    const wrapper = await open({ 'DELETE /api/settings/keys/openai': null })
    await tab(wrapper, 'API keys')
    await wrapper.find('[aria-label="Remove the OpenAI key"]').trigger('click')
    await flushPromises()
    expect(fetch.mock.calls.some(([p, init]) => p === '/api/settings/keys/openai' && init.method === 'DELETE')).toBe(true)
    expect(wrapper.find('[role="status"]').text()).toBe('Key removed from the keychain')
  })
})

describe('SettingsPanel sandbox', () => {
  it('loads the sandbox state and says why it is off', async () => {
    const wrapper = await open({ 'GET /api/sandbox': SANDBOX_OFF })
    await tab(wrapper, 'Sandbox')
    await flushPromises()
    expect(wrapper.text()).toContain('The sandbox is off: the Docker sandbox is off.')
    expect(wrapper.find('#image').element.value).toBe('python:3.12-slim')
  })

  it('saves it and says when it is on', async () => {
    const wrapper = await open({
      'GET /api/sandbox': SANDBOX_OFF,
      'PUT /api/sandbox': body => ({ active: true, problem: '', settings: body }),
    })
    await tab(wrapper, 'Sandbox')
    await flushPromises()
    await wrapper.find('input[type="checkbox"]').setValue(true)
    await wrapper.find('#image').setValue(' ubuntu:24.04 ')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(sent('PUT', '/api/sandbox')).toEqual([{ enabled: true, image: 'ubuntu:24.04', timeout: 120 }])
    expect(wrapper.find('[role="status"]').text()).toBe('Saved. The sandbox is on.')
    expect(wrapper.text()).toContain('The Docker sandbox is on.')
  })
})

describe('SettingsPanel theme', () => {
  it('applies and remembers the picked theme', async () => {
    const wrapper = await open()
    await tab(wrapper, 'Theme')
    const hacker = wrapper.findAll('[role="radio"]').find(r => r.text().includes('Hacker'))
    await hacker.trigger('click')
    expect(hacker.attributes('aria-checked')).toBe('true')
    expect(savedThemeId()).toBe('hacker')
    expect(document.documentElement.style.getPropertyValue('--color-juli-accent')).toBe('#39ff14')
    expect(document.documentElement.style.getPropertyValue('--color-juli-accent-rgb')).toBe('57, 255, 20')
  })

  it('reads an older saved theme stored as JSON', () => {
    localStorage.setItem('juli-theme', JSON.stringify({ id: 'slate' }))
    expect(savedThemeId()).toBe('slate')
    restoreTheme()
    expect(document.documentElement.style.getPropertyValue('--color-juli-accent')).toBe('#7c8aff')
    localStorage.clear()
  })
})
