<template>
  <SidePanel :open="open" title="Settings" icon="sliders" @close="$emit('close')">
    <template #tabs>
      <div class="tab-bar" role="tablist" aria-label="Settings sections">
        <button v-for="t in TABS" :key="t.id" type="button" role="tab" class="tab" :aria-selected="tab === t.id" @click="tab = t.id">{{ t.label }}</button>
      </div>
    </template>

    <!-- Run limits -->
    <form v-if="tab === 'run'" class="space-y-5" @submit.prevent="saveRun">
      <p class="hint">Limits are off unless you set them. When a limit is reached, the run stops and keeps its output so far.</p>
      <div class="grid gap-4 sm:grid-cols-2">
        <div>
          <label for="budget" class="label">Budget cap per run (US$)</label>
          <input id="budget" v-model="run.budget_usd" type="number" min="0.01" max="10000" step="0.01" inputmode="decimal" class="field" placeholder="No limit" />
          <p class="hint mt-1">Cloud cost only; local models count as $0.</p>
        </div>
        <div>
          <label for="tokencap" class="label">Token cap per run</label>
          <input id="tokencap" v-model="run.token_cap" type="number" min="1" max="100000000" step="1" inputmode="numeric" class="field" placeholder="No limit" />
          <p class="hint mt-1">Input plus output tokens, every agent, local and cloud.</p>
        </div>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <div>
          <label for="rounds" class="label">Tool rounds per agent turn</label>
          <input id="rounds" v-model="run.max_tool_rounds" type="number" min="1" max="100" step="1" inputmode="numeric" class="field" />
          <p class="hint mt-1">A loop guard: after this many rounds of tool use, the agent has to answer. An agent can have its own in the crew settings.</p>
        </div>
        <div>
          <label for="handoffs" class="label">Handoffs per run</label>
          <input id="handoffs" v-model="run.max_handoffs" type="number" min="0" max="50" step="1" inputmode="numeric" class="field" />
          <p class="hint mt-1">How often agents may hand work to a colleague in one run. 0 turns handoffs off.</p>
        </div>
      </div>

      <div>
        <label for="discuss" class="label">Crew discussion of the plan</label>
        <select id="discuss" v-model.number="run.discussion_rounds" class="field sm:w-60">
          <option :value="0">Off</option>
          <option v-for="n in 4" :key="n" :value="n">Up to {{ n }} round{{ n > 1 ? 's' : '' }}</option>
        </select>
        <p class="hint mt-1">Before coding, the Coder and Reviewer give feedback on the plan and the Planner revises it. Each round adds turns, so it uses more tokens.</p>
      </div>

      <fieldset class="surface space-y-3 p-4">
        <legend class="px-1 text-xs font-medium text-slate-300">When a cloud key fails</legend>
        <label class="flex cursor-pointer items-start gap-2 text-sm text-slate-200">
          <input v-model="run.auto_fallback" type="checkbox" class="mt-0.5 h-4 w-4 accent-cyan-500" />
          <span>Switch to a local model automatically instead of pausing (out of credit or invalid key).</span>
        </label>
        <div>
          <label for="fallback" class="label">Local fallback model</label>
          <input id="fallback" v-model="run.fallback_model" list="local-models" class="field font-mono" placeholder="ollama:qwen3:8b" spellcheck="false" autocomplete="off" />
          <datalist id="local-models"><option v-for="m in localModels" :key="m" :value="m" /></datalist>
        </div>
      </fieldset>

      <div class="flex items-center gap-3">
        <button type="submit" class="btn btn-primary" :disabled="busy">Save limits</button>
        <p v-if="notice.run" class="text-sm" :class="notice.run.ok ? 'text-emerald-300' : 'text-red-300'" role="status">{{ notice.run.text }}</p>
      </div>
    </form>

    <!-- API keys -->
    <form v-else-if="tab === 'keys'" class="space-y-4" @submit.prevent="saveKeys">
      <p class="hint">Keys are stored in your system keychain, never in settings files or logs. The monthly allowance is tracked on this machine: JULI warns at 80% and blocks new runs at 100% (you can override it per run).</p>
      <div v-for="p in keyProviders" :key="p.id" class="surface space-y-3 p-4">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="text-sm font-semibold text-white">{{ p.label }}</h3>
          <span v-if="p.key_hint" class="font-mono text-xs text-slate-400">{{ p.key_hint }}</span>
          <span class="badge" :class="health(p).tone" :title="health(p).detail">{{ health(p).label }}</span>
          <span class="ml-auto flex gap-1">
            <button type="button" class="btn btn-secondary !min-h-0 !px-2.5 !py-1 text-xs" :disabled="!p.key_hint || checking[p.id]" @click="check(p.id)">{{ checking[p.id] ? 'Checking…' : 'Check' }}</button>
            <button v-if="p.key_hint" type="button" class="icon-btn !h-8 !w-8 hover:!text-red-300" :aria-label="`Remove the ${p.label} key`" @click="removeKey(p.id)"><Icon name="trash" class="h-4 w-4" /></button>
          </span>
        </div>
        <div class="grid gap-3 sm:grid-cols-[1fr_9rem]">
          <div>
            <label :for="`key-${p.id}`" class="label">{{ p.key_hint ? 'Replace key' : 'API key' }}</label>
            <div class="relative">
              <input :id="`key-${p.id}`" v-model="keys[p.id]" :type="show[p.id] ? 'text' : 'password'" maxlength="500" class="field pr-10 font-mono" autocomplete="off" spellcheck="false" :placeholder="p.key_hint ? 'Saved' : 'Paste a key…'" />
              <button type="button" class="icon-btn absolute right-0.5 top-1/2 !h-8 !w-8 -translate-y-1/2" :aria-label="show[p.id] ? 'Hide key' : 'Show key'" @click="show[p.id] = !show[p.id]">
                <Icon :name="show[p.id] ? 'eye-off' : 'eye'" class="h-4 w-4" />
              </button>
            </div>
          </div>
          <div>
            <label :for="`allow-${p.id}`" class="label">Monthly allowance ($)</label>
            <input :id="`allow-${p.id}`" v-model="allowances[p.id]" type="number" min="0.01" max="10000" step="0.01" inputmode="decimal" class="field" placeholder="None" />
          </div>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <button type="submit" class="btn btn-primary" :disabled="busy">Save keys and allowances</button>
        <p v-if="notice.keys" class="text-sm" :class="notice.keys.ok ? 'text-emerald-300' : 'text-red-300'" role="status">{{ notice.keys.text }}</p>
      </div>
    </form>

    <!-- Tools: MCP servers -->
    <form v-else-if="tab === 'tools'" class="space-y-5" @submit.prevent="saveMcp">
      <p class="hint">Agents read, search and write the project's files, run checks and hand work to each other with built-in tools. MCP servers add more. Every MCP call asks you first, unless you trust that tool and its server runs in the sandbox or over HTTP. In Privacy Mode, only sandboxed servers and HTTP servers on this machine or your network are used.</p>
      <div v-for="srv in servers" :key="srv.uid" class="surface space-y-3 p-4">
        <div class="flex flex-wrap items-end gap-3">
          <div class="min-w-0 flex-1">
            <label :for="`mcp-name-${srv.uid}`" class="label">Name</label>
            <input :id="`mcp-name-${srv.uid}`" v-model="srv.name" maxlength="24" class="field font-mono" placeholder="github" spellcheck="false" autocomplete="off" />
          </div>
          <div>
            <label :for="`mcp-transport-${srv.uid}`" class="label">Connects over</label>
            <select :id="`mcp-transport-${srv.uid}`" v-model="srv.transport" class="field">
              <option value="stdio">A program (stdio)</option>
              <option value="http">HTTP</option>
            </select>
          </div>
          <label class="flex min-h-10 cursor-pointer items-center gap-2 text-sm text-slate-200">
            <input v-model="srv.enabled" type="checkbox" class="h-4 w-4 accent-cyan-500" />
            On
          </label>
          <button type="button" class="icon-btn hover:!text-red-300" :aria-label="`Remove ${srv.name || 'this server'}`" @click="removeServer(srv)"><Icon name="trash" class="h-4 w-4" /></button>
        </div>

        <template v-if="srv.transport === 'stdio'">
          <div>
            <label :for="`mcp-command-${srv.uid}`" class="label">Command</label>
            <input :id="`mcp-command-${srv.uid}`" v-model="srv.command" class="field font-mono" placeholder="npx -y @modelcontextprotocol/server-memory" spellcheck="false" autocomplete="off" />
          </div>
          <label class="flex cursor-pointer items-start gap-2 text-sm text-slate-200">
            <input v-model="srv.sandbox" type="checkbox" class="mt-0.5 h-4 w-4 accent-cyan-500" />
            <span>Run it in the Docker sandbox (no network, only the project folder). The sandbox image must already have what it needs.</span>
          </label>
        </template>
        <div v-else>
          <label :for="`mcp-url-${srv.uid}`" class="label">URL</label>
          <input :id="`mcp-url-${srv.uid}`" v-model="srv.url" type="url" class="field font-mono" placeholder="http://127.0.0.1:8000/mcp" spellcheck="false" autocomplete="off" />
        </div>

        <div class="grid gap-3 sm:grid-cols-2">
          <div>
            <label :for="`mcp-token-${srv.uid}`" class="label">{{ srv.token_hint ? `Token (saved: ${srv.token_hint})` : 'Token (optional)' }}</label>
            <input :id="`mcp-token-${srv.uid}`" v-model="srv.token" type="password" maxlength="500" class="field font-mono" :placeholder="srv.token_hint ? 'Saved' : 'Kept in your keychain'" autocomplete="off" spellcheck="false" />
          </div>
          <div v-if="srv.transport === 'stdio'">
            <label :for="`mcp-env-${srv.uid}`" class="label">Pass the token as</label>
            <input :id="`mcp-env-${srv.uid}`" v-model="srv.token_env" maxlength="64" class="field font-mono" placeholder="GITHUB_TOKEN" spellcheck="false" autocomplete="off" />
          </div>
        </div>

        <div>
          <label :for="`mcp-trusted-${srv.uid}`" class="label">Trusted tools (no approval)</label>
          <input :id="`mcp-trusted-${srv.uid}`" v-model="srv.trusted" class="field font-mono" placeholder="search, read_page" spellcheck="false" autocomplete="off" />
          <p class="hint mt-1">Comma-separated. Only applies when the server is sandboxed or over HTTP; otherwise every call still asks.</p>
        </div>

        <fieldset>
          <legend class="label">Roles that get its tools (none ticked: every role)</legend>
          <div class="flex flex-wrap gap-x-4 gap-y-2">
            <label v-for="r in ROLES" :key="r" class="flex cursor-pointer items-center gap-1.5 text-sm text-slate-200">
              <input v-model="srv.roles" type="checkbox" :value="r" class="h-4 w-4 accent-cyan-500" />{{ r }}
            </label>
          </div>
        </fieldset>
      </div>
      <p v-if="!servers.length" class="text-sm text-slate-400">No MCP servers yet.</p>
      <div class="flex flex-wrap items-center gap-3">
        <button type="button" class="btn btn-secondary" @click="addServer"><Icon name="plus" class="h-4 w-4" />Add MCP server</button>
        <button type="submit" class="btn btn-primary" :disabled="busy">Save tools</button>
        <p v-if="notice.tools" class="text-sm" :class="notice.tools.ok ? 'text-emerald-300' : 'text-red-300'" role="status">{{ notice.tools.text }}</p>
      </div>
    </form>

    <!-- Data: retention, and deleting everything -->
    <div v-else-if="tab === 'data'" class="space-y-6">
      <form class="space-y-3" @submit.prevent="saveRetention">
        <div>
          <label for="retention" class="label">Keep run history</label>
          <select id="retention" v-model="retention" class="field sm:w-72">
            <option v-for="o in RETENTION" :key="o.days ?? 'forever'" :value="o.days">{{ o.label }}</option>
          </select>
          <p class="hint mt-1">Run history is each run's prompt, the agents' replies, tool and command output, diffs and checkpoints. Runs older than this are deleted when you save, when JULI starts and after each run. A run that hasn't ended is never deleted.</p>
        </div>
        <ul class="hint list-disc space-y-0.5 pl-5">
          <li>Projects and their files stay until you delete them. Deleting a project keeps its files on disk.</li>
          <li>Settings, keys and model speed results stay until you change or remove them.</li>
        </ul>
        <div class="flex items-center gap-3">
          <button type="submit" class="btn btn-primary" :disabled="busy">Save retention</button>
          <p v-if="notice.data" class="text-sm" :class="notice.data.ok ? 'text-emerald-300' : 'text-red-300'" role="status">{{ notice.data.text }}</p>
        </div>
      </form>

      <form class="space-y-3 rounded-xl border border-red-500/30 bg-red-500/[0.05] p-4" @submit.prevent="deleteAll">
        <h3 class="flex items-center gap-2 text-sm font-semibold text-red-200"><Icon name="trash" class="h-4 w-4" />Delete all data</h3>
        <p class="text-sm leading-relaxed text-slate-200">This deletes every project and its files, all run history, your settings and crew, and the API keys and MCP tokens JULI saved in the system keychain. It can't be undone: download any project you want to keep first (Workspace &gt; Download zip).</p>
        <p class="hint">Not touched: a <code class="font-mono">.env</code> file, models downloaded with Ollama, and Docker images. Remove those yourself if you want them gone.</p>
        <div>
          <label for="delete-confirm" class="label">Type <span class="font-mono text-slate-200">{{ DELETE_PHRASE }}</span> to confirm</label>
          <input id="delete-confirm" v-model="deletePhrase" class="field font-mono sm:w-72" autocomplete="off" spellcheck="false" />
        </div>
        <div class="flex items-center gap-3">
          <button type="submit" class="btn btn-danger" :disabled="busy || deletePhrase.trim() !== DELETE_PHRASE"><Icon name="trash" class="h-4 w-4" />Delete everything</button>
          <p v-if="notice.deleteAll" class="text-sm" :class="notice.deleteAll.ok ? 'text-emerald-300' : 'text-red-300'" role="status">{{ notice.deleteAll.text }}</p>
        </div>
      </form>
    </div>

    <!-- Sandbox -->
    <form v-else-if="tab === 'sandbox'" class="space-y-5" @submit.prevent="saveSandbox">
      <div class="surface flex items-start gap-3 p-4" :class="sandbox.active ? '!border-emerald-500/30' : ''">
        <Icon :name="sandbox.active ? 'shield' : 'alert'" class="mt-0.5 h-5 w-5 shrink-0" :class="sandbox.active ? 'text-emerald-300' : 'text-amber-300'" />
        <p class="text-sm leading-relaxed text-slate-200">
          <template v-if="sandbox.active">The Docker sandbox is on. Agent test commands such as <code class="font-mono">pytest</code> run on their own inside it, with only the workspace mounted and no network. Anything else still asks you first.</template>
          <template v-else>The sandbox is off: {{ sandbox.problem }}. Every agent command asks you to approve it first and shows the exact command.</template>
        </p>
      </div>
      <label class="flex cursor-pointer items-center gap-2 text-sm text-slate-200">
        <input v-model="sandboxForm.enabled" type="checkbox" class="h-4 w-4 accent-cyan-500" />
        Run agent commands in the Docker sandbox
      </label>
      <div class="grid gap-4 sm:grid-cols-[1fr_9rem]">
        <div>
          <label for="image" class="label">Image</label>
          <input id="image" v-model="sandboxForm.image" class="field font-mono" spellcheck="false" autocomplete="off" />
          <p class="hint mt-1">Pick an image that has the tools your project tests with (Python, Node…). JULI doesn't download images for you.</p>
        </div>
        <div>
          <label for="timeout" class="label">Timeout (seconds)</label>
          <input id="timeout" v-model.number="sandboxForm.timeout" type="number" min="5" max="3600" class="field" />
        </div>
      </div>
      <div class="flex items-center gap-3">
        <button type="submit" class="btn btn-primary" :disabled="busy">Save sandbox</button>
        <p v-if="notice.sandbox" class="text-sm" :class="notice.sandbox.ok ? 'text-emerald-300' : 'text-red-300'" role="status">{{ notice.sandbox.text }}</p>
      </div>
    </form>

    <!-- Theme -->
    <div v-else class="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Theme">
      <button v-for="t in THEMES" :key="t.id" type="button" role="radio" :aria-checked="theme === t.id" class="surface flex items-center gap-3 p-3 text-left transition-colors hover:bg-white/[0.04]" :class="theme === t.id ? '!border-white/40' : ''" @click="pickTheme(t)">
        <span class="flex h-10 w-10 shrink-0 items-end gap-0.5 rounded-lg p-1.5" :style="{ backgroundColor: t.bg, border: `1px solid ${t.border}` }" aria-hidden="true">
          <span class="h-2 flex-1 rounded-sm" :style="{ backgroundColor: t.accent }"></span>
          <span class="h-4 flex-1 rounded-sm" :style="{ backgroundColor: t.text }"></span>
        </span>
        <span class="min-w-0">
          <span class="block text-sm font-medium text-white">{{ t.name }}</span>
          <span class="block text-xs text-slate-400">{{ t.desc }}</span>
        </span>
        <Icon v-if="theme === t.id" name="check" class="ml-auto h-4 w-4 text-white" />
      </button>
    </div>
  </SidePanel>
