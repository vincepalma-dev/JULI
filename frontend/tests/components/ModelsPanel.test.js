import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ModelsPanel from '../../src/components/ModelsPanel.vue'
import PullControl from '../../src/components/PullControl.vue'
import { sent, serveApi } from '../helpers.js'

const HW = { cpu: 'Intel i5', cores: 4, ram_gb: 16.9, disk_free_gb: 36.2, gpu: null, budgets: { gpu_gb: 0, total_gb: 12.7 } }
const GEMMA = { id: 'gemma', name: 'Gemma Terms of Use', url: 'https://ai.google.dev/gemma/terms', accept: true, accepted: false }
const APACHE = { id: 'apache', name: 'Apache License 2.0', url: 'https://apache.org', accept: false }
const CATALOGUE = [
  { tag: 'qwen3:8b', size_gb: 5.2, context_max: 40960, roles: ['general', 'coder'], fit: { tier: 'slow' }, license: APACHE, installed: false },
  { tag: 'qwen3:32b', size_gb: 20, context_max: 40960, roles: ['reviewer'], fit: { tier: 'cannot', reason: 'needs 22.0 GB, this machine has 12.7 GB for models' }, license: APACHE, installed: false },
  { tag: 'gemma3:1b', size_gb: 0.8, context_max: 32768, roles: ['docs'], fit: { tier: 'great' }, license: GEMMA, installed: false },
  { tag: 'llama3:latest', size_gb: 4.7, context_max: 8192, roles: ['general'], fit: { tier: 'slow' }, license: APACHE, installed: true },
]
const OLLAMA_UP = { running: true, version: '0.24.0' }

function routes(extra = {}) {
  return {
    'GET /api/local/hardware': HW,
    'GET /api/local/pulls': [],
    'GET /api/local/models': { ollama: OLLAMA_UP, installed: [{ name: 'llama3:latest', size: 4_700_000_000, benchmark: { tok_per_sec: 2.34 } }, { name: 'llava:7b', size: 4_700_000_000 }] },
    'GET /api/local/catalogue': { ollama: OLLAMA_UP, models: CATALOGUE },
    ...extra,
  }
}

async function open(extra, props = {}) {
  serveApi(routes(extra))
  const wrapper = mount(ModelsPanel, { props: { open: true, ...props }, attachTo: document.body })
  await flushPromises()
  return wrapper
}
const tab = (wrapper, name) => wrapper.findAll('[role="tab"]').find(t => t.text() === name).trigger('click')
const card = (wrapper, tag) => wrapper.findAll('article').find(a => a.find('h3').text() === tag)

