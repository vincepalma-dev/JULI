<template>
  <div class="relative flex min-h-0 flex-1 flex-col">
    <!-- Agent filter -->
    <div v-if="filter" class="flex items-center gap-2 border-b border-juli-border px-4 py-2 text-sm sm:px-6">
      <span class="text-slate-400">Showing only</span>
      <span class="font-medium" :style="{ color: colorOf(filter) }">{{ agentLabel(filter, agents) }}</span>
      <button type="button" class="btn btn-secondary ml-auto !min-h-0 !py-1 text-xs" @click="$emit('clear-filter')">
        <Icon name="x" class="h-3.5 w-3.5" />Show everyone
      </button>
    </div>

    <div ref="scroller" class="min-h-0 flex-1 overflow-y-auto" @scroll="onScroll">
      <div class="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
        <!-- Empty state -->
        <div v-if="!timeline.length && !draft" class="flex flex-col items-center py-16 text-center">
          <!-- Juli herself, or the agent the view is filtered to -->
          <JuliMascot state="idle" :size="112" v-bind="agentLook(agents[filter])" />
          <h2 class="mt-4 text-lg font-semibold text-white">Ready when you are</h2>
          <p class="mt-2 max-w-sm text-sm leading-relaxed text-slate-400">
            Describe what to build below. The crew plans it, writes the code, reviews and tests it, and the files land in this project's workspace.
          </p>
        </div>

        <section v-for="group in shown" :key="group.run ? group.run.id : 'earlier'" class="mb-10" :aria-label="group.run ? `Run ${group.run.id}` : 'Earlier messages'">
          <!-- The task, as the user's message -->
          <div v-if="group.run" class="mb-5 flex flex-col items-end">
            <div class="max-w-[85%] rounded-2xl rounded-br-md bg-white/[0.07] px-4 py-2.5">
              <p class="prose-msg text-slate-100">{{ group.run.prompt || '…' }}</p>
            </div>
            <p class="mt-1.5 flex flex-wrap items-center justify-end gap-x-2 gap-y-1 text-xs text-slate-500">
              <span>Run {{ group.run.id }}</span>
              <span v-if="group.run.mode">· {{ modeLabel(group.run.mode) }}</span>
              <span v-if="group.run.started_at">· {{ formatTime(group.run.started_at) }}</span>
              <span v-if="group.run.status && group.run.status !== 'running'" class="badge" :class="statusTone(group.run.status)">{{ group.run.status }}</span>
            </p>
          </div>
          <p v-else class="mb-4 text-center text-xs text-slate-500">Earlier messages</p>

          <!-- Whole crew: every entry in order -->
          <div v-if="!juliView" class="space-y-5">
            <TimelineItem v-for="m in group.items" :key="m.key" :m="m" v-bind="itemProps" :zip-project="m.key === group.filesKey ? projectId : null" @answered="relayAnswer" @open-file="p => $emit('open-file', p)" />
          </div>

          <!-- Juli only: the crew's work folded away, then one reply -->
          <div v-else class="space-y-5">
            <details v-if="group.work.length" class="group rounded-xl border border-juli-border bg-white/[0.02]">
              <summary class="flex cursor-pointer list-none flex-wrap items-center gap-2 px-4 py-2.5 text-sm text-slate-300">
                <Icon name="users" class="h-4 w-4 shrink-0 text-slate-400" />
                <span>Show the crew's work</span>
                <span class="text-slate-500">· {{ group.work.length }} step{{ group.work.length === 1 ? '' : 's' }} · {{ group.workers }}</span>
                <Icon name="chevron-down" class="ml-auto h-4 w-4 text-slate-500 transition-transform group-open:rotate-180" />
              </summary>
              <div class="space-y-5 border-t border-juli-border px-4 py-4">
                <TimelineItem v-for="m in group.work" :key="m.key" :m="m" v-bind="itemProps" @answered="relayAnswer" @open-file="p => $emit('open-file', p)" />
              </div>
            </details>

            <TimelineItem v-for="m in group.before" :key="m.key" :m="m" v-bind="itemProps" as-juli @answered="relayAnswer" @open-file="p => $emit('open-file', p)" />

            <!-- The reply: the crew's last message, as Juli, with the whole run's totals -->
            <article v-if="group.reply" class="flex gap-3">
              <JuliMascot still :size="32" class="mt-0.5" />
              <div class="min-w-0 flex-1">
                <h3 class="mb-1.5 text-sm font-semibold text-juli-accent">Juli</h3>
                <MessageBody :text="group.reply.content" />
                <p class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs tabular-nums text-slate-500">
                  <span>from {{ agentLabel(group.reply.agent_name, agents) }}</span>
                  <template v-if="group.total">
                    <span>run total {{ formatTokens(group.total.tokens_in) }} in · {{ formatTokens(group.total.tokens_out) }} out</span>
                    <span>{{ formatCost(group.total.cost_usd) }}</span>
                  </template>
                  <span>{{ formatTime(group.reply.timestamp) }}</span>
                </p>
                <ReplyActions :text="group.reply.content" :filename="group.run ? `juli-run-${group.run.id}.md` : 'juli.md'" :zip-project="group.filesKey ? projectId : null" />
              </div>
            </article>

            <TimelineItem v-for="m in group.after" :key="m.key" :m="m" v-bind="itemProps" as-juli @answered="relayAnswer" @open-file="p => $emit('open-file', p)" />
          </div>
        </section>

        <!-- Text streaming in (the whole-crew view only; in Juli only the line below says who is working) -->
        <article v-if="!juliView && draft && draft.text && (!filter || filter === draft.agent)" class="mb-6 flex gap-3" aria-busy="true">
          <AgentAvatar :agent="agents[draft.agent]" :color="colorOf(draft.agent)" active class="mt-0.5" />
          <div class="min-w-0 flex-1">
            <h3 class="mb-1.5 text-sm font-semibold" :style="{ color: colorOf(draft.agent) }">{{ agentLabel(draft.agent, agents) }}</h3>
            <MessageBody :text="draft.text" />
          </div>
        </article>

        <NowWorking v-if="showLine" :status="status" :turn="turn" :asking="asking" :streaming="Boolean(draft && draft.text)" :agents="agents" />
      </div>
    </div>

    <button v-if="!atBottom" type="button" class="btn btn-secondary absolute bottom-3 left-1/2 -translate-x-1/2 shadow-lg" @click="scrollToBottom">
      <Icon name="chevron-down" class="h-4 w-4" />Latest
    </button>
  </div>