</template>

<script setup>
// Run limits, API keys with health badges and allowances, MCP tool servers,
// data retention and deleting all data, the Docker sandbox, and the theme.
import { ref, reactive, computed, watch } from 'vue'
import Icon from './Icon.vue'
import SidePanel from './SidePanel.vue'
import { apiFetch } from '../api.js'
import { THEMES, applyTheme, savedThemeId } from '../theme.js'
import { ROLES, joinArgs, splitArgs } from '../labels.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  settings: { type: Object, default: () => ({}) },
  providers: { type: Array, default: () => [] },
  localModels: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'saved', 'data-deleted'])

const TABS = [
  { id: 'run', label: 'Run limits' },
  { id: 'keys', label: 'API keys' },
  { id: 'tools', label: 'Tools' },
  { id: 'data', label: 'Data' },
  { id: 'sandbox', label: 'Sandbox' },
  { id: 'theme', label: 'Theme' },
]
const tab = ref('run')
const busy = ref(false)
const notice = reactive({ run: null, keys: null, tools: null, data: null, deleteAll: null, sandbox: null })

// ─── Run limits ───
const run = reactive({})
const keys = reactive({})
const show = reactive({})
const allowances = reactive({})
const results = reactive({}) // provider -> last health check
// The Tools tab's forms; declared here because the watcher below fills them at once when open.
const servers = ref([])
let nextUid = 0

