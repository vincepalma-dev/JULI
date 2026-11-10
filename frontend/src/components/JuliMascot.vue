<template>
  <span
    class="juli-mascot"
    :class="{ 'juli-mascot--once': once }"
    :style="{
      '--juli-size': `${size}px`,
      '--juli-sprite': `url('/mascot/sprites/juli-${safeState}-16f.webp')`,
      '--juli-still': `url('/mascot/stills/juli-${safeState}.png')`,
    }"
    aria-hidden="true"
  ></span>
</template>

<script setup>
/**
 * Juli, the mascot. Each state is a 16-frame horizontal WebP strip played with
 * CSS steps() at 12 fps; prefers-reduced-motion shows the state's still PNG.
 * Decorative only (aria-hidden): the text beside it carries the meaning.
 */
import { computed } from 'vue'
import { MASCOT_STATES } from '../labels.js'

const props = defineProps({
  state: { type: String, default: 'idle' },
  size: { type: Number, default: 40 },
})

const safeState = computed(() => (MASCOT_STATES.includes(props.state) ? props.state : 'idle'))
// "Done" plays once and holds its last frame; every other state loops.
const once = computed(() => safeState.value === 'done')

preload()
</script>

<script>
// Fetch every strip once per page, so switching states doesn't flash an empty frame.
let preloaded = false
function preload() {
  // No window or matchMedia (e.g. a test DOM): nothing to preload.
  if (preloaded || typeof window === 'undefined' || !window.matchMedia) return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  preloaded = true
  setTimeout(() => {
    for (const s of MASCOT_STATES) new Image().src = `/mascot/sprites/juli-${s}-16f.webp`
  }, 1500)
}
</script>

<style scoped>
.juli-mascot {
  display: inline-block;
  flex-shrink: 0;
  width: var(--juli-size);
  height: var(--juli-size);
  background-image: var(--juli-sprite);
  background-repeat: no-repeat;
  background-size: calc(var(--juli-size) * 16) var(--juli-size);
  background-position: 0 0;
  animation: juli-loop 1.333s steps(16) infinite;
  pointer-events: none;
}

/* 15 steps to the last frame, then hold it. */
.juli-mascot--once {
  animation: juli-once 1.25s steps(15) 1 forwards;
}

@keyframes juli-loop {
  to { background-position: calc(var(--juli-size) * -16) 0; }
}

@keyframes juli-once {
  to { background-position: calc(var(--juli-size) * -15) 0; }
}

@media (prefers-reduced-motion: reduce) {
  .juli-mascot,
  .juli-mascot--once {
    background-image: var(--juli-still);
    background-size: 100% 100%;
    animation: none !important;
  }
}
</style>
