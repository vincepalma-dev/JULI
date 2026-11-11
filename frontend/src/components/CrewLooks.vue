<template>
  <div class="space-y-6">
    <!-- Whose look -->
    <div class="flex flex-wrap gap-2" role="radiogroup" aria-label="Whose look to change">
      <button v-for="who in people" :key="who.id" type="button" role="radio" :aria-checked="selected === who.id" class="surface flex w-[5.5rem] flex-col items-center gap-1.5 px-2 py-2.5 transition-colors hover:bg-white/[0.04]" :class="selected === who.id ? '!border-white/40' : ''" @click="pick(who.id)">
        <AgentAvatar v-if="who.agent" :agent="who.agent" still />
        <span v-else class="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full border border-juli-border bg-white/[0.06]"><JuliMascot bust still :size="30" /></span>
        <span class="w-full truncate text-center text-xs text-slate-200">{{ who.label }}</span>
      </button>
    </div>

    <div class="grid gap-6 sm:grid-cols-[12rem_1fr]">
      <!-- Preview -->
      <div class="surface flex flex-col items-center gap-2 self-start p-4 sm:sticky sm:top-0">
        <JuliMascot :state="previewState" :size="152" v-bind="preview" />
        <p class="text-sm font-semibold text-white">{{ current.label }}</p>
        <p v-if="status[current.id]" class="text-xs" :class="status[current.id].ok ? 'text-emerald-300' : 'text-red-300'" role="status">{{ status[current.id].text }}</p>
        <div v-if="current.agent" class="flex gap-1.5" role="group" aria-label="Preview">
          <button type="button" class="btn btn-secondary !min-h-0 !py-1 text-xs" :class="working ? '' : '!border-white/40'" :aria-pressed="!working" @click="working = false">Idle</button>
          <button type="button" class="btn btn-secondary !min-h-0 !py-1 text-xs" :class="working ? '!border-white/40' : ''" :aria-pressed="working" @click="working = true">Working</button>
        </div>
        <p v-else class="hint text-center">Juli's own look is kept in this browser. Agents set to "Same as Juli" follow it.</p>
      </div>

      <div class="min-w-0 space-y-5">
        <fieldset>
          <legend class="label">Outfit</legend>
          <div class="grid grid-cols-3 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Outfit">
            <button v-for="o in choices(OUTFITS)" :key="o.id" type="button" role="radio" :aria-checked="value('outfit') === o.id" class="surface flex flex-col items-center gap-1 px-1 py-2 transition-colors hover:bg-white/[0.04]" :class="value('outfit') === o.id ? '!border-white/40' : ''" @click="set('outfit', o.id)">
              <JuliMascot still :size="64" :outfit="o.id" :accessory="preview.accessory" idle="calm" :accent="preview.accent" />
              <span class="text-center text-xs text-slate-200">{{ o.name }}</span>
            </button>
          </div>
        </fieldset>

        <fieldset>
          <legend class="label">Accessory</legend>
          <div class="grid grid-cols-3 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Accessory">
            <button v-for="a in choices(ACCESSORIES)" :key="a.id" type="button" role="radio" :aria-checked="value('accessory') === a.id" class="surface flex flex-col items-center gap-1 px-1 py-2 transition-colors hover:bg-white/[0.04]" :class="value('accessory') === a.id ? '!border-white/40' : ''" @click="set('accessory', a.id)">
              <JuliMascot bust still :size="48" :outfit="preview.outfit" :accessory="a.id" idle="calm" :accent="preview.accent" />
              <span class="text-center text-xs text-slate-200">{{ a.name }}</span>
            </button>
          </div>
          <p v-if="preview.outfit === 'space-suit' || preview.outfit === 'rider'" class="hint mt-1.5">This outfit's helmet takes the place of other headwear.</p>
        </fieldset>

        <fieldset>
          <legend class="label">Idle style</legend>
          <div class="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Idle style">
            <button v-for="i in choices(IDLES)" :key="i.id" type="button" role="radio" :aria-checked="value('idle') === i.id" class="surface px-3 py-2 text-left transition-colors hover:bg-white/[0.04]" :class="value('idle') === i.id ? '!border-white/40' : ''" @click="set('idle', i.id)">
              <span class="block text-sm font-medium text-white">{{ i.name }}</span>
              <span class="block text-xs text-slate-400">{{ i.desc }}</span>
            </button>
          </div>
        </fieldset>

        <fieldset v-if="current.agent">
          <legend class="label">Working pose</legend>
          <div class="flex flex-wrap gap-2" role="radiogroup" aria-label="Working pose">
            <button v-for="p in POSES" :key="p.id" type="button" role="radio" :aria-checked="value('pose') === p.id" class="surface px-3 py-1.5 text-sm text-slate-200 transition-colors hover:bg-white/[0.04]" :class="value('pose') === p.id ? '!border-white/40 text-white' : ''" @click="set('pose', p.id)">{{ p.name }}</button>
          </div>
          <p class="hint mt-1.5">What {{ current.label }} looks like while it works. "By role" picks the pose from its role.</p>
        </fieldset>
      </div>
    </div>
  </div>
</template>

<script setup>
// The Looks tab of the crew builder: dress Juli and each crew member, and
// choose how each one idles and works. An agent's look is saved with the
// agent; Juli's own is kept in this browser.
import { ref, computed } from 'vue'
import AgentAvatar from './AgentAvatar.vue'
import JuliMascot from './JuliMascot.vue'
import { agentLabel, turnMascot } from '../labels.js'
import { OUTFITS, ACCESSORIES, IDLES, POSES, agentLook, mascotLook, setLook } from '../mascot.js'

const props = defineProps({
  agents: { type: Object, default: () => ({}) },
  status: { type: Object, default: () => ({}) }, // per agent: how its last save went
})
const emit = defineEmits(['save'])

const JULI = '' // not a valid agent name
const SAME = { id: 'default', name: 'Same as Juli', desc: "Follows Juli's own look" }

const people = computed(() => [
  { id: JULI, label: 'Juli' },
  ...Object.entries(props.agents).map(([name, agent]) => ({ id: name, label: agentLabel(name, props.agents), agent })),
])
const selected = ref(JULI)
const working = ref(false)
// Falls back to Juli if the chosen agent is removed.
const current = computed(() => people.value.find(p => p.id === selected.value) || people.value[0])

function pick(id) {
  selected.value = id
  working.value = false
}

// An agent may also follow Juli.
const choices = list => (current.value.agent ? [SAME, ...list] : list)

function value(part) {
  if (!current.value.agent) return mascotLook[part]
  return current.value.agent[part] || (part === 'pose' ? 'auto' : 'default')
}

function set(part, id) {
  if (!current.value.agent) return setLook(part, id)
  if (part === 'pose') working.value = true
  emit('save', current.value.id, { [part]: id })
}

const preview = computed(() => (current.value.agent ? agentLook(current.value.agent) : { ...mascotLook, accent: '' }))
const previewState = computed(() => {
  if (!working.value || !current.value.agent) return 'idle'
  return turnMascot({ agent: current.value.id, role: current.value.agent.role }, true, props.agents)
})
</script>
