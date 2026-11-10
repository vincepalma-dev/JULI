<template>
  <section :data-decision="message.key" class="rounded-xl border p-4" :class="open ? 'border-amber-400/40 bg-amber-400/[0.06]' : 'border-juli-border bg-white/[0.02]'" :aria-label="heading">
    <div class="flex items-start gap-3">
      <Icon :name="kind === 'command_approval' ? 'terminal' : kind === 'key_problem' ? 'key' : 'check'" class="mt-0.5 h-5 w-5 shrink-0" :class="open ? 'text-amber-300' : 'text-slate-500'" />
      <div class="min-w-0 flex-1 space-y-3">
        <div>
          <h3 class="text-sm font-semibold text-white">{{ heading }}</h3>
          <p class="prose-msg mt-1 text-slate-300">{{ intro }}</p>
        </div>

        <!-- The exact command, never shortened -->
        <template v-if="kind === 'command_approval'">
          <pre class="overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-juli-border bg-black/40 px-3 py-2 font-mono text-sm text-slate-100">{{ data.command }}</pre>
          <p class="flex flex-wrap items-center gap-2 text-xs">
            <span class="badge" :class="data.sandbox ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-200'">
              <Icon :name="data.sandbox ? 'shield' : 'alert'" class="h-3.5 w-3.5" />
              {{ data.sandbox ? 'Docker sandbox, no network' : 'On this machine, no sandbox' }}
            </span>
            <span class="text-slate-400">Asks because {{ data.reason }}.</span>
          </p>
        </template>

        <p v-if="!open" class="text-xs text-slate-400">{{ outcome }}</p>

        <template v-else>
          <!-- Plan approval -->
          <div v-if="kind === 'plan_approval'" class="space-y-3">
            <div v-if="revising">
              <label :for="`revise-${uid}`" class="label">What should the planner change?</label>
              <textarea :id="`revise-${uid}`" v-model="revision" rows="3" maxlength="4000" class="field resize-y" placeholder="Use SQLite instead of Postgres, and add a CLI…" @keydown.ctrl.enter="answer('revise')" @keydown.meta.enter="answer('revise')"></textarea>
            </div>
            <div class="flex flex-wrap gap-2">
              <template v-if="!revising">
                <button type="button" class="btn btn-primary" :disabled="busy" @click="answer('approve')"><Icon name="check" class="h-4 w-4" />Approve plan</button>
                <button type="button" class="btn btn-secondary" :disabled="busy" @click="revising = true"><Icon name="pencil" class="h-4 w-4" />Ask for changes…</button>
              </template>
              <template v-else>
                <button type="button" class="btn btn-primary" :disabled="busy || !revision.trim()" @click="answer('revise')"><Icon name="send" class="h-4 w-4" />Send to planner</button>
                <button type="button" class="btn btn-secondary" :disabled="busy" @click="revising = false">Back</button>
              </template>
              <button type="button" class="btn btn-danger" :disabled="busy" @click="answer('stop')"><Icon name="stop" class="h-4 w-4" />Stop run</button>
            </div>
          </div>

          <!-- Agent command -->
          <div v-else-if="kind === 'command_approval'" class="flex flex-wrap gap-2">
            <button type="button" class="btn btn-primary" :disabled="busy" @click="answer('approve')"><Icon name="play" class="h-4 w-4" />Run command</button>
            <button type="button" class="btn btn-danger" :disabled="busy" @click="answer('deny')"><Icon name="x" class="h-4 w-4" />Deny</button>
          </div>

          <!-- Key problem: switch model and resume, or stop -->
          <div v-else-if="kind === 'key_problem'" class="space-y-3">
            <div>
              <label :for="`model-${uid}`" class="label">Switch {{ data.agent }} to</label>
              <input :id="`model-${uid}`" v-model="model" :list="`models-${uid}`" class="field font-mono" placeholder="ollama:qwen3:8b" spellcheck="false" autocomplete="off" />
              <datalist :id="`models-${uid}`">
                <option v-for="m in models" :key="m" :value="m" />
              </datalist>
            </div>
            <div class="flex flex-wrap gap-2">
              <button type="button" class="btn btn-primary" :disabled="busy || !model.trim()" @click="answer('switch')"><Icon name="refresh" class="h-4 w-4" />Switch and resume</button>
              <button type="button" class="btn btn-danger" :disabled="busy" @click="answer('stop')"><Icon name="stop" class="h-4 w-4" />Stop run</button>
            </div>
          </div>

          <p v-if="error" role="alert" class="text-sm text-red-300">{{ error }}</p>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup>
// A paused run's question, answerable inline: approve/revise/stop a plan,
// approve/deny an agent command, or switch model/stop on a key problem.
import { ref, computed } from 'vue'
import Icon from './Icon.vue'
import { apiFetch } from '../api.js'

const props = defineProps({
  message: { type: Object, required: true },
  open: { type: Boolean, default: false }, // still waiting for an answer
  answeredWith: { type: String, default: '' }, // what this browser answered, if anything
  models: { type: Array, default: () => [] }, // suggestions for "switch"
})
const emit = defineEmits(['answered'])

const uid = Math.random().toString(36).slice(2, 8)
const data = computed(() => props.message.data || {})
const kind = computed(() => data.value.kind || 'plan_approval')
const revising = ref(false)
const revision = ref('') // what to change in the plan
const model = ref('')
const busy = ref(false)
const error = ref('')

const heading = computed(() => ({
  plan_approval: 'Approve the plan?',
  command_approval: `${data.value.agent || 'An agent'} wants to run a command`,
  key_problem: `${data.value.agent || 'An agent'} can't continue`,
}[kind.value] || 'The run is waiting for you'))

// The first line of the server's text; the command itself is shown separately.
const intro = computed(() => {
  const text = props.message.content || ''
  return kind.value === 'command_approval' ? text.split('\n\n')[0] : text
})

const LABELS = { approve: 'Approved', revise: 'Changes sent to the planner', deny: 'Denied', switch: 'Switched model and resumed', stop: 'Stopped' }
const outcome = computed(() => (props.answeredWith ? LABELS[props.answeredWith] || 'Answered' : 'No longer waiting for an answer'))

async function answer(action) {
  busy.value = true
  error.value = ''
  const body = { action }
  if (action === 'revise') body.message = revision.value.trim()
  if (action === 'switch') body.model = model.value.trim()
  try {
    await apiFetch('/api/task/decision', { method: 'POST', body })
    emit('answered', action)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>