watch(() => [props.open, props.settings], () => {
  if (!props.open) return
  const r = props.settings.run || {}
  Object.assign(run, { ...r, budget_usd: r.budget_usd ?? '', token_cap: r.token_cap ?? '', fallback_model: r.fallback_model ?? '' })
  for (const p of Object.keys(allowances)) delete allowances[p]
  for (const [p, v] of Object.entries(r.allowances || {})) allowances[p] = v
}, { immediate: true })

// The server forms are filled when the panel opens, not on every settings reload:
// saving another tab reloads the settings, and that mustn't wipe unsaved server edits.
watch(() => props.open, open => {
  if (open) servers.value = Object.entries(props.settings.mcp_servers || {}).map(([name, cfg]) => serverForm(name, cfg))
}, { immediate: true })

const blank = v => v === '' || v == null
function allowanceMap() {
  const allow = {}
  for (const [p, v] of Object.entries(allowances)) if (!blank(v)) allow[p] = Number(v)
  return allow
}
function runBody() {
  return {
    budget_usd: blank(run.budget_usd) ? null : Number(run.budget_usd),
    token_cap: blank(run.token_cap) ? null : Math.round(Number(run.token_cap)),
    privacy_mode: Boolean(run.privacy_mode),
    auto_fallback: Boolean(run.auto_fallback),
    fallback_model: run.fallback_model ? run.fallback_model.trim() : null,
    discussion_rounds: Number(run.discussion_rounds) || 0,
    allowances: allowanceMap(),
    max_tool_rounds: blank(run.max_tool_rounds) ? 25 : Math.round(Number(run.max_tool_rounds)),
    max_handoffs: blank(run.max_handoffs) ? 12 : Math.round(Number(run.max_handoffs)),
  }
}

