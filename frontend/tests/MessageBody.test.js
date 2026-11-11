import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import MessageBody from '../src/components/MessageBody.vue'
import { watchSaves } from './helpers.js'

const blocks = text => mount(MessageBody, { props: { text } }).findAll('pre, p').map(w => [w.element.tagName, w.text()])

describe('MessageBody', () => {
  it('splits text and fenced code', () => {
    const wrapper = mount(MessageBody, { props: { text: 'Here it is:\n```python path=src/app.py\nprint(1)\n```\nDone.' } })
    expect(wrapper.findAll('p').map(p => p.text())).toEqual(['Here it is:', 'Done.'])
    expect(wrapper.find('pre').text()).toBe('print(1)')
    expect(wrapper.text()).toContain('src/app.py') // the path wins over the language
  })

  it('labels a block by language, else "code"', () => {
    expect(mount(MessageBody, { props: { text: '```bash run\nnpm test\n```' } }).text()).toContain('bash')
    expect(mount(MessageBody, { props: { text: '```\nx\n```' } }).text()).toContain('code')
  })

  it('keeps an unclosed fence as text while it streams in', () => {
    expect(blocks('Start\n```js\nconst a = 1')).toEqual([['P', 'Start\n```js\nconst a = 1']])
  })

  it('shows several blocks in order', () => {
    expect(blocks('```a\n1\n```\nmid\n```b\n2\n```')).toEqual([['PRE', '1'], ['P', 'mid'], ['PRE', '2']])
  })
})

describe('MessageBody copy', () => {
  it('copies a code block and says so for a moment', async () => {
    vi.useFakeTimers()
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const wrapper = mount(MessageBody, { props: { text: '```py\nprint(1)\n```' } })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('print(1)')
    expect(wrapper.find('button').text()).toBe('Copied')
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(wrapper.find('button').text()).toBe('Copy')
    vi.useRealTimers()
  })

  it("downloads a block that names its file, under the file's own name", async () => {
    const saved = watchSaves()
    const wrapper = mount(MessageBody, { props: { text: '```python path=src/app.py\nprint(1)\n```\n```bash run\npytest\n```' } })
    const downloads = wrapper.findAll('button').filter(b => b.text() === 'Download')
    expect(downloads).toHaveLength(1) // the command has no file to be
    await downloads[0].trigger('click')
    expect(saved.map(s => s.name)).toEqual(['app.py'])
    expect(await saved[0].blob.text()).toBe('print(1)\n')
    vi.restoreAllMocks()
  })

  it('stays quiet when the clipboard is blocked', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('blocked') } }, configurable: true })
    const wrapper = mount(MessageBody, { props: { text: '```py\nx\n```' } })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('button').text()).toBe('Copy')
  })
})
