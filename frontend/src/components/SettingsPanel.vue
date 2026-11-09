<template>
  <transition name="slide-panel">
    <div v-if="open" class="fixed inset-0 z-50 flex justify-end" @click.self="$emit('close')">
      <!-- Backdrop -->
      <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="$emit('close')"></div>

      <!-- Panel -->
      <div class="relative w-full max-w-lg glass flex flex-col h-full shadow-glass-lg animate-slide-in" style="border-left: 1px solid rgba(6,182,212,0.12);">
        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 glow-line">
          <div class="flex items-center gap-2.5">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5 text-juli-accent">
              <path fill-rule="evenodd" d="M8.34 1.804A1 1 0 0 1 9.32 1h1.36a1 1 0 0 1 .98.804l.295 1.473c.497.144.971.342 1.416.587l1.25-.834a1 1 0 0 1 1.262.125l.962.962a1 1 0 0 1 .125 1.262l-.834 1.25c.245.445.443.919.587 1.416l1.473.295a1 1 0 0 1 .804.98v1.361a1 1 0 0 1-.804.98l-1.473.295a6.95 6.95 0 0 1-.587 1.416l.834 1.25a1 1 0 0 1-.125 1.262l-.962.962a1 1 0 0 1-1.262.125l-1.25-.834a6.953 6.953 0 0 1-1.416.587l-.295 1.473a1 1 0 0 1-.98.804H9.32a1 1 0 0 1-.98-.804l-.295-1.473a6.957 6.957 0 0 1-1.416-.587l-1.25.834a1 1 0 0 1-1.262-.125l-.962-.962a1 1 0 0 1-.125-1.262l.834-1.25a6.957 6.957 0 0 1-.587-1.416l-1.473-.295A1 1 0 0 1 1 10.68V9.32a1 1 0 0 1 .804-.98l1.473-.295c.144-.497.342-.971.587-1.416l-.834-1.25a1 1 0 0 1 .125-1.262l.962-.962A1 1 0 0 1 5.38 3.03l1.25.834a6.957 6.957 0 0 1 1.416-.587l.294-1.473ZM13 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" clip-rule="evenodd" />
            </svg>
            <h2 class="text-sm font-bold text-white tracking-wide">Settings</h2>
          </div>
          <button @click="$emit('close')" class="text-juli-muted hover:text-white transition-colors p-1 rounded-lg hover:bg-white/5">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        </div>

        <!-- Tabs -->
        <div class="flex px-5 gap-1 border-b border-juli-border/50">
          <button
            v-for="tab in tabs" :key="tab.id"
            @click="activeTab = tab.id"
            class="px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wider transition-all relative"
            :class="activeTab === tab.id ? 'text-juli-accent' : 'text-juli-muted hover:text-juli-text'"
          >
            {{ tab.label }}
            <div v-if="activeTab === tab.id" class="absolute bottom-0 left-0 right-0 h-0.5 bg-juli-accent rounded-full"></div>
          </button>
        </div>

        <!-- Tab Content -->
        <div class="flex-1 overflow-y-auto px-5 py-4">

          <!-- AGENTS TAB -->
          <div v-if="activeTab === 'agents'" class="space-y-3">
            <div
              v-for="(config, name) in settings.agents" :key="name"
              class="glass-card rounded-xl p-4 space-y-3"
            >
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <AgentOrb :icon="config.icon || 'system'" :color="config.color || '#6b7280'" size="sm" />
                  <input
                    :value="config.job_title !== undefined && config.job_title !== '' ? config.job_title : formatName(name)"
                    @input="updateAgentField(name, 'job_title', $event.target.value)"
                    class="text-sm font-bold text-white bg-transparent outline-none border-b border-transparent focus:border-juli-accent/60 hover:bg-white/5 transition-all w-48 placeholder-white/30 px-1 py-0.5 -ml-1 rounded"
                    :placeholder="formatName(name)"
                  />
                </div>
                <button
                  @click="removeAgent(name)"
                  class="text-juli-muted hover:text-red-400 transition-colors p-1 rounded"
                  title="Remove agent"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5">
                    <path fill-rule="evenodd" d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.52.149.023a.75.75 0 0 0 .23-1.482A41.03 41.03 0 0 0 14 4.193V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4ZM8.58 7.72a.75.75 0 0 0-1.5.06l.3 7.5a.75.75 0 1 0 1.5-.06l-.3-7.5Zm4.34.06a.75.75 0 1 0-1.5-.06l-.3 7.5a.75.75 0 1 0 1.5.06l.3-7.5Z" clip-rule="evenodd" />
                  </svg>
                </button>
              </div>

              <!-- Model selector -->
              <div class="space-y-2 mt-2">
                <div>
                  <label class="text-[10px] text-juli-muted uppercase tracking-wider font-semibold block mb-1">Model</label>
                <select
                  :value="config.model"
                  @change="updateAgentField(name, 'model', $event.target.value)"
                  class="w-full glass-input rounded-lg px-3 py-2 text-xs text-gray-200 bg-juli-bg"
                >
                  <option v-for="m in availableModels" :key="m" :value="m">{{ modelLabel(m) }}</option>
                </select>
              </div>
              </div>

              <!-- Icon selector -->
              <div>
                <label class="text-[10px] text-juli-muted uppercase tracking-wider font-semibold block mb-1">Icon</label>
                <div class="flex gap-1.5 flex-wrap">
                  <button
                    v-for="ic in iconOptions" :key="ic.id"
                    @click="updateAgentField(name, 'icon', ic.id)"
                    class="w-8 h-8 rounded-lg flex items-center justify-center transition-all"
                    :class="config.icon === ic.id ? 'bg-juli-accent/20 border border-juli-accent/40' : 'bg-white/5 border border-transparent hover:border-juli-border'"
                    :title="ic.label"
                  >
                    <AgentOrb :icon="ic.id" :color="config.icon === ic.id ? config.color : '#64748b'" size="sm" />
                  </button>
                </div>
              </div>

              <!-- Color -->
              <div>
                <label class="text-[10px] text-juli-muted uppercase tracking-wider font-semibold block mb-1">Color</label>
                <div class="flex gap-1.5">
                  <button
                    v-for="c in colorOptions" :key="c"
                    @click="updateAgentField(name, 'color', c)"
                    class="w-6 h-6 rounded-full transition-all border-2"
                    :style="{ backgroundColor: c, borderColor: config.color === c ? 'white' : 'transparent' }"
                  ></button>
                </div>
              </div>
            </div>

            <!-- Add New Agent -->
            <button @click="showAddAgent = true" class="w-full glass-card rounded-xl p-3 flex items-center justify-center gap-2 text-juli-accent hover:text-white transition-colors group">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
                <path d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z" />
              </svg>
              <span class="text-xs font-semibold">Add New Job</span>
            </button>

            <!-- Add Agent Form -->
            <div v-if="showAddAgent" class="glass-card rounded-xl p-4 space-y-3">
              <h3 class="text-xs font-bold text-white">New Agent Job</h3>
              <div>
                <label class="text-[10px] text-juli-muted uppercase tracking-wider font-semibold block mb-1">Name</label>
                <input v-model="newAgent.name" placeholder="e.g. DatabaseArchitect" class="w-full glass-input rounded-lg px-3 py-2 text-xs text-gray-200" />
              </div>
              <div>
                <label class="text-[10px] text-juli-muted uppercase tracking-wider font-semibold block mb-1">Job Title</label>
                <input v-model="newAgent.job_title" placeholder="e.g. Lead DB Admin" class="w-full glass-input rounded-lg px-3 py-2 text-xs text-gray-200" />
              </div>
              <div>
                <label class="text-[10px] text-juli-muted uppercase tracking-wider font-semibold block mb-1">Model</label>
                <select v-model="newAgent.model" class="w-full glass-input rounded-lg px-3 py-2 text-xs text-gray-200 bg-juli-bg">
                  <option v-for="m in availableModels" :key="m" :value="m">{{ modelLabel(m) }}</option>
                </select>
              </div>
              <div>
                <label class="text-[10px] text-juli-muted uppercase tracking-wider font-semibold block mb-1">System Prompt</label>
                <textarea v-model="newAgent.prompt" rows="3" placeholder="Describe what this agent does..." class="w-full glass-input rounded-lg px-3 py-2 text-xs text-gray-200 resize-none"></textarea>
              </div>
              <div class="flex gap-2">
                <button @click="addAgent" class="btn-glow text-white text-xs font-semibold px-4 py-2 rounded-lg flex-1">Create Agent</button>
                <button @click="showAddAgent = false" class="text-xs text-juli-muted hover:text-white px-3 py-2 rounded-lg hover:bg-white/5 transition-colors">Cancel</button>
              </div>
            </div>
          </div>

          <!-- PROMPTS TAB -->
          <div v-if="activeTab === 'prompts'" class="space-y-3">
            <div v-for="(config, name) in settings.agents" :key="name" class="glass-card rounded-xl p-4 space-y-2">
              <div class="flex items-center gap-2">
                <AgentOrb :icon="config.icon || 'system'" :color="config.color || '#6b7280'" size="sm" />
                <span class="text-xs font-bold text-white">{{ formatName(name) }}</span>
              </div>
              <textarea
                :value="config.prompt"
                @change="updateAgentField(name, 'prompt', $event.target.value)"
                rows="4"
                class="w-full glass-input rounded-lg px-3 py-2 text-xs text-gray-300 resize-none leading-relaxed font-mono"
                placeholder="System prompt for this agent..."
              ></textarea>
            </div>
          </div>

          <!-- API KEYS TAB -->
          <div v-if="activeTab === 'keys'" class="space-y-4">
            <p class="text-[11px] text-juli-muted leading-relaxed">Configure your LLM API keys. Add any AI provider you need.</p>

            <div v-for="(key, provider) in settings.api_keys" :key="provider" class="glass-card rounded-xl p-4 space-y-2">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold" :style="{ backgroundColor: (providerColors[provider] || '#6b7280') + '20', color: providerColors[provider] || '#6b7280' }">
                    {{ (providerLabels[provider] || provider)[0].toUpperCase() }}
                  </div>
                  <span class="text-xs font-bold text-white">{{ providerLabels[provider] || provider }}</span>
                </div>
                <button
                  @click="removeProvider(provider)"
                  class="text-juli-muted hover:text-red-400 transition-colors p-1 rounded"
                  title="Remove provider"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
                    <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
                  </svg>
                </button>
              </div>
              <div class="relative">
                <input
                  :type="showKey[provider] ? 'text' : 'password'"
                  :value="apiKeys[provider] ?? key"
                  @input="apiKeys[provider] = $event.target.value"
                  :placeholder="'Enter ' + (providerLabels[provider] || provider) + ' API key...'"
                  class="w-full glass-input rounded-lg px-3 py-2 text-xs text-gray-200 pr-8 font-mono"
                />
                <button @click="showKey[provider] = !showKey[provider]" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-juli-muted hover:text-white transition-colors">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5">
                    <path v-if="showKey[provider]" d="M10 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" />
                    <path v-if="showKey[provider]" fill-rule="evenodd" d="M.664 10.59a1.651 1.651 0 0 1 0-1.186A10.004 10.004 0 0 1 10 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0 1 10 17c-4.257 0-7.893-2.66-9.336-6.41ZM14 10a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z" clip-rule="evenodd" />
                    <path v-if="!showKey[provider]" fill-rule="evenodd" d="M3.28 2.22a.75.75 0 0 0-1.06 1.06l14.5 14.5a.75.75 0 1 0 1.06-1.06l-1.745-1.745a10.029 10.029 0 0 0 3.3-4.38 1.651 1.651 0 0 0 0-1.185A10.004 10.004 0 0 0 9.999 3a9.956 9.956 0 0 0-4.744 1.194L3.28 2.22ZM7.752 6.69l1.092 1.092a2.5 2.5 0 0 1 3.374 3.373l1.092 1.092a4 4 0 0 0-5.558-5.558Z" clip-rule="evenodd" />
                    <path v-if="!showKey[provider]" d="M10.748 13.93l2.523 2.523A9.987 9.987 0 0 1 10 17a10.003 10.003 0 0 1-9.335-6.41 1.651 1.651 0 0 1 0-1.186 10.018 10.018 0 0 1 2.862-4.156l1.912 1.912A4 4 0 0 0 10.748 13.93Z" />
                  </svg>
                </button>
              </div>
            </div>

            <!-- Add Provider -->
            <div v-if="!showAddProvider" class="flex gap-2">
              <button @click="showAddProvider = true" class="flex-1 glass-card rounded-xl p-3 flex items-center justify-center gap-2 text-juli-accent hover:text-white transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
                  <path d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z" />
                </svg>
                <span class="text-xs font-semibold">Add Provider</span>
              </button>
              <button @click="saveApiKeys" class="btn-glow text-white text-xs font-semibold px-5 py-2.5 rounded-xl">
                Save Keys
              </button>
            </div>

            <!-- Add Provider Form -->
            <div v-if="showAddProvider" class="glass-card rounded-xl p-4 space-y-3">
              <h3 class="text-xs font-bold text-white">New AI Provider</h3>
              <div>
                <label class="text-[10px] text-juli-muted uppercase tracking-wider font-semibold block mb-1">Provider Name</label>
                <input v-model="newProviderName" placeholder="e.g. Mistral, Cohere, DeepSeek..." class="w-full glass-input rounded-lg px-3 py-2 text-xs text-gray-200" />
              </div>
              <div>
                <label class="text-[10px] text-juli-muted uppercase tracking-wider font-semibold block mb-1">API Key</label>
                <input v-model="newProviderKey" type="password" placeholder="Enter API key..." class="w-full glass-input rounded-lg px-3 py-2 text-xs text-gray-200 font-mono" />
              </div>
              <div class="flex gap-2">
                <button @click="addProvider" class="btn-glow text-white text-xs font-semibold px-4 py-2 rounded-lg flex-1">Add Provider</button>
                <button @click="showAddProvider = false" class="text-xs text-juli-muted hover:text-white px-3 py-2 rounded-lg hover:bg-white/5 transition-colors">Cancel</button>
              </div>
            </div>
          </div>

          <!-- THEMES TAB -->
          <div v-if="activeTab === 'themes'" class="space-y-3">
            <p class="text-[11px] text-juli-muted leading-relaxed">Choose a theme for your dashboard. Inspired by GitHub Pages themes.</p>

            <div
              v-for="theme in themePresets" :key="theme.id"
              @click="applyTheme(theme)"
              class="glass-card rounded-xl p-4 flex items-center gap-4 cursor-pointer transition-all duration-200 hover:scale-[1.01]"
              :class="activeTheme === theme.id ? 'ring-1 ring-offset-0' : ''"
              :style="activeTheme === theme.id ? { borderColor: theme.accent + '60', ringColor: theme.accent + '40' } : {}"
            >
              <!-- Color preview -->
              <div class="w-12 h-12 rounded-lg shrink-0 overflow-hidden relative" :style="{ backgroundColor: theme.bg }">
                <div class="absolute inset-x-0 top-0 h-3" :style="{ backgroundColor: theme.panel }"></div>
                <div class="absolute left-1 top-4 w-2 h-6 rounded-sm" :style="{ backgroundColor: theme.border }"></div>
                <div class="absolute right-2 top-5 w-4 h-1 rounded-full" :style="{ backgroundColor: theme.accent }"></div>
                <div class="absolute right-2 top-7 w-3 h-1 rounded-full" :style="{ backgroundColor: theme.text + '60' }"></div>
                <div class="absolute right-2 top-9 w-5 h-1 rounded-full" :style="{ backgroundColor: theme.text + '30' }"></div>
              </div>

              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-bold text-white">{{ theme.name }}</span>
                  <div v-if="activeTheme === theme.id" class="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded" :style="{ backgroundColor: theme.accent + '20', color: theme.accent }">Active</div>
                </div>
                <p class="text-[11px] mt-0.5" :style="{ color: theme.text }">{{ theme.desc }}</p>
              </div>

              <!-- Accent dot -->
              <div class="w-4 h-4 rounded-full shrink-0" :style="{ backgroundColor: theme.accent }"></div>
            </div>
          </div>
        </div>

        <!-- Save indicator -->
        <div v-if="saveMessage" class="px-5 py-2 text-center">
          <span class="text-[11px] font-medium" :class="saveMessage.includes('Error') ? 'text-red-400' : 'text-emerald-400'">{{ saveMessage }}</span>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import AgentOrb from './AgentOrb.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  currentAgents: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'agents-updated'])

