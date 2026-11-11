<template>
  <SidePanel :open="open" title="Models" icon="cube" wide @close="$emit('close')">
    <template #tabs>
      <div class="tab-bar" role="tablist" aria-label="Model sources">
        <button v-for="t in TABS" :key="t.id" type="button" role="tab" class="tab" :aria-selected="tab === t.id" @click="tab = t.id">{{ t.label }}</button>
      </div>
    </template>

    <!-- This machine -->
    <section class="surface mb-5 grid gap-x-6 gap-y-2 p-4 text-sm sm:grid-cols-2" aria-label="This machine">
      <h3 class="flex items-center gap-2 font-semibold text-white sm:col-span-2"><Icon name="cpu" class="h-4 w-4 text-slate-400" />This machine</h3>
      <template v-if="hw">
        <p class="text-slate-300">{{ hw.cpu || 'CPU' }} · {{ hw.cores }} cores</p>
        <p class="text-slate-300">{{ hw.ram_gb?.toFixed(1) }} GB RAM · {{ hw.disk_free_gb?.toFixed(0) }} GB free for models</p>
        <p class="text-slate-300">{{ hw.gpu ? `${hw.gpu.name} · ${hw.gpu.vram_gb ?? '?'} GB` : 'No supported GPU: models run on the CPU' }}</p>
        <p class="text-slate-300">Room for models: {{ hw.budgets.gpu_gb }} GB on the GPU, {{ hw.budgets.total_gb }} GB in total</p>
      </template>
      <p v-else class="text-slate-400">Reading the hardware…</p>
      <p class="flex flex-wrap items-center gap-2 sm:col-span-2">
        <span v-if="!ollama" class="badge bg-slate-500/20 text-slate-300">Checking Ollama…</span>
        <span v-else class="badge" :class="ollama.running ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-200'">{{ ollama.running ? `Ollama ${ollama.version}` : 'Ollama is not running' }}</span>
        <span v-if="ollama && !ollama.running" class="text-xs text-slate-400">Start it with <code class="font-mono">ollama serve</code>, then refresh.</span>
        <button type="button" class="btn btn-secondary ml-auto !min-h-0 !py-1 text-xs" @click="load"><Icon name="refresh" class="h-3.5 w-3.5" />Refresh</button>
      </p>
    </section>

    <p v-if="error" role="alert" class="mb-4 text-sm text-red-300">{{ error }}</p>

    <!-- Installed -->
    <section v-if="tab === 'installed'">
      <p v-if="loading.models && !installed.length" class="text-sm text-slate-400" role="status">Checking installed models…</p>
      <p v-else-if="!installed.length" class="text-sm text-slate-400">{{ ollama?.running ? 'No models installed yet. Pick one from the catalogue.' : 'Start Ollama to see installed models.' }}</p>
      <ul class="space-y-2">
        <li v-for="m in installed" :key="m.name" class="surface flex flex-wrap items-center gap-x-3 gap-y-2 p-3">
          <div class="min-w-0 flex-1">
            <p class="font-mono text-sm text-slate-100" style="overflow-wrap: anywhere">{{ m.name }}</p>
            <p class="text-xs text-slate-400">
              {{ formatBytes(m.size) }}
              <template v-if="m.benchmark"> · {{ m.benchmark.tok_per_sec.toFixed(1) }} tok/s on this machine</template>
              <template v-else> · speed not measured</template>
            </p>
          </div>
          <button type="button" class="btn btn-secondary !min-h-0 !py-1 text-xs" :disabled="benching === m.name" @click="bench(m.name)"><Icon name="gauge" class="h-3.5 w-3.5" />{{ benching === m.name ? 'Measuring…' : 'Measure speed' }}</button>
          <template v-if="deleting === m.name">
            <button type="button" class="btn btn-danger !min-h-0 !py-1 text-xs" @click="removeModel(m.name)">Delete {{ formatBytes(m.size) }}</button>
            <button type="button" class="btn btn-secondary !min-h-0 !py-1 text-xs" @click="deleting = null">Keep</button>
          </template>
          <button v-else type="button" class="icon-btn hover:!text-red-300" :aria-label="`Delete ${m.name}`" @click="deleting = m.name"><Icon name="trash" class="h-4 w-4" /></button>
        </li>
      </ul>
    </section>

    <!-- Catalogue -->
    <section v-else-if="tab === 'catalogue'" class="grid gap-3 sm:grid-cols-2">
      <p v-if="loading.catalogue && !catalogue.length" class="text-sm text-slate-400 sm:col-span-2" role="status">Checking which models fit this machine…</p>
      <article v-for="m in catalogue" :key="m.tag" class="surface flex flex-col gap-2 p-4" :class="m.fit.tier === 'cannot' && !m.installed ? 'opacity-60' : ''">
        <div class="flex items-start gap-2">
          <h3 class="min-w-0 flex-1 font-mono text-sm text-slate-100">{{ m.tag }}</h3>
          <span class="badge" :class="fitTone(m)">{{ fitLabel(m) }}</span>
        </div>
        <p class="text-xs text-slate-400">{{ m.size_gb }} GB · {{ Math.round((m.context_max || 0) / 1024) }}K context · {{ m.roles.join(', ') }}<template v-if="m.note"> · {{ m.note }}</template></p>
        <p v-if="m.fit.reason" class="text-xs text-amber-200/90">{{ capitalise(m.fit.reason) }}</p>
        <p class="text-xs text-slate-400">
          <a :href="m.license.url" target="_blank" rel="noopener noreferrer" class="underline decoration-slate-600 underline-offset-2 hover:text-slate-200">{{ m.license.name }}</a>
          <template v-if="m.license.accept">{{ m.license.accepted ? ' · accepted' : ' · must be accepted before download' }}</template>
        </p>
        <PullControl class="mt-auto" :tag="m.tag" :installed="m.installed" :blocked="m.fit.tier === 'cannot'" :progress="progress(m.tag)" :license="licenseAsk[m.tag]" @pull="pull(m.tag)" @cancel="cancel(m.tag)" @accept="accept(m.tag)" />
      </article>
    </section>

    <!-- Bring your own -->
    <section v-else class="space-y-8">
      <div>
        <h3 class="mb-1 text-sm font-semibold text-white">A GGUF model from Hugging Face</h3>
        <p class="hint mb-3">Paste a repo with GGUF files. Each quantisation gets a fit check for this machine.</p>
        <form class="flex gap-2" @submit.prevent="lookup">
          <label for="hf-repo" class="sr-only">Hugging Face repo</label>
          <input id="hf-repo" v-model="repo" class="field font-mono" placeholder="bartowski/Llama-3.2-1B-Instruct-GGUF" spellcheck="false" autocomplete="off" />
          <button type="submit" class="btn btn-secondary shrink-0" :disabled="!repo.includes('/') || looking">{{ looking ? 'Looking…' : 'Look up' }}</button>
        </form>
        <div v-if="hf" class="mt-3 space-y-2">
          <p class="text-xs text-slate-400">
            <a :href="hf.license.url" target="_blank" rel="noopener noreferrer" class="underline underline-offset-2">{{ hf.license.name }}</a>
            {{ hf.license.accepted ? '· accepted' : hf.license.accept ? '· must be accepted before download' : '' }}
          </p>
          <p v-if="!hf.models.length" class="text-sm text-slate-400">No GGUF files in this repo.</p>
          <div v-for="m in hf.models" :key="m.tag" class="surface flex flex-wrap items-center gap-3 p-3" :class="m.fit.tier === 'cannot' && !m.installed ? 'opacity-60' : ''">
            <div class="min-w-0 flex-1">
              <p class="font-mono text-sm text-slate-100">{{ m.quant }}</p>
              <p class="text-xs text-slate-400">{{ m.size_gb }} GB<template v-if="m.fit.reason"> · {{ m.fit.reason }}</template></p>
            </div>
            <span class="badge" :class="fitTone(m)">{{ fitLabel(m) }}</span>
            <PullControl class="w-full sm:w-56" :tag="m.tag" :installed="m.installed" :blocked="m.fit.tier === 'cannot'" :progress="progress(m.tag)" :license="licenseAsk[m.tag]" @pull="pull(m.tag)" @cancel="cancel(m.tag)" @accept="accept(m.tag)" />
          </div>
        </div>
      </div>

      <div>
        <h3 class="mb-1 text-sm font-semibold text-white">An OpenAI-compatible server</h3>
        <p class="hint mb-3">LM Studio, llama.cpp, vLLM and others. Plain http is allowed only on this machine or your local network.</p>
        <ul class="mb-3 space-y-2">
          <li v-for="e in endpoints" :key="e.id" class="surface flex flex-wrap items-center gap-3 p-3">
            <div class="min-w-0 flex-1">
              <p class="text-sm text-slate-100">{{ e.label }} <span class="font-mono text-xs text-slate-400">({{ e.id }})</span></p>
              <p class="font-mono text-xs text-slate-400" style="overflow-wrap: anywhere">{{ e.base_url }}</p>
            </div>
            <span class="badge" :class="e.local ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-200'">{{ e.local ? 'Local' : 'Remote' }}</span>
            <button type="button" class="icon-btn hover:!text-red-300" :aria-label="`Remove ${e.label}`" @click="removeEndpoint(e.id)"><Icon name="trash" class="h-4 w-4" /></button>
          </li>
        </ul>
        <form class="surface grid gap-3 p-4 sm:grid-cols-2" @submit.prevent="addEndpoint">
          <div>
            <label for="ep-id" class="label">Id (used in model refs)</label>
            <input id="ep-id" v-model="endpoint.id" class="field font-mono" pattern="[a-z][a-z0-9_]{0,31}" placeholder="lmstudio" required spellcheck="false" autocomplete="off" />
          </div>
          <div>
            <label for="ep-label" class="label">Name</label>
            <input id="ep-label" v-model="endpoint.label" maxlength="60" class="field" placeholder="LM Studio" required />
          </div>
          <div class="sm:col-span-2">
            <label for="ep-url" class="label">Base URL</label>
            <input id="ep-url" v-model="endpoint.base_url" class="field font-mono" placeholder="http://localhost:1234/v1" required spellcheck="false" autocomplete="off" />
          </div>
          <div class="sm:col-span-2">
            <label for="ep-key" class="label">API key (optional)</label>
            <input id="ep-key" v-model="endpoint.key" type="password" maxlength="500" class="field font-mono" autocomplete="off" />
          </div>
          <p class="flex items-start gap-2 rounded-lg border border-amber-400/25 bg-amber-400/[0.06] px-3 py-2 text-xs leading-relaxed text-amber-100 sm:col-span-2">
            <Icon name="alert" class="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            <span><strong class="font-semibold">A server you don't run is a third party.</strong> It receives everything the agents using it send: your prompts, your code and the files they read. Add only servers you trust, and check their terms. Privacy Mode blocks every server outside this machine and your local network.</span>
          </p>
          <div class="flex flex-wrap items-center gap-3 sm:col-span-2">
            <button type="submit" class="btn btn-primary" :disabled="adding">{{ adding ? 'Testing…' : 'Add and test' }}</button>
            <p v-if="endpointResult" class="text-sm" :class="endpointResult.ok ? 'text-emerald-300' : 'text-amber-200'" role="status">{{ endpointResult.text }}</p>
          </div>
        </form>
      </div>
    </section>
  </SidePanel>
