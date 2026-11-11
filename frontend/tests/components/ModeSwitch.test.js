import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ModeSwitch from '../../src/components/ModeSwitch.vue'
import { sent, serveApi } from '../helpers.js'

const CLOUD = ['openai:gpt-6.1-sol', 'anthropic:claude-sonnet-5-5']
const mountSwitch = (props = {}) => mount(ModeSwitch, { props: { mode: 'privacy', cloudModels: CLOUD, ...props }, attachTo: document.body })
const pick = (wrapper, label) => wrapper.find(`[aria-label="${label} mode"]`).trigger('click')

describe('ModeSwitch', () => {
  it('marks the current mode', () => {
    const wrapper = mountSwitch({ mode: 'hybrid' })
    expect(wrapper.find('[aria-label="Hybrid mode"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[aria-label="Privacy mode"]').attributes('aria-pressed')).toBe('false')
  })

  it('switches to Privacy at once', async () => {
    serveApi({ 'PUT /api/settings/mode': { mode: 'privacy' } })
    const wrapper = mountSwitch({ mode: 'cloud' })
    await pick(wrapper, 'Privacy')
    await flushPromises()
    expect(sent('PUT', '/api/settings/mode')).toEqual([{ mode: 'privacy', cloud_model: null }])
    expect(wrapper.emitted('changed')).toEqual([[{ mode: 'privacy' }]])
    expect(wrapper.find('dialog').attributes('open')).toBeUndefined()
  })

  it.each([['Hybrid', 'the planner and reviewer'], ['Cloud', 'every agent']])(
    'asks before %s mode and says what goes to third parties', async (label, who) => {
      serveApi({ 'PUT /api/settings/mode': { mode: label.toLowerCase() } })
      const wrapper = mountSwitch()
      await pick(wrapper, label)
      expect(sent('PUT', '/api/settings/mode')).toEqual([]) // nothing switched yet
      const dialog = wrapper.find('dialog')
      expect(dialog.attributes('open')).toBeDefined()
      expect(dialog.text()).toContain(`your prompts and code for ${who} are sent to third-party AI providers`)
      expect(dialog.find('select').element.value).toBe(CLOUD[0])
      await dialog.find('form').trigger('submit')
      await flushPromises()
      expect(sent('PUT', '/api/settings/mode')).toEqual([{ mode: label.toLowerCase(), cloud_model: CLOUD[0] }])
      expect(wrapper.find('dialog').attributes('open')).toBeUndefined()
    },
  )

  it('Cancel leaves the mode as it was', async () => {
    const wrapper = mountSwitch()
    await pick(wrapper, 'Cloud')
    await wrapper.findAll('dialog button').find(b => b.text() === 'Cancel').trigger('click')
    expect(wrapper.find('dialog').attributes('open')).toBeUndefined()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('keeps the dialog open with the error when the switch fails', async () => {
    serveApi({ 'PUT /api/settings/mode': { status: 409, body: { detail: 'A task is running' } } })
    const wrapper = mountSwitch()
    await pick(wrapper, 'Cloud')
    await wrapper.find('dialog select').setValue('')
    await wrapper.find('dialog form').trigger('submit')
    await flushPromises()
    expect(sent('PUT', '/api/settings/mode')).toEqual([{ mode: 'cloud', cloud_model: null }])
    expect(wrapper.find('dialog [role="alert"]').text()).toBe('A task is running')
    expect(wrapper.find('dialog').attributes('open')).toBeDefined()
  })

  it('reports a failed switch to Privacy', async () => {
    serveApi({ 'PUT /api/settings/mode': { status: 500, body: { detail: 'boom' } } })
    const wrapper = mountSwitch({ mode: 'cloud' })
    await pick(wrapper, 'Privacy')
    await flushPromises()
    expect(wrapper.emitted('error')[0][0].message).toBe('boom')
  })

  it('is locked while a run is going, and does nothing for the current mode', async () => {
    const locked = mountSwitch({ locked: true })
    expect(locked.find('[aria-label="Cloud mode"]').attributes('disabled')).toBeDefined()
    const wrapper = mountSwitch()
    await pick(wrapper, 'Privacy')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('explains a custom mix', () => {
    expect(mountSwitch({ mode: 'custom' }).text()).toContain('custom mix of local and cloud models')
    expect(mountSwitch({ mode: 'custom', compact: true }).text()).not.toContain('custom mix')
  })
})
