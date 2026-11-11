import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Terminal } from '@xterm/xterm'
import TerminalDock from '../../src/components/TerminalDock.vue'

const sockets = () => window.WebSocket.instances
const commands = [
  { key: 'a', agent: 'Coder', command: 'pytest -q', sandbox: true, output: '\x1b[32m1 passed\x1b[0m', status: 'passed', exit_code: 0, seconds: 1.23 },
  { key: 'b', agent: 'Tester', command: 'npm test', sandbox: false, output: '', status: 'running', exit_code: null, seconds: null },
]

async function openShell(props = {}) {
  sessionStorage.setItem('juli-token', 't')
  const wrapper = mount(TerminalDock, { props: { open: false, projectId: 'p1', commands: [], ...props }, attachTo: document.body })
  await wrapper.setProps({ open: true })
  await flushPromises()
  return wrapper
}
const note = wrapper => wrapper.find('[role="status"]').text()

describe('TerminalDock shell', () => {
  it('opens the shell for the project and sends the token first', async () => {
    const wrapper = await openShell()
    const [ws] = sockets()
    expect(ws.url).toBe(`ws://${window.location.host}/ws/terminal`)
    expect(note(wrapper)).toBe('Connecting…')
    ws.readyState = window.WebSocket.OPEN
    ws.onopen()
    expect(JSON.parse(ws.sent[0])).toEqual({ token: 't', project_id: 'p1', cols: 80, rows: 24 })
    await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('writes shell output and says when the shell ends', async () => {
    const write = vi.spyOn(Terminal.prototype, 'write')
    const wrapper = await openShell()
    const [ws] = sockets()
    ws.onopen()
    ws.onmessage({ data: JSON.stringify({ type: 'output', data: 'PS> ' }) })
    ws.onmessage({ data: 'not json' })
    expect(write).toHaveBeenCalledWith('PS> ')
    ws.onmessage({ data: JSON.stringify({ type: 'exit' }) })
    await flushPromises()
    expect(note(wrapper)).toBe('The shell ended.')
    write.mockRestore()
  })

  it.each([
    [4401, 'The session token was refused. Reopen JULI from its launch link.'],
    [4429, 'Too many terminals are open, or they opened too quickly. Wait a moment, then start a new session.'],
    [1006, 'The terminal disconnected.'],
  ])('explains close code %i', async (code, text) => {
    const wrapper = await openShell()
    sockets()[0].onclose({ code, reason: '' })
    await flushPromises()
    expect(note(wrapper)).toBe(text)
    expect(wrapper.findAll('button').some(b => b.text().includes('New session'))).toBe(true)
  })

  it("adds the server's reason when the machine can't open a terminal", async () => {
    const wrapper = await openShell()
    sockets()[0].onclose({ code: 4503, reason: 'pywinpty is missing' })
    await flushPromises()
    expect(note(wrapper)).toBe("This machine can't open a terminal: pywinpty is missing")
  })

  it('starts a new session', async () => {
    const wrapper = await openShell()
    sockets()[0].onclose({ code: 1006 })
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text().includes('New session')).trigger('click')
    expect(sockets()).toHaveLength(2)
  })

  it('starts a new shell for another project', async () => {
    const wrapper = await openShell()
    await wrapper.setProps({ projectId: 'p2' })
    await flushPromises()
    expect(sockets()[0].readyState).toBe(window.WebSocket.CLOSED)
    sockets()[1].onopen()
    expect(JSON.parse(sockets()[1].sent[0]).project_id).toBe('p2')
  })

  it('waits for a project before connecting', async () => {
    const wrapper = await openShell({ projectId: null })
    expect(sockets()).toHaveLength(0)
    await wrapper.setProps({ projectId: 'p1' })
    await flushPromises()
    expect(sockets()).toHaveLength(1)
  })

  it('closes its socket when it goes away', async () => {
    const wrapper = await openShell()
    wrapper.unmount()
    expect(sockets()[0].readyState).toBe(window.WebSocket.CLOSED)
  })

  it('resizes and hides', async () => {
    const wrapper = await openShell()
    const taller = wrapper.find('[aria-label="Make the terminal taller"]')
    await taller.trigger('click')
    expect(wrapper.find('[aria-label="Make the terminal shorter"]').exists()).toBe(true)
    await wrapper.find('[aria-label="Hide the terminal"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})

describe('TerminalDock agent tab', () => {
  it("lists the agents' commands, where they ran and how they ended", async () => {
    const wrapper = mount(TerminalDock, { props: { open: true, commands } })
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    const text = wrapper.text()
    expect(text).toContain('running') // the tab's badge and npm test's status
    const [first, second] = wrapper.findAll('[aria-live="polite"] > div')
    expect(first.text()).toContain('pytest -q')
    expect(first.text()).toContain('sandbox')
    expect(first.text()).toContain('passed · exit 0 · 1.2 s')
    expect(first.find('pre').text()).toBe('1 passed') // colour codes stripped
    expect(second.text()).toContain('this machine')
    expect(second.find('pre').exists()).toBe(false)
  })

  it('lists tool calls with their server', async () => {
    const tools = [
      { key: 't1', kind: 'tool', agent: 'Coder', command: 'read_file app.py', server: null, output: 'x', status: 'ok', seconds: 0.1 },
      { key: 't2', kind: 'tool', agent: 'Coder', command: 'mcp__gh__search', server: 'gh', output: '', status: 'denied', seconds: null },
    ]
    const wrapper = mount(TerminalDock, { props: { open: true, commands: tools } })
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    const [first, second] = wrapper.findAll('[aria-live="polite"] > div')
    expect(first.text()).toContain('›read_file app.py')
    expect(first.text()).toContain('tool')
    expect(first.find('.badge.bg-emerald-500\\/15').exists()).toBe(true)
    expect(second.text()).toContain('MCP · gh')
    expect(second.text()).not.toContain('this machine')
    // Your own denial isn't an error.
    const denied = second.findAll('.badge').find(b => b.text().startsWith('denied'))
    expect(denied.classes()).toContain('text-slate-300')
    expect(denied.classes()).not.toContain('text-red-300')
  })

  it('says what the tab is for when empty, and switches to it when asked', async () => {
    const wrapper = mount(TerminalDock, { props: { open: true, commands: [] } })
    await wrapper.setProps({ showAgent: 1 })
    expect(wrapper.findAll('[role="tab"]')[1].attributes('aria-selected')).toBe('true')
    expect(wrapper.text()).toContain('Each command that isn\'t safe to run on its own asks you first.')
  })
})
