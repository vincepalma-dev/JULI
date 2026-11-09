<template>
  <div class="h-screen flex flex-col overflow-hidden grid-bg">
    <!-- Particle Background -->
    <ParticleBackground />

    <!-- No session notice -->
    <div v-if="sessionMissing" role="alert" class="relative z-20 mx-5 mt-3 glass-card rounded-xl px-4 py-3 flex items-start gap-3 text-amber-300">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5 shrink-0 mt-0.5" aria-hidden="true">
        <path fill-rule="evenodd" d="M10 1a4.5 4.5 0 0 0-4.5 4.5V9H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-.5V5.5A4.5 4.5 0 0 0 10 1Zm3 8V5.5a3 3 0 1 0-6 0V9h6Z" clip-rule="evenodd" />
      </svg>
      <div class="text-xs leading-relaxed">
        <p class="font-semibold">No session</p>
        <p class="text-juli-muted">This page has no valid session token. Start JULI with <code class="font-mono">python run.py</code> and open the link it prints.</p>
      </div>
    </div>

    <!-- Error toast -->
    <div v-if="errorMessage" role="alert" class="fixed bottom-14 right-5 z-50 glass-card rounded-xl px-4 py-2.5 text-xs text-red-300">
      {{ errorMessage }}
    </div>

    <!-- Top Bar -->
    <TopBar
      :status="taskStatus"
      :project-name="activeProjectName"
      @start-task="handleStartTask"
    />

    <!-- Main Content -->
    <div class="flex flex-1 overflow-hidden">
      <Sidebar
        :agents="agents"
        :active-agents="activeAgents"
        :selected-agent="selectedAgent"
        :collapsed="sidebarCollapsed"
        @select-agent="selectedAgent = $event"
        @toggle="sidebarCollapsed = !sidebarCollapsed"
        @open-settings="settingsOpen = true"
        @open-projects="projectsOpen = true"
      />

      <ChatStream
        :messages="filteredMessages"
        :selected-agent="selectedAgent"
        :agents="agents"
        @clear-filter="selectedAgent = null"
      />
    </div>

    <!-- Stats Bar -->
    <StatsBar
      :message-count="messages.length"
      :active-count="activeAgents.size"
      :total-agents="agents.length"
      :is-connected="isConnected"
      :status="taskStatus"
    />

    <!-- Settings Panel -->
    <SettingsPanel
      :open="settingsOpen"
      :current-agents="agents"
      @close="settingsOpen = false"
      @agents-updated="handleAgentsUpdated"
    />

    <!-- Projects Panel -->
    <ProjectsPanel
      :open="projectsOpen"
      :projects="projectsList"
      :active-project-id="activeProjectId"
      @close="projectsOpen = false"
      @create-project="handleCreateProject"
      @select-project="handleSelectProject"
      @delete-project="handleDeleteProject"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useWebSocket } from './composables/useWebSocket.js'
import { apiFetch, getToken } from './api.js'
import ParticleBackground from './components/ParticleBackground.vue'
import TopBar from './components/TopBar.vue'
import Sidebar from './components/Sidebar.vue'
import ChatStream from './components/ChatStream.vue'
import StatsBar from './components/StatsBar.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import ProjectsPanel from './components/ProjectsPanel.vue'

// ─── 6 Consolidated Agents ──────────────────────────────
const agents = ref([
  { name: 'PlannerResearcher', icon: 'planner', color: '#6366f1', model: 'GPT-4' },
  { name: 'Coder',            icon: 'coder',   color: '#06b6d4', model: 'Claude Opus' },
  { name: 'ReviewerSecurity', icon: 'reviewer', color: '#ef4444', model: 'GPT-4' },
  { name: 'DevOps',           icon: 'devops',  color: '#10b981', model: 'Gemini' },
  { name: 'TestMonitor',      icon: 'test',    color: '#f59e0b', model: 'Gemini' },
  { name: 'DocsDiagram',      icon: 'docs',    color: '#8b5cf6', model: 'Gemini Flash' },
])

// ─── WebSocket ──────────────────────────────────────────
const { messages, isConnected, status: wsStatus, clearMessages } = useWebSocket()

// ─── State ──────────────────────────────────────────────
const taskStatus = ref('idle')
const selectedAgent = ref(null)
const sidebarCollapsed = ref(false)
const settingsOpen = ref(false)
const projectsOpen = ref(false)
const errorMessage = ref('')
const hasSession = Boolean(getToken())
const sessionMissing = computed(() => !hasSession || wsStatus.value === 'unauthorized')

