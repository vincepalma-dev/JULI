import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Composer from '../../src/components/Composer.vue'

const agents = { PlannerResearcher: {}, Coder: { job_title: 'Lead dev' } }
const ok = vi.fn((payload, done) => done.resolve())

function mountComposer(props = {}, handlers = {}) {
  return mount(Composer, { props: { agents, onStart: ok, onNote: ok, onAsk: ok, ...handlers, ...props } })
}
const box = wrapper => wrapper.find('#composer-text')
const send = wrapper => wrapper.find('button[type="submit"]')

describe('Composer', () => {
  it('starts a task with the chosen mode and plan approval, then clears', async () => {
    const onStart = vi.fn((payload, done) => done.resolve())
    const wrapper = mountComposer({}, { onStart })
    expect(send(wrapper).attributes('aria-label')).toBe('Start task')
    expect(send(wrapper).attributes('disabled')).toBeDefined() // nothing typed
    await wrapper.find('#run-mode').setValue('code')
    await wrapper.find('input[type="checkbox"]').setValue(true)
    await box(wrapper).setValue('  Build a CSV tool  ')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(onStart.mock.calls[0][0]).toEqual({ prompt: 'Build a CSV tool', mode: 'code', approve_plan: true })
    expect(box(wrapper).element.value).toBe('')
  })

  it('never asks for plan approval in review mode', async () => {
    const onStart = vi.fn((payload, done) => done.resolve())
    const wrapper = mountComposer({}, { onStart })
    await wrapper.find('input[type="checkbox"]').setValue(true)
    await wrapper.find('#run-mode').setValue('review')
    expect(wrapper.find('input[type="checkbox"]').attributes('disabled')).toBeDefined()
    expect(box(wrapper).attributes('placeholder')).toBe('What should the reviewer focus on…')
    await box(wrapper).setValue('security')
    await wrapper.find('form').trigger('submit')
    expect(onStart.mock.calls[0][0]).toEqual({ prompt: 'security', mode: 'review', approve_plan: false })
  })

  it('keeps the text when the task does not start', async () => {
    const onStart = vi.fn((payload, done) => done.reject(new Error('allowance')))
    const wrapper = mountComposer({}, { onStart })
    await box(wrapper).setValue('Build it')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(box(wrapper).element.value).toBe('Build it')
  })

  it('drops a kept task once it starts anyway, so the box is free for notes', async () => {
    const wrapper = mountComposer({}, { onStart: (payload, done) => done.reject(new Error('blocked')) })
    await box(wrapper).setValue('Build it')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    await wrapper.setProps({ status: 'running' })
    expect(box(wrapper).element.value).toBe('')
  })

  it('sends a note to the running crew', async () => {
    const onNote = vi.fn((payload, done) => done.resolve())
    const wrapper = mountComposer({ status: 'running' }, { onNote })
    expect(wrapper.text()).toContain('The crew is working.')
    expect(wrapper.find('#run-mode').exists()).toBe(false)
    expect(send(wrapper).attributes('aria-label')).toBe('Send note')
    await box(wrapper).setValue('Use SQLite')
    await wrapper.find('form').trigger('submit')
    expect(onNote.mock.calls[0][0]).toBe('Use SQLite')
    expect(mountComposer({ status: 'paused' }).text()).toContain('The crew is waiting.')
  })

  it('asks an agent about the last run', async () => {
    const onAsk = vi.fn((payload, done) => done.resolve())
    const wrapper = mountComposer({ lastRun: { id: 7 } }, { onAsk })
    await wrapper.findAll('[role="radio"]')[1].trigger('click')
    expect(wrapper.text()).toContain('about run 7')
    await wrapper.find('#ask-agent').setValue('Coder')
    expect(box(wrapper).attributes('placeholder')).toBe('Ask Lead dev about the run…')
    expect(send(wrapper).attributes('aria-label')).toBe('Ask question')
    await box(wrapper).setValue('Why SQLite?')
    await wrapper.find('form').trigger('submit')
    expect(onAsk.mock.calls[0][0]).toEqual({ agent: 'Coder', question: 'Why SQLite?' })
  })

  it('goes back to a new task when there is no last run', async () => {
    const wrapper = mountComposer({ lastRun: { id: 7 } })
    await wrapper.findAll('[role="radio"]')[1].trigger('click')
    await wrapper.setProps({ lastRun: null })
    expect(wrapper.find('#run-mode').exists()).toBe(true)
  })

  it('sends on Enter but not on Shift+Enter or while composing', async () => {
    const onStart = vi.fn((payload, done) => done.resolve())
    const wrapper = mountComposer({}, { onStart })
    await box(wrapper).setValue('Build it')
    await box(wrapper).trigger('keydown', { key: 'Enter', shiftKey: true })
    await box(wrapper).trigger('keydown.enter', { isComposing: true })
    expect(onStart).not.toHaveBeenCalled()
    await box(wrapper).trigger('keydown.enter')
    expect(onStart).toHaveBeenCalledTimes(1)
  })

  it('sends nothing while disabled, and shows the cloud notice', async () => {
    const onStart = vi.fn()
    const wrapper = mountComposer({ disabled: true, cloudNotice: 'Prompts go to OpenAI.' }, { onStart })
    expect(box(wrapper).attributes('disabled')).toBeDefined()
    await wrapper.find('form').trigger('submit')
    expect(onStart).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Prompts go to OpenAI.')
  })
})
