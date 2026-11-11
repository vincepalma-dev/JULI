// JULI end to end: the plan's verification list, against the real API and a
// fake model server. The tests share one server and run in order.
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

const TOKEN = 'e2e-session'
const AUTH = { Authorization: `Bearer ${TOKEN}` }
const AGENTS = ['PlannerResearcher', 'Coder', 'ReviewerSecurity', 'DevOps', 'TestMonitor', 'DocsDiagram']
const ENDED = ['complete', 'stopped', 'error']
const PYTHON = process.env.JULI_PYTHON || (process.platform === 'win32' ? resolve('../.venv/Scripts/python.exe') : 'python')

test.describe.configure({ mode: 'serial' })

/** A zip's entries as { name: text }, read (and so checked) with Python's zipfile: the dashboard has no zip reader. */
function unzip(path) {
  const code = 'import json, sys, zipfile\nwith zipfile.ZipFile(sys.argv[1]) as z:\n    print(json.dumps({n: z.read(n).decode() for n in z.namelist()}))'
  return JSON.parse(execFileSync(PYTHON, ['-c', code, path], { encoding: 'utf8' }))
}

async function open(page) {
  await page.goto(`/#token=${TOKEN}`)
  await expect(page.getByText('Connected')).toBeVisible()
}

async function api(request, path, options = {}) {
  const res = await request.fetch(path, { ...options, headers: { ...AUTH, ...options.headers } })
  return res.json()
}

/** Open a side panel from the sidebar (the top bar has buttons with the same names). */
async function panel(page, name) {
  await page.locator('nav').getByRole('button', { name, exact: true }).last().click()
}

async function closePanel(page) {
  await page.keyboard.press('Escape')
}

/** Set a crew field (model for every agent, or max tokens for the Coder) and wait until it's saved. */
async function setAgent(page, request, field, value) {
  await panel(page, 'Crew')
  const names = field === 'model' ? AGENTS : ['Coder']
  for (const name of names) {
    const input = page.locator(`#${field}-${name}`)
    await input.fill(String(value))
    await input.press('Tab')
  }
  const key = field === 'model' ? 'model' : 'max_tokens'
  const want = field === 'model' ? value : value === '' ? null : Number(value)
  await expect.poll(async () => {
    const { agents } = await api(request, '/api/settings')
    return names.map(n => agents[n]?.[key] ?? null)
  }).toEqual(names.map(() => want))
  await closePanel(page)
}

async function startTask(page, text) {
  await page.fill('#composer-text', text)
  await page.locator('#composer-text').press('Enter')
}

/** Wait for the run to end, answering approvals with the button(s) named in `answer`. */
async function finish(page, request, answer = 'Run command') {
  const asked = []
  await expect(async () => {
    // Pick the answer from one card's text and click it on that same card: if
    // the next decision replaces it meanwhile, the click misses and the next pass retries.
    const card = page.locator('dialog[open] section[data-decision]')
    const key = await card.getAttribute('data-decision', { timeout: 1000 }).catch(() => null)
    const text = key ? await card.innerText({ timeout: 1000 }).catch(() => '') : ''
    const name = [answer].flat().find(n => text.includes(n))
    if (name) {
      const clicked = await page
        .locator(`dialog[open] section[data-decision="${key}"]`)
        .getByRole('button', { name })
        .click({ timeout: 2000 })
        .then(() => true, () => false)
      if (clicked) asked.push(text)
    }
    expect(ENDED).toContain((await api(request, '/api/status')).status)
  }).toPass({ timeout: 90_000, intervals: [500] })
  return { status: (await api(request, '/api/status')).status, asked }
}

async function lastRunMessages(request) {
  const [project] = await api(request, '/api/projects')
  const { messages } = await api(request, `/api/projects/${project.id}`)
  const runId = Math.max(...messages.map(m => m.run_id || 0))
  return messages.filter(m => m.run_id === runId)
}

test('the API refuses requests without the session token', async ({ request }) => {
  expect((await request.get('/api/health')).status()).toBe(200)
  expect((await request.get('/api/status')).status()).toBe(401)
  expect((await request.get('/api/status', { headers: { Authorization: 'Bearer wrong' } })).status()).toBe(401)
})

test('a page without the token asks for a session', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('alert')).toContainText('No session.')
})