const activeTab = ref('agents')
const showAddAgent = ref(false)
const saveMessage = ref('')

const settings = reactive({
  agents: {},
  api_keys: { openai: '', anthropic: '', google: '' },
  available_models: ['gpt4', 'claude', 'gemini', 'gemini_flash'],
})

const apiKeys = reactive({})
const showKey = reactive({})
const showAddProvider = ref(false)
const newProviderName = ref('')
const newProviderKey = ref('')

const newAgent = reactive({
  name: '',
  model: 'gpt4',
  prompt: '',
  color: '#6b7280',
  icon: 'system',
})

const tabs = [
  { id: 'agents', label: 'Agents' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'keys', label: 'API Keys' },
  { id: 'themes', label: 'Themes' },
]

const availableModels = ['gpt4', 'claude', 'gemini', 'gemini_flash']

const iconOptions = [
  { id: 'planner', label: 'Planner' },
  { id: 'coder', label: 'Coder' },
  { id: 'reviewer', label: 'Shield' },
  { id: 'devops', label: 'Rocket' },
  { id: 'test', label: 'Beaker' },
  { id: 'docs', label: 'Document' },
  { id: 'user', label: 'User' },
  { id: 'system', label: 'Cog' },
  { id: 'database', label: 'Database' },
  { id: 'brain', label: 'Brain' },
  { id: 'chart', label: 'Chart' },
  { id: 'globe', label: 'Globe' },
  { id: 'wrench', label: 'Wrench' },
  { id: 'lock', label: 'Lock' },
  { id: 'bolt', label: 'Bolt' },
  { id: 'eye', label: 'Eye' },
  { id: 'heart', label: 'Heart' },
  { id: 'sparkles', label: 'Sparkles' },
  { id: 'fire', label: 'Fire' },
  { id: 'puzzle', label: 'Puzzle' },
]

