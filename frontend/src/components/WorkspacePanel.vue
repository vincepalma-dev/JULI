<template>
  <SidePanel :open="open" title="Workspace" icon="code" wide @close="$emit('close')">
    <template #tabs>
      <div class="tab-bar items-center" role="tablist" aria-label="Workspace views">
        <button type="button" role="tab" class="tab" :aria-selected="tab === 'files'" @click="tab = 'files'">Files</button>
        <button type="button" role="tab" class="tab" :aria-selected="tab === 'changes'" @click="tab = 'changes'">Changes by run</button>
        <button type="button" class="btn btn-secondary my-1.5 ml-auto !min-h-0 !py-1 text-xs" :disabled="!files.length" @click="downloadZip"><Icon name="download" class="h-3.5 w-3.5" />Download zip</button>
      </div>
    </template>

    <p v-if="error" role="alert" class="mb-4 text-sm text-red-300">{{ error }}</p>

    <!-- Files -->
    <div v-if="tab === 'files'" class="grid gap-4 md:grid-cols-[16rem_1fr]">
      <nav aria-label="Files" class="surface max-h-[60vh] overflow-auto p-1.5 md:max-h-[calc(100dvh-12rem)]">
        <p v-if="!files.length" class="p-2 text-sm text-slate-400">No files yet. They appear here when the Coder writes them.</p>
        <ul>
          <li v-for="row in rows" :key="row.path">
            <button
              type="button"
              class="flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left text-sm hover:bg-white/[0.05]"
              :class="row.path === selected ? 'bg-white/[0.08] text-white' : 'text-slate-300'"
              :style="{ paddingLeft: `${row.depth * 14 + 6}px` }"
              :aria-expanded="row.dir ? expanded.has(row.path) : undefined"
              :aria-current="row.path === selected ? 'true' : undefined"
              @click="row.dir ? toggle(row.path) : openFile(row.path)"
            >
              <Icon :name="row.dir ? (expanded.has(row.path) ? 'chevron-down' : 'chevron-right') : 'file'" class="h-3.5 w-3.5 shrink-0 text-slate-500" />
              <span class="min-w-0 font-mono text-xs" style="overflow-wrap: anywhere">{{ row.name }}</span>
            </button>
          </li>
        </ul>
      </nav>
      <section class="min-w-0" aria-live="polite">
        <template v-if="file">
          <p class="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span class="font-mono text-slate-200" style="overflow-wrap: anywhere">{{ file.path }}</span>
            <span>{{ formatBytes(file.size) }}</span>
          </p>
          <p v-if="file.binary" class="text-sm text-slate-400">A binary file. Download the zip to get it.</p>
          <p v-else-if="file.too_large" class="text-sm text-slate-400">Too large to show here. Download the zip to get it.</p>
          <pre v-else class="surface max-h-[calc(100dvh-14rem)] overflow-auto p-3 font-mono text-xs leading-relaxed text-slate-200">{{ file.content }}</pre>
        </template>
        <p v-else-if="files.length" class="text-sm text-slate-400">Pick a file to read it.</p>
      </section>
    </div>

    <!-- Changes by run -->
    <div v-else class="space-y-4">
      <div class="flex flex-wrap items-end gap-3">
        <div>
          <label for="diff-run" class="label">Run</label>
          <select id="diff-run" v-model.number="runId" class="field !w-auto">
            <option v-for="r in [...runs].reverse()" :key="r.id" :value="r.id">Run {{ r.id }}: {{ r.prompt.slice(0, 50) }}{{ r.prompt.length > 50 ? '…' : '' }}</option>
          </select>
        </div>
        <button type="button" class="btn btn-secondary" :disabled="!runId || !changed.length || gitBusy || runLive" @click="commit"><Icon name="branch" class="h-4 w-4" />Commit to juli/run-{{ runId }}</button>
      </div>
      <p v-if="runLive" class="hint">This run is still going. Commit when it's done.</p>
      <p v-if="gitNote" class="text-sm" :class="gitNote.ok ? 'text-emerald-300' : 'text-red-300'" role="status">{{ gitNote.text }}</p>

      <!-- Push asks first, every time -->
      <form class="surface space-y-2 p-3" @submit.prevent="push(false)">
        <label for="remote" class="label">Push the run's branch</label>
        <div class="flex flex-wrap gap-2">
          <input id="remote" v-model="remote" class="field min-w-0 flex-1 font-mono" placeholder="Remote URL (empty: the workspace's own remote)" spellcheck="false" autocomplete="off" />
          <button type="submit" class="btn btn-secondary" :disabled="!runId || gitBusy || runLive"><Icon name="upload" class="h-4 w-4" />Push…</button>
        </div>
        <div v-if="pushAsk" class="rounded-lg border border-amber-400/30 bg-amber-400/[0.06] p-3 text-sm text-amber-100" role="alertdialog" aria-label="Confirm push">
          <p>Push <code class="font-mono">{{ pushAsk.branch }}</code> to <code class="font-mono" style="overflow-wrap: anywhere">{{ pushAsk.remote }}</code>? This sends the run's code to that server.</p>
          <div class="mt-2 flex gap-2">
            <button type="button" class="btn btn-primary" :disabled="gitBusy" @click="push(true)">Push</button>
            <button type="button" class="btn btn-secondary" @click="pushAsk = null">Cancel</button>
          </div>
        </div>
      </form>

      <p v-if="runId && !changed.length" class="text-sm text-slate-400">This run didn't write any files.</p>
      <ul v-else class="flex flex-wrap gap-1.5">
        <li v-for="f in changed" :key="f.path" class="badge font-mono" :class="f.status === 'added' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-200'">
          {{ f.status === 'added' ? 'A' : 'M' }} {{ f.path }}
        </li>
      </ul>
      <div v-if="diffLines.length" class="surface overflow-auto font-mono text-xs leading-relaxed" role="region" aria-label="Diff">
        <div v-for="(line, i) in diffLines" :key="i" class="whitespace-pre px-3" :class="lineTone(line)">{{ line || ' ' }}</div>
        <p v-if="diffCut" class="px-3 py-2 text-slate-400">The diff is long; the rest is in the zip.</p>
      </div>
    </div>
  </SidePanel>