</template>

<script setup>
// The run view: every run of the project in one timeline, like a chat.
// "Whole crew" shows each agent's message as it streams in and settles with
// a footer (model, tokens, cost). "Juli only" folds the crew's work away and
// shows one reply per run; anything that needs you stays in view. Every reply
// can be copied or downloaded; a finished run that wrote files also offers them.
import { ref, computed, watch, nextTick } from 'vue'
import AgentAvatar from './AgentAvatar.vue'
import Icon from './Icon.vue'
import JuliMascot from './JuliMascot.vue'
import MessageBody from './MessageBody.vue'
import NowWorking from './NowWorking.vue'
import ReplyActions from './ReplyActions.vue'
import TimelineItem from './TimelineItem.vue'
import { agentLabel, formatCost, formatTime, formatTokens, RUN_MODES } from '../labels.js'
import { agentLook } from '../mascot.js'

const props = defineProps({
  timeline: { type: Array, default: () => [] },
  draft: { type: Object, default: null },
  status: { type: String, default: 'idle' },
  turn: { type: Object, default: null },
  asking: { type: Object, default: null },
  agents: { type: Object, default: () => ({}) },
  filter: { type: String, default: null },
  openDecisionKey: { type: String, default: null },
  answered: { type: Object, default: () => ({}) },
  models: { type: Array, default: () => [] },
  view: { type: String, default: 'crew' }, // crew or juli
  activeRunId: { type: Number, default: null },
  totals: { type: Function, default: null }, // run id -> { tokens_in, tokens_out, cost_usd }
  projectId: { type: String, default: null }, // the project shown, for "Download files"
})
const emit = defineEmits(['clear-filter', 'answered', 'open-file'])