const colorOptions = [
  '#6366f1', '#06b6d4', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6',
  '#ec4899', '#f97316', '#3b82f6', '#6b7280', '#14b8a6', '#a855f7',
  '#e11d48', '#0ea5e9', '#84cc16', '#d946ef', '#facc15', '#78716c',
  '#22d3ee', '#fb923c',
]

const activeTheme = ref('midnight')

const themePresets = [
  { id: 'midnight', name: 'Midnight', desc: 'Deep dark with cyan accents', bg: '#0a0e1a', panel: '#0d1321', accent: '#06b6d4', border: '#1a2744', text: '#94a3b8' },
  { id: 'cayman', name: 'Cayman', desc: 'Ocean teal gradient feel', bg: '#0d1117', panel: '#111822', accent: '#27d4a5', border: '#1a3a35', text: '#9eb3a8' },
  { id: 'slate', name: 'Slate', desc: 'Cool grey sophistication', bg: '#1a1d23', panel: '#21252b', accent: '#7c8aff', border: '#2d333b', text: '#adbac7' },
  { id: 'hacker', name: 'Hacker', desc: 'Terminal green on black', bg: '#0d0d0d', panel: '#141414', accent: '#39ff14', border: '#1a2e1a', text: '#7dbb7d' },
  { id: 'architect', name: 'Architect', desc: 'Blueprint blue on navy', bg: '#0a1628', panel: '#0f1d32', accent: '#4a9eff', border: '#1c3554', text: '#8ba4c4' },
  { id: 'merlot', name: 'Merlot', desc: 'Rich wine red tones', bg: '#1a0a10', panel: '#21101a', accent: '#e84393', border: '#3a1a2a', text: '#b88a9a' },
  { id: 'minimal', name: 'Minimal', desc: 'Clean near-black + white', bg: '#111111', panel: '#1a1a1a', accent: '#ffffff', border: '#2a2a2a', text: '#888888' },
  { id: 'tactile', name: 'Tactile', desc: 'Warm amber on charcoal', bg: '#1a1510', panel: '#211c14', accent: '#f59e0b', border: '#3a3020', text: '#b8a88a' },
]

