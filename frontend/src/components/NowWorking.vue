<template>
  <div class="flex items-center gap-3 py-2" role="status" aria-live="polite">
    <JuliMascot :state="view.mascot" :size="44" />
    <div class="min-w-0 flex-1">
      <p class="text-sm font-medium" :class="view.tone">{{ view.text }}</p>
      <p v-if="view.meta" class="mt-0.5 text-xs text-slate-400" aria-hidden="true">{{ view.meta }}</p>
    </div>
  </div>
</template>

<script setup>
// The live line at the bottom of the run: Juli plus what the crew is doing.
// Driven by turn_start (who and what), the run status, and follow-up questions.
import { ref, computed, onUnmounted, watch } from 'vue'
import JuliMascot from './JuliMascot.vue'
import { agentLabel, workingPhrase, turnMascot, splitRef } from '../labels.js'

const props = defineProps({
  status: { type: String, default: 'idle' },
  turn: { type: Object, default: null },
  asking: { type: Object, default: null },
  streaming: { type: Boolean, default: false },
  agents: { type: Object, default: () => ({}) },
})

const now = ref(Date.now())
let timer = null
watch(() => props.status === 'running' || Boolean(props.asking), (live) => {
  clearInterval(timer)
  if (live) timer = setInterval(() => { now.value = Date.now() }, 1000)
}, { immediate: true })
onUnmounted(() => clearInterval(timer))

function elapsed(since) {
  const s = Math.max(0, Math.floor((now.value - since) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

const view = computed(() => {
  if (props.asking) {
    return { mascot: 'follow-up', text: `${agentLabel(props.asking.agent, props.agents)} is answering…`, tone: 'text-slate-100' }
  }
  const turn = props.turn
  switch (props.status) {
    case 'running':
      if (!turn) return { mascot: 'idle', text: 'Starting the crew…', tone: 'text-slate-100' }
      return {
        mascot: turnMascot(turn, props.streaming),
        text: turn.command ? `Running ${turn.command.split(/\s+/).slice(0, 3).join(' ')}…` : workingPhrase(turn, props.agents),
        meta: `${agentLabel(turn.agent, props.agents)} · ${splitRef(turn.model).model || turn.model || ''} · ${elapsed(turn.since)}`,
        tone: 'text-slate-100',
      }
    case 'paused':
      return { mascot: 'waiting', text: 'Waiting for you', meta: 'Answer the question above to continue.', tone: 'text-amber-200' }
    case 'complete':
      return { mascot: 'done', text: 'Done', tone: 'text-emerald-300' }
    case 'stopped':
      return { mascot: 'stopped', text: 'Stopped', meta: 'The output so far is kept.', tone: 'text-slate-300' }
    case 'error':
      return { mascot: 'error', text: 'Something went wrong', meta: 'The error is in the run above.', tone: 'text-red-300' }
    default:
      return { mascot: 'idle', text: 'Ready', tone: 'text-slate-300' }
  }
})
</script>
