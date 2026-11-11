<template>
  <!-- A speaker outside the crew (System, a removed agent) has no Juli -->
  <AgentOrb v-if="!agent" icon="system" :color="color" :active="active" size="sm" />
  <div v-else class="relative inline-flex h-8 w-8 shrink-0 items-center justify-center">
    <div v-if="active" class="animate-pulse-glow absolute inset-0 rounded-full" :style="{ color: tint, boxShadow: `0 0 8px ${tint}40, 0 0 20px ${tint}20` }"></div>
    <div class="relative flex h-8 w-8 items-center justify-center overflow-hidden rounded-full" :style="{ background: `radial-gradient(circle at 35% 35%, ${tint}40, ${tint}14)`, border: `1.5px solid ${tint}${active ? '90' : '45'}` }">
      <JuliMascot bust :size="30" v-bind="agentLook(agent)" :still="still" />
    </div>
    <div v-if="active" class="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-juli-panel bg-emerald-500"></div>
  </div>
</template>

<script setup>
// A crew member's face: its own Juli (outfit, accessory and idle style from
// its settings) in a ring of the agent's colour.
import { computed } from 'vue'
import AgentOrb from './AgentOrb.vue'
import JuliMascot from './JuliMascot.vue'
import { agentLook } from '../mascot.js'

const props = defineProps({
  agent: { type: Object, default: null }, // the agent's settings; none for a speaker outside the crew
  color: { type: String, default: '#94a3b8' }, // for a speaker outside the crew
  active: { type: Boolean, default: false },
  still: { type: Boolean, default: false },
})

const tint = computed(() => props.agent?.color || props.color)
</script>
