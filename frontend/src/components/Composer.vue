<template>
  <div class="border-t border-juli-border bg-juli-panel/80 px-3 pb-3 pt-2 sm:px-6">
    <form class="mx-auto w-full max-w-3xl" @submit.prevent="submit">
      <!-- What the box does -->
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <template v-if="live">
          <span class="text-xs text-slate-400">The crew is {{ status === 'paused' ? 'waiting' : 'working' }}. Notes reach every later turn and take priority.</span>
        </template>
        <div v-else-if="lastRun" role="radiogroup" aria-label="What to send" class="inline-flex rounded-lg border border-juli-border p-0.5">
          <button v-for="opt in kinds" :key="opt.id" type="button" role="radio" :aria-checked="kind === opt.id" class="rounded-md px-2.5 py-1 text-xs font-medium" :class="kind === opt.id ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-slate-200'" @click="kind = opt.id">{{ opt.label }}</button>
        </div>

        <template v-if="!live && kind === 'task'">
          <label class="sr-only" for="run-mode">Run mode</label>
          <select id="run-mode" v-model="mode" class="field !w-auto !py-1 text-xs" :title="currentMode.hint">
            <option v-for="m in RUN_MODES" :key="m.id" :value="m.id">{{ m.label }}</option>
          </select>
          <label class="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-300">
            <input v-model="approvePlan" type="checkbox" class="h-4 w-4 rounded accent-cyan-500" :disabled="mode === 'review'" />
            Approve the plan first
          </label>
        </template>
        <template v-else-if="!live && kind === 'ask'">
          <label class="text-xs text-slate-400" for="ask-agent">Ask</label>
          <select id="ask-agent" v-model="askAgent" class="field !w-auto !py-1 text-xs">
            <option v-for="name in agentNames" :key="name" :value="name">{{ agentLabel(name, agents) }}</option>
          </select>
          <span class="text-xs text-slate-400">about run {{ lastRun.id }}</span>
        </template>
      </div>

      <div class="flex items-end gap-2">
        <label class="sr-only" for="composer-text">{{ placeholder }}</label>
        <textarea
          id="composer-text"
          ref="box"
          v-model="text"
          rows="1"
          :maxlength="live || kind === 'ask' ? 4000 : 20000"
          :placeholder="placeholder"
          :disabled="disabled"
          class="field max-h-48 min-h-[44px] flex-1 resize-none leading-relaxed"
          @input="grow"
          @keydown.enter.exact="onEnter"
        ></textarea>
        <button type="submit" class="btn btn-primary h-11 w-11 !px-0" :disabled="disabled || busy || !text.trim()" :aria-label="sendLabel">
          <Icon name="send" class="h-5 w-5" />
        </button>
      </div>
      <p class="mt-1.5 hidden text-xs text-slate-500 sm:block">Enter sends, Shift+Enter adds a line.</p>
      <p v-if="cloudNotice" class="mt-1.5 flex items-start gap-1.5 text-xs leading-relaxed text-amber-200/90">
        <Icon name="cloud" class="mt-px h-3.5 w-3.5 shrink-0" />{{ cloudNotice }}
      </p>
    </form>
  </div>
</template>

<script setup>
// The box at the bottom: a new task, a note to the running crew, or a
// follow-up question to one agent about the finished run.
import { ref, computed, watch, nextTick } from 'vue'
import Icon from './Icon.vue'
import { agentLabel, RUN_MODES } from '../labels.js'

const props = defineProps({
  status: { type: String, default: 'idle' },
  lastRun: { type: Object, default: null }, // the latest finished run, for follow-ups
  agents: { type: Object, default: () => ({}) },
  disabled: { type: Boolean, default: false },
  cloudNotice: { type: String, default: '' },
})
const emit = defineEmits(['start', 'note', 'ask'])

const kinds = [{ id: 'task', label: 'New task' }, { id: 'ask', label: 'Ask about the last run' }]
const kind = ref('task')
const mode = ref('full')
const approvePlan = ref(false)
const askAgent = ref('')
const text = ref('')
const busy = ref(false)
const failedPrompt = ref('') // a task that didn't start (e.g. an allowance block), kept in the box
const box = ref(null)

const live = computed(() => props.status === 'running' || props.status === 'paused')
const agentNames = computed(() => Object.keys(props.agents))
const currentMode = computed(() => RUN_MODES.find(m => m.id === mode.value) || RUN_MODES[0])

watch(agentNames, names => { if (!names.includes(askAgent.value)) askAgent.value = names[0] || '' }, { immediate: true })
watch(() => props.lastRun, run => { if (!run) kind.value = 'task' })
// That task may start later ("Start anyway"): then the box is for notes, so drop its text.
watch(live, isLive => {
  if (isLive && failedPrompt.value && text.value.trim() === failedPrompt.value) {
    text.value = ''
    nextTick(grow)
  }
  failedPrompt.value = ''
})

const placeholder = computed(() => {
  if (live.value) return 'Tell the crew something…'
  if (kind.value === 'ask') return `Ask ${agentLabel(askAgent.value, props.agents)} about the run…`
  return mode.value === 'review' ? 'What should the reviewer focus on…' : 'Describe what to build…'
})
const sendLabel = computed(() => (live.value ? 'Send note' : kind.value === 'ask' ? 'Ask question' : 'Start task'))

function grow() {
  const el = box.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 192)}px`
}

// Enter sends, except while an input method (IME) is composing text.
function onEnter(event) {
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  submit()
}

async function submit() {
  const value = text.value.trim()
  if (!value || busy.value || props.disabled) return
  busy.value = true
  failedPrompt.value = ''
  try {
    if (live.value) await emitAndWait('note', value)
    else if (kind.value === 'ask') await emitAndWait('ask', { agent: askAgent.value, question: value })
    else await emitAndWait('start', { prompt: value, mode: mode.value, approve_plan: approvePlan.value && mode.value !== 'review' })
    text.value = ''
    nextTick(grow)
  } catch {
    // The parent showed the error; keep the text so nothing is lost.
    if (!live.value && kind.value === 'task') failedPrompt.value = value
  } finally {
    busy.value = false
  }
}

// The parent's handler gets a `done` callback pair, so the box keeps the text on failure.
function emitAndWait(event, payload) {
  return new Promise((resolve, reject) => emit(event, payload, { resolve, reject }))
}
</script>
