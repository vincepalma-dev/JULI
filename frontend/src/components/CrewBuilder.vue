<template>
  <SidePanel :open="open" title="Crew" icon="users" wide @close="$emit('close')">
    <!-- Where the models run -->
    <section class="mb-6">
      <h3 class="mb-2 text-sm font-semibold text-white">Where models run</h3>
      <ModeSwitch :mode="settings.mode || 'custom'" :cloud-models="cloudModels" :locked="locked" @changed="$emit('mode-changed', $event)" @error="error = $event.message" />
    </section>

    <!-- Auto-Crew -->
    <section class="surface mb-6 p-4">
      <div class="flex flex-wrap items-center gap-3">
        <div class="min-w-0 flex-1">
          <h3 class="text-sm font-semibold text-white">Auto-Crew</h3>
          <p class="hint">Picks the strongest local model for each agent that fits this machine, measured against its memory.</p>
        </div>
        <button type="button" class="btn btn-secondary" :disabled="suggesting" @click="suggest"><Icon name="sparkle" class="h-4 w-4" />{{ suggesting ? 'Checking this machine…' : 'Suggest models' }}</button>
      </div>

      <div v-if="picks" class="mt-4 space-y-3">
        <ul class="divide-y divide-juli-border rounded-lg border border-juli-border">
          <li v-for="(pick, name) in picks.agents" :key="name" class="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
            <label class="flex min-w-0 flex-1 cursor-pointer items-center gap-2">
              <input v-model="chosen" type="checkbox" :value="name" class="h-4 w-4 accent-cyan-500" :disabled="!pick" />
              <span class="text-slate-100">{{ agentLabel(name, settings.agents) }}</span>
            </label>
            <template v-if="pick">
              <code class="font-mono text-xs text-slate-200">{{ pick.model }}</code>
              <span class="badge" :class="pick.tier === 'great' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-200'">{{ pick.tier === 'great' ? 'Runs well' : 'Runs slowly' }}</span>
              <span class="text-xs text-slate-400">{{ pick.installed ? 'Installed' : `${pick.size_gb} GB download` }}</span>
            </template>
            <span v-else class="text-xs text-red-300">Nothing fits this machine</span>
          </li>
        </ul>
        <p v-if="picks.shared" class="hint">The best picks don't all fit on disk, so every agent shares one model.</p>
        <p v-if="picks.downloads.length" class="hint">Downloads needed: {{ picks.downloads.join(', ') }} ({{ picks.download_gb }} GB). Get them in Models.</p>
        <p v-for="lic in picks.licenses || []" :key="lic.id" class="hint">{{ lic.name }} must be accepted before download.</p>
        <label class="flex cursor-pointer items-center gap-2 text-sm text-slate-200">
          <input v-model="setFallback" type="checkbox" class="h-4 w-4 accent-cyan-500" />
          Also use {{ picks.fallback_model || 'the best general model' }} as the local fallback
        </label>
        <div class="flex gap-2">
          <button type="button" class="btn btn-primary" :disabled="!chosen.length || applying" @click="applyPicks">Use for {{ chosen.length }} agent{{ chosen.length === 1 ? '' : 's' }}</button>
          <button type="button" class="btn btn-secondary" @click="picks = null">Dismiss</button>
        </div>
      </div>
    </section>

    <p v-if="error" role="alert" class="mb-4 text-sm text-red-300">{{ error }}</p>

    <!-- Agents -->
    <section class="space-y-3">
      <h3 class="text-sm font-semibold text-white">Agents</h3>
      <article v-for="(cfg, name) in settings.agents" :key="name" class="surface p-4">
        <div class="mb-3 flex items-center gap-3">
          <AgentOrb :icon="cfg.icon || 'system'" :color="cfg.color || '#94a3b8'" size="sm" />
          <div class="min-w-0 flex-1">
            <p class="text-sm font-semibold text-white">{{ agentLabel(name, settings.agents) }}</p>
            <p class="font-mono text-xs text-slate-400">{{ name }}</p>
          </div>
          <span v-if="status[name]" class="text-xs" :class="status[name].ok ? 'text-emerald-300' : 'text-red-300'" role="status">{{ status[name].text }}</span>
          <template v-if="removing === name">
            <button type="button" class="btn btn-danger !min-h-0 !py-1 text-xs" @click="remove(name)">Remove</button>
            <button type="button" class="btn btn-secondary !min-h-0 !py-1 text-xs" @click="removing = null">Keep</button>
          </template>
          <button v-else type="button" class="icon-btn hover:!text-red-300" :aria-label="`Remove ${name}`" @click="removing = name"><Icon name="trash" class="h-4 w-4" /></button>
        </div>

        <div class="grid gap-3 sm:grid-cols-[9rem_1fr_10rem]">
          <div>
            <label :for="`role-${name}`" class="label">Role</label>
            <select :id="`role-${name}`" :value="cfg.role || 'custom'" class="field" @change="save(name, { role: $event.target.value })">
              <option v-for="r in ROLES" :key="r" :value="r">{{ r }}</option>
            </select>
          </div>
          <div>
            <label :for="`model-${name}`" class="label">Model</label>
            <input :id="`model-${name}`" :value="shown(name, 'model')" list="crew-models" class="field font-mono" spellcheck="false" autocomplete="off" @input="type(name, 'model', $event)" @change="save(name, { model: $event.target.value.trim() })" />
          </div>
          <div>
            <label :for="`max-${name}`" class="label">Max output tokens</label>
            <input :id="`max-${name}`" :value="shown(name, 'max_tokens')" type="number" min="1" max="200000" inputmode="numeric" class="field" placeholder="Model default" @input="type(name, 'max_tokens', $event)" @change="save(name, { max_tokens: $event.target.value ? Number($event.target.value) : null })" />
          </div>
        </div>

        <details class="mt-3">
          <summary class="cursor-pointer text-xs font-medium text-slate-400 hover:text-slate-200">Title, colour and prompt</summary>
          <div class="mt-3 space-y-3">
            <div>
              <label :for="`title-${name}`" class="label">Job title</label>
              <input :id="`title-${name}`" :value="shown(name, 'job_title')" maxlength="80" class="field" placeholder="e.g. Lead DB Admin" @input="type(name, 'job_title', $event)" @change="save(name, { job_title: $event.target.value.trim() })" />
            </div>
            <fieldset>
              <legend class="label">Colour</legend>
              <div class="flex flex-wrap gap-1.5">
                <button v-for="c in COLORS" :key="c" type="button" class="h-7 w-7 rounded-full border-2" :style="{ backgroundColor: c, borderColor: cfg.color === c ? '#fff' : 'transparent' }" :aria-label="`Colour ${c}`" :aria-pressed="cfg.color === c" @click="save(name, { color: c })"></button>
              </div>
            </fieldset>
            <div>
              <label :for="`prompt-${name}`" class="label">System prompt</label>
              <textarea :id="`prompt-${name}`" :value="shown(name, 'prompt')" rows="5" maxlength="8000" class="field resize-y font-mono text-xs leading-relaxed" @input="type(name, 'prompt', $event)" @change="save(name, { prompt: $event.target.value })"></textarea>
            </div>
          </div>
        </details>
      </article>

      <datalist id="crew-models"><option v-for="m in allModels" :key="m" :value="m" /></datalist>

      <!-- New agent -->
      <form class="surface space-y-3 p-4" @submit.prevent="add">
        <h4 class="text-sm font-semibold text-white">Add an agent</h4>
        <div class="grid gap-3 sm:grid-cols-3">
          <div>
            <label for="new-name" class="label">Name</label>
            <input id="new-name" v-model="draft.name" class="field font-mono" pattern="[A-Za-z][A-Za-z0-9_]{0,39}" maxlength="40" placeholder="DatabaseArchitect" required spellcheck="false" autocomplete="off" />
          </div>
          <div>
            <label for="new-role" class="label">Role</label>
            <select id="new-role" v-model="draft.role" class="field"><option v-for="r in ROLES" :key="r" :value="r">{{ r }}</option></select>
          </div>
          <div>
            <label for="new-model" class="label">Model</label>
            <input id="new-model" v-model="draft.model" list="crew-models" class="field font-mono" spellcheck="false" autocomplete="off" />
          </div>
        </div>
        <p class="hint">Letters, digits and underscores, starting with a letter. Custom agents run after the code is approved, before testing.</p>
        <button type="submit" class="btn btn-primary" :disabled="!draft.name.trim()"><Icon name="plus" class="h-4 w-4" />Add agent</button>
      </form>
    </section>
  </SidePanel>