</template>

<script setup>
// The project's working tree: files, one file, a zip; each run's changed files
// and unified diff; commit to juli/run-<id>; push, which always asks first.
import { ref, computed, watch } from 'vue'
import Icon from './Icon.vue'
import SidePanel from './SidePanel.vue'
import { apiDownload, apiFetch } from '../api.js'
import { formatBytes } from '../labels.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  projectId: { type: String, default: null },
  runs: { type: Array, default: () => [] },
  activeRunId: { type: Number, default: null },
  live: { type: Boolean, default: false }, // a run is going
  showPath: { type: String, default: '' }, // a file to open (from the timeline)
})
defineEmits(['close'])

const MAX_DIFF_LINES = 4000
const tab = ref('files')
const error = ref('')
const files = ref([])
const expanded = ref(new Set())
const selected = ref('')
const file = ref(null)
const runId = ref(null) // the run whose changes are shown

// Each tree or file request gets a number; only the latest one's answer is shown,
// so a slow earlier answer (another project, or the same one asked again) never wins.
let treeRequest = 0
let fileRequest = 0

async function loadTree() {
  const project = props.projectId
  if (!project) return
  const request = ++treeRequest
  try {
    const tree = await apiFetch(`/api/projects/${project}/workspace/tree`)
    if (request === treeRequest) files.value = tree.files
  } catch (e) {
    if (request === treeRequest) error.value = e.message
  }
}

// Another project: nothing shown so far belongs to it. Registered before the
// loading watcher below, so the new project's requests start after this reset.
watch(() => props.projectId, () => {
  treeRequest++ // answers still on their way belong to the old project
  fileRequest++
  files.value = []
  selected.value = ''
  file.value = null
  expanded.value = new Set()
  changed.value = []
  diff.value = ''
  pushAsk.value = null
  gitNote.value = null
  runId.value = latestRunId()
})

watch(() => [props.open, props.projectId, props.showPath], ([open]) => {
  if (!open) return
  error.value = ''
  loadTree()
  if (!runId.value && props.runs.length) runId.value = props.runs[props.runs.length - 1].id
  if (props.showPath) openFile(props.showPath)
}, { immediate: true })

const latestRunId = () => (props.runs.length ? props.runs[props.runs.length - 1].id : null)

// Runs load (or change): keep the chosen run if it's still listed, else show the latest.
watch(() => props.runs.map(r => r.id).join(), () => {
  if (!props.runs.some(r => r.id === runId.value)) runId.value = latestRunId()
})

