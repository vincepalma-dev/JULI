<template>
  <svg
    class="juli-mascot"
    :class="{ 'juli-mascot--still': still }"
    :width="size"
    :height="size"
    viewBox="0 0 256 256"
    aria-hidden="true"
    focusable="false"
  >
    <!-- The crew talking it over: three small Julis -->
    <template v-if="safeState === 'discussion'">
      <g v-for="(member, i) in CREW" :key="member.accent" :transform="member.at">
        <JuliFigure state="discussion" :accent="member.accent" :delay="i * 0.6" :still="still" />
      </g>
      <g class="juli-fx" stroke="#1a1625" stroke-linejoin="round">
        <rect x="106" y="28" width="44" height="26" rx="11" fill="#ffffff" stroke-width="5.5" />
        <circle v-for="x in [118, 128, 138]" :key="x" class="juli-dot" :cx="x" cy="41" r="3.4" fill="#0d9488" stroke="none" />
      </g>
    </template>

    <template v-else>
      <JuliFigure :state="safeState" :still="still" />
      <g v-if="safeState === 'waiting'" class="juli-fx juli-bubble" stroke-linecap="round" stroke-linejoin="round">
        <path d="M186 60 H212 A10 10 0 0 1 222 70 V80 A10 10 0 0 1 212 90 H192 L182 98 L184 89 A10 10 0 0 1 176 80 V70 A10 10 0 0 1 186 60 Z" fill="#ffffff" stroke="#1a1625" stroke-width="5.5" />
        <path d="M194 71 Q199 65 204 70 Q206 74 199 78" fill="none" stroke="#0d9488" stroke-width="4" />
        <circle cx="199" cy="84" r="2.3" fill="#0d9488" />
      </g>
      <g v-else-if="safeState === 'follow-up'" class="juli-fx juli-bubble" stroke-linejoin="round">
        <path d="M186 60 H214 A10 10 0 0 1 224 70 V80 A10 10 0 0 1 214 90 H192 L182 98 L184 89 A10 10 0 0 1 176 80 V70 A10 10 0 0 1 186 60 Z" fill="#ffffff" stroke="#1a1625" stroke-width="5.5" />
        <circle v-for="x in [190, 200, 210]" :key="x" class="juli-dot" :cx="x" cy="75" r="3.2" fill="#0891b2" />
      </g>
      <g v-else-if="safeState === 'coder-thinking'" class="juli-fx" fill="#ffffff" stroke="#1a1625" stroke-width="4.5">
        <circle class="juli-dot" cx="184" cy="66" r="4.5" />
        <circle class="juli-dot" cx="197" cy="50" r="6.5" />
        <circle class="juli-dot" cx="214" cy="30" r="9.5" />
      </g>
      <g v-else-if="safeState === 'done'" class="juli-fx" fill="#10b981">
        <path v-for="s in SPARKLES" :key="s.at" class="juli-sparkle" :transform="s.at" d="M0 -10 Q1.5 -1.5 10 0 Q1.5 1.5 0 10 Q-1.5 1.5 -10 0 Q-1.5 -1.5 0 -10 Z" />
      </g>
      <path v-else-if="safeState === 'error'" class="juli-fx juli-sweat" d="M190 64 Q200 80 190 86 Q180 80 190 64 Z" fill="#7dd3fc" stroke="#1a1625" stroke-width="4.5" stroke-linejoin="round" />
    </template>
  </svg>
</template>

<script setup>
/**
 * Juli, the mascot: an SVG drawing that CSS animates. This is the frame around
 * her (the size, and the speech bubbles and sparkles some states have);
 * JuliFigure is Juli herself. `still` holds the pose without motion, as does
 * prefers-reduced-motion. Decorative only (aria-hidden): the text beside it
 * carries the meaning.
 */
import { computed } from 'vue'
import JuliFigure from './JuliFigure.vue'
import { MASCOT_STATES } from '../labels.js'

const props = defineProps({
  state: { type: String, default: 'idle' },
  size: { type: Number, default: 40 },
  still: { type: Boolean, default: false },
})

const safeState = computed(() => (MASCOT_STATES.includes(props.state) ? props.state : 'idle'))

// Where the three stand, and the lanyard each wears.
const CREW = [
  { accent: '#6366f1', at: 'translate(2 96) scale(0.52)' },
  { accent: '#ef4444', at: 'translate(121 96) scale(0.52)' },
  { accent: '#0d9488', at: 'translate(55 102) scale(0.57)' },
]

const SPARKLES = [
  { at: 'translate(62 62)' },
  { at: 'translate(196 70) scale(0.8)' },
  { at: 'translate(48 128) scale(0.55)' },
  { at: 'translate(208 132) scale(0.6)' },
]
</script>

<style scoped>
.juli-mascot {
  display: inline-block;
  flex-shrink: 0;
  overflow: visible;
  pointer-events: none;
}

.juli-bubble { animation: juli-bob 2.2s ease-in-out infinite; }

.juli-dot { animation: juli-dot 1.2s ease-in-out infinite; }
.juli-dot:nth-of-type(2) { animation-delay: 0.2s; }
.juli-dot:nth-of-type(3) { animation-delay: 0.4s; }

/* The fill box, so each sparkle turns about its own centre. */
.juli-sparkle {
  transform-box: fill-box;
  transform-origin: center;
  animation: juli-twinkle 1.6s ease-in-out infinite;
}
.juli-sparkle:nth-of-type(2) { animation-delay: 0.4s; }
.juli-sparkle:nth-of-type(3) { animation-delay: 0.8s; }
.juli-sparkle:nth-of-type(4) { animation-delay: 1.2s; }

.juli-sweat { animation: juli-drip 1.8s ease-in infinite; }

@keyframes juli-bob { 50% { transform: translateY(-4px); } }
@keyframes juli-dot {
  0%, 60%, 100% { opacity: 0.35; }
  30% { opacity: 1; }
}
@keyframes juli-twinkle {
  0%, 100% { opacity: 0.25; scale: 0.6; }
  50% { opacity: 1; scale: 1; }
}
@keyframes juli-drip {
  0% { transform: translateY(-4px); opacity: 0; }
  25% { opacity: 1; }
  100% { transform: translateY(16px); opacity: 0; }
}

.juli-mascot--still .juli-fx,
.juli-mascot--still .juli-fx * { animation: none !important; }

@media (prefers-reduced-motion: reduce) {
  .juli-fx,
  .juli-fx * { animation: none !important; }
}
</style>