</template>

<script setup>
// The crew: each agent's role, model and optional output limit; Auto-Crew picks; the mode switch.
import { ref, reactive, computed, watch } from 'vue'
import AgentOrb from './AgentOrb.vue'
import Icon from './Icon.vue'
import ModeSwitch from './ModeSwitch.vue'
import SidePanel from './SidePanel.vue'
import { apiFetch } from '../api.js'
import { agentLabel, ROLES } from '../labels.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  settings: { type: Object, default: () => ({}) },
  localModels: { type: Array, default: () => [] },
  cloudModels: { type: Array, default: () => [] },
  locked: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved', 'mode-changed'])

const COLORS = ['#6366f1', '#06b6d4', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#f97316', '#3b82f6', '#14b8a6', '#84cc16', '#94a3b8']

const allModels = computed(() => [...new Set([...props.localModels, ...(props.settings.available_models || [])])])
const status = reactive({})
const error = ref('')
const removing = ref(null)

// Text typed into a field but not saved yet, by "<agent>.<field>". Each save
// reloads the settings, and that re-render must not undo typing elsewhere; a
// draft goes once the reloaded settings hold what was typed.
const typed = reactive({})
const saved = (name, field) => String(props.settings.agents?.[name]?.[field] ?? '')
const shown = (name, field) => typed[`${name}.${field}`] ?? saved(name, field)
const type = (name, field, event) => { typed[`${name}.${field}`] = event.target.value }
watch(() => props.settings, () => {
  for (const key of Object.keys(typed)) {
    const [name, field] = key.split('.')
    const value = saved(name, field)
    // Models and titles are saved trimmed; prompts as typed.
    if (value === typed[key] || value === typed[key].trim()) delete typed[key]
  }
})

async function save(name, patch) {
  status[name] = { ok: true, text: 'Saving…' }
  try {
    await apiFetch('/api/settings/agents', { method: 'PUT', body: { [name]: patch } })
    status[name] = { ok: true, text: 'Saved' }
    emit('saved')
  } catch (e) {
    status[name] = { ok: false, text: e.message }
  }
}

async function remove(name) {
  removing.value = null
  try {
    await apiFetch(`/api/settings/agents/${encodeURIComponent(name)}`, { method: 'DELETE' })
    emit('saved')
  } catch (e) {
    error.value = e.message
  }
}

const draft = reactive({ name: '', role: 'custom', model: 'ollama:qwen3:8b' })
async function add() {
  error.value = ''
  try {
    await apiFetch('/api/settings/agents', { method: 'POST', body: { name: draft.name.trim(), role: draft.role, model: draft.model.trim() } })
    draft.name = ''
    emit('saved')
  } catch (e) {
    error.value = e.message
  }
}

// ─── Auto-Crew ───
const picks = ref(null)
const chosen = ref([])
const setFallback = ref(true)
const suggesting = ref(false)
const applying = ref(false)

async function suggest() {
  suggesting.value = true
  error.value = ''
  try {
    picks.value = await apiFetch('/api/local/auto-crew', { method: 'POST', body: {} })
    chosen.value = Object.entries(picks.value.agents).filter(([, p]) => p).map(([n]) => n)
  } catch (e) {
    error.value = e.message
  } finally {
    suggesting.value = false
  }
}

async function applyPicks() {
  applying.value = true
  try {
    await apiFetch('/api/local/auto-crew', { method: 'POST', body: { agents: chosen.value, apply: true, set_fallback: setFallback.value } })
    picks.value = null
    emit('saved')
  } catch (e) {
    error.value = e.message
  } finally {
    applying.value = false
  }
}
</script>