// A nested tree, flattened to the rows that are visible (folders first).
const rows = computed(() => {
  const root = { children: new Map() }
  for (const f of files.value) {
    let node = root
    const parts = f.path.split('/')
    parts.forEach((part, i) => {
      const path = parts.slice(0, i + 1).join('/')
      if (!node.children.has(part)) node.children.set(part, { name: part, path, dir: i < parts.length - 1, children: new Map() })
      node = node.children.get(part)
    })
  }
  const out = []
  const walk = (node, depth) => {
    const kids = [...node.children.values()].sort((a, b) => (b.dir - a.dir) || a.name.localeCompare(b.name))
    for (const kid of kids) {
      out.push({ name: kid.name, path: kid.path, dir: kid.dir, depth })
      if (kid.dir && expanded.value.has(kid.path)) walk(kid, depth + 1)
    }
  }
  walk(root, 0)
  return out
})

function toggle(path) {
  const next = new Set(expanded.value)
  next.has(path) ? next.delete(path) : next.add(path)
  expanded.value = next
}

async function openFile(path) {
  tab.value = 'files'
  selected.value = path
  // Open the folders above it.
  const next = new Set(expanded.value)
  path.split('/').slice(0, -1).forEach((_, i, parts) => next.add(parts.slice(0, i + 1).join('/')))
  expanded.value = next
  const request = ++fileRequest
  try {
    const result = await apiFetch(`/api/projects/${props.projectId}/workspace/file?path=${encodeURIComponent(path)}`)
    if (request === fileRequest) file.value = result
  } catch (e) {
    if (request !== fileRequest) return
    file.value = null
    error.value = e.message
  }
}

async function downloadZip() {
  try {
    await apiDownload(`/api/projects/${props.projectId}/workspace/zip`, `juli-${props.projectId.slice(0, 8)}.zip`)
  } catch (e) {
    error.value = e.message
  }
}

// ─── Changes by run ───
const changed = ref([])
const diff = ref('')
const runLive = computed(() => props.live && runId.value === props.activeRunId)

watch([runId, () => props.open, runLive], async () => {
  const id = runId.value
  if (!props.open || !id) {
    changed.value = []
    diff.value = ''
    return
  }
  try {
    const [list, d] = await Promise.all([apiFetch(`/api/runs/${id}/files`), apiFetch(`/api/runs/${id}/diff`)])
    if (id !== runId.value) return // another run was picked meanwhile
    changed.value = list
    diff.value = d.diff
  } catch (e) {
    if (id === runId.value) error.value = e.message
  }
})

const allDiffLines = computed(() => (diff.value ? diff.value.split('\n') : []))
const diffLines = computed(() => allDiffLines.value.slice(0, MAX_DIFF_LINES))
const diffCut = computed(() => allDiffLines.value.length > MAX_DIFF_LINES)

function lineTone(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'text-slate-400'
  if (line.startsWith('+')) return 'bg-emerald-500/10 text-emerald-200'
  if (line.startsWith('-')) return 'bg-red-500/10 text-red-200'
  if (line.startsWith('@@')) return 'text-cyan-300'
  return 'text-slate-300'
}

const gitBusy = ref(false)
const gitNote = ref(null)
const remote = ref('')
const pushAsk = ref(null)

async function commit() {
  await git(async () => (await apiFetch(`/api/runs/${runId.value}/commit`, { method: 'POST' })).detail)
}

// A confirmation is for one run and remote: changing either withdraws it.
watch([runId, remote], () => { pushAsk.value = null })

async function push(confirm) {
  // Confirming pushes exactly what the dialog showed, not what the fields say now.
  const ask = confirm ? pushAsk.value : null
  if (confirm && !ask) return
  const id = ask ? ask.runId : runId.value
  const target = ask ? ask.remoteInput : remote.value.trim()
  await git(async () => {
    try {
      const body = { confirm }
      if (target) body.remote = target
      const res = await apiFetch(`/api/runs/${id}/push`, { method: 'POST', body })
      pushAsk.value = null
      return res.detail
    } catch (e) {
      // Without confirm, the server says what it would push: ask the user.
      if (e.status === 409 && e.detail?.confirm) {
        pushAsk.value = { ...e.detail.confirm, runId: id, remoteInput: target }
        return null
      }
      throw e
    }
  })
}

async function git(fn) {
  gitBusy.value = true
  gitNote.value = null
  try {
    const text = await fn()
    if (text) gitNote.value = { ok: true, text }
  } catch (e) {
    gitNote.value = { ok: false, text: e.message }
  } finally {
    gitBusy.value = false
  }
}
</script>