// A filter picks one agent's messages, which only makes sense with the whole crew shown.
const juliView = computed(() => props.view === 'juli' && !props.filter)
const itemProps = computed(() => ({ agents: props.agents, openDecisionKey: props.openDecisionKey, answered: props.answered, models: props.models }))
const relayAnswer = (key, action) => emit('answered', key, action)

// The crew's working steps, plus questions already answered; everything else
// (your notes, an open question, warnings, errors, follow-ups) stays in view.
const CREW_WORK = new Set(['agent', 'files', 'command', 'tool', 'system'])
const isWork = m => CREW_WORK.has(m.message_type) || (m.message_type === 'decision' && m.key !== props.openDecisionKey)
const live = computed(() => props.status === 'running' || props.status === 'paused')

function foldForJuli(group) {
  const items = group.items
  // A finished run's reply is its last agent message; a live run has none yet.
  const running = live.value && group.run && group.run.id === props.activeRunId
  let replyAt = -1
  if (!running) {
    for (let i = items.length - 1; i >= 0; i--) {
      if (items[i].message_type === 'agent') { replyAt = i; break }
    }
  }
  const work = items.filter((m, i) => isWork(m) && i !== replyAt)
  const visible = (m, i) => !isWork(m) && i !== replyAt
  const workers = [...new Set(work.filter(m => m.message_type === 'agent').map(m => agentLabel(m.agent_name, props.agents)))].join(', ')
  return {
    ...group,
    work,
    workers,
    before: items.filter((m, i) => visible(m, i) && (replyAt < 0 || i < replyAt)),
    reply: replyAt >= 0 ? items[replyAt] : null,
    after: replyAt >= 0 ? items.filter((m, i) => visible(m, i) && i > replyAt) : [],
    total: replyAt >= 0 && group.run && props.totals ? props.totals(group.run.id) : null,
  }
}

// "Download files" goes under the last reply of a run that has ended and wrote files.
const ENDED = new Set(['complete', 'stopped', 'error'])
function filesKey(group) {
  if (!group.run || !ENDED.has(group.run.status) || !group.items.some(m => m.message_type === 'files')) return null
  return group.items.findLast(m => m.message_type === 'agent')?.key ?? null
}

const shown = computed(() => props.timeline.map(g => {
  const group = { ...g, filesKey: filesKey(g) }
  if (props.filter) return { ...group, items: g.items.filter(m => m.agent_name === props.filter) }
  return juliView.value ? foldForJuli(group) : group
}))

// The live line shows while the crew works or waits, and after a run ends (until the next one).
const showLine = computed(() => Boolean(props.asking) || (props.status !== 'idle' && props.timeline.some(g => g.run)))

const colorOf = name => props.agents[name]?.color || '#94a3b8'
const modeLabel = id => RUN_MODES.find(m => m.id === id)?.label || id

function statusTone(status) {
  return {
    complete: 'bg-emerald-500/15 text-emerald-300',
    stopped: 'bg-slate-500/20 text-slate-300',
    error: 'bg-red-500/15 text-red-300',
    paused: 'bg-amber-500/15 text-amber-200',
  }[status] || 'bg-slate-500/20 text-slate-300'
}

// Follow the newest text unless the user has scrolled up to read.
const scroller = ref(null)
const atBottom = ref(true)

function onScroll() {
  const el = scroller.value
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 120
}

function scrollToBottom() {
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
  atBottom.value = true
}

watch(
  () => [props.timeline.reduce((n, g) => n + g.items.length, 0), props.draft?.text.length, props.status, props.turn, props.view],
  () => { if (atBottom.value) nextTick(scrollToBottom) },
)
</script>
