<template>
  <div class="grid-bg flex h-dvh flex-col overflow-hidden">
    <ParticleBackground />
    <h1 class="sr-only">JULI dashboard</h1>

    <div class="relative z-10 flex min-h-0 flex-1">
      <Sidebar
        :agents="agents"
        :active-agent="run.status.value === 'running' ? run.turn.value?.agent : null"
        :filter="filter"
        :open="sidebarOpen"
        :terminal-open="terminalOpen"
        :agent-commands="run.commands.value.filter(c => c.status === 'running').length"
        :view="view"
        @view="view = $event"
        @filter="filter = $event; sidebarOpen = false"
        @close="sidebarOpen = false"
        @open="openPanel"
      />

      <div class="flex min-w-0 flex-1 flex-col">
        <TopBar
          :status="run.status.value"
          :project-name="activeProjectName"
          :mode="settings.mode"
          :cloud-models="cloudModels"
          :stopping="stopping"
          @menu="sidebarOpen = true"
          @stop="stopRun"
          @mode-changed="modeChanged"
          @error="toastError"
        />

        <!-- No session -->
        <div v-if="sessionMissing" role="alert" class="mx-3 mt-3 flex items-start gap-3 rounded-xl border border-amber-400/30 bg-amber-400/[0.07] p-3 text-sm text-amber-100 sm:mx-6">
          <Icon name="lock" class="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
          <p><strong class="font-semibold">No session.</strong> This page has no valid session token. Start JULI with <code class="font-mono">start-juli.bat</code> or <code class="font-mono">python -m juli serve</code> and use the page it opens.</p>
        </div>

        <!-- A key problem pauses the run: switch model and resume (in the card), or stop -->
        <div v-if="keyProblem" class="mx-3 mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/[0.08] p-3 text-sm sm:mx-6" role="alert">
          <Icon name="key" class="h-5 w-5 shrink-0 text-red-300" />
          <p class="min-w-0 flex-1 text-red-100">{{ keyProblemText }}</p>
          <button type="button" class="btn btn-primary" @click="focusDecision(keyProblem.key)">Choose a model…</button>
          <button type="button" class="btn btn-danger" :disabled="stopping" @click="stopRun">Stop run</button>
        </div>

        <!-- Runs a restart, crash or error cut short -->
        <div v-for="r in resumable" :key="r.id" class="mx-3 mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-juli-border bg-white/[0.03] p-3 text-sm sm:mx-6">
          <Icon name="refresh" class="h-5 w-5 shrink-0 text-cyan-300" />
          <p class="min-w-0 flex-1 text-slate-200">Run {{ r.id }} was cut short ({{ r.status === 'error' ? 'an error' : 'JULI stopped' }}). Resume it from its last finished step.</p>
          <button type="button" class="btn btn-primary" :disabled="live" @click="resume(r)">Resume run {{ r.id }}</button>
          <button type="button" class="icon-btn" :aria-label="`Dismiss run ${r.id}`" @click="resumable = resumable.filter(x => x.id !== r.id)"><Icon name="x" class="h-4 w-4" /></button>
        </div>

        <main class="flex min-h-0 flex-1 flex-col">
          <ChatStream
            :timeline="run.timeline.value"
            :draft="run.draft.value"
            :status="run.status.value"
            :turn="run.turn.value"
            :asking="run.asking.value"
            :agents="agents"
            :filter="filter"
            :open-decision-key="run.openDecision.value?.key || null"
            :answered="run.answered"
            :models="localModels"
            :view="view"
            :active-run-id="run.activeRunId.value"
            :totals="run.totals"
            :project-id="activeProjectId"
            @clear-filter="filter = null"
            @answered="answered"
            @open-file="openFile"
          />
          <Composer
            :status="run.status.value"
            :last-run="lastFinishedRun"
            :agents="agents"
            :disabled="!hasSession || !activeProjectId"
            :cloud-notice="cloudNotice"
            @start="startTask"
            @note="sendNote"
            @ask="askAgent"
          />
        </main>

        <TerminalDock :open="terminalOpen" :project-id="activeProjectId" :commands="run.commands.value" :show-agent="showAgentTick" @close="terminalOpen = false" />

        <StatsBar
          :run-id="meterRunId"
          :totals="meterRunId ? run.totals(meterRunId) : undefined"
          :last-speed="run.lastSpeed.value"
          :is-local="isLocal"
          :budget="settings.run?.budget_usd || null"
          :token-cap="settings.run?.token_cap || null"
          :connected="isConnected"
        />
      </div>
    </div>

    <!-- Panels -->
    <CrewBuilder :open="panel === 'crew'" :settings="settings" :local-models="localModels" :cloud-models="cloudModels" :locked="live" @close="panel = null" @saved="loadSettings" @mode-changed="modeChanged" />
    <ModelsPanel :open="panel === 'models'" :pulls="run.pulls" :providers="providers" @close="panel = null" @changed="loadSettings" />
    <WorkspacePanel :open="panel === 'workspace'" :project-id="activeProjectId" :runs="run.runs.value" :active-run-id="run.activeRunId.value" :live="live" :show-path="showPath" @close="panel = null" />
    <ProjectsPanel :open="panel === 'projects'" :projects="projects" :active-project-id="activeProjectId" @close="panel = null" @create-project="createProject($event, true)" @select-project="selectProject($event, true)" @delete-project="deleteProject" />
    <SettingsPanel :open="panel === 'settings'" :settings="settings" :providers="providers" :local-models="localModels" @close="panel = null" @saved="loadSettings" @data-deleted="startOver" />

    <!-- Plan, command and tool approvals also come up as a modal; closing it leaves the card in the run -->
    <dialog ref="decisionDialog" class="modal" aria-label="The run is waiting for you" @close="dismissed = modalDecision?.key || dismissed">
      <div v-if="modalDecision" class="p-1">
        <DecisionCard :message="modalDecision" open :models="localModels" @answered="answered(modalDecision.key, $event)" />
        <div class="flex justify-end px-3 pb-3">
          <button type="button" class="btn btn-secondary" @click="decisionDialog.close()">Answer later</button>
        </div>
      </div>
    </dialog>

    <!-- Toasts -->
    <div class="pointer-events-none fixed bottom-14 right-3 z-50 flex w-[min(24rem,calc(100vw-1.5rem))] flex-col gap-2" aria-live="polite">
      <div v-for="t in toasts" :key="t.id" class="pointer-events-auto flex items-start gap-2 rounded-xl border p-3 text-sm shadow-lg" :class="t.tone === 'error' ? 'border-red-500/30 bg-[#2a1215] text-red-100' : t.tone === 'warning' ? 'border-amber-400/30 bg-[#2a2010] text-amber-100' : 'border-juli-border bg-juli-panel text-slate-100'" :role="t.tone === 'error' ? 'alert' : 'status'">
        <Icon :name="t.tone === 'info' ? 'info' : 'alert'" class="mt-0.5 h-4 w-4 shrink-0" />
        <div class="min-w-0 flex-1">
          <p style="overflow-wrap: anywhere">{{ t.text }}</p>
          <button v-if="t.action" type="button" class="btn btn-secondary mt-2 !min-h-0 !py-1 text-xs" @click="t.action.run(); dropToast(t.id)">{{ t.action.label }}</button>
        </div>
        <button type="button" class="icon-btn !h-7 !w-7" aria-label="Dismiss" @click="dropToast(t.id)"><Icon name="x" class="h-3.5 w-3.5" /></button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useWebSocket } from './composables/useWebSocket.js'
