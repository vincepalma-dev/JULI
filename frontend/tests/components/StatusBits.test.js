// The small pieces: the live line, the meter, the top bar, the sidebar, the mascot, the orb and icons.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AgentOrb from '../../src/components/AgentOrb.vue'
import Icon from '../../src/components/Icon.vue'
import JuliMascot from '../../src/components/JuliMascot.vue'
import NowWorking from '../../src/components/NowWorking.vue'
import Sidebar from '../../src/components/Sidebar.vue'
import StatsBar from '../../src/components/StatsBar.vue'
import TopBar from '../../src/components/TopBar.vue'

afterEach(() => vi.useRealTimers())

describe('NowWorking', () => {
  const line = props => mount(NowWorking, { props })
  const since = Date.parse('2026-11-10T00:00:00Z')

  it('says who is working on what, with a running clock', async () => {
    vi.useFakeTimers({ now: since + 65_000 })
    const wrapper = line({ status: 'running', turn: { agent: 'Coder', role: 'coder', model: 'ollama:qwen3:8b', since } })
    expect(wrapper.text()).toContain('Deliberation of the Coder…')
    expect(wrapper.text()).toContain('Coder · qwen3:8b · 1:05')
    vi.advanceTimersByTime(2000)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('1:07')
  })

  it('names a running command instead of the phrase', () => {
    const wrapper = line({ status: 'running', turn: { agent: 'Coder', role: 'coder', model: 'm', since: Date.now(), command: 'python -m pytest -q tests' } })
    expect(wrapper.text()).toContain('Running python -m pytest…')
  })

  it.each([
    [{ status: 'running' }, 'Starting the crew…'],
    [{ status: 'paused' }, 'Waiting for you'],
    [{ status: 'complete' }, 'Done'],
    [{ status: 'stopped' }, 'The output so far is kept.'],
    [{ status: 'error' }, 'Something went wrong'],
    [{ status: 'idle' }, 'Ready'],
    [{ status: 'complete', asking: { agent: 'Coder' } }, 'Coder is answering…'],
  ])('%o says %s', (props, text) => {
    expect(line(props).text()).toContain(text)
  })
})

describe('StatsBar', () => {
  it('shows the run, tokens, cost against the budget, and the token cap', () => {
    const wrapper = mount(StatsBar, { props: { runId: 3, totals: { tokens_in: 1500, tokens_out: 300, cost_usd: 0.25 }, budget: 1, tokenCap: 200000, connected: true } })
    const text = wrapper.text()
    expect(text).toContain('Run 3')
    expect(text).toContain('1,500 in · 300 out')
    expect(text).toContain('$0.25')
    expect(text).toContain('of $1.00')
    expect(text).toContain('token cap 200K')
    expect(wrapper.find('[role="status"]').text()).toBe('Connected')
  })

  it('shows tok/s and $0 for a local model only', () => {
    const lastSpeed = { model: 'ollama:qwen3:8b', tokPerSec: 12.34 }
    const local = mount(StatsBar, { props: { lastSpeed, isLocal: ref => ref.startsWith('ollama:') } })
    expect(local.text()).toContain('12.3 tok/s · local $0')
    expect(mount(StatsBar, { props: { lastSpeed } }).text()).not.toContain('tok/s')
    expect(local.find('[role="status"]').text()).toBe('Offline, reconnecting…')
  })
})

describe('TopBar', () => {
  it.each([['idle', 'Ready'], ['running', 'Working'], ['paused', 'Waiting for you'], ['complete', 'Done'], ['error', 'Error'], ['odd', 'Ready']])(
    'shows %s as %s', (status, label) => {
      expect(mount(TopBar, { props: { status } }).find('[role="status"]').attributes('aria-label')).toBe(`Run status: ${label}`)
    },
  )

  it('offers Stop only while a run is live, and locks the mode switch then', async () => {
    const idle = mount(TopBar, { props: { status: 'complete', projectName: 'Calc' } })
    expect(idle.text()).toContain('Calc')
    expect(idle.find('[aria-label="Stop the run"]').exists()).toBe(false)
    const live = mount(TopBar, { props: { status: 'running' } })
    expect(live.find('[aria-label="Cloud mode"]').attributes('disabled')).toBeDefined()
    await live.find('[aria-label="Stop the run"]').trigger('click')
    expect(live.emitted('stop')).toHaveLength(1)
    expect(mount(TopBar, { props: { status: 'running', stopping: true } }).text()).toContain('Stopping…')
  })

  it('opens the menu on phones', async () => {
    const wrapper = mount(TopBar)
    await wrapper.find('[aria-label="Open menu"]').trigger('click')
    expect(wrapper.emitted('menu')).toHaveLength(1)
  })
})

