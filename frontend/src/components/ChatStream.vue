<template>
  <div class="flex-1 flex flex-col overflow-hidden relative" style="z-index: 5;">
    <!-- Filter bar -->
    <transition name="collapse-fade">
      <div
        v-if="selectedAgent"
        class="flex items-center gap-2 px-5 py-2 glass-light border-b border-juli-border/50"
      >
        <span class="text-[10px] text-juli-muted uppercase tracking-wider font-medium">Filtering</span>
        <span
          class="text-[11px] font-semibold px-2.5 py-0.5 rounded-full"
          :style="{ backgroundColor: agentColor(selectedAgent) + '15', color: agentColor(selectedAgent), border: '1px solid ' + agentColor(selectedAgent) + '25' }"
        >
          {{ selectedAgent }}
        </span>
        <button
          @click="$emit('clearFilter')"
          class="text-[10px] text-juli-muted hover:text-white ml-auto flex items-center gap-1 transition-colors"
        >
          <span>✕</span> Clear
        </button>
      </div>
    </transition>

    <!-- Messages -->
    <div ref="scrollContainer" class="flex-1 overflow-y-auto px-5 py-5 space-y-3">
      <!-- Empty State -->
      <div v-if="messages.length === 0" class="flex flex-col items-center justify-center h-full">
        <div class="relative mb-6">
          <!-- Animated rings -->
          <div class="absolute inset-0 w-24 h-24 rounded-full border border-juli-accent/10 animate-spin-slow" style="margin: -12px;"></div>
          <div class="absolute inset-0 w-20 h-20 rounded-full border border-juli-accent/5 animate-spin-slow" style="margin: -4px; animation-direction: reverse; animation-duration: 12s;"></div>
          <div
            class="w-16 h-16 rounded-full flex items-center justify-center animate-float"
            style="background: radial-gradient(circle at 35% 35%, rgba(6, 182, 212, 0.2), rgba(6, 182, 212, 0.05)); border: 1px solid rgba(6, 182, 212, 0.15);"
          >
            <!-- Heroicon: sparkles -->
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-8 h-8 text-juli-accent">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
            </svg>
          </div>
        </div>
        <p class="text-base font-semibold text-juli-text glow-text">JULI Ready</p>
        <p class="text-xs text-juli-muted mt-2 text-center max-w-xs">Enter a task above to activate the elite agent team</p>
      </div>

      <!-- Message Cards -->
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="animate-slide-up"
        :style="{ animationDelay: `${Math.min(i * 30, 300)}ms` }"
      >
        <!-- System / Status Messages -->
        <div v-if="msg.message_type === 'status' || msg.message_type === 'system'" class="flex items-center gap-3 py-2 px-2">
          <div class="flex-1 h-px bg-gradient-to-r from-transparent via-juli-border to-transparent"></div>
          <span class="text-[10px] text-juli-muted font-medium flex items-center gap-1.5 shrink-0">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3 text-juli-accent shrink-0">
              <path fill-rule="evenodd" d="M8.34 1.804A1 1 0 0 1 9.32 1h1.36a1 1 0 0 1 .98.804l.295 1.473c.497.144.971.342 1.416.587l1.25-.834a1 1 0 0 1 1.262.125l.962.962a1 1 0 0 1 .125 1.262l-.834 1.25c.245.445.443.919.587 1.416l1.473.295a1 1 0 0 1 .804.98v1.361a1 1 0 0 1-.804.98l-1.473.295a6.95 6.95 0 0 1-.587 1.416l.834 1.25a1 1 0 0 1-.125 1.262l-.962.962a1 1 0 0 1-1.262.125l-1.25-.834a6.953 6.953 0 0 1-1.416.587l-.295 1.473a1 1 0 0 1-.98.804H9.32a1 1 0 0 1-.98-.804l-.295-1.473a6.957 6.957 0 0 1-1.416-.587l-1.25.834a1 1 0 0 1-1.262-.125l-.962-.962a1 1 0 0 1-.125-1.262l.834-1.25a6.957 6.957 0 0 1-.587-1.416l-1.473-.295A1 1 0 0 1 1 10.68V9.32a1 1 0 0 1 .804-.98l1.473-.295c.144-.497.342-.971.587-1.416l-.834-1.25a1 1 0 0 1 .125-1.262l.962-.962A1 1 0 0 1 5.38 3.03l1.25.834a6.957 6.957 0 0 1 1.416-.587l.294-1.473ZM13 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" clip-rule="evenodd" />
            </svg>
            {{ msg.content }}
          </span>
          <div class="flex-1 h-px bg-gradient-to-r from-transparent via-juli-border to-transparent"></div>
        </div>

        <!-- Error Messages -->
        <div
          v-else-if="msg.message_type === 'error'"
          class="glass-card rounded-xl px-4 py-3"
          style="border-color: rgba(239, 68, 68, 0.2); background: rgba(239, 68, 68, 0.05);"
        >
          <span class="text-xs font-semibold text-red-400 flex items-center gap-1.5">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5">
              <path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495ZM10 5a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 10 5Zm0 9a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" clip-rule="evenodd" />
            </svg>
            Error
          </span>
          <p class="text-sm text-red-300/80 mt-1.5 leading-relaxed">{{ msg.content }}</p>
        </div>

        <!-- Agent Messages -->
        <div
          v-else
          class="glass-card rounded-xl p-4 group"
          :style="{
            borderLeftWidth: '3px',
            borderLeftColor: agentColor(msg.agent_name) + '80',
          }"
        >
          <!-- Header -->
          <div class="flex items-center gap-2.5 mb-2.5">
            <AgentOrb
              :icon="agentIcon(msg.agent_name)"
              :color="agentColor(msg.agent_name)"
              size="sm"
            />
            <span class="text-sm font-bold" :style="{ color: agentColor(msg.agent_name) }">
              {{ agentDisplayName(msg.agent_name) }}
            </span>
            <span class="text-[10px] text-juli-muted ml-auto font-mono opacity-0 group-hover:opacity-100 transition-opacity">
              {{ formatTime(msg.timestamp) }}
            </span>
          </div>

          <!-- Content -->
          <div class="text-[13px] text-gray-300/90 leading-relaxed whitespace-pre-wrap break-words pl-0.5">
            <template v-if="hasCodeBlock(msg.content)">
              <div v-for="(block, bIdx) in parseContent(msg.content)" :key="bIdx">
                <div v-if="block.type === 'code'" class="code-block my-3 relative group/code">
                  <div class="flex items-center justify-between mb-2 pb-2" style="border-bottom: 1px solid rgba(6, 182, 212, 0.08);">
                    <span class="text-[9px] text-juli-accent/60 font-mono uppercase tracking-wider">{{ block.lang || 'code' }}</span>
                    <button
                      @click="copyCode(block.code)"
                      class="text-[10px] text-juli-muted hover:text-juli-accent transition-colors flex items-center gap-1"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
                        <path d="M7 3.5A1.5 1.5 0 0 1 8.5 2h3.879a1.5 1.5 0 0 1 1.06.44l3.122 3.12A1.5 1.5 0 0 1 17 6.622V12.5a1.5 1.5 0 0 1-1.5 1.5h-1v-3.379a3 3 0 0 0-.879-2.121L10.5 5.379A3 3 0 0 0 8.379 4.5H7v-1Z" />
                        <path d="M4.5 6A1.5 1.5 0 0 0 3 7.5v9A1.5 1.5 0 0 0 4.5 18h7a1.5 1.5 0 0 0 1.5-1.5v-5.879a1.5 1.5 0 0 0-.44-1.06L9.44 6.439A1.5 1.5 0 0 0 8.378 6H4.5Z" />
                      </svg>
                      Copy
                    </button>
                  </div>
                  <pre class="text-xs text-gray-300/80 leading-relaxed">{{ block.code }}</pre>
                </div>
                <span v-else>{{ block.text }}</span>
              </div>
            </template>
            <template v-else>{{ msg.content }}</template>
          </div>
        </div>
      </div>
      <div ref="scrollAnchor"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import AgentOrb from './AgentOrb.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  selectedAgent: { type: String, default: null },
  agents: { type: Array, default: () => [] },
})
defineEmits(['clearFilter'])