import { useRun } from './composables/useRun.js'
import { apiFetch, getToken } from './api.js'
import { agentLabel, splitRef } from './labels.js'
import ParticleBackground from './components/ParticleBackground.vue'
import Icon from './components/Icon.vue'
import TopBar from './components/TopBar.vue'
import Sidebar from './components/Sidebar.vue'
import ChatStream from './components/ChatStream.vue'
import Composer from './components/Composer.vue'
import DecisionCard from './components/DecisionCard.vue'
import StatsBar from './components/StatsBar.vue'
import TerminalDock from './components/TerminalDock.vue'
import CrewBuilder from './components/CrewBuilder.vue'
import ModelsPanel from './components/ModelsPanel.vue'
import WorkspacePanel from './components/WorkspacePanel.vue'
import ProjectsPanel from './components/ProjectsPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'

const hasSession = Boolean(getToken())

// ─── Toasts ─────────────────────────────────────────────
const toasts = ref([])
let toastId = 0
function toast(text, tone = 'info', action = null, ms = 7000) {
  const id = ++toastId
  toasts.value = [...toasts.value.slice(-3), { id, text, tone, action }]
  if (ms) setTimeout(() => dropToast(id), action ? ms * 2 : ms)
}
const dropToast = id => { toasts.value = toasts.value.filter(t => t.id !== id) }
const toastError = e => toast(e.message || 'The request failed', 'error')
const allowanceBlocked = e => e.status === 409 && String(e.message || '').startsWith('Monthly allowance')

// ─── Live run ───────────────────────────────────────────
const run = useRun({
  onWarning: m => toast(m.content, 'warning'),
  onEnded: () => {
    stopping.value = false
    if (activeProjectId.value) run.refreshRuns(activeProjectId.value).catch(() => {})
  },
})
const { isConnected, status: wsStatus } = useWebSocket(m => {
  run.ingest(m)
  if (m.message_type === 'command_start' && terminalOpen.value) showAgentTick.value++
})
const sessionMissing = computed(() => !hasSession || wsStatus.value === 'unauthorized')
const live = computed(() => run.status.value === 'running' || run.status.value === 'paused')

