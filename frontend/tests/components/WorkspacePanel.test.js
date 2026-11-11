import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import WorkspacePanel from '../../src/components/WorkspacePanel.vue'
import { sent, serveApi } from '../helpers.js'

const P = 'p1234567-aaaa'
const runs = [{ id: 1, prompt: 'First task' }, { id: 2, prompt: 'Second task' }]
const TREE = { files: [{ path: 'src/app.py', size: 10 }, { path: 'README.md', size: 5 }] }
const DIFF = '--- /dev/null\n+++ b/src/app.py\n@@ -0,0 +1 @@\n+print(1)'
const CONFIRM = { status: 409, body: { detail: { message: 'Push?', confirm: { branch: 'juli/run-2', remote: 'https://example.com/a.git' } } } }

function routes(extra = {}) {
  return {
    [`GET /api/projects/${P}/workspace/tree`]: TREE,
    [`GET /api/projects/${P}/workspace/file`]: (_, path) => ({ path: new URL(path, 'http://x').searchParams.get('path'), size: 10, content: 'print(1)\n' }),
    'GET /api/runs/2/files': [{ path: 'src/app.py', status: 'added' }],
    'GET /api/runs/2/diff': { diff: DIFF },
    'GET /api/runs/1/files': [],
    'GET /api/runs/1/diff': { diff: '' },
    ...extra,
  }
}

async function open(props = {}, extra = {}) {
  serveApi(routes(extra))
  // Like the app: mounted closed, then opened.
  const wrapper = mount(WorkspacePanel, { props: { open: false, projectId: P, runs, ...props }, attachTo: document.body })
  await wrapper.setProps({ open: true })
  await flushPromises()
  return wrapper
}

const button = (wrapper, name) => wrapper.findAll('button').find(b => b.text().includes(name))

describe('WorkspacePanel files', () => {
  it('lists folders first and opens a file', async () => {
    const wrapper = await open()
    const names = () => wrapper.findAll('nav[aria-label="Files"] button').map(b => b.text())
    expect(names()).toEqual(['src', 'README.md'])
    await wrapper.find('nav button').trigger('click') // expand src
    expect(names()).toEqual(['src', 'app.py', 'README.md'])
    await button(wrapper, 'app.py').trigger('click')
    await flushPromises()
    expect(wrapper.find('pre').text()).toBe('print(1)')
    expect(fetch.mock.calls.some(([p]) => p.endsWith('/workspace/file?path=src%2Fapp.py'))).toBe(true)
  })

  it('opens a file asked for by the timeline, with its folders', async () => {
    const wrapper = await open({ showPath: 'src/app.py' })
    expect(wrapper.find('[aria-current="true"]').text()).toBe('app.py')
    expect(wrapper.find('pre').text()).toBe('print(1)')
  })

  it("says binary and too-large files can't be shown", async () => {
    const wrapper = await open({ showPath: 'logo.png' }, { [`GET /api/projects/${P}/workspace/file`]: { path: 'logo.png', size: 3, binary: true } })
    expect(wrapper.text()).toContain('A binary file. Download the zip to get it.')
  })

  it('shows an empty workspace and a tree error', async () => {
    const empty = await open({}, { [`GET /api/projects/${P}/workspace/tree`]: { files: [] } })
    expect(empty.text()).toContain('No files yet')
    expect(button(empty, 'Download zip').attributes('disabled')).toBeDefined()
    const broken = await open({}, { [`GET /api/projects/${P}/workspace/tree`]: { status: 500, body: { detail: 'disk full' } } })
    expect(broken.find('[role="alert"]').text()).toBe('disk full')
  })

  it('downloads the zip with the session token', async () => {
    sessionStorage.setItem('juli-token', 't')
    const saved = []
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { saved.push(this.download) })
    const wrapper = await open({}, { [`GET /api/projects/${P}/workspace/zip`]: {} })
    await button(wrapper, 'Download zip').trigger('click')
    await flushPromises()
    const [, init] = fetch.mock.calls.find(([p]) => p.endsWith('/workspace/zip'))
    expect(init.headers.Authorization).toBe('Bearer t')
    expect(saved).toEqual(['juli-p1234567.zip'])
    click.mockRestore()
  })
})