test('the dashboard opens with the token and takes it out of the address bar', async ({ page }) => {
  await open(page)
  expect(page.url()).not.toContain('token=')
  await expect(page.getByRole('alert').filter({ hasText: 'No session' })).toHaveCount(0)
  // First launch: a panel opened while the first project is being made stays open.
  await panel(page, 'Models')
  await expect(page.getByText('My first project').first()).toBeVisible()
  await page.waitForTimeout(1000)
  await expect(page.locator('dialog[open]')).toHaveCount(1)
})

test('the models panel shows this machine and greys out models that cannot fit', async ({ page }) => {
  await open(page)
  await panel(page, 'Models')
  await expect(page.locator('section[aria-label="This machine"]')).toContainText('RAM')
  await page.getByRole('tab', { name: 'Catalogue' }).click()
  await expect(page.getByText(/Needs [\d.]+ GB, this machine has [\d.]+ GB/).first()).toBeVisible()
})

test('an OpenAI-compatible endpoint is added and tested', async ({ page }) => {
  await open(page)
  await panel(page, 'Models')
  await page.getByRole('tab', { name: 'Bring your own' }).click()
  await page.fill('#ep-id', 'fake')
  await page.fill('#ep-label', 'Fake LLM')
  await page.fill('#ep-url', 'http://127.0.0.1:8099/v1')
  await page.getByRole('button', { name: 'Add and test' }).click()
  await expect(page.locator('p[role="status"]')).toContainText('It answers.')
})

test('a Privacy Mode run executes on the local endpoint and asks before a command', async ({ page, request }) => {
  await open(page)
  await panel(page, 'Crew')
  await page.locator('button[aria-label="Privacy mode"]').last().click()
  // The switch may ask first; wait until it has happened before editing the crew.
  const confirm = page.getByRole('button', { name: /Switch to Privacy/ })
  await expect(async () => {
    if (await confirm.isVisible().catch(() => false)) await confirm.click()
    expect((await api(request, '/api/settings')).mode).toBe('privacy')
  }).toPass({ timeout: 30_000 })
  await expect(page.locator('dialog.modal[open]')).toHaveCount(0)
  await closePanel(page)
  await setAgent(page, request, 'model', 'fake:fake')
  expect((await api(request, '/api/settings')).mode).toBe('privacy')

  await startTask(page, 'Write add(a, b) in calc.py with a test.')
  const { status, asked } = await finish(page, request)
  expect(status).toBe('complete')
  expect(asked[0]).toContain('pytest -q')
  expect(asked[0]).toContain('outside any sandbox')
  await expect(page.getByText('VERDICT: APPROVED').first()).toBeVisible()
  await expect(page.getByText('README.md', { exact: true }).first()).toBeVisible() // the docs agent wrote it

  // The reviewer read calc.py with a tool before its verdict.
  const tool = (await lastRunMessages(request)).find(m => m.message_type === 'tool')
  expect(tool.content).toBe('read_file calc.py')
  expect(tool.data.status).toBe('ok')
  expect(tool.data.output).toContain('return a + b')
  await expect(page.locator('summary').filter({ hasText: 'read_file calc.py' }).first()).toBeVisible()
})

test('the workspace shows the files, the run diff and a zip', async ({ page }) => {
  await open(page)
  await panel(page, 'Workspace')
  const files = page.locator('nav[aria-label="Files"]')
  await expect(files.getByText('calc.py', { exact: true })).toBeVisible()
  await expect(files.getByText('test_calc.py', { exact: true })).toBeVisible()
  await files.getByText('calc.py', { exact: true }).click()
  await expect(page.getByRole('dialog').getByText('return a + b')).toBeVisible()
  await page.getByRole('tab', { name: 'Changes by run' }).click()
  await expect(page.locator('[aria-label="Diff"]')).toContainText('+def add(a, b):')
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download zip' }).click()])
  expect(download.suggestedFilename()).toMatch(/^juli-.*\.zip$/)
})