async function saveRun() {
  await act('run', async () => {
    await apiFetch('/api/settings/run', { method: 'PUT', body: runBody() })
    return 'Limits saved'
  })
}

// ─── Keys ───
const keyProviders = computed(() => props.providers.filter(p => p.needs_key))

const HEALTH = {
  ok: ['Working', 'bg-emerald-500/15 text-emerald-300'],
  invalid: ['Invalid', 'bg-red-500/15 text-red-300'],
  out_of_credit: ['Out of credit', 'bg-red-500/15 text-red-300'],
  rate_limit: ['Rate limited', 'bg-amber-500/15 text-amber-200'],
  overloaded: ['Overloaded', 'bg-amber-500/15 text-amber-200'],
  missing: ['No key', 'bg-slate-500/20 text-slate-300'],
  skipped: ['Not checked: Privacy mode', 'bg-slate-500/20 text-slate-300'],
}
function health(p) {
  const r = results[p.id]
  if (!r) return p.key_hint ? { label: 'Not checked', tone: 'bg-slate-500/20 text-slate-300', detail: '' } : { label: 'No key', tone: 'bg-slate-500/20 text-slate-300', detail: '' }
  const [label, tone] = HEALTH[r.status] || ['Problem', 'bg-red-500/15 text-red-300']
  return { label, tone, detail: r.detail || '' }
}