const providerLabels = { openai: 'OpenAI', anthropic: 'Anthropic', google: 'Google AI' }
const providerColors = { openai: '#10b981', anthropic: '#f59e0b', google: '#3b82f6' }

function modelLabel(m) {
  return { gpt4: 'GPT-4 (OpenAI)', claude: 'Claude Opus (Anthropic)', gemini: 'Gemini Pro (Google)', gemini_flash: 'Gemini Flash (Google)' }[m] || m
}

function formatName(name) {
  return name.replace(/([A-Z])/g, ' $1').trim()
}

function buildDefaultAgents() {
  const defaults = {}
  for (const a of props.currentAgents) {
    const modelKey = { 'GPT-4': 'gpt4', 'Claude Opus': 'claude', 'Gemini': 'gemini', 'Gemini Flash': 'gemini_flash' }[a.model] || 'gpt4'
    defaults[a.name] = {
      model: modelKey,
      prompt: '',
      color: a.color || '#6b7280',
      icon: a.icon || 'system',
    }
  }
  return defaults
}

async function fetchSettings() {
  // Always start with local agent data as base
  const localDefaults = buildDefaultAgents()
  if (Object.keys(localDefaults).length && !Object.keys(settings.agents).length) {
    Object.assign(settings.agents, localDefaults)
  }
  try {
    const res = await fetch('/api/settings')
    const data = await res.json()
    if (data.agents && Object.keys(data.agents).length) {
      Object.assign(settings, data)
    }
  } catch {
    // Backend offline — use local defaults, which are already set
  }
}