const projectsList = ref([])
const activeProjectId = ref(null)

const activeProjectName = computed(() => {
  const p = projectsList.value.find(p => p.id === activeProjectId.value)
  return p ? p.name : ''
})

function handleAgentsUpdated(agentsConfig) {
  // Sync sidebar agents with settings
  const updated = Object.entries(agentsConfig).map(([name, config]) => ({
    name,
    icon: config.icon || 'system',
    color: config.color || '#6b7280',
    model: modelLabel(config.model || 'gpt4'),
    job_title: config.job_title || ''
  }))
  agents.value = updated
}

function modelLabel(m) {
  return { gpt4: 'GPT-4', claude: 'Claude Opus', gemini: 'Gemini', gemini_flash: 'Gemini Flash' }[m] || m
}

// ─── Computed ───────────────────────────────────────────
const activeAgents = computed(() => {
  const active = new Set()
  messages.value.slice(-50).forEach(msg => {
    if (msg.agent_name !== 'System' && msg.agent_name !== 'UserProxy') {
      active.add(msg.agent_name)
    }
  })
  return active
})

const filteredMessages = computed(() => {
  if (!selectedAgent.value) return messages.value
  return messages.value.filter(msg =>
    msg.agent_name === selectedAgent.value || msg.agent_name === 'System'
  )
})

// ─── Watch status ───────────────────────────────────────
watch(messages, (msgs) => {
  const last = msgs[msgs.length - 1]
  if (last && last.message_type === 'status') {
    if (last.content.includes('running')) taskStatus.value = 'running'
    else if (last.content.includes('complete')) taskStatus.value = 'complete'
    else if (last.content.includes('error')) taskStatus.value = 'error'
    else if (last.content.includes('idle')) taskStatus.value = 'idle'
  }
}, { deep: true })

// ─── Methods ────────────────────────────────────────────
async function handleStartTask(prompt) {
  if (!activeProjectId.value) {
    showError(new Error('Select or create a project first'))
    return
  }
  clearMessages()
  taskStatus.value = 'running'
  selectedAgent.value = null

  try {
    await apiFetch('/api/task', {
      method: 'POST',
      body: { prompt, mode: 'full', project_id: activeProjectId.value },
    })
  } catch (e) {
    taskStatus.value = 'error'
    showError(e)
  }
}

async function fetchProjects() {
  try {
    projectsList.value = await apiFetch('/api/projects')
  } catch (e) { showError(e) }
}

async function handleCreateProject(name) {
  try {
    const data = await apiFetch('/api/projects', { method: 'POST', body: { name } })
    projectsList.value.unshift(data)
    await handleSelectProject(data.id)
  } catch (e) { showError(e) }
}

async function handleSelectProject(id) {
  try {
    await apiFetch(`/api/projects/${id}/activate`, { method: 'PUT' })
    const data = await apiFetch(`/api/projects/${id}`)
    clearMessages()
    if (data.messages && data.messages.length > 0) {
      messages.value = data.messages
    }
    activeProjectId.value = id
  } catch (e) { showError(e) }
}

async function handleDeleteProject(id) {
  if (!confirm('Are you sure you want to delete this project?')) return
  try {
    await apiFetch(`/api/projects/${id}`, { method: 'DELETE' })
    projectsList.value = projectsList.value.filter(p => p.id !== id)
    if (activeProjectId.value === id) {
      if (projectsList.value.length > 0) {
        await handleSelectProject(projectsList.value[0].id)
      } else {
        await handleCreateProject('Default Project')
      }
    }
  } catch (e) { showError(e) }
}

let errorTimeout = null
function showError(e) {
  errorMessage.value = e.message || 'Something went wrong'
  clearTimeout(errorTimeout)
  errorTimeout = setTimeout(() => { errorMessage.value = '' }, 5000)
}

onMounted(async () => {
  if (!hasSession) return
  await fetchProjects()
  if (projectsList.value.length === 0) {
    await handleCreateProject('Default Project')
  } else {
    await handleSelectProject(projectsList.value[0].id)
  }

  try {
    const data = await apiFetch('/api/status')
    taskStatus.value = data.status || 'idle'
  } catch { /* backend not ready */ }
})
</script>
