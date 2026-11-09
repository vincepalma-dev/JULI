<template>
  <div class="h-screen flex flex-col overflow-hidden grid-bg">
    <!-- Particle Background -->
    <ParticleBackground />

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
const { messages, isConnected, sendMessage, clearMessages } = useWebSocket()

// ─── State ──────────────────────────────────────────────
const taskStatus = ref('idle')
const selectedAgent = ref(null)
const sidebarCollapsed = ref(false)
const settingsOpen = ref(false)
const projectsOpen = ref(false)

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
  clearMessages()
  taskStatus.value = 'running'
  selectedAgent.value = null

  try {
    const response = await fetch('/api/task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, mode: 'full' }),
    })
    const data = await response.json()
    if (data.error) taskStatus.value = 'error'
  } catch {
    sendMessage({ type: 'start_task', prompt, mode: 'full' })
  }
}

async function fetchProjects() {
  try {
    const res = await fetch('/api/projects')
    projectsList.value = await res.json()
  } catch { /* ignore */ }
}

async function handleCreateProject(name) {
  try {
    const res = await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    })
    const data = await res.json()
    projectsList.value.unshift(data)
    handleSelectProject(data.id)
  } catch { /* ignore */ }
}

async function handleSelectProject(id) {
  try {
    await fetch(`/api/projects/${id}/activate`, { method: 'PUT' })
    const res = await fetch(`/api/projects/${id}`)
    const data = await res.json()
    
    clearMessages()
    if (data.messages && data.messages.length > 0) {
      messages.value = data.messages
    }
    activeProjectId.value = id
  } catch { /* ignore */ }
}

async function handleDeleteProject(id) {
  if (!confirm('Are you sure you want to delete this project?')) return
  try {
    await fetch(`/api/projects/${id}`, { method: 'DELETE' })
    projectsList.value = projectsList.value.filter(p => p.id !== id)
    if (activeProjectId.value === id) {
      if (projectsList.value.length > 0) {
        handleSelectProject(projectsList.value[0].id)
      } else {
        handleCreateProject('Default Project')
      }
    }
  } catch { /* ignore */ }
}

onMounted(async () => {
  await fetchProjects()
  if (projectsList.value.length === 0) {
    await handleCreateProject('Default Project')
  } else {
    await handleSelectProject(projectsList.value[0].id)
  }

  try {
    const res = await fetch('/api/status')
    const data = await res.json()
    taskStatus.value = data.status || 'idle'
  } catch { /* backend not ready */ }
})
</script>