function updateAgentField(name, field, value) {
  settings.agents[name][field] = value
  saveAgents()
}

let saveTimeout = null
async function saveAgents() {
  clearTimeout(saveTimeout)
  saveTimeout = setTimeout(async () => {
    try {
      await fetch('/api/settings/agents', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings.agents),
      })
      flash('Settings saved')
      emit('agents-updated', settings.agents)
    } catch {
      flash('Saved locally')
      emit('agents-updated', settings.agents)
    }
  }, 500)
}

async function addAgent() {
  if (!newAgent.name.trim()) return
  const agentName = newAgent.name.replace(/\s+/g, '')
  settings.agents[agentName] = {
    model: newAgent.model,
    prompt: newAgent.prompt || `You are ${newAgent.name}. Follow instructions precisely.`,
    color: colorOptions[Object.keys(settings.agents).length % colorOptions.length],
    icon: 'system',
  }
  try {
    await fetch('/api/settings/agents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: agentName, ...settings.agents[agentName] }),
    })
  } catch { /* offline — saved locally */ }
  newAgent.name = ''
  newAgent.prompt = ''
  showAddAgent.value = false
  flash('Agent created')
  emit('agents-updated', settings.agents)
}

async function removeAgent(name) {
  delete settings.agents[name]
  try {
    await fetch(`/api/settings/agents/${name}`, { method: 'DELETE' })
  } catch { /* offline */ }
  flash('Agent removed')
  emit('agents-updated', settings.agents)
}

