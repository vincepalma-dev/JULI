<template>
  <header class="relative z-10 flex shrink-0 flex-wrap items-center gap-2 border-b border-juli-border bg-juli-panel/90 px-2 py-2 sm:gap-3 sm:px-4">
    <button type="button" class="icon-btn md:hidden" aria-label="Open menu" @click="$emit('menu')">
      <Icon name="menu" class="h-5 w-5" />
    </button>

    <!-- Run status -->
    <div class="badge shrink-0 !px-2.5 !py-1" :class="tone.badge" role="status" :aria-label="`Run status: ${tone.label}`">
      <span class="h-2 w-2 rounded-full" :class="tone.dot" aria-hidden="true"></span>
      {{ tone.label }}
    </div>

    <p v-if="projectName" class="hidden min-w-0 items-center gap-1.5 text-sm text-slate-300 sm:flex">
      <Icon name="folder" class="h-4 w-4 shrink-0 text-slate-500" />
      <span style="overflow-wrap: anywhere">{{ projectName }}</span>
    </p>

    <!-- On the narrowest phones this group wraps to its own row rather than clipping Stop. -->
    <div class="ml-auto flex flex-wrap items-center justify-end gap-2">
      <ModeSwitch :mode="mode" :cloud-models="cloudModels" :locked="live" compact @changed="$emit('mode-changed', $event)" @error="$emit('error', $event)" />
      <button v-if="live" type="button" class="btn btn-danger !px-2.5 sm:!px-3.5" :disabled="stopping" aria-label="Stop the run" @click="$emit('stop')">
        <Icon name="stop" class="h-4 w-4" />
        <span class="hidden sm:inline">{{ stopping ? 'Stopping…' : 'Stop' }}</span>
      </button>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import Icon from './Icon.vue'
import ModeSwitch from './ModeSwitch.vue'

const props = defineProps({
  status: { type: String, default: 'idle' },
  projectName: { type: String, default: '' },
  mode: { type: String, default: 'custom' },
  cloudModels: { type: Array, default: () => [] },
  stopping: { type: Boolean, default: false },
})
defineEmits(['menu', 'stop', 'mode-changed', 'error'])

const live = computed(() => props.status === 'running' || props.status === 'paused')

const TONES = {
  idle: { label: 'Ready', badge: 'bg-slate-500/15 text-slate-300', dot: 'bg-slate-400' },
  running: { label: 'Working', badge: 'bg-cyan-500/15 text-cyan-200', dot: 'bg-cyan-300' },
  paused: { label: 'Waiting for you', badge: 'bg-amber-500/15 text-amber-200', dot: 'bg-amber-300' },
  complete: { label: 'Done', badge: 'bg-emerald-500/15 text-emerald-300', dot: 'bg-emerald-400' },
  stopped: { label: 'Stopped', badge: 'bg-slate-500/15 text-slate-300', dot: 'bg-slate-400' },
  error: { label: 'Error', badge: 'bg-red-500/15 text-red-300', dot: 'bg-red-400' },
}
const tone = computed(() => TONES[props.status] || TONES.idle)
</script>
