<template>
  <div>
    <div role="group" aria-label="Where models run" class="inline-flex rounded-lg border border-juli-border p-0.5">
      <button
        v-for="m in MODES"
        :key="m.id"
        type="button"
        class="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors sm:px-2.5"
        :class="mode === m.id ? m.active : 'text-slate-400 hover:text-slate-200'"
        :aria-pressed="mode === m.id"
        :aria-label="`${m.label} mode`"
        :title="m.hint"
        :disabled="busy || locked"
        @click="choose(m.id)"
      >
        <Icon :name="m.icon" class="h-4 w-4" />
        <span :class="compact ? 'hidden lg:inline' : ''">{{ m.label }}</span>
      </button>
    </div>
    <p v-if="mode === 'custom' && !compact" class="hint mt-1.5">The crew is a custom mix of local and cloud models.</p>

    <dialog ref="dialog" class="modal" aria-labelledby="mode-title" @cancel.prevent="close" @close="pending = null">
      <form v-if="pending" class="space-y-4 p-5" @submit.prevent="apply">
        <h2 id="mode-title" class="text-base font-semibold text-white">Switch to {{ label(pending) }} mode?</h2>
        <p class="flex items-start gap-2 rounded-lg border border-amber-400/30 bg-amber-400/[0.07] p-3 text-sm leading-relaxed text-amber-100">
          <Icon name="cloud" class="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
          <span>
            In {{ label(pending) }} mode, your prompts and code for
            {{ pending === 'hybrid' ? 'the planner and reviewer' : 'every agent' }}
            are sent to third-party AI providers, under their terms. Privacy mode keeps everything on this machine.
          </span>
        </p>
        <div>
          <label for="cloud-model" class="label">Cloud model for the agents that move to the cloud</label>
          <select id="cloud-model" v-model="cloudModel" class="field">
            <option value="">Keep each agent's current cloud model</option>
            <option v-for="m in cloudModels" :key="m" :value="m">{{ m }}</option>
          </select>
          <p class="hint mt-1">Agents that run locally now need a cloud model. You can change each one later in the crew.</p>
        </div>
        <p v-if="error" role="alert" class="text-sm text-red-300">{{ error }}</p>
        <div class="flex justify-end gap-2">
          <button type="button" class="btn btn-secondary" @click="close">Cancel</button>
          <button type="submit" class="btn btn-primary" :disabled="busy">Switch to {{ label(pending) }}</button>
        </div>
      </form>
    </dialog>
  </div>
</template>

<script setup>
// Privacy (everything local, enforced in the code that calls models), Hybrid
// (plan and review in the cloud) or Cloud. Leaving Privacy asks first and says
// that prompts and code go to third parties.
import { ref, nextTick } from 'vue'
import Icon from './Icon.vue'
import { apiFetch } from '../api.js'

const props = defineProps({
  mode: { type: String, default: 'custom' },
  cloudModels: { type: Array, default: () => [] },
  compact: { type: Boolean, default: false },
  locked: { type: Boolean, default: false }, // e.g. while a run is going
})
const emit = defineEmits(['changed', 'error'])

const MODES = [
  { id: 'privacy', label: 'Privacy', icon: 'lock', hint: 'Every agent runs on this machine', active: 'bg-emerald-500/15 text-emerald-300' },
  { id: 'hybrid', label: 'Hybrid', icon: 'arrows', hint: 'Plan and review in the cloud, the rest local', active: 'bg-amber-500/15 text-amber-200' },
  { id: 'cloud', label: 'Cloud', icon: 'cloud', hint: 'Every agent uses a cloud model', active: 'bg-sky-500/15 text-sky-200' },
]
const label = id => MODES.find(m => m.id === id)?.label || id

const dialog = ref(null)
const pending = ref(null)
const cloudModel = ref('')
const busy = ref(false)
const error = ref('')

async function choose(id) {
  if (id === props.mode) return
  if (id === 'privacy') {
    await send('privacy', null)
    return
  }
  pending.value = id
  cloudModel.value = props.cloudModels[0] || ''
  error.value = ''
  await nextTick()
  dialog.value.showModal()
}

async function apply() {
  if (await send(pending.value, cloudModel.value || null)) close()
}

async function send(mode, model) {
  busy.value = true
  error.value = ''
  try {
    const result = await apiFetch('/api/settings/mode', { method: 'PUT', body: { mode, cloud_model: model } })
    emit('changed', result)
    return true
  } catch (e) {
    if (pending.value) error.value = e.message
    else emit('error', e)
    return false
  } finally {
    busy.value = false
  }
}

function close() {
  dialog.value?.close()
}
</script>
