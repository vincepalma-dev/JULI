<template>
  <footer class="glass glow-line shrink-0 px-5 py-2.5">
    <div class="flex items-center justify-between">
      <!-- Left metrics -->
      <div class="flex items-center gap-5">
        <div class="flex items-center gap-2">
          <!-- Heroicon: chat-bubble-left (mini) -->
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5 text-juli-accent">
            <path fill-rule="evenodd" d="M3.43 2.524A41.29 41.29 0 0 1 10 2c2.236 0 4.43.18 6.57.524 1.437.231 2.43 1.49 2.43 2.902v5.148c0 1.413-.993 2.67-2.43 2.902a41.102 41.102 0 0 1-3.55.414c-.28.02-.521.18-.643.413l-1.712 3.293a.75.75 0 0 1-1.33 0l-1.713-3.293a.783.783 0 0 0-.642-.413 41.108 41.108 0 0 1-3.55-.414C1.993 13.245 1 11.986 1 10.574V5.426c0-1.413.993-2.67 2.43-2.902Z" clip-rule="evenodd" />
          </svg>
          <span class="text-[11px] text-juli-text font-medium">
            <span class="text-white font-semibold">{{ messageCount }}</span> messages
          </span>
        </div>

        <div class="w-px h-3.5 bg-juli-border"></div>

        <div class="flex items-center gap-2">
          <!-- Heroicon: cpu-chip (mini) -->
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5 text-juli-accent">
            <path d="M14 6H6v8h8V6Z" />
            <path fill-rule="evenodd" d="M9.25 3V1.75a.75.75 0 0 1 1.5 0V3h1.5V1.75a.75.75 0 0 1 1.5 0V3h.5A2.75 2.75 0 0 1 17 5.75v.5h1.25a.75.75 0 0 1 0 1.5H17v1.5h1.25a.75.75 0 0 1 0 1.5H17v1.5h1.25a.75.75 0 0 1 0 1.5H17v.5A2.75 2.75 0 0 1 14.25 17h-.5v1.25a.75.75 0 0 1-1.5 0V17h-1.5v1.25a.75.75 0 0 1-1.5 0V17h-1.5v1.25a.75.75 0 0 1-1.5 0V17h-.5A2.75 2.75 0 0 1 3 14.25v-.5H1.75a.75.75 0 0 1 0-1.5H3v-1.5H1.75a.75.75 0 0 1 0-1.5H3v-1.5H1.75a.75.75 0 0 1 0-1.5H3v-.5A2.75 2.75 0 0 1 5.75 3h.5V1.75a.75.75 0 0 1 1.5 0V3h1.5ZM4.5 5.75c0-.69.56-1.25 1.25-1.25h8.5c.69 0 1.25.56 1.25 1.25v8.5c0 .69-.56 1.25-1.25 1.25h-8.5c-.69 0-1.25-.56-1.25-1.25v-8.5Z" clip-rule="evenodd" />
          </svg>
          <span class="text-[11px] text-juli-text font-medium">
            <span class="text-white font-semibold">{{ activeCount }}</span> / {{ totalAgents }} agents
          </span>
        </div>

        <div class="w-px h-3.5 bg-juli-border"></div>

        <div class="flex items-center gap-2">
          <!-- Heroicon: clock (mini) -->
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5 text-juli-accent">
            <path fill-rule="evenodd" d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm.75-13a.75.75 0 0 0-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 0 0 0-1.5h-3.25V5Z" clip-rule="evenodd" />
          </svg>
          <span class="text-[11px] text-juli-text font-mono font-medium">{{ elapsed }}</span>
        </div>
      </div>

      <!-- Right status -->
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-1.5">
          <!-- Heroicon: signal (mini) -->
          <svg v-if="isConnected" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5 text-emerald-400">
            <path d="M16.364 3.636a.75.75 0 0 0-1.06 1.06 7.5 7.5 0 0 1 0 10.608.75.75 0 0 0 1.06 1.06 9 9 0 0 0 0-12.728ZM4.697 4.697a.75.75 0 0 0-1.06-1.06 9 9 0 0 0 0 12.727.75.75 0 1 0 1.06-1.06 7.5 7.5 0 0 1 0-10.607Z" />
            <path d="M12.475 6.465a.75.75 0 0 1 1.06 0 6 6 0 0 1 0 8.49.75.75 0 0 1-1.06-1.06 4.5 4.5 0 0 0 0-6.37.75.75 0 0 1 0-1.06ZM7.525 6.465a.75.75 0 0 0 0 1.06 4.5 4.5 0 0 1 0 6.37.75.75 0 0 0 1.06 1.06 6 6 0 0 0 0-8.49.75.75 0 0 0-1.06 0Z" />
            <path d="M11 10a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z" />
          </svg>
          <!-- Heroicon: signal-slash (mini) -->
          <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5 text-red-400">
            <path d="M1.28 2.22a.75.75 0 0 0-1.06 1.06l1.386 1.386A9.012 9.012 0 0 0 1 10c0 2.485 1.005 4.735 2.636 6.364a.75.75 0 1 0 1.06-1.06A7.462 7.462 0 0 1 2.5 10c0-1.63.52-3.14 1.4-4.37l1.182 1.183A5.478 5.478 0 0 0 4.5 10a5.47 5.47 0 0 0 1.758 4.026.75.75 0 0 1-1.06 1.06A6.97 6.97 0 0 1 3 10c0-1.384.402-2.673 1.095-3.76L18.72 17.78a.75.75 0 1 0 1.06-1.06L1.28 2.22Z" />
          </svg>
          <span class="text-[10px] font-medium" :class="isConnected ? 'text-emerald-400' : 'text-red-400'">
            {{ isConnected ? 'Connected' : 'Offline' }}
          </span>
        </div>

        <span class="text-[10px] text-juli-muted font-mono">v1.0.0</span>
      </div>
    </div>
  </footer>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'

const props = defineProps({
  messageCount: { type: Number, default: 0 },
  activeCount: { type: Number, default: 0 },
  totalAgents: { type: Number, default: 6 },
  isConnected: { type: Boolean, default: false },
  status: { type: String, default: 'idle' },
})

const startTime = ref(null)
const now = ref(Date.now())
let timer = null

watch(() => props.status, (val) => {
  if (val === 'running' && !startTime.value) {
    startTime.value = Date.now()
    timer = setInterval(() => { now.value = Date.now() }, 1000)
  } else if (val === 'complete' || val === 'error' || val === 'idle') {
    if (timer) clearInterval(timer)
  }
})

const elapsed = computed(() => {
  if (!startTime.value) return '00:00'
  const diff = Math.floor((now.value - startTime.value) / 1000)
  const m = Math.floor(diff / 60).toString().padStart(2, '0')
  const s = (diff % 60).toString().padStart(2, '0')
  return `${m}:${s}`
})

onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