describe('WorkspacePanel changes by run', () => {
  async function changes(props, extra) {
    const wrapper = await open(props, extra)
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()
    return wrapper
  }

  it("shows the latest run's changed files and diff", async () => {
    const wrapper = await changes()
    expect(wrapper.find('select').element.value).toBe('2')
    expect(wrapper.text()).toContain('A src/app.py')
    const lines = wrapper.findAll('[aria-label="Diff"] div')
    expect(lines.map(l => l.text())).toEqual(DIFF.split('\n'))
    expect(lines[3].classes()).toContain('text-emerald-200')
  })

  it('says when a run wrote no files', async () => {
    const wrapper = await changes()
    await wrapper.find('select').setValue('1')
    await flushPromises()
    expect(wrapper.text()).toContain("This run didn't write any files.")
    expect(button(wrapper, 'Commit to juli/run-1').attributes('disabled')).toBeDefined()
  })

  it('commits the run', async () => {
    const wrapper = await changes({}, { 'POST /api/runs/2/commit': { detail: 'Committed to juli/run-2' } })
    await button(wrapper, 'Commit to juli/run-2').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="status"]').text()).toBe('Committed to juli/run-2')
  })

  it("won't commit or push a run that is still going", async () => {
    const wrapper = await changes({ live: true, activeRunId: 2 })
    expect(wrapper.text()).toContain('This run is still going')
    expect(button(wrapper, 'Commit').attributes('disabled')).toBeDefined()
    expect(button(wrapper, 'Push').attributes('disabled')).toBeDefined()
  })

  it('asks before pushing, and Cancel sends nothing more', async () => {
    const wrapper = await changes({}, { 'POST /api/runs/2/push': CONFIRM })
    await wrapper.find('#remote').setValue('https://example.com/a.git')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    // The first request never pushes: it asks the server what would be pushed.
    expect(sent('POST', '/api/runs/2/push')).toEqual([{ confirm: false, remote: 'https://example.com/a.git' }])
    const dialog = wrapper.find('[role="alertdialog"]')
    expect(dialog.text()).toContain('juli/run-2')
    expect(dialog.text()).toContain('https://example.com/a.git')
    await button(wrapper, 'Cancel').trigger('click')
    expect(wrapper.find('[role="alertdialog"]').exists()).toBe(false)
    expect(sent('POST', '/api/runs/2/push')).toHaveLength(1)
  })

  it('pushes exactly what the dialog showed once confirmed', async () => {
    const wrapper = await changes({}, {
      'POST /api/runs/2/push': body => (body.confirm ? { detail: 'Pushed juli/run-2' } : CONFIRM),
    })
    await wrapper.find('#remote').setValue('https://example.com/a.git')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    await wrapper.find('[role="alertdialog"] .btn-primary').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/runs/2/push')[1]).toEqual({ confirm: true, remote: 'https://example.com/a.git' })
    expect(wrapper.find('[role="status"]').text()).toBe('Pushed juli/run-2')
  })

  it('withdraws the confirmation when the remote changes', async () => {
    const wrapper = await changes({}, { 'POST /api/runs/2/push': CONFIRM })
    await wrapper.find('#remote').setValue('https://example.com/a.git')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    await wrapper.find('#remote').setValue('https://example.com/other.git')
    expect(wrapper.find('[role="alertdialog"]').exists()).toBe(false)
  })

  it('shows a push refusal', async () => {
    const wrapper = await changes({}, { 'POST /api/runs/2/push': { status: 409, body: { detail: 'Say which remote to push to' } } })
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(sent('POST', '/api/runs/2/push')).toEqual([{ confirm: false }])
    expect(wrapper.find('[role="status"]').text()).toBe('Say which remote to push to')
  })
})
