<template>
  <!-- Phones: a drawer over the page -->
  <div v-if="open" class="fixed inset-0 z-30 bg-black/50 md:hidden" aria-hidden="true" @click="$emit('close')"></div>
  <aside
    class="fixed inset-y-0 left-0 z-40 flex w-72 max-w-[85vw] flex-col border-r border-juli-border bg-juli-panel transition-transform md:static md:z-auto md:w-64 md:translate-x-0"
    :class="open ? 'translate-x-0' : '-translate-x-full'"
    :inert="(narrow && !open) || undefined"
    aria-label="Crew and tools"
  >
    <div class="flex items-center gap-2 border-b border-juli-border px-4 py-3">
      <JuliMascot state="idle" :size="32" />
      <div class="min-w-0 flex-1">
        <p class="text-sm font-bold tracking-wide text-white" translate="no">JULI</p>
        <p class="text-xs text-slate-400">Understand. Learn. Improve.</p>
      </div>
      <button type="button" class="icon-btn md:hidden" aria-label="Close menu" @click="$emit('close')">
        <Icon name="x" class="h-5 w-5" />
      </button>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-2 py-3">
      <div class="flex items-center gap-2 px-2 pb-2">
        <h2 class="flex-1 text-xs font-medium text-slate-400">Crew</h2>
        <!-- Juli only: one voice in the run view; the crew still works behind it -->
        <label class="flex cursor-pointer items-center gap-2 text-xs text-slate-300" title="Show one reply per run from Juli; the crew's steps fold away">
          Juli only
          <button
            type="button"
            role="switch"
            :aria-checked="view === 'juli'"
            aria-label="Juli only"
            class="relative h-5 w-9 shrink-0 rounded-full border transition-colors"
            :class="view === 'juli' ? 'border-transparent bg-cyan-500' : 'border-juli-border bg-white/10'"
            @click="$emit('view', view === 'juli' ? 'crew' : 'juli')"
          >
            <span class="absolute top-0.5 h-3.5 w-3.5 rounded-full bg-white transition-[left]" :class="view === 'juli' ? 'left-[18px]' : 'left-0.5'"></span>
          </button>
        </label>
      </div>
      <p v-if="!names.length" class="px-2 text-sm text-slate-400">No agents yet. Add them in the crew builder.</p>
      <ul class="space-y-0.5">
        <li v-for="name in names" :key="name">
          <button
            type="button"
            class="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors"
            :class="filter === name ? 'bg-white/[0.08]' : 'hover:bg-white/[0.04]'"
            :aria-pressed="filter === name"
            :title="filter === name ? 'Show everyone' : `Show only ${agentLabel(name, agents)}`"
            @click="$emit('filter', filter === name ? null : name)"
          >
            <AgentOrb :icon="agents[name].icon || 'system'" :color="agents[name].color || '#94a3b8'" :active="activeAgent === name" size="sm" />
            <span class="min-w-0 flex-1">
              <span class="block text-sm font-medium text-slate-100">{{ agentLabel(name, agents) }}</span>
              <span class="block font-mono text-xs text-slate-400" style="overflow-wrap: anywhere">{{ agents[name].model }}</span>
            </span>
            <span v-if="activeAgent === name" class="sr-only">working now</span>
          </button>
        </li>
      </ul>
    </div>

    <nav class="space-y-0.5 border-t border-juli-border p-2" aria-label="Panels">
      <button v-for="item in NAV" :key="item.id" type="button" class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-slate-300 transition-colors hover:bg-white/[0.05] hover:text-white" :aria-pressed="item.id === 'terminal' ? terminalOpen : undefined" @click="$emit('open', item.id)">
        <Icon :name="item.icon" class="h-[18px] w-[18px] shrink-0 text-slate-400" />
        <span class="flex-1">{{ item.label }}</span>
        <span v-if="item.id === 'terminal' && agentCommands" class="badge bg-cyan-500/15 text-cyan-200" :aria-label="`${agentCommands} agent commands`">{{ agentCommands }}</span>
      </button>
    </nav>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import AgentOrb from './AgentOrb.vue'
import Icon from './Icon.vue'
import JuliMascot from './JuliMascot.vue'
import { agentLabel } from '../labels.js'

const props = defineProps({
  agents: { type: Object, default: () => ({}) },
  activeAgent: { type: String, default: null },
  filter: { type: String, default: null },
  open: { type: Boolean, default: false },
  terminalOpen: { type: Boolean, default: false },
  agentCommands: { type: Number, default: 0 },
  view: { type: String, default: 'crew' }, // crew or juli
})
defineEmits(['filter', 'close', 'open', 'view'])

const names = computed(() => Object.keys(props.agents))

// On phones the closed drawer stays out of the tab order.
const query = window.matchMedia('(max-width: 767px)')
const narrow = ref(query.matches)
const onChange = e => { narrow.value = e.matches }
onMounted(() => query.addEventListener('change', onChange))
onUnmounted(() => query.removeEventListener('change', onChange))

const NAV = [
  { id: 'crew', label: 'Crew', icon: 'users' },
  { id: 'models', label: 'Models', icon: 'cube' },
  { id: 'workspace', label: 'Workspace', icon: 'code' },
  { id: 'terminal', label: 'Terminal', icon: 'terminal' },
  { id: 'projects', label: 'Projects', icon: 'folder' },
  { id: 'settings', label: 'Settings', icon: 'sliders' },
]
</script>