const checking = reactive({})
async function check(id) {
  checking[id] = true
  try {
    results[id] = await apiFetch(`/api/providers/${id}/check`, { method: 'POST' })
  } catch (e) {
    results[id] = { status: 'error', detail: e.message }
  } finally {
    checking[id] = false
  }
}

async function saveKeys() {
  await act('keys', async () => {
    const typed = Object.fromEntries(Object.entries(keys).filter(([, v]) => v && v.trim()))
    if (Object.keys(typed).length) {
      const res = await apiFetch('/api/settings/keys', { method: 'PUT', body: typed })
      Object.assign(results, res.health || {})
      for (const p of Object.keys(keys)) delete keys[p]
    }
    // Only the allowances: unsaved edits on the Run limits tab stay unsaved.
    await apiFetch('/api/settings/run', { method: 'PUT', body: { ...props.settings.run, allowances: allowanceMap() } })
    return 'Saved'
  })
}

async function removeKey(id) {
  await act('keys', async () => {
    await apiFetch(`/api/settings/keys/${encodeURIComponent(id)}`, { method: 'DELETE' })
    delete results[id]
    return 'Key removed from the keychain'
  })
}

// ─── Tools: MCP servers ───
function serverForm(name, cfg = {}) {
  return {
    uid: ++nextUid,
    name,
    transport: cfg.transport || 'stdio',
    command: joinArgs(cfg.command || []),
    url: cfg.url || '',
    enabled: cfg.enabled !== false,
    sandbox: Boolean(cfg.sandbox),
    trusted: (cfg.trusted_tools || []).join(', '),
    roles: [...(cfg.roles || [])],
    token_env: cfg.token_env || '',
    token: '',
    token_hint: cfg.token_hint || '',
  }
}