describe('Sidebar', () => {
  const agents = { Coder: { model: 'ollama:qwen3:8b', color: '#06b6d4' }, SecurityAuditor: { model: 'openai:gpt-6.1-sol', job_title: 'Auditor' } }

  it('lists the crew and marks who is working', () => {
    const wrapper = mount(Sidebar, { props: { agents, activeAgent: 'Coder' } })
    expect(wrapper.text()).toContain('ollama:qwen3:8b')
    expect(wrapper.text()).toContain('Auditor')
    expect(wrapper.text()).toContain('working now')
    expect(mount(Sidebar).text()).toContain('No agents yet.')
  })

  it('filters by agent, and clears the filter on a second click', async () => {
    const wrapper = mount(Sidebar, { props: { agents, filter: 'Coder' } })
    const coder = wrapper.findAll('ul button')[0]
    expect(coder.attributes('aria-pressed')).toBe('true')
    await coder.trigger('click')
    await wrapper.findAll('ul button')[1].trigger('click')
    expect(wrapper.emitted('filter')).toEqual([[null], ['SecurityAuditor']])
  })

  it('switches the "Juli only" view and opens panels', async () => {
    const wrapper = mount(Sidebar, { props: { agents, view: 'juli', agentCommands: 2, terminalOpen: true } })
    const toggle = wrapper.find('[role="switch"]')
    expect(toggle.attributes('aria-checked')).toBe('true')
    await toggle.trigger('click')
    expect(wrapper.emitted('view')).toEqual([['crew']])
    const terminal = wrapper.findAll('nav button').find(b => b.text().includes('Terminal'))
    expect(terminal.attributes('aria-pressed')).toBe('true')
    expect(terminal.find('[aria-label="2 agent commands"]').exists()).toBe(true)
    await terminal.trigger('click')
    expect(wrapper.emitted('open')).toEqual([['terminal']])
  })

  it('closes the phone drawer from its button and backdrop', async () => {
    const wrapper = mount(Sidebar, { props: { agents, open: true } })
    await wrapper.find('[aria-label="Close menu"]').trigger('click')
    await wrapper.find('.fixed.inset-0').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)
  })
})

describe('JuliMascot', () => {
  it('uses the sprite and still for a known state, and idle for an unknown one', () => {
    const coder = mount(JuliMascot, { props: { state: 'coder', size: 44 } })
    const style = coder.attributes('style')
    expect(style).toContain('juli-coder-16f.webp')
    expect(style).toContain('juli-coder.png')
    expect(style).toContain('--juli-size: 44px')
    expect(coder.attributes('aria-hidden')).toBe('true')
    expect(mount(JuliMascot, { props: { state: 'dancing' } }).attributes('style')).toContain('juli-idle-16f.webp')
  })

  it('plays "done" once', () => {
    expect(mount(JuliMascot, { props: { state: 'done' } }).classes()).toContain('juli-mascot--once')
    expect(mount(JuliMascot, { props: { state: 'idle' } }).classes()).not.toContain('juli-mascot--once')
  })
})

describe('AgentOrb and Icon', () => {
  it('draws an orb in the agent colour', () => {
    const orb = mount(AgentOrb, { props: { icon: 'coder', color: '#06b6d4', active: true } })
    expect(orb.find('.animate-pulse-glow').exists()).toBe(true) // active: the glow ring
    expect(orb.find('svg').exists()).toBe(true)
  })

  it('draws known icons as SVG, hidden from screen readers', () => {
    const icon = mount(Icon, { props: { name: 'check' } })
    expect(icon.element.tagName.toLowerCase()).toBe('svg')
    expect(icon.attributes('aria-hidden')).toBe('true')
    expect(icon.findAll('path').length).toBeGreaterThan(0)
  })
})