describe('ModelsPanel', () => {
  it('shows this machine and whether Ollama runs', async () => {
    const wrapper = await open()
    const machine = wrapper.find('[aria-label="This machine"]').text()
    expect(machine).toContain('Intel i5 · 4 cores')
    expect(machine).toContain('16.9 GB RAM · 36 GB free for models')
    expect(machine).toContain('No supported GPU: models run on the CPU')
    expect(machine).toContain('Room for models: 0 GB on the GPU, 12.7 GB in total')
    expect(machine).toContain('Ollama 0.24.0')
  })

  it('tells you to start Ollama when it is down', async () => {
    const down = { running: false, version: null }
    const wrapper = await open({ 'GET /api/local/models': { ollama: down, installed: [] }, 'GET /api/local/catalogue': { ollama: down, models: [] } })
    expect(wrapper.text()).toContain('Ollama is not running')
    expect(wrapper.text()).toContain('Start Ollama to see installed models.')
  })

  it('lists installed models with their measured speed', async () => {
    const wrapper = await open()
    const rows = wrapper.findAll('li').map(li => li.text())
    expect(rows[0]).toContain('2.3 tok/s on this machine')
    expect(rows[1]).toContain('speed not measured')
  })

  it('measures a model, then reloads', async () => {
    const wrapper = await open({ 'POST /api/local/benchmark': { tok_per_sec: 3 } })
    await wrapper.findAll('button').find(b => b.text().includes('Measure speed')).trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/local/benchmark')).toEqual([{ model: 'llama3:latest' }])
    expect(sent('GET', '/api/local/models')).toHaveLength(2)
  })

  it('asks before deleting a model, and Keep keeps it', async () => {
    const wrapper = await open({ 'DELETE /api/local/models/llava:7b': null })
    await wrapper.find('[aria-label="Delete llava:7b"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text() === 'Keep').trigger('click')
    expect(fetch.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
    await wrapper.find('[aria-label="Delete llava:7b"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text().startsWith('Delete 4')).trigger('click')
    await flushPromises()
    expect(fetch.mock.calls.some(([p, init]) => p === '/api/local/models/llava:7b' && init?.method === 'DELETE')).toBe(true)
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('greys out models that will not fit, with the reason, and blocks their download', async () => {
    const wrapper = await open()
    await tab(wrapper, 'Catalogue')
    const big = card(wrapper, 'qwen3:32b')
    expect(big.classes()).toContain('opacity-60')
    expect(big.text()).toContain("Won't fit")
    expect(big.text()).toContain('Needs 22.0 GB, this machine has 12.7 GB for models')
    expect(big.find('button').attributes('disabled')).toBeDefined()
    expect(card(wrapper, 'qwen3:8b').text()).toContain('Runs slowly')
    expect(card(wrapper, 'gemma3:1b').text()).toContain('Runs well')
    expect(card(wrapper, 'llama3:latest').text()).toContain('Installed')
    expect(card(wrapper, 'gemma3:1b').text()).toContain('must be accepted before download')
  })

  it('asks to accept a licence before downloading, then downloads', async () => {
    let accepted = false
    const wrapper = await open({
      'POST /api/local/pulls': () => (accepted ? { model: 'gemma3:1b', status: 'pulling', completed: 0, total: 100 } : { status: 409, body: { detail: { message: 'Accept first', license: GEMMA } } }),
      'POST /api/local/licenses': () => { accepted = true; return {} },
    })
    await tab(wrapper, 'Catalogue')
    await card(wrapper, 'gemma3:1b').find('button').trigger('click')
    await flushPromises()
    expect(card(wrapper, 'gemma3:1b').text()).toContain('gemma3:1b needs the Gemma Terms of Use')
    await card(wrapper, 'gemma3:1b').findAll('button').find(b => b.text() === 'Accept and download').trigger('click')
    await flushPromises()
    expect(sent('POST', '/api/local/licenses')).toEqual([{ license: 'gemma' }])
    expect(sent('POST', '/api/local/pulls')).toEqual([{ model: 'gemma3:1b' }, { model: 'gemma3:1b' }])
    expect(card(wrapper, 'gemma3:1b').find('[role="progressbar"]').exists()).toBe(true)
  })

  it('cancels a download', async () => {
    const wrapper = await open({ 'DELETE /api/local/pulls/qwen3:8b': null }, { pulls: { 'qwen3:8b': { status: 'pulling', completed: 50, total: 200, detail: 'pulling layer' } } })
    await tab(wrapper, 'Catalogue')
    const qwen = card(wrapper, 'qwen3:8b')
    expect(qwen.find('[role="progressbar"]').attributes('aria-valuenow')).toBe('25')
    expect(qwen.text()).toContain('25% pulling layer')
    await qwen.findAll('button').find(b => b.text() === 'Cancel').trigger('click')
    await flushPromises()
    expect(fetch.mock.calls.some(([p, init]) => p === '/api/local/pulls/qwen3:8b' && init?.method === 'DELETE')).toBe(true)
  })

  it('reloads and tells the app when a download finishes', async () => {
    const wrapper = await open()
    await wrapper.setProps({ pulls: { 'qwen3:8b': { status: 'success' } } })
    await flushPromises()
    expect(sent('GET', '/api/local/catalogue')).toHaveLength(2)
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('looks up a Hugging Face repo', async () => {
    const wrapper = await open({
      'GET /api/local/hf': { license: APACHE, models: [{ tag: 'hf.co/a/b:Q4_K_M', quant: 'Q4_K_M', size_gb: 0.8, fit: { tier: 'great' }, installed: false }] },
    })
    await tab(wrapper, 'Bring your own')
    expect(wrapper.find('form button').attributes('disabled')).toBeDefined() // needs owner/repo
    await wrapper.find('#hf-repo').setValue(' a/b ')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(fetch.mock.calls.some(([p]) => p === '/api/local/hf?repo=a%2Fb')).toBe(true)
    expect(wrapper.text()).toContain('Q4_K_M')
    expect(wrapper.text()).toContain('Runs well')
  })

  it('adds an OpenAI-compatible endpoint and says whether it answers', async () => {
    const providers = [{ id: 'lm', label: 'LM Studio', base_url: 'http://127.0.0.1:1234/v1', custom: true, local: true }]
    const wrapper = await open({
      'POST /api/providers/endpoints': body => ({ label: body.label, health: body.id === 'fake' ? { status: 'ok' } : { status: 'error', detail: 'refused' } }),
      'DELETE /api/providers/endpoints/lm': null,
    }, { providers })
    await tab(wrapper, 'Bring your own')
    expect(wrapper.text()).toContain('LM Studio (lm)')
    expect(wrapper.text()).toContain('Local')
    const forms = wrapper.findAll('form')
    const add = forms[forms.length - 1]
    await wrapper.find('#ep-id').setValue('fake')
    await wrapper.find('#ep-label').setValue('Fake LLM')
    await wrapper.find('#ep-url').setValue('http://127.0.0.1:8099/v1')
    await add.trigger('submit')
    await flushPromises()
    expect(sent('POST', '/api/providers/endpoints')).toEqual([{ id: 'fake', label: 'Fake LLM', base_url: 'http://127.0.0.1:8099/v1', key: null }])
    expect(wrapper.find('form [role="status"]').text()).toBe('Added Fake LLM. It answers.')
    expect(wrapper.find('#ep-id').element.value).toBe('') // the form clears
    await wrapper.find('#ep-id').setValue('other')
    await wrapper.find('#ep-label').setValue('Other')
    await wrapper.find('#ep-url').setValue('http://127.0.0.1:1/v1')
    await add.trigger('submit')
    await flushPromises()
    expect(wrapper.find('form [role="status"]').text()).toBe("Added Other, but it didn't answer: refused")
    await wrapper.find('[aria-label="Remove LM Studio"]').trigger('click')
    await flushPromises()
    expect(fetch.mock.calls.some(([p, init]) => p === '/api/providers/endpoints/lm' && init?.method === 'DELETE')).toBe(true)
  })

  it('shows a load error', async () => {
    const wrapper = await open({ 'GET /api/local/hardware': { status: 500, body: { detail: 'no psutil' } } })
    expect(wrapper.find('[role="alert"]').text()).toBe('no psutil')
  })
})

describe('PullControl', () => {
  it('offers to resume a failed or cancelled download', () => {
    const failed = mount(PullControl, { props: { tag: 't', progress: { status: 'error', error: 'disk full' } } })
    expect(failed.text()).toContain('Download failed: disk full')
    expect(failed.find('button').text()).toBe('Resume download')
    const cancelled = mount(PullControl, { props: { tag: 't', progress: { status: 'cancelled' } } })
    expect(cancelled.text()).toContain('Downloading again resumes it')
  })

  it('shows an unknown size as an indeterminate bar, and nothing to download when installed', () => {
    const pulling = mount(PullControl, { props: { tag: 't', progress: { status: 'pulling', detail: 'starting' } } })
    expect(pulling.find('[role="progressbar"]').attributes('aria-valuenow')).toBeUndefined()
    expect(mount(PullControl, { props: { tag: 't', installed: true } }).find('button').exists()).toBe(false)
  })
})