function addServer() {
  servers.value.push(serverForm(''))
}

function removeServer(srv) {
  servers.value = servers.value.filter(s => s !== srv)
}

async function saveMcp() {
  await act('tools', async () => {
    const body = {}
    for (const srv of servers.value) {
      const name = srv.name.trim()
      if (!name) throw new Error('Give every server a name')
      if (body[name]) throw new Error(`Two servers are called ${name}`)
      const stdio = srv.transport === 'stdio'
      body[name] = {
        transport: srv.transport,
        command: stdio ? splitArgs(srv.command).filter(a => a !== '') : [], // the API takes no empty arguments
        url: stdio ? null : srv.url.trim(),
        enabled: srv.enabled,
        sandbox: stdio && srv.sandbox,
        trusted_tools: srv.trusted.split(',').map(t => t.trim()).filter(Boolean),
        roles: srv.roles.length ? srv.roles : null,
        token_env: stdio && srv.token_env.trim() ? srv.token_env.trim() : null,
      }
    }
    await apiFetch('/api/settings/mcp', { method: 'PUT', body })
    for (const srv of servers.value) {
      if (!srv.token.trim()) continue
      const saved = await apiFetch(`/api/settings/mcp/${encodeURIComponent(srv.name.trim())}/token`, { method: 'PUT', body: { token: srv.token.trim() } })
      srv.token = ''
      srv.token_hint = saved.token_hint
    }
    return 'Tools saved'
  })
}

