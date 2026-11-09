<template>
  <header class="glass glow-line shrink-0 relative" style="z-index: 10;">
    <div class="px-5 py-3 flex items-center gap-4">
      <!-- Status Badge -->
      <div
        class="flex items-center gap-2 px-3 py-1.5 rounded-full shrink-0"
        :class="statusClasses"
      >
        <div class="status-dot" :class="{ 'active': status === 'running' }" :style="statusDotStyle"></div>
        <span class="text-[10px] font-bold uppercase tracking-widest">{{ status }}</span>
      </div>

      <!-- Project Name -->
      <div v-if="projectName" class="px-3 py-1.5 rounded-full border border-juli-border bg-juli-bg/50 text-[10px] font-bold text-juli-accent flex items-center gap-1.5 shrink-0 transition-opacity">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5">
          <path d="M3 4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-5.828A2 2 0 0 1 9.757 5.414l-1.172-1.171A2 2 0 0 0 7.172 3.657L3 4Z" />
        </svg>
        {{ projectName }}
      </div>

      <!-- Task Input -->
      <div class="flex-1 relative">
        <div class="absolute left-3.5 top-1/2 -translate-y-1/2 text-juli-muted pointer-events-none">
          <!-- Heroicon: command-line (mini) -->
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
            <path fill-rule="evenodd" d="M3.25 3A2.25 2.25 0 0 0 1 5.25v9.5A2.25 2.25 0 0 0 3.25 17h13.5A2.25 2.25 0 0 0 19 14.75v-9.5A2.25 2.25 0 0 0 16.75 3H3.25Zm.943 8.752a.75.75 0 0 1 .055-1.06L6.128 9l-1.88-1.693a.75.75 0 1 1 1.004-1.114l2.5 2.25a.75.75 0 0 1 0 1.114l-2.5 2.25a.75.75 0 0 1-1.06-.055ZM9.75 10.25a.75.75 0 0 0 0 1.5h2.5a.75.75 0 0 0 0-1.5h-2.5Z" clip-rule="evenodd" />
          </svg>
        </div>
        <input
          v-model="taskPrompt"
          @keydown.enter="startTask"
          type="text"
          placeholder="Describe a task for the AI team..."
          :disabled="status === 'running'"
          class="w-full glass-input rounded-xl pl-10 pr-4 py-2.5 text-sm text-gray-200 placeholder-juli-muted/50 disabled:opacity-30 disabled:cursor-not-allowed font-medium"
        />
        <div
          v-if="status === 'running'"
          class="absolute right-3.5 top-1/2 -translate-y-1/2"
        >
          <div class="w-4 h-4 border-2 border-juli-accent/30 border-t-juli-accent rounded-full animate-spin"></div>
        </div>
      </div>

      <!-- Start Button -->
      <button
        @click="startTask"
        :disabled="!taskPrompt.trim() || status === 'running'"
        class="btn-glow shrink-0 text-white text-sm font-semibold px-6 py-2.5 rounded-xl flex items-center gap-2 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:transform-none disabled:hover:shadow-none"
      >
        <span v-if="status !== 'running'">
          <!-- Heroicon: bolt (mini) -->
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
            <path d="M11.983 1.907a.75.75 0 0 0-1.292-.657l-8.5 9.5A.75.75 0 0 0 2.75 12h6.572l-1.305 6.093a.75.75 0 0 0 1.292.657l8.5-9.5A.75.75 0 0 0 17.25 8h-6.572l1.305-6.093Z" />
          </svg>
        </span>
        <span v-else>
          <div class="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
        </span>
        {{ status === 'running' ? 'Running...' : 'Execute' }}
      </button>
    </div>
  </header>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'idle' },
  projectName: { type: String, default: '' },
})

const emit = defineEmits(['startTask'])
const taskPrompt = ref('')

const statusClasses = computed(() => ({
  'bg-juli-muted/10 text-juli-muted': props.status === 'idle',
  'bg-amber-500/10 text-amber-400': props.status === 'running',
  'bg-emerald-500/10 text-emerald-400': props.status === 'complete',
  'bg-red-500/10 text-red-400': props.status === 'error',
}))

const statusDotStyle = computed(() => {
  const colors = {
    idle: '#64748b',
    running: '#f59e0b',
    complete: '#10b981',
    error: '#ef4444',
  }
  return { backgroundColor: colors[props.status] || '#64748b', color: colors[props.status] || '#64748b' }
})

function startTask() {
  if (taskPrompt.value.trim() && props.status !== 'running') {
    emit('startTask', taskPrompt.value.trim())
  }
}
</script>