async function saveApiKeys() {
  try {
    await fetch('/api/settings/keys', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(apiKeys),
    })
    flash('API keys saved')
    await fetchSettings()
  } catch {
    flash('Saved locally')
  }
}

function addProvider() {
  const name = newProviderName.value.trim().toLowerCase().replace(/\s+/g, '_')
  if (!name) return
  settings.api_keys[name] = newProviderKey.value || ''
  apiKeys[name] = newProviderKey.value || ''
  showKey[name] = false
  newProviderName.value = ''
  newProviderKey.value = ''
  showAddProvider.value = false
  flash('Provider added')
  saveApiKeys()
}

function removeProvider(provider) {
  delete settings.api_keys[provider]
  delete apiKeys[provider]
  delete showKey[provider]
  flash('Provider removed')
  saveApiKeys()
}

function flash(msg) {
  saveMessage.value = msg
  setTimeout(() => { saveMessage.value = '' }, 2000)
}

function hexToRgb(hex) {
  let c = hex.substring(1)
  if (c.length === 3) c = c.split('').map(x => x + x).join('')
  let r = parseInt(c.slice(0, 2), 16)
  let g = parseInt(c.slice(2, 4), 16)
  let b = parseInt(c.slice(4, 6), 16)
  return `${r}, ${g}, ${b}`
}

function applyTheme(theme) {
  activeTheme.value = theme.id
  const root = document.documentElement
  root.style.setProperty('--color-juli-bg', theme.bg)
  root.style.setProperty('--color-juli-bg-rgb', hexToRgb(theme.bg))
  root.style.setProperty('--color-juli-panel', theme.panel)
  root.style.setProperty('--color-juli-panel-rgb', hexToRgb(theme.panel))
  root.style.setProperty('--color-juli-accent', theme.accent)
  root.style.setProperty('--color-juli-accent-rgb', hexToRgb(theme.accent))
  root.style.setProperty('--color-juli-border', theme.border)
  root.style.setProperty('--color-juli-border-rgb', hexToRgb(theme.border))
  root.style.setProperty('--color-juli-muted', theme.text)
  root.style.setProperty('--color-juli-muted-rgb', hexToRgb(theme.text))
  localStorage.setItem('juli-theme', JSON.stringify(theme))
  flash(`Theme: ${theme.name}`)
}

function restoreTheme() {
  try {
    const saved = localStorage.getItem('juli-theme')
    if (saved) {
      const theme = JSON.parse(saved)
      applyTheme(theme)
    }
  } catch { /* use default */ }
}

watch(() => props.open, (val) => { if (val) fetchSettings() })
onMounted(() => {
  fetchSettings()
  restoreTheme()
})
</script>
