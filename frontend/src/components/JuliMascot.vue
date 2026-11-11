<template>
  <svg
    class="juli-mascot"
    :class="{ 'juli-mascot--still': still, 'juli-mascot--bust': bust }"
    :width="size"
    :height="size"
    :viewBox="bust ? '56 12 144 144' : '0 0 256 256'"
    aria-hidden="true"
    focusable="false"
  >
    <!-- The crew talking it over: three small Julis -->
    <template v-if="safeState === 'discussion'">
      <g v-for="(member, i) in CREW" :key="member.accent" :transform="member.at">
        <JuliFigure state="discussion" v-bind="wear" :accent="member.accent" :delay="i * 0.6" :still="still" />
      </g>
      <g class="juli-fx" stroke="#1a1625" stroke-linejoin="round">
        <rect x="106" y="28" width="44" height="26" rx="11" fill="#ffffff" stroke-width="5.5" />
        <circle v-for="x in [118, 128, 138]" :key="x" class="juli-dot" :cx="x" cy="41" r="3.4" fill="#0d9488" stroke="none" />
      </g>
    </template>

    <template v-else>
      <JuliFigure :state="safeState" v-bind="wear" :idle="idleStyle" :accent="accent" :still="still" />
      <!-- What floats around her. The bust has no room for it. -->
      <template v-if="!bust">
        <g v-if="fx === 'waiting'" class="juli-fx juli-bubble" stroke-linecap="round" stroke-linejoin="round">
          <path d="M186 60 H212 A10 10 0 0 1 222 70 V80 A10 10 0 0 1 212 90 H192 L182 98 L184 89 A10 10 0 0 1 176 80 V70 A10 10 0 0 1 186 60 Z" fill="#ffffff" stroke="#1a1625" stroke-width="5.5" />
          <path d="M194 71 Q199 65 204 70 Q206 74 199 78" fill="none" stroke="#0d9488" stroke-width="4" />
          <circle cx="199" cy="84" r="2.3" fill="#0d9488" />
        </g>
        <g v-else-if="fx === 'follow-up'" class="juli-fx juli-bubble" stroke-linejoin="round">
          <path d="M186 60 H214 A10 10 0 0 1 224 70 V80 A10 10 0 0 1 214 90 H192 L182 98 L184 89 A10 10 0 0 1 176 80 V70 A10 10 0 0 1 186 60 Z" fill="#ffffff" stroke="#1a1625" stroke-width="5.5" />
          <circle v-for="x in [190, 200, 210]" :key="x" class="juli-dot" :cx="x" cy="75" r="3.2" fill="#0891b2" />
        </g>
        <g v-else-if="fx === 'coder-thinking'" class="juli-fx" fill="#ffffff" stroke="#1a1625" stroke-width="4.5">
          <circle class="juli-dot" cx="184" cy="66" r="4.5" />
          <circle class="juli-dot" cx="197" cy="50" r="6.5" />
          <circle class="juli-dot" cx="214" cy="30" r="9.5" />
        </g>
        <g v-else-if="fx === 'done'" class="juli-fx" fill="#10b981">
          <path v-for="s in SPARKLES" :key="s.at" class="juli-sparkle" :transform="s.at" d="M0 -10 Q1.5 -1.5 10 0 Q1.5 1.5 0 10 Q-1.5 1.5 -10 0 Q-1.5 -1.5 0 -10 Z" />
        </g>
        <path v-else-if="fx === 'error'" class="juli-fx juli-sweat" d="M190 64 Q200 80 190 86 Q180 80 190 64 Z" fill="#7dd3fc" stroke="#1a1625" stroke-width="4.5" stroke-linejoin="round" />
        <!-- Analysing: a chart she points at, its bars growing -->
        <g v-else-if="fx === 'analyst'" class="juli-fx juli-bubble" stroke="#1a1625" stroke-linecap="round" stroke-linejoin="round">
          <rect x="188" y="52" width="56" height="50" rx="8" fill="#ffffff" stroke-width="5.5" />
          <rect v-for="(bar, i) in BARS" :key="bar.x" class="juli-bar" :class="`juli-bar--${i}`" :x="bar.x" :y="94 - bar.h" width="9" :height="bar.h" rx="2" :fill="accent || '#3b82f6'" stroke="none" />
        </g>
        <!-- Dancing: notes drifting up -->
        <g v-else-if="fx === 'dance'" class="juli-fx" fill="#f472b6" stroke="#f472b6" stroke-width="4" stroke-linecap="round">
          <g v-for="at in ['translate(196 86)', 'translate(52 70) scale(0.8)']" :key="at" :transform="at">
            <g class="juli-note">
              <path d="M4 6 V-14 L16 -18 V2" fill="none" />
              <ellipse cx="0" cy="7" rx="5" ry="4" stroke="none" />
              <ellipse cx="12" cy="3" rx="5" ry="4" stroke="none" />
            </g>
          </g>
        </g>
        <!-- Napping: Zs drifting up -->
        <g v-else-if="fx === 'nap'" class="juli-fx" fill="none" stroke="#94a3b8" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round">
          <g v-for="at in ['translate(182 76) scale(0.7)', 'translate(196 54)', 'translate(214 26) scale(1.3)']" :key="at" :transform="at">
            <path class="juli-note" d="M-6 -6 H6 L-6 6 H6" />
          </g>
        </g>
        <!-- Riding: the road rushing past on both sides -->
        <g v-else-if="fx === 'ride'" class="juli-fx" fill="none" stroke="#94a3b8" stroke-width="4" stroke-linecap="round">
          <path v-for="d in SPEED_LINES" :key="d" class="juli-speed" :d="d" />
        </g>
      </template>
    </template>
  </svg>
