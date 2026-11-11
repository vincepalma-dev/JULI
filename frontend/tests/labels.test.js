import { describe, expect, it } from 'vitest'
import { agentLabel, formatBytes, formatCost, formatTokens, splitRef, stripAnsi, turnMascot, workingPhrase } from '../src/labels.js'

describe('agentLabel', () => {
  it('splits camel case unless the agent has a job title', () => {
    expect(agentLabel('ReviewerSecurity')).toBe('Reviewer Security')
    expect(agentLabel('Coder', { Coder: { job_title: 'Lead dev' } })).toBe('Lead dev')
    expect(agentLabel('You')).toBe('You')
  })
})

describe('workingPhrase', () => {
  it('has a phrase per role', () => {
    expect(workingPhrase({ agent: 'Planner', role: 'planner' })).toBe('Planning the build…')
    expect(workingPhrase({ agent: 'Coder', role: 'coder' })).toBe('Deliberation of the Coder…')
    expect(workingPhrase({ agent: 'Reviewer', role: 'reviewer' })).toBe('Checking of the Checker…')
    expect(workingPhrase({ agent: 'Tester', role: 'tester' })).toBe('Testing…')
    expect(workingPhrase({ agent: 'Docs', role: 'docs' })).toBe('Writing the docs…')
  })

  it('names the activity before the role', () => {
    expect(workingPhrase({ agent: 'Coder', role: 'coder', activity: 'discussing the plan' })).toBe('The crew is discussing the plan…')
    expect(workingPhrase({ agent: 'Coder', role: 'coder', activity: 'fixing a failed command' })).toBe('Coder is fixing a failed command…')
  })

  it('falls back to the agent and activity for custom roles', () => {
    expect(workingPhrase({ agent: 'SecurityAuditor', role: 'custom', activity: 'answering' })).toBe('Security Auditor is answering…')
    expect(workingPhrase({ agent: 'Helper', role: 'custom' })).toBe('Helper is working…')
  })
})

describe('turnMascot', () => {
  it('shows the coder thinking, then typing once text arrives', () => {
    expect(turnMascot({ role: 'coder' }, false)).toBe('coder-thinking')
    expect(turnMascot({ role: 'coder' }, true)).toBe('coder-typing')
    expect(turnMascot({ role: 'reviewer' }, true)).toBe('reviewer')
    expect(turnMascot({ role: 'coder', activity: 'discussing the plan' }, true)).toBe('discussion')
  })
})

describe('formatting', () => {
  it('formats tokens, compact from 100k', () => {
    expect(formatTokens(null)).toBe('0')
    expect(formatTokens(12345)).toBe('12,345')
    expect(formatTokens(1_250_000)).toBe('1.3M')
  })

  it("keeps small costs from showing as $0.00", () => {
    expect(formatCost(0)).toBe('$0.00')
    expect(formatCost(0.0012)).toBe('$0.0012')
    expect(formatCost(1.5)).toBe('$1.50')
  })

  it('formats bytes', () => {
    expect(formatBytes(null)).toBe('')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB')
  })

  it('splits a model ref at the first colon', () => {
    expect(splitRef('ollama:qwen3:8b')).toEqual({ provider: 'ollama', model: 'qwen3:8b' })
    expect(splitRef('gpt')).toEqual({ provider: '', model: 'gpt' })
  })

  it('strips terminal colour codes', () => {
    expect(stripAnsi('\x1b[32mok\x1b[0m done')).toBe('ok done')
    expect(stripAnsi(null)).toBe('')
  })
})