</template>

<script setup>
// On-device models: this machine, installed models with measured speed, the
// catalogue with fit checks (greyed out with a reason when a model won't fit),
// downloads with progress, and your own GGUF repos or OpenAI-compatible servers.
import { ref, reactive, computed, watch } from 'vue'
import Icon from './Icon.vue'
import SidePanel from './SidePanel.vue'
import PullControl from './PullControl.vue'
import { apiFetch } from '../api.js'
import { formatBytes } from '../labels.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  pulls: { type: Object, default: () => ({}) }, // live pull_progress by model
  providers: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'changed'])

const TABS = [
  { id: 'installed', label: 'Installed' },
  { id: 'catalogue', label: 'Catalogue' },
  { id: 'own', label: 'Bring your own' },
]
const tab = ref('installed')
const hw = ref(null)
const ollama = ref(null)
const installed = ref([])
const catalogue = ref([])
const knownPulls = ref({}) // pulls already going when the panel opened
const error = ref('')

const loading = reactive({ models: false, catalogue: false })

// Each part shows as soon as it arrives: with Ollama down, its checks are the slow ones.
function load() {
  error.value = ''
  const fail = e => { error.value = e.message }
  apiFetch('/api/local/hardware').then(h => { hw.value = h }).catch(fail)
  apiFetch('/api/local/pulls').then(list => { knownPulls.value = Object.fromEntries(list.map(p => [p.model, p])) }).catch(fail)
  loading.models = true
  const models = apiFetch('/api/local/models')
    .then(m => { ollama.value = m.ollama; installed.value = m.installed })
    .catch(fail)
    .finally(() => { loading.models = false })
  loading.catalogue = true
  const cat = apiFetch('/api/local/catalogue')
    .then(c => { catalogue.value = c.models; ollama.value = c.ollama })
    .catch(fail)
    .finally(() => { loading.catalogue = false })
  return Promise.all([models, cat])
}
watch(() => props.open, o => { if (o) load() }, { immediate: true })