</template>

<script setup>
/**
 * Juli, the mascot: an SVG drawing that CSS animates. This is the frame around
 * her (the size, and the speech bubbles and sparkles some states have);
 * JuliFigure is Juli herself. Without `outfit`, `accessory` or `idle` she
 * wears Juli's own look (mascot.js). `still` holds the pose without motion, as
 * does prefers-reduced-motion; `bust` shows her head and shoulders, for small
 * avatars. Decorative only (aria-hidden): the text beside it carries the meaning.
 */
import { computed, watchEffect } from 'vue'
import JuliFigure from './JuliFigure.vue'
import { MASCOT_STATES } from '../labels.js'
import { lookOf, shuffledIdle, startShuffle } from '../mascot.js'

const props = defineProps({
  state: { type: String, default: 'idle' },
  size: { type: Number, default: 40 },
  still: { type: Boolean, default: false },
  bust: { type: Boolean, default: false },
  outfit: { type: String, default: '' },
  accessory: { type: String, default: '' },
  idle: { type: String, default: '' },
  // An agent's colour, for the lanyard and hair clip. Empty: the state's own.
  accent: { type: String, default: '' },
})

const safeState = computed(() => (MASCOT_STATES.includes(props.state) ? props.state : 'idle'))

const look = computed(() => lookOf(props))
const wear = computed(() => ({ outfit: look.value.outfit, accessory: look.value.accessory }))
const idleStyle = computed(() => (look.value.idle === 'shuffle' ? shuffledIdle.value : look.value.idle))
watchEffect(() => { if (look.value.idle === 'shuffle' && !props.still) startShuffle() })

// Which floating extras to draw: a state's, or an idle style's.
const fx = computed(() => (safeState.value === 'idle' ? idleStyle.value : safeState.value))

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

const BARS = [{ x: 197, h: 14 }, { x: 211, h: 24 }, { x: 225, h: 34 }]
const SPEED_LINES = ['M40 150 V172', 'M22 186 V214', 'M216 150 V172', 'M234 186 V214']
</script>

<style scoped>
.juli-mascot {
  display: inline-block;
  flex-shrink: 0;
  overflow: visible;
  pointer-events: none;
}

/* The bust is a crop: the rest of her stays out of sight. */
.juli-mascot--bust { overflow: hidden; }

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

/* Bars grow from the chart's floor. */
.juli-bar {
  transform-box: fill-box;
  transform-origin: bottom;
  animation: juli-grow 2.4s ease-in-out infinite;
}
.juli-bar--1 { animation-delay: 0.25s; }
.juli-bar--2 { animation-delay: 0.5s; }

.juli-note { animation: juli-drift 2.4s ease-out infinite; }
g:nth-of-type(2) > .juli-note { animation-delay: 0.8s; }
g:nth-of-type(3) > .juli-note { animation-delay: 1.6s; }

.juli-speed { animation: juli-rush 0.7s linear infinite; }
.juli-speed:nth-of-type(2n) { animation-delay: 0.35s; }

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
@keyframes juli-grow {
  0%, 100% { transform: scaleY(0.35); }
  50%, 80% { transform: scaleY(1); }
}
@keyframes juli-drift {
  0% { transform: translateY(8px); opacity: 0; }
  25% { opacity: 1; }
  100% { transform: translateY(-22px); opacity: 0; }
}
@keyframes juli-rush {
  0% { transform: translateY(-16px); opacity: 0; }
  30% { opacity: 0.9; }
  100% { transform: translateY(30px); opacity: 0; }
}

.juli-mascot--still .juli-fx,
.juli-mascot--still .juli-fx * { animation: none !important; }

@media (prefers-reduced-motion: reduce) {
  .juli-fx,
  .juli-fx * { animation: none !important; }
}
</style>
