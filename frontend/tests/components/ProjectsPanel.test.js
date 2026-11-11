import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ProjectsPanel from '../../src/components/ProjectsPanel.vue'
import SidePanel from '../../src/components/SidePanel.vue'

const projects = [
  { id: 'a', name: 'Calc', updated_at: '2026-11-10T08:00:00Z' },
  { id: 'b', name: 'Todo', updated_at: null },
]
const mountPanel = (props = {}) => mount(ProjectsPanel, { props: { open: true, projects, activeProjectId: 'a', ...props }, attachTo: document.body })
const button = (wrapper, name) => wrapper.findAll('button').find(b => b.text().includes(name))

describe('ProjectsPanel', () => {
  it('lists projects and marks the open one', () => {
    const wrapper = mountPanel()
    const current = wrapper.find('[aria-current="true"]')
    expect(current.text()).toContain('Calc')
    expect(current.text()).toContain('Open now · Updated')
    expect(mountPanel({ projects: [] }).text()).toContain('No projects yet.')
  })

  it('creates a project with a trimmed name, and only with a name', async () => {
    const wrapper = mountPanel()
    expect(button(wrapper, 'Create').attributes('disabled')).toBeDefined()
    await wrapper.find('#new-project').setValue('  Shop  ')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('create-project')).toEqual([['Shop']])
    expect(wrapper.find('#new-project').element.value).toBe('')
  })

  it('selects a project', async () => {
    const wrapper = mountPanel()
    await button(wrapper, 'Todo').trigger('click')
    expect(wrapper.emitted('select-project')).toEqual([['b']])
  })

  it('asks before deleting, says what goes, and Keep keeps it', async () => {
    const wrapper = mountPanel()
    await wrapper.find('[aria-label="Delete Todo"]').trigger('click')
    expect(wrapper.text()).toContain('Delete Todo with all its runs and messages? Its workspace files stay on disk.')
    await button(wrapper, 'Keep').trigger('click')
    expect(wrapper.emitted('delete-project')).toBeUndefined()
    await wrapper.find('[aria-label="Delete Todo"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text() === 'Delete').trigger('click')
    expect(wrapper.emitted('delete-project')).toEqual([['b']])
  })
})

describe('SidePanel', () => {
  const mountSide = open => mount(SidePanel, { props: { open, title: 'Things' }, slots: { default: '<p>Body</p>' }, attachTo: document.body })

  it('opens as a modal dialog, titled, with its content', () => {
    const wrapper = mountSide(true)
    const dialog = wrapper.find('dialog')
    expect(dialog.attributes('open')).toBeDefined()
    expect(wrapper.find(`#${dialog.attributes('aria-labelledby')}`).text()).toBe('Things')
    expect(wrapper.text()).toContain('Body')
  })

  it('renders nothing inside while closed, and opens and closes with its prop', async () => {
    const wrapper = mountSide(false)
    expect(wrapper.find('dialog').attributes('open')).toBeUndefined()
    expect(wrapper.text()).not.toContain('Body')
    await wrapper.setProps({ open: true })
    expect(wrapper.find('dialog').attributes('open')).toBeDefined()
    await wrapper.setProps({ open: false })
    expect(wrapper.find('dialog').attributes('open')).toBeUndefined()
  })

  it('asks to close from the close button, Escape and the backdrop', async () => {
    const wrapper = mountSide(true)
    await wrapper.find('[aria-label="Close"]').trigger('click')
    await wrapper.find('dialog').trigger('cancel') // Escape
    await wrapper.find('dialog').trigger('click') // a click on the backdrop lands on the dialog itself
    expect(wrapper.emitted('close').length).toBeGreaterThanOrEqual(3)
    expect(wrapper.find('dialog').attributes('open')).toBeUndefined()
  })
})