test('a reply downloads as Markdown, a code block as its file, and a finished run offers its files', async ({ page }) => {
  // Text downloads are blobs made in the page: the dashboard's CSP must let them through.
  const blocked = []
  page.on('console', m => { if (m.type() === 'error' && /Content Security Policy/i.test(m.text())) blocked.push(m.text()) })
  await open(page)
  // The file's name and, once it has been saved completely (path() waits, and fails if it wasn't), where it is.
  const saved = async button => {
    const [download] = await Promise.all([page.waitForEvent('download'), button.click()])
    const path = await download.path()
    return { name: download.suggestedFilename(), path, bytes: readFileSync(path) }
  }

  // The run's last reply is the docs agent's: the reply as written, then its code block as the file it names.
  const reply = await saved(page.getByTitle('Download this reply as a Markdown file').last())
  expect(reply.name).toMatch(/^juli-run-\d+(-\w+)?\.md$/)
  expect(reply.bytes.toString()).toContain('```markdown path=README.md\n# Calc\n\nadd(a, b) returns the sum.\n```')
  const readme = await saved(page.getByTitle('Download README.md').last())
  expect(readme.name).toBe('README.md')
  expect(readme.bytes.toString()).toBe('# Calc\n\nadd(a, b) returns the sum.\n')

  // The zip opens, holds the files the crew wrote as they wrote them (see fake_llm.py), and nothing of git's.
  const zip = await saved(page.getByRole('button', { name: 'Download files' }).last())
  expect(zip.name).toMatch(/^juli-.*\.zip$/)
  const entries = unzip(zip.path)
  const text = name => entries[name]?.replace(/\r\n/g, '\n').trimEnd() // the same on every OS
  expect(text('calc.py')).toBe('def add(a, b):\n    return a + b')
  expect(text('test_calc.py')).toBe('from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3')
  expect(text('README.md')).toBe('# Calc\n\nadd(a, b) returns the sum.')
  expect(Object.keys(entries).filter(name => name === '.git' || name.startsWith('.git/'))).toEqual([])
  expect(blocked).toEqual([])
})

test('Stop ends a run mid-turn and keeps its output', async ({ page, request }) => {
  await open(page)
  await setAgent(page, request, 'model', 'fake:fake-slow')
  await startTask(page, 'A slow task to stop.')
  await expect(page.getByText('Deliberation of the Coder…').first()).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'Stop the run' }).click()
  const { status } = await finish(page, request, 'Deny')
  expect(status).toBe('stopped')
  await expect(page.getByText('Run stopped: stopped by the user.')).toBeVisible()
  await setAgent(page, request, 'model', 'fake:fake')
})

test("a role's max output tokens shortens its reply", async ({ page, request }) => {
  await open(page)
  await setAgent(page, request, 'max', 3)
  await startTask(page, 'A short coder reply.')
  expect((await finish(page, request, 'Deny')).status).toBe('complete')
  const coder = (await lastRunMessages(request)).filter(m => m.agent_name === 'Coder' && m.message_type === 'agent')
  expect(coder[0].tokens_out).toBe(3)
  await setAgent(page, request, 'max', '')
})

test('a token cap stops a local run', async ({ page, request }) => {
  await open(page)
  await panel(page, 'Settings')
  await page.fill('#tokencap', '250')
  await page.getByRole('button', { name: 'Save limits' }).click()
  await expect(page.getByText('Limits saved')).toBeVisible() // saved before the run reads the settings
  await closePanel(page)
  await startTask(page, 'Run into the token cap.')
  expect((await finish(page, request, 'Deny')).status).toBe('stopped')
  const limit = (await lastRunMessages(request)).filter(m => m.message_type === 'limit_reached')
  expect(limit[0].content).toContain('the token cap of 250 tokens')
  await panel(page, 'Settings')
  await page.fill('#tokencap', '')
  await page.getByRole('button', { name: 'Save limits' }).click()
  await expect.poll(async () => (await api(request, '/api/settings')).run.token_cap).toBe(null)
})

test('an MCP tool call asks first and its result reaches the agent', async ({ page, request }) => {
  const server = { transport: 'stdio', command: [PYTHON, fileURLToPath(new URL('../../tests/fixtures/mcp_server.py', import.meta.url))] }
  // In Privacy Mode a server outside the sandbox doesn't start, so this run is out of it.
  const { run } = await api(request, '/api/settings')
  // Later tests share this server: the settings come back even when an assertion fails.
  try {
    await api(request, '/api/settings/mcp', { method: 'PUT', data: { fake: server } })
    await api(request, '/api/settings/run', { method: 'PUT', data: { ...run, privacy_mode: false } })
    await open(page)
    await startTask(page, 'Use the MCP tool.')
    const { status, asked } = await finish(page, request, ['Allow this call', 'Deny'])
    expect(status).toBe('complete')
    const approval = asked.find(text => text.includes('wants to use a tool'))
    expect(approval).toContain('from the MCP server')
    expect(approval).toContain('"text": "from the tester"')
    const tool = (await lastRunMessages(request)).find(m => m.message_type === 'tool' && m.data.server === 'fake')
    expect(tool.data.output).toBe('echo: from the tester')
  } finally {
    await api(request, '/api/settings/mcp', { method: 'PUT', data: {} })
    await api(request, '/api/settings/run', { method: 'PUT', data: run })
  }
})

