<template>
  <footer class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-t border-juli-border bg-juli-panel/90 px-3 py-1.5 text-xs tabular-nums text-slate-400 sm:px-4">
    <span v-if="runId" class="text-slate-500">Run {{ runId }}</span>
    <span class="inline-flex items-center gap-1.5" title="Tokens this run: input and output, all agents">
      <Icon name="cpu" class="h-3.5 w-3.5" />
      <span><span class="text-slate-200">{{ formatTokens(totals.tokens_in) }}</span> in · <span class="text-slate-200">{{ formatTokens(totals.tokens_out) }}</span> out</span>
    </span>
    <span class="inline-flex items-center gap-1.5" title="Cloud cost this run. Local models cost $0.">
      <Icon name="coin" class="h-3.5 w-3.5" />
      <span class="text-slate-200">{{ formatCost(totals.cost_usd) }}</span>
      <span v-if="budget" class="text-slate-500">of {{ formatCost(budget) }}</span>
    </span>
    <span v-if="tokenCap" class="text-slate-500">token cap {{ formatTokens(tokenCap) }}</span>
    <span v-if="speed" class="inline-flex items-center gap-1.5" :title="`Last turn on ${speed.model}, including prompt processing`">
      <Icon name="gauge" class="h-3.5 w-3.5" />
      <span><span class="text-slate-200">{{ speed.tokPerSec.toFixed(1) }}</span> tok/s · local $0</span>
    </span>

    <span class="ml-auto inline-flex items-center gap-1.5" :class="connected ? 'text-emerald-400' : 'text-red-300'" role="status">
      <Icon :name="connected ? 'signal' : 'signal-off'" class="h-3.5 w-3.5" />
      {{ connected ? 'Connected' : 'Offline, reconnecting…' }}
    </span>
  </footer>
</template>

<script setup>
// The cost and token meter for the current run. Local models show their
// speed on this machine and cost $0.
import { computed } from 'vue'
import Icon from './Icon.vue'
import { formatCost, formatTokens } from '../labels.js'

const props = defineProps({
  runId: { type: Number, default: null },
  totals: { type: Object, default: () => ({ tokens_in: 0, tokens_out: 0, cost_usd: 0 }) },
  lastSpeed: { type: Object, default: null },
  isLocal: { type: Function, default: () => false },
  budget: { type: Number, default: null },
  tokenCap: { type: Number, default: null },
  connected: { type: Boolean, default: false },
})

const speed = computed(() => (props.lastSpeed && props.isLocal(props.lastSpeed.model) ? props.lastSpeed : null))
</script>
