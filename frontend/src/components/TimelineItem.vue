<template>
  <!-- Agent reply / follow-up answer -->
  <article v-if="m.message_type === 'agent' || m.message_type === 'answer'" class="flex gap-3">
    <JuliMascot v-if="asJuli" still :size="32" class="mt-0.5" />
    <AgentOrb v-else :icon="agents[m.agent_name]?.icon || 'system'" :color="colorOf(m.agent_name)" size="sm" class="mt-0.5" />
    <div class="min-w-0 flex-1">
      <h3 class="mb-1.5 text-sm font-semibold" :style="{ color: asJuli ? 'var(--color-juli-accent)' : colorOf(m.agent_name) }">
        {{ asJuli ? 'Juli' : agentLabel(m.agent_name, agents) }}
        <span v-if="m.message_type === 'answer'" class="font-normal text-slate-500">· follow-up{{ asJuli ? ` from ${agentLabel(m.agent_name, agents)}` : '' }}</span>
      </h3>
      <MessageBody :text="m.content" />
      <p class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs tabular-nums text-slate-500">
        <span v-if="m.model" class="font-mono">{{ m.model }}</span>
        <span v-if="m.tokens_in != null">{{ formatTokens(m.tokens_in) }} in · {{ formatTokens(m.tokens_out) }} out</span>
        <span v-if="m.model">{{ m.cost_usd == null ? 'no price' : formatCost(m.cost_usd) }}</span>
        <span>{{ formatTime(m.timestamp) }}</span>
      </p>
    </div>
  </article>

  <!-- The user: a mid-run note or a follow-up question -->
  <div v-else-if="m.message_type === 'user' || m.message_type === 'question'" class="flex flex-col items-end">
    <div class="max-w-[85%] rounded-2xl rounded-br-md border border-juli-border bg-white/[0.04] px-4 py-2">
      <p class="mb-0.5 text-xs text-slate-400">{{ m.message_type === 'user' ? 'Note to the crew' : 'Your question' }}</p>
      <p class="prose-msg">{{ m.content }}</p>
    </div>
  </div>

  <DecisionCard
    v-else-if="m.message_type === 'decision'"
    :message="m"
    :open="openDecisionKey === m.key"
    :answered-with="answered[m.key] || ''"
    :models="models"
    @answered="$emit('answered', m.key, $event)"
  />

  <!-- Files written -->
  <div v-else-if="m.message_type === 'files'" class="flex items-start gap-2 text-sm text-slate-300">
    <Icon name="file" class="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
    <p class="min-w-0">
      {{ agentLabel(m.agent_name, agents) }} wrote
      <button v-for="p in m.data?.paths || []" :key="p" type="button" class="mx-0.5 rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-xs text-slate-200 hover:bg-white/[0.12]" @click="$emit('open-file', p)">{{ p }}</button>
    </p>
  </div>

  <!-- An agent command's result -->
  <details v-else-if="m.message_type === 'command'" class="group rounded-lg border border-juli-border bg-black/20">
    <summary class="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3 py-2 text-sm">
      <Icon name="terminal" class="h-4 w-4 shrink-0 text-slate-400" />
      <code class="min-w-0 break-all font-mono text-xs text-slate-200">{{ m.data?.command }}</code>
      <span class="badge ml-auto" :class="commandTone(m.data?.status)">{{ commandLabel(m.data) }}</span>
      <Icon name="chevron-down" class="h-4 w-4 text-slate-500 transition-transform group-open:rotate-180" />
    </summary>
    <pre class="max-h-72 overflow-auto whitespace-pre-wrap break-all border-t border-juli-border px-3 py-2 font-mono text-xs text-slate-300">{{ stripAnsi(m.data?.output) || 'No output.' }}</pre>
  </details>

  <!-- A tool call: compact, with its result inside -->
  <details v-else-if="m.message_type === 'tool'" class="group rounded-lg border border-juli-border bg-black/20">
    <summary class="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3 py-1.5 text-sm">
      <Icon :name="toolIcon(m.data?.tool)" class="h-4 w-4 shrink-0 text-slate-400" />
      <span class="text-xs text-slate-400">{{ agentLabel(m.agent_name, agents) }}</span>
      <code class="min-w-0 break-all font-mono text-xs text-slate-200">{{ m.content }}</code>
      <span v-if="m.data?.server" class="text-xs text-slate-500">MCP · {{ m.data.server }}</span>
      <span class="badge ml-auto" :class="toolTone(m.data?.status)">{{ toolLabel(m.data) }}</span>
      <Icon name="chevron-down" class="h-4 w-4 text-slate-500 transition-transform group-open:rotate-180" />
    </summary>
    <pre class="max-h-72 overflow-auto whitespace-pre-wrap break-all border-t border-juli-border px-3 py-2 font-mono text-xs text-slate-300">{{ m.data?.output || 'No output.' }}</pre>
  </details>

  <!-- Limits, warnings, errors, system lines -->
  <div v-else-if="m.message_type === 'limit_reached' || m.message_type === 'warning'" class="flex items-start gap-2 rounded-lg border border-amber-400/25 bg-amber-400/[0.06] px-3 py-2 text-sm text-amber-100">
    <Icon name="alert" class="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
    <p class="prose-msg text-amber-100">{{ m.content }}</p>
  </div>
  <div v-else-if="m.message_type === 'error'" role="alert" class="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/[0.07] px-3 py-2 text-sm">
    <Icon name="alert" class="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
    <p class="prose-msg text-red-200">{{ m.content }}</p>
  </div>
  <p v-else class="text-center text-xs leading-relaxed text-slate-500" style="overflow-wrap: anywhere">{{ m.content }}</p>
</template>

<script setup>
// One timeline entry: an agent's reply, your note or question, a decision
// card, files written, a command result, a tool call, or a warning, error or
// system line.
import AgentOrb from './AgentOrb.vue'
import DecisionCard from './DecisionCard.vue'
import Icon from './Icon.vue'
import JuliMascot from './JuliMascot.vue'
import MessageBody from './MessageBody.vue'
import { agentLabel, formatCost, formatTime, formatTokens, stripAnsi, toolIcon } from '../labels.js'

const props = defineProps({
  m: { type: Object, required: true },
  agents: { type: Object, default: () => ({}) },
  openDecisionKey: { type: String, default: null },
  answered: { type: Object, default: () => ({}) },
  models: { type: Array, default: () => [] },
  asJuli: { type: Boolean, default: false }, // "Juli only" view: replies speak as Juli
})
defineEmits(['answered', 'open-file'])

const colorOf = name => props.agents[name]?.color || '#94a3b8'

function commandTone(status) {
  return status === 'passed' || status === 'ok' ? 'bg-emerald-500/15 text-emerald-300'
    : status === 'denied' || status === 'stopped' ? 'bg-slate-500/20 text-slate-300'
    : 'bg-red-500/15 text-red-300'
}

function toolTone(status) {
  return status === 'ok' ? 'bg-emerald-500/15 text-emerald-300'
    : status === 'denied' ? 'bg-slate-500/20 text-slate-300'
    : 'bg-red-500/15 text-red-300'
}

function toolLabel(d = {}) {
  const status = { ok: 'done', error: 'failed', denied: 'denied' }[d.status] || d.status || 'done'
  return d.seconds != null ? `${status} · ${Number(d.seconds).toFixed(1)} s` : status
}

function commandLabel(d = {}) {
  const parts = [d.status || 'done']
  if (d.exit_code != null) parts.push(`exit ${d.exit_code}`)
  if (d.seconds != null) parts.push(`${Number(d.seconds).toFixed(1)} s`)
  return parts.join(' · ')
}
</script>