test('the terminal runs commands', async ({ page }) => {
  await open(page)
  await panel(page, 'Terminal')
  const dock = page.locator('section[aria-label="Terminal"]')
  await dock.locator('.xterm').click()
  await expect(async () => {
    await page.keyboard.type('echo juli-$((6*7))')
    await page.keyboard.press('Enter')
    await expect(dock.locator('.xterm-rows')).toContainText('juli-42', { timeout: 2000 })
  }).toPass({ timeout: 30_000 })
  await dock.getByRole('tab', { name: /Agent/ }).click()
  await expect(dock).toContainText(/\$\s*pytest -q/)
})

const sandboxImage = process.env.E2E_SANDBOX_IMAGE || 'ubuntu:24.04'
function imagePresent() {
  try {
    execFileSync('docker', ['image', 'inspect', sandboxImage], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

test('with the Docker sandbox on, a test command runs without asking', async ({ page, request }) => {
  test.skip(!imagePresent(), `Docker or the ${sandboxImage} image isn't available`)
  await open(page)
  await panel(page, 'Settings')
  await page.getByRole('tab', { name: 'Sandbox' }).click()
  await page.getByLabel('Run agent commands in the Docker sandbox').check()
  await page.fill('#image', sandboxImage)
  await page.getByRole('button', { name: 'Save sandbox' }).click()
  await expect(page.getByText('Saved. The sandbox is on.')).toBeVisible()
  await closePanel(page)

  await startTask(page, 'Sandboxed tests.')
  const { status, asked } = await finish(page, request, 'Deny')
  expect(status).toBe('complete')
  expect(asked).toEqual([]) // nothing asked: allowlisted and sandboxed
  const command = (await lastRunMessages(request)).find(m => m.message_type === 'command')
  expect(command.data.sandbox).toBe(true)

  await panel(page, 'Settings')
  await page.getByRole('tab', { name: 'Sandbox' }).click()
  await page.getByLabel('Run agent commands in the Docker sandbox').uncheck()
  await page.getByRole('button', { name: 'Save sandbox' }).click()
})

test('"Juli only" folds the crew\'s work into one reply', async ({ page }) => {
  await open(page)
  await page.getByRole('switch', { name: 'Juli only' }).or(page.getByLabel('Juli only')).first().click()
  await expect(page.getByText('Deliberation of the Coder…')).toHaveCount(0)
  await expect(page.getByText(/crew's work|worked on this/i).first()).toBeVisible()
})

// Last, since it wipes what the earlier tests made. The test server's keychain
// is in memory (e2e/serve.py), so no real key can be touched.
test('"Delete all data" wipes projects, runs and settings, and the dashboard starts over', async ({ page, request }) => {
  await open(page)
  const [before] = await api(request, '/api/projects')
  expect((await api(request, `/api/projects/${before.id}/runs`)).length).toBeGreaterThan(0)
  await panel(page, 'Settings')
  await page.getByRole('tab', { name: 'Data' }).click()
  const remove = page.getByRole('button', { name: 'Delete everything' })
  await expect(remove).toBeDisabled()
  await page.fill('#delete-confirm', 'delete all data')
  await remove.click()

  // The page reloads and makes a fresh first project, with no runs and default settings.
  await expect.poll(async () => (await api(request, '/api/projects')).map(p => p.name)).toEqual(['My first project'])
  await expect(page.getByText('Connected')).toBeVisible()
  const [fresh] = await api(request, '/api/projects')
  expect(fresh.id).not.toBe(before.id)
  expect(await api(request, `/api/projects/${fresh.id}/runs`)).toEqual([])
  const settings = await api(request, '/api/settings')
  expect(settings.agents.Coder.model).not.toBe('fake:fake')
  expect(settings.run.privacy_mode).toBe(false)
})