const scrollContainer = ref(null)
const scrollAnchor = ref(null)

const agentColor = (n) => {
  const agent = props.agents.find(a => a.name === n)
  if (agent) return agent.color
  if (n === 'System') return '#374151'
  if (n === 'UserProxy' || n === 'You') return '#6b7280'
  return '#6b7280'
}

const agentIcon = (n) => {
  if (n === 'System') return 'system'
  if (n === 'UserProxy' || n === 'You') return 'user'
  const agent = props.agents.find(a => a.name === n)
  return agent ? agent.icon : 'system'
}

const agentDisplayName = (n) => {
  if (n === 'System') return 'System'
  if (n === 'UserProxy') return 'You'
  if (n === 'error') return 'Error'
  const agent = props.agents.find(a => a.name === n)
  if (agent && agent.job_title) return agent.job_title
  return n.replace(/([A-Z])/g, ' $1').trim()
}

function formatTime(ts) {
  if (!ts) return ''
  try { return new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
  catch { return '' }
}

const hasCodeBlock = (c) => c?.includes('```')

function parseContent(content) {
  const blocks = []
  for (const part of content.split(/(```[\s\S]*?```)/g)) {
    if (part.startsWith('```')) {
      const m = part.match(/```(\w+)?\n?([\s\S]*?)```/)
      if (m) blocks.push({ type: 'code', lang: m[1] || '', code: m[2].trim() })
    } else if (part.trim()) {
      blocks.push({ type: 'text', text: part })
    }
  }
  return blocks
}

const copyCode = (code) => navigator.clipboard.writeText(code).catch(() => {})

function scrollToBottom() {
  nextTick(() => scrollAnchor.value?.scrollIntoView({ behavior: 'smooth' }))
}

watch(() => props.messages.length, scrollToBottom)
</script>