// ─── Settings, providers, local models ──────────────────
const settings = ref({ agents: {}, available_models: [], run: {}, mode: 'custom' })
const providers = ref([])
const installed = ref([])
const agents = computed(() => settings.value.agents || {})

// After "delete all data". In full: load the dashboard afresh (the session token
// stays in sessionStorage). In part: the Settings panel stays open with what's
// left to fix, and the projects and live view refresh in place.
async function startOver({ reload = true } = {}) {
  if (reload) {
    window.location.reload()
    return
  }
  activeProjectId.value = null
  resumable.value = []
  filter.value = null
  run.activeRunId.value = null
  run.reset()
  await loadSettings()
  try {
    await fetchProjects()
    if (projects.value.length) await selectProject(projects.value[0].id)
    else await createProject('My first project')
  } catch (e) {
    toastError(e)
  }
}

async function loadSettings() {
  try {
    const [s, p] = await Promise.all([apiFetch('/api/settings'), apiFetch('/api/providers')])
    settings.value = s
    providers.value = p
  } catch (e) {
    toastError(e)
  }
  try {
    installed.value = (await apiFetch('/api/local/models')).installed.map(m => m.name)
  } catch { /* Ollama may be off */ }
}

function isLocal(ref) {
  const provider = providers.value.find(p => p.id === splitRef(ref).provider)
  return Boolean(provider?.local)
}
const cloudModels = computed(() => (settings.value.available_models || []).filter(m => !isLocal(m)))
const localModels = computed(() => [...new Set([...installed.value.map(n => `ollama:${n}`), ...(settings.value.available_models || []).filter(isLocal)])])

// Third-party transfer notice whenever any agent uses a cloud model.
const cloudNotice = computed(() => {
  if (settings.value.run?.privacy_mode || !providers.value.length) return ''
  const cloud = Object.entries(agents.value).filter(([, cfg]) => cfg.model && !isLocal(cfg.model))
  if (!cloud.length) return ''
  const names = cloud.map(([name]) => agentLabel(name, agents.value)).join(', ')
  const to = [...new Set(cloud.map(([, cfg]) => splitRef(cfg.model).provider))].join(', ')
  return `Prompts and code for ${names} go to ${to}, third-party providers with their own terms. Privacy mode keeps everything on this machine.`
})

function modeChanged(result) {
  if (result.notice) toast(result.notice, 'info')
  for (const w of result.warnings || []) toast(w, 'warning')
  loadSettings()
}

// ─── Projects ───────────────────────────────────────────
const projects = ref([])
const activeProjectId = ref(null)
const activeProjectName = computed(() => projects.value.find(p => p.id === activeProjectId.value)?.name || '')
const resumable = ref([])

async function fetchProjects() {
  projects.value = await apiFetch('/api/projects')
}

async function selectProject(id, fromPanel = false) {
  try {
    await apiFetch(`/api/projects/${id}/activate`, { method: 'PUT' })
    await run.loadProject(id)
    activeProjectId.value = id
    filter.value = null
    resumable.value = await apiFetch(`/api/runs/resumable?project_id=${encodeURIComponent(id)}`)
    if (fromPanel) panel.value = null
  } catch (e) {
    toastError(e)
  }
}

// fromPanel: the Projects panel asked, so it closes; a project made on load leaves any open panel alone.
async function createProject(name, fromPanel = false) {
  try {
    const project = await apiFetch('/api/projects', { method: 'POST', body: { name } })
    projects.value.unshift(project)
    await selectProject(project.id, fromPanel)
  } catch (e) {
    toastError(e)
  }
}

async function deleteProject(id) {
  try {
    await apiFetch(`/api/projects/${id}`, { method: 'DELETE' })
    projects.value = projects.value.filter(p => p.id !== id)
    if (activeProjectId.value === id) {
      activeProjectId.value = null
      run.reset()
      if (projects.value.length) await selectProject(projects.value[0].id)
      else await createProject('My first project')
    }
  } catch (e) {
    toastError(e)
  }
}

// ─── Tasks ──────────────────────────────────────────────
const stopping = ref(false)

async function startTask({ prompt, mode, approve_plan }, done, ignoreAllowance = false) {
  try {
    const res = await apiFetch('/api/task', {
      method: 'POST',
      body: { prompt, mode, approve_plan, project_id: activeProjectId.value, ignore_allowance: ignoreAllowance },
    })
    run.started(res.run_id, prompt, mode)
    filter.value = null
    done?.resolve()
  } catch (e) {
    if (allowanceBlocked(e) && !ignoreAllowance) {
      toast(e.message, 'warning', { label: 'Start anyway', run: () => startTask({ prompt, mode, approve_plan }, null, true) })
    } else {
      toastError(e)
    }
    done?.reject(e)
  }
}