const progress = tag => props.pulls[tag] || knownPulls.value[tag] || null

// A finished download shows up as installed.
watch(() => Object.values(props.pulls).filter(p => p.status === 'success').length, n => { if (n && props.open) { load(); emit('changed') } })

function fitLabel(m) {
  if (m.installed) return 'Installed'
  return { great: 'Runs well', slow: 'Runs slowly', cannot: "Won't fit" }[m.fit.tier] || m.fit.tier
}
function fitTone(m) {
  if (m.installed) return 'bg-cyan-500/15 text-cyan-200'
  return { great: 'bg-emerald-500/15 text-emerald-300', slow: 'bg-amber-500/15 text-amber-200' }[m.fit.tier] || 'bg-red-500/15 text-red-300'
}
const capitalise = s => s.charAt(0).toUpperCase() + s.slice(1)

// ─── Downloads ───
const licenseAsk = reactive({}) // tag -> licence that must be accepted first

async function pull(tag) {
  error.value = ''
  try {
    const job = await apiFetch('/api/local/pulls', { method: 'POST', body: { model: tag } })
    knownPulls.value = { ...knownPulls.value, [tag]: job }
    delete licenseAsk[tag]
  } catch (e) {
    if (e.status === 409 && e.detail?.license) licenseAsk[tag] = e.detail.license
    else error.value = e.message
  }
}