// ─── Data ───
const RETENTION = [
  { days: null, label: 'Until I delete it' },
  { days: 30, label: '30 days after a run ends' },
  { days: 90, label: '90 days after a run ends' },
  { days: 180, label: '180 days after a run ends' },
  { days: 365, label: '1 year after a run ends' },
]
const DELETE_PHRASE = 'delete all data'
const retention = ref(null)
const deletePhrase = ref('')

watch(() => props.open, open => {
  if (!open) return
  retention.value = props.settings.data?.retention_days ?? null
  deletePhrase.value = ''
}, { immediate: true })

async function saveRetention() {
  await act('data', async () => {
    const res = await apiFetch('/api/settings/data', { method: 'PUT', body: { retention_days: retention.value } })
    const n = res.deleted_runs || 0
    return n ? `Saved. ${n} older run${n === 1 ? ' was' : 's were'} deleted.` : 'Saved'
  })
}

async function deleteAll() {
  busy.value = true
  notice.deleteAll = null
  try {
    const res = await apiFetch('/api/data/delete-all', { method: 'POST', body: { confirm: DELETE_PHRASE } })
    deletePhrase.value = ''
    if (res.problems?.length) {
      // Stay here so the user can read what's left, fix it and try again.
      notice.deleteAll = { ok: false, text: `Mostly deleted. ${res.problems.join(' ')}` }
      emit('data-deleted', { reload: false }) // the dashboard refreshes in place
    } else {
      notice.deleteAll = { ok: true, text: 'Everything is deleted.' }
      emit('data-deleted', { reload: true }) // the dashboard starts over
    }
  } catch (e) {
    notice.deleteAll = { ok: false, text: e.message }
  } finally {
    busy.value = false
  }
}

// ─── Sandbox ───
const sandbox = reactive({ active: false, problem: '' })
const sandboxForm = reactive({ enabled: false, image: '', timeout: 120 })

async function loadSandbox() {
  try {
    const s = await apiFetch('/api/sandbox')
    Object.assign(sandbox, s)
    Object.assign(sandboxForm, s.settings)
  } catch (e) {
    notice.sandbox = { ok: false, text: e.message }
  }
}
watch(tab, t => { if (t === 'sandbox') loadSandbox() })
watch(() => props.open, o => { if (o && tab.value === 'sandbox') loadSandbox() })

async function saveSandbox() {
  await act('sandbox', async () => {
    const s = await apiFetch('/api/sandbox', { method: 'PUT', body: { ...sandboxForm, image: sandboxForm.image.trim() } })
    Object.assign(sandbox, s)
    return s.active ? 'Saved. The sandbox is on.' : 'Saved'
  })
}

// ─── Theme ───
const theme = ref(savedThemeId() || 'midnight')
function pickTheme(t) {
  theme.value = t.id
  applyTheme(t)
}

async function act(section, fn) {
  busy.value = true
  notice[section] = null
  try {
    notice[section] = { ok: true, text: await fn() }
    emit('saved')
  } catch (e) {
    notice[section] = { ok: false, text: e.message }
  } finally {
    busy.value = false
  }
}
</script>