async function sendNote(content, done) {
  try {
    await apiFetch('/api/task/message', { method: 'POST', body: { content } })
    done.resolve()
  } catch (e) {
    toastError(e)
    done.reject(e)
  }
}

async function askAgent({ agent, question }, done) {
  try {
    await run.ask(lastFinishedRun.value.id, agent, question)
    done.resolve()
  } catch (e) {
    toastError(e)
    done.reject(e)
  }
}

async function stopRun() {
  stopping.value = true
  try {
    await apiFetch('/api/task/stop', { method: 'POST' })
  } catch (e) {
    stopping.value = false
    toastError(e)
  }
}

async function resume(r, ignoreAllowance = false) {
  try {
    await apiFetch(`/api/runs/${r.id}/resume`, { method: 'POST', body: { ignore_allowance: ignoreAllowance } })
    resumable.value = resumable.value.filter(x => x.id !== r.id)
    run.started(r.id, r.prompt, r.mode)
  } catch (e) {
    if (allowanceBlocked(e) && !ignoreAllowance) {
      toast(e.message, 'warning', { label: 'Resume anyway', run: () => resume(r, true) })
    } else {
      toastError(e)
    }
  }
}

const lastFinishedRun = computed(() => {
  const rows = run.runs.value.filter(r => r.id !== run.activeRunId.value || !live.value)
  return [...rows].reverse().find(r => ['complete', 'stopped', 'error'].includes(r.status)) || null
})
const meterRunId = computed(() => {
  const rows = run.runs.value
  if (rows.some(r => r.id === run.activeRunId.value)) return run.activeRunId.value
  return rows.length ? rows[rows.length - 1].id : null
})

// ─── Decisions ──────────────────────────────────────────
const decisionDialog = ref(null)
const dismissed = ref(null)
const keyProblem = computed(() => (run.openDecision.value?.data?.kind === 'key_problem' ? run.openDecision.value : null))
const modalDecision = computed(() => {
  const d = run.openDecision.value
  return d && d.key !== dismissed.value && ['plan_approval', 'command_approval', 'tool_approval'].includes(d.data?.kind) ? d : null
})

watch(modalDecision, async d => {
  await nextTick()
  const el = decisionDialog.value
  if (!el) return
  if (d && !el.open) el.showModal()
  if (!d && el.open) el.close()
})

const PROBLEMS = { out_of_credit: 'is out of credit', invalid: 'has an invalid key', missing: 'has no key' }
const keyProblemText = computed(() => {
  const d = keyProblem.value?.data || {}
  const provider = splitRef(d.model).provider || 'The provider'
  return `${provider} ${PROBLEMS[d.problem] || 'refused the request'}: ${agentLabel(d.agent, agents.value)} paused on ${d.model}. Switch to another model to resume, or stop.`
})

function focusDecision(key) {
  const card = document.querySelector(`[data-decision="${CSS.escape(key)}"]`)
  card?.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  card?.querySelector('input, button')?.focus({ preventScroll: true })
}

function answered(key, action) {
  run.answered[key] = action
}

// ─── Layout ─────────────────────────────────────────────
const panel = ref(null)
const sidebarOpen = ref(false)
const terminalOpen = ref(false)
const showAgentTick = ref(0)
const filter = ref(null)
const showPath = ref('')

// Run view: the whole crew, or "Juli only" (one reply per run). Remembered in this browser.
const VIEW_KEY = 'juli-view'
function savedView() {
  try {
    return localStorage.getItem(VIEW_KEY) === 'juli' ? 'juli' : 'crew'
  } catch {
    return 'crew'
  }
}
const view = ref(savedView())
watch(view, v => {
  try {
    localStorage.setItem(VIEW_KEY, v)
  } catch { /* storage blocked: the choice lasts this visit */ }
})

function openPanel(id) {
  sidebarOpen.value = false
  if (id === 'terminal') {
    terminalOpen.value = !terminalOpen.value
    return
  }
  panel.value = id
}

function openFile(path) {
  showPath.value = path
  panel.value = 'workspace'
}

onMounted(async () => {
  if (!hasSession) return
  await loadSettings()
  try {
    const [status] = await Promise.all([apiFetch('/api/status'), fetchProjects()])
    // A run going on in a project: show that one.
    const busy = ['running', 'paused'].includes(status.status) && projects.value.some(p => p.id === status.project_id)
    if (busy) {
      run.activeRunId.value = status.run_id
      run.status.value = status.status
      await selectProject(status.project_id)
    } else if (projects.value.length) {
      await selectProject(projects.value[0].id)
    } else {
      await createProject('My first project')
    }
  } catch (e) {
    toastError(e)
  }
})
</script>