async function accept(tag) {
  try {
    await apiFetch('/api/local/licenses', { method: 'POST', body: { license: licenseAsk[tag].id } })
    await pull(tag)
  } catch (e) {
    error.value = e.message
  }
}

async function cancel(tag) {
  try {
    await apiFetch(`/api/local/pulls/${tag}`, { method: 'DELETE' })
  } catch (e) {
    error.value = e.message
  }
}

// ─── Installed ───
const benching = ref(null)
const deleting = ref(null)

async function bench(name) {
  benching.value = name
  error.value = ''
  try {
    await apiFetch('/api/local/benchmark', { method: 'POST', body: { model: name } })
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    benching.value = null
  }
}

async function removeModel(name) {
  deleting.value = null
  try {
    await apiFetch(`/api/local/models/${name}`, { method: 'DELETE' })
    await load()
    emit('changed')
  } catch (e) {
    error.value = e.message
  }
}

// ─── Bring your own ───
const repo = ref('')
const hf = ref(null)
const looking = ref(false)

async function lookup() {
  looking.value = true
  error.value = ''
  try {
    hf.value = await apiFetch(`/api/local/hf?repo=${encodeURIComponent(repo.value.trim())}`)
  } catch (e) {
    error.value = e.message
  } finally {
    looking.value = false
  }
}

const endpoints = computed(() => props.providers.filter(p => p.custom))
const endpoint = reactive({ id: '', label: '', base_url: '', key: '' })
const adding = ref(false)
const endpointResult = ref(null)

async function addEndpoint() {
  adding.value = true
  endpointResult.value = null
  try {
    const res = await apiFetch('/api/providers/endpoints', {
      method: 'POST',
      body: { id: endpoint.id.trim(), label: endpoint.label.trim(), base_url: endpoint.base_url.trim(), key: endpoint.key.trim() || null },
    })
    const ok = res.health?.status === 'ok'
    endpointResult.value = { ok, text: ok ? `Added ${res.label}. It answers.` : `Added ${res.label}, but it didn't answer: ${res.health?.detail || res.health?.status}` }
    Object.assign(endpoint, { id: '', label: '', base_url: '', key: '' })
    emit('changed')
  } catch (e) {
    endpointResult.value = { ok: false, text: e.message }
  } finally {
    adding.value = false
  }
}

async function removeEndpoint(id) {
  try {
    await apiFetch(`/api/providers/endpoints/${encodeURIComponent(id)}`, { method: 'DELETE' })
    emit('changed')
  } catch (e) {
    error.value = e.message
  }
}
</script>
