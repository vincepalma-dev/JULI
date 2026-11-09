<template>
  <aside
    class="glass shrink-0 flex flex-col sidebar-transition relative"
    :class="collapsed ? 'w-16' : 'w-72'"
    style="z-index: 10;"
  >
    <!-- Logo Section -->
    <div class="px-4 py-4 glow-line">
      <div class="flex items-center gap-3">
        <!-- Logo orb -->
        <div
          class="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 cursor-pointer"
          :style="`background: linear-gradient(135deg, var(--color-juli-accent), color-mix(in srgb, var(--color-juli-accent) 60%, #2563eb)); box-shadow: 0 4px 15px color-mix(in srgb, var(--color-juli-accent) 25%, transparent);`"
          @click="$emit('toggle')"
        >
          <!-- Heroicon: sparkles (mini) -->
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5 text-white">
            <path d="M15.98 1.804a1 1 0 0 0-1.96 0l-.24 1.192a1 1 0 0 1-.784.785l-1.192.238a1 1 0 0 0 0 1.962l1.192.238a1 1 0 0 1 .785.785l.238 1.192a1 1 0 0 0 1.962 0l.238-1.192a1 1 0 0 1 .785-.785l1.192-.238a1 1 0 0 0 0-1.962l-1.192-.238a1 1 0 0 1-.785-.785l-.238-1.192ZM6.949 5.684a1 1 0 0 0-1.898 0l-.683 2.051a1 1 0 0 1-.633.633l-2.051.683a1 1 0 0 0 0 1.898l2.051.684a1 1 0 0 1 .633.632l.683 2.051a1 1 0 0 0 1.898 0l.683-2.051a1 1 0 0 1 .633-.633l2.051-.683a1 1 0 0 0 0-1.898l-2.051-.683a1 1 0 0 1-.633-.633L6.95 5.684ZM13.949 13.684a1 1 0 0 0-1.898 0l-.184.551a1 1 0 0 1-.632.633l-.551.183a1 1 0 0 0 0 1.898l.551.183a1 1 0 0 1 .633.633l.183.551a1 1 0 0 0 1.898 0l.184-.551a1 1 0 0 1 .632-.633l.551-.183a1 1 0 0 0 0-1.898l-.551-.184a1 1 0 0 1-.633-.632l-.183-.551Z" />
          </svg>
        </div>

        <transition name="collapse-fade">
          <div v-if="!collapsed" class="min-w-0">
            <h1 class="text-sm font-bold tracking-widest text-juli-accent glow-text">J.U.L.I.</h1>
            <p class="text-[9px] text-juli-muted font-medium tracking-wider uppercase mt-0.5">Little Intelligences</p>
          </div>
        </transition>
      </div>
    </div>

    <!-- Agent List -->
    <div class="flex-1 overflow-y-auto py-3">
      <transition name="collapse-fade">
        <div v-if="!collapsed" class="px-3 pb-2">
          <h2 class="text-[9px] font-semibold text-juli-muted uppercase tracking-[0.15em] px-1">Agents</h2>
        </div>
      </transition>

      <div class="space-y-1 px-2">
        <button
          v-for="agent in agents"
          :key="agent.name"
          @click="$emit('selectAgent', selectedAgent === agent.name ? null : agent.name)"
          class="w-full flex items-center rounded-xl text-left transition-all duration-200 group"
          :class="[
            collapsed ? 'justify-center px-1 py-2.5' : 'gap-3 px-3 py-2.5',
            selectedAgent === agent.name
              ? 'glass-card'
              : 'hover:bg-white/[0.03]',
          ]"
          :style="selectedAgent === agent.name ? { borderColor: agent.color + '30' } : {}"
          :title="collapsed ? agent.name : ''"
        >
          <AgentOrb
            :icon="agent.icon"
            :color="agent.color"
            :active="activeAgents.has(agent.name)"
            :size="collapsed ? 'sm' : 'md'"
          />

          <transition name="collapse-fade">
            <div v-if="!collapsed" class="flex-1 min-w-0">
              <p
                class="text-sm font-medium truncate transition-colors"
                :style="{ color: selectedAgent === agent.name ? agent.color : '#cbd5e1' }"
              >
                {{ agent.job_title || formatAgentName(agent.name) }}
              </p>
              <p class="text-[10px] text-juli-muted mt-0.5">{{ agent.model }}</p>
            </div>
          </transition>

          <transition name="collapse-fade">
            <div
              v-if="!collapsed && activeAgents.has(agent.name)"
              class="w-1.5 h-1.5 rounded-full shrink-0"
              :style="{ backgroundColor: '#10b981', boxShadow: '0 0 6px #10b98180' }"
            ></div>
          </transition>
        </button>
      </div>
    </div>

    <!-- Footer -->
    <div class="px-3 py-3 glow-line" style="border-top: none;">
      <div
        class="relative overflow-hidden"
        :style="{ height: collapsed ? '0' : 'auto', opacity: collapsed ? 0 : 1, transition: 'all 0.2s ease' }"
      >
        <div class="flex items-center justify-between text-[10px] text-juli-muted px-1">
          <span>{{ agents.length }} agents</span>
          <span class="text-juli-accent font-medium">{{ activeAgents.size }} active</span>
        </div>
      </div>

      <!-- Projects Button -->
      <button
        @click="$emit('open-projects')"
        class="w-full flex items-center gap-2 px-2 py-2 mt-2 rounded-lg text-juli-muted hover:text-juli-accent hover:bg-white/[0.03] transition-all duration-200"
        :class="collapsed ? 'justify-center' : ''"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4 shrink-0">
          <path d="M3 4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-5.828A2 2 0 0 1 9.757 5.414l-1.172-1.171A2 2 0 0 0 7.172 3.657L3 4Z" />
        </svg>
        <transition name="collapse-fade">
          <span v-if="!collapsed" class="text-[11px] font-medium">Projects</span>
        </transition>
      </button>

      <!-- Settings Button -->
      <button
        @click="$emit('open-settings')"
        class="w-full flex items-center gap-2 px-2 py-2 mt-2 rounded-lg text-juli-muted hover:text-juli-accent hover:bg-white/[0.03] transition-all duration-200"
        :class="collapsed ? 'justify-center' : ''"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4 shrink-0">
          <path fill-rule="evenodd" d="M8.34 1.804A1 1 0 0 1 9.32 1h1.36a1 1 0 0 1 .98.804l.295 1.473c.497.144.971.342 1.416.587l1.25-.834a1 1 0 0 1 1.262.125l.962.962a1 1 0 0 1 .125 1.262l-.834 1.25c.245.445.443.919.587 1.416l1.473.295a1 1 0 0 1 .804.98v1.361a1 1 0 0 1-.804.98l-1.473.295a6.95 6.95 0 0 1-.587 1.416l.834 1.25a1 1 0 0 1-.125 1.262l-.962.962a1 1 0 0 1-1.262.125l-1.25-.834a6.953 6.953 0 0 1-1.416.587l-.295 1.473a1 1 0 0 1-.98.804H9.32a1 1 0 0 1-.98-.804l-.295-1.473a6.957 6.957 0 0 1-1.416-.587l-1.25.834a1 1 0 0 1-1.262-.125l-.962-.962a1 1 0 0 1-.125-1.262l.834-1.25a6.957 6.957 0 0 1-.587-1.416l-1.473-.295A1 1 0 0 1 1 10.68V9.32a1 1 0 0 1 .804-.98l1.473-.295c.144-.497.342-.971.587-1.416l-.834-1.25a1 1 0 0 1 .125-1.262l.962-.962A1 1 0 0 1 5.38 3.03l1.25.834a6.957 6.957 0 0 1 1.416-.587l.294-1.473ZM13 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" clip-rule="evenodd" />
        </svg>
        <transition name="collapse-fade">
          <span v-if="!collapsed" class="text-[11px] font-medium">Settings</span>
        </transition>
      </button>
    </div>

    <!-- Collapse Toggle -->
    <button
      @click="$emit('toggle')"
      class="absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full glass flex items-center justify-center text-juli-muted hover:text-juli-accent transition-all hover:border-juli-accent/30 z-20"
      style="font-size: 10px;"
    >
      {{ collapsed ? '▸' : '◂' }}
    </button>
  </aside>
</template>

<script setup>
import AgentOrb from './AgentOrb.vue'

defineProps({
  agents: { type: Array, required: true },
  activeAgents: { type: Set, default: () => new Set() },
  selectedAgent: { type: String, default: null },
  collapsed: { type: Boolean, default: false },
})

defineEmits(['selectAgent', 'toggle', 'open-settings', 'open-projects'])

function formatAgentName(name) {
  return name.replace(/([A-Z])/g, ' $1').trim()
}
</script>
