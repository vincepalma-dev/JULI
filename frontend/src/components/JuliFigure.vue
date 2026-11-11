<template>
  <g class="juli-figure" :class="[`juli--${state}`, { 'juli-figure--still': still }]" :style="vars">
    <ellipse class="juli-shadow" cx="128" cy="230" rx="44" ry="9" fill="#06b6d4" fill-opacity="0.18" />
    <g class="juli-hop">
      <g stroke="#1a1625" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="106" y="196" width="16" height="30" rx="7" fill="#334155" />
        <rect x="134" y="196" width="16" height="30" rx="7" fill="#334155" />
      </g>

      <g class="juli-upper">
        <!-- Lab coat over a dark top -->
        <g stroke="#1a1625" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="98" y="132" width="60" height="68" rx="16" fill="#1e293b" />
          <path d="M114 133 L94 138 Q86 170 92 202 L116 202 Z" fill="#f1f5f9" />
          <path d="M142 133 L162 138 Q170 170 164 202 L140 202 Z" fill="#f1f5f9" />
          <polygon points="114,133 100,154 113,162" fill="#cbd5e1" />
          <polygon points="142,133 156,154 143,162" fill="#cbd5e1" />
        </g>
        <polyline class="juli-accent-stroke" points="118,136 128,172 138,136" fill="none" stroke-width="4.5" stroke-linecap="round" />
        <rect x="118" y="170" width="20" height="25" rx="4" fill="#ffffff" stroke="#1a1625" stroke-width="4.5" />
        <rect class="juli-accent-fill" x="122" y="175" width="12" height="6" rx="2" />

        <g class="juli-head" stroke="#1a1625" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round">
          <g class="juli-bun">
            <circle cx="102" cy="52" r="24" fill="#3d2722" />
            <path class="juli-accent-stroke" d="M90 58 A16 16 0 0 1 116 64" fill="none" stroke-width="5" />
          </g>
          <path d="M84 80 C80 40 176 40 172 80 C178 114 162 130 128 130 C94 130 78 114 84 80 Z" fill="#fcd5b8" />
          <ellipse cx="100" cy="110" rx="8.5" ry="4.8" fill="#eeb492" stroke="none" />
          <ellipse cx="156" cy="110" rx="8.5" ry="4.8" fill="#eeb492" stroke="none" />
          <circle class="juli-lens" cx="109" cy="94" r="16" fill="#cffafe" fill-opacity="0.5" stroke="none" />
          <circle class="juli-lens" cx="147" cy="94" r="16" fill="#cffafe" fill-opacity="0.5" stroke="none" />
          <g class="juli-eyes">
            <!-- Happy eyes: two arcs -->
            <g v-if="face.eyes === 'happy'" fill="none" stroke-width="5">
              <path d="M102 97 Q109 88 116 97" />
              <path d="M140 97 Q147 88 154 97" />
            </g>
            <g v-else class="juli-blink" stroke="none">
              <ellipse cx="109" cy="94" rx="5.5" ry="7" fill="#1a1625" />
              <ellipse cx="147" cy="94" rx="5.5" ry="7" fill="#1a1625" />
              <circle cx="107" cy="91" r="2.2" fill="#ffffff" />
              <circle cx="145" cy="91" r="2.2" fill="#ffffff" />
            </g>
          </g>
          <circle cx="109" cy="94" r="16" fill="none" stroke="#1e293b" stroke-width="5.5" />
          <circle cx="147" cy="94" r="16" fill="none" stroke="#1e293b" stroke-width="5.5" />
          <path d="M125 93 Q128 89 131 93" fill="none" stroke="#1e293b" stroke-width="5.5" />
          <ellipse v-if="face.mouth === 'open'" class="juli-mouth" cx="128" cy="115" rx="3.6" ry="4.4" fill="#1a1625" stroke="none" />
          <path v-else class="juli-mouth" :d="MOUTHS[face.mouth]" fill="none" stroke-width="4.2" />
          <path d="M84 80 C82 40 174 40 172 80 Q150 64 128 74 Q106 62 84 80 Z" fill="#3d2722" />
          <path d="M84 78 C72 102 80 124 92 140 C98 128 90 104 92 82 Z" fill="#3d2722" />
          <path d="M172 78 C184 102 176 124 164 140 C158 128 166 104 164 82 Z" fill="#3d2722" />
        </g>

        <!-- Things she holds in front of her: the hands come to them -->
        <g v-if="carried === 'laptop'" stroke="#1a1625" stroke-width="6.5" stroke-linejoin="round">
          <rect x="94" y="181" width="68" height="10" rx="4" fill="#cbd5e1" />
          <rect x="100" y="146" width="56" height="38" rx="6" fill="#06b6d4" />
          <rect class="juli-laptop-light" x="123" y="159" width="10" height="10" rx="2.5" fill="#ecfeff" stroke="none" />
        </g>
        <g v-else-if="carried === 'clipboard'" class="juli-clipboard" stroke="#1a1625" stroke-linecap="round" stroke-linejoin="round">
          <rect x="42" y="150" width="38" height="46" rx="5" fill="#ffffff" stroke-width="6" />
          <rect class="juli-accent-fill" x="52" y="145" width="18" height="9" rx="3" stroke-width="4" />
          <g class="juli-accent-stroke juli-writing" fill="none" stroke-width="3.5">
            <path d="M51 165 H71" />
            <path d="M51 174 H71" />
            <path d="M51 183 H64" />
          </g>
        </g>
        <g v-else-if="carried === 'notebook'" stroke="#1a1625" stroke-linecap="round" stroke-linejoin="round">
          <rect x="98" y="148" width="60" height="44" rx="5" fill="#ffffff" stroke-width="6" />
          <rect class="juli-accent-fill" x="98" y="148" width="60" height="10" rx="4" stroke-width="6" />
          <g class="juli-accent-stroke juli-writing" fill="none" stroke-width="3">
            <path d="M108 168 H136" />
            <path d="M108 176 H136" />
            <path d="M108 184 H124" />
          </g>
        </g>

        <!-- Arms: the ink outline first, then the sleeve and hand on top, so the elbow has no seam -->
        <g v-for="arm in ARMS" :key="arm.side" :transform="`translate(${arm.x} 150)`">
          <g :class="`juli-arm--${arm.side}`" stroke="#1a1625" stroke-width="22" stroke-linecap="round">
            <line y2="20" />
            <g transform="translate(0 20)">
              <line :class="`juli-fore--${arm.side}`" y2="15" />
            </g>
          </g>
          <g :class="`juli-arm--${arm.side}`" stroke-linecap="round" stroke-linejoin="round">
            <line class="juli-sleeve" y2="20" stroke-width="9.5" />
            <g transform="translate(0 20)">
              <g :class="`juli-fore--${arm.side}`">
                <line class="juli-sleeve" y2="15" stroke-width="9.5" />
                <!-- What the right hand holds stays upright whatever the arm does -->
                <g v-if="arm.side === 'r' && held" :transform="`translate(0 22) rotate(${heldTurn})`" stroke="#1a1625">
                  <path v-if="held === 'pen'" class="juli-accent-stroke" d="M-5 9 L7 -14" fill="none" stroke-width="5.5" />
                  <g v-else-if="held === 'magnifier'">
                    <path d="M0 0 L-14 -14" fill="none" stroke-width="12" />
                    <path class="juli-accent-stroke" d="M0 0 L-14 -14" fill="none" stroke-width="5.5" />
                    <circle cx="-25" cy="-25" r="16" fill="#fecaca" fill-opacity="0.75" stroke-width="5.5" />
                    <path d="M-33 -28 A10 10 0 0 1 -25 -35" fill="none" stroke="#ffffff" stroke-width="3" />
                  </g>
                  <g v-else-if="held === 'flask'" class="juli-flask">
                    <path d="M-5 -42 V-28 L-18 -4 H18 L5 -28 V-42 Z" fill="#ffffff" stroke-width="5" />
                    <path class="juli-accent-fill" d="M-10.5 -15 H10.5 L15 -6.5 H-15 Z" stroke="none" />
                    <path d="M-8 -42 H8" fill="none" stroke-width="5" />
                    <circle class="juli-accent-fill juli-bubble" cx="-2" cy="-20" r="2.6" stroke="none" />
                    <circle class="juli-accent-fill juli-bubble juli-bubble--late" cx="3" cy="-18" r="2" stroke="none" />
                  </g>
                </g>
                <circle cy="22" r="7" fill="#fcd5b8" stroke="#1a1625" stroke-width="5.5" />
              </g>
            </g>
          </g>
        </g>
      </g>
    </g>
  </g>
</template>

<script setup>
/**
 * One Juli, drawn as a rig of SVG parts that CSS moves: head, eyes, mouth, and
 * two arms that bend at the shoulder and elbow. A state sets a pose (the angles
 * below) and CSS adds motion around it, so with animation off she still holds
 * the right pose. Lives inside JuliMascot's <svg>.
 */
import { computed } from 'vue'

const props = defineProps({
  state: { type: String, default: 'idle' },
  still: { type: Boolean, default: false },
  // Overrides the state's accent colour (the crew in "discussion" wear different ones).
  accent: { type: String, default: '' },
  // Seconds to hold back the head's motion, so a group doesn't nod in step.
  delay: { type: Number, default: 0 },
})

const ARMS = [{ side: 'l', x: 92 }, { side: 'r', x: 164 }]

// The lanyard, badge stripe and hair clip.
const ACCENTS = {
  idle: '#64748b', waiting: '#0d9488', done: '#10b981', stopped: '#f59e0b', error: '#ef4444',
  planner: '#6366f1', coder: '#06b6d4', 'coder-thinking': '#06b6d4', 'coder-typing': '#06b6d4',
  reviewer: '#ef4444', tester: '#f59e0b', docs: '#8b5cf6', discussion: '#0d9488', 'follow-up': '#0891b2',
}

// Arm angles in degrees: left shoulder, left elbow, right shoulder, right elbow.
// 0 hangs straight down; positive turns clockwise. The elbow is relative to the upper arm.
const REST = [18, -16, -18, 16]
const POSES = {
  coder: [13, -50, -13, 50],
  'coder-typing': [13, -50, -13, 50],
  'coder-thinking': [13, -50, -156, -112],
  planner: [-8, 51, -100, -112],
  reviewer: [18, -16, -65, 92],
  tester: [18, -16, -2, -72],
  docs: [14, -46, -11, 95],
  waiting: [18, -16, -54, -116],
  done: [122, 45, -122, -45],
  stopped: [18, -16, -42, -121],
  error: [21, 87, -21, -87],
  'follow-up': [18, -16, -4, -119],
}

const CARRIED = { coder: 'laptop', 'coder-typing': 'laptop', 'coder-thinking': 'laptop', planner: 'clipboard', docs: 'notebook' }
const HELD = { planner: 'pen', docs: 'pen', reviewer: 'magnifier', tester: 'flask' }
// How far the held thing leans from upright, in degrees.
const HELD_LEAN = { pen: 20, magnifier: 0, flask: 0 }

const MOUTHS = {
  smile: 'M121 112 Q128 119 135 112',
  grin: 'M119 110 Q128 124 137 110 Z',
  flat: 'M123 115 H134',
  frown: 'M122 117 Q128 111 134 117',
}
const FACES = {
  done: { eyes: 'happy', mouth: 'grin' },
  error: { mouth: 'frown' },
  coder: { mouth: 'flat' },
  'coder-typing': { mouth: 'flat' },
  'coder-thinking': { mouth: 'flat' },
  tester: { mouth: 'open' },
  'follow-up': { mouth: 'open' },
}

const pose = computed(() => POSES[props.state] || REST)
const face = computed(() => ({ eyes: 'open', mouth: 'smile', ...FACES[props.state] }))
const carried = computed(() => CARRIED[props.state])
const held = computed(() => HELD[props.state])
const heldTurn = computed(() => HELD_LEAN[held.value] - pose.value[2] - pose.value[3])

const vars = computed(() => ({
  '--juli-accent': props.accent || ACCENTS[props.state] || ACCENTS.idle,
  '--juli-delay': `${props.delay}s`,
  '--ls': `${pose.value[0]}deg`,
  '--le': `${pose.value[1]}deg`,
  '--rs': `${pose.value[2]}deg`,
  '--re': `${pose.value[3]}deg`,
}))
</script>

<style scoped>
.juli-accent-stroke { stroke: var(--juli-accent); }
.juli-accent-fill { fill: var(--juli-accent); }
.juli-sleeve { stroke: var(--juli-sleeve, #f1f5f9); }

/* ─── The pose, and the small motion every state has ─── */

.juli-upper { animation: juli-breathe 3.4s ease-in-out infinite; }

.juli-head {
  transform-origin: 128px 128px;
  transform: rotate(var(--tilt, 0deg));
  animation: juli-head var(--tilt-time, 5.1s) ease-in-out var(--juli-delay) infinite;
}

.juli-bun {
  transform-origin: 112px 68px;
  animation: juli-bun 3.4s ease-in-out infinite;
}

.juli-eyes {
  transform: translate(var(--look-x, 0px), var(--look-y, 0px));
  animation: juli-glance var(--glance-time, 8s) ease-in-out infinite;
}

.juli-blink {
  transform-origin: 128px 94px;
  animation: juli-blink 4.6s infinite;
}

.juli-arm--l { transform: rotate(var(--ls)); animation: juli-arm-l var(--l-time, 3.4s) ease-in-out infinite; }
.juli-arm--r { transform: rotate(var(--rs)); animation: juli-arm-r var(--r-time, 3.4s) ease-in-out infinite; }
.juli-fore--l { transform: rotate(var(--le)); animation: juli-fore-l var(--l-time, 3.4s) ease-in-out infinite; }
.juli-fore--r { transform: rotate(var(--re)); animation: juli-fore-r var(--r-time, 3.4s) ease-in-out infinite; }

/* A keyframe with no start or end swings out from the pose and back to it. */
@keyframes juli-breathe { 50% { transform: translateY(-1.6px); } }
@keyframes juli-head { 50% { transform: rotate(calc(var(--tilt, 0deg) + var(--tilt-swing, 1.6deg))); } }
@keyframes juli-bun { 50% { transform: rotate(-3deg); } }
@keyframes juli-arm-l { 50% { transform: rotate(calc(var(--ls) + var(--ls-swing, 2deg))); } }
@keyframes juli-arm-r { 50% { transform: rotate(calc(var(--rs) + var(--rs-swing, -2deg))); } }
@keyframes juli-fore-l { 50% { transform: rotate(calc(var(--le) + var(--le-swing, 0deg))); } }
@keyframes juli-fore-r { 50% { transform: rotate(calc(var(--re) + var(--re-swing, 0deg))); } }

@keyframes juli-blink {
  0%, 93%, 100% { transform: scaleY(1); }
  96% { transform: scaleY(0.08); }
}

@keyframes juli-glance {
  0%, 58%, 100% { transform: translate(var(--look-x, 0px), var(--look-y, 0px)); }
  64%, 74% { transform: translate(calc(var(--look-x, 0px) + var(--glance, 3px)), var(--look-y, 0px)); }
  82%, 92% { transform: translate(calc(var(--look-x, 0px) - var(--glance, 3px)), var(--look-y, 0px)); }
}

/* ─── Per state ─── */

/* Typing: eyes on the screen, hands tapping in turn, the screen lighting her glasses. */
.juli--coder-typing { --look-y: 3px; --glance: 1.5px; --glance-time: 3s; --tilt: 0deg; --tilt-swing: 1deg; --l-time: 0.3s; --r-time: 0.36s; --ls-swing: 0deg; --rs-swing: 0deg; --le-swing: -9deg; --re-swing: 9deg; }
.juli--coder-typing .juli-lens { animation: juli-screen 1.8s ease-in-out infinite; }
.juli--coder-typing .juli-laptop-light,
.juli--coder-thinking .juli-laptop-light { animation: juli-pulse 1.2s ease-in-out infinite; }

/* Thinking: a hand at her chin, looking up. */
.juli--coder-thinking { --look-y: -3px; --tilt: 4deg; --tilt-swing: -3deg; --r-time: 1.7s; --rs-swing: 0deg; --re-swing: -7deg; }
.juli--coder { --look-y: 2px; }

/* Planning: tapping the pen while the list fills in. */
.juli--planner { --tilt: -3deg; --look-x: -2px; --look-y: 1px; --r-time: 0.9s; --rs-swing: 0deg; --re-swing: 10deg; --ls-swing: 3deg; }
.juli--docs { --look-y: 3px; --glance: 2px; --glance-time: 4s; --r-time: 0.5s; --rs-swing: 4deg; --re-swing: -6deg; --ls-swing: 0deg; }
.juli-writing path {
  stroke-dasharray: 30;
  animation: juli-write 3.2s ease-in-out infinite;
}
.juli-writing path:nth-child(2) { animation-delay: 0.5s; }
.juli-writing path:nth-child(3) { animation-delay: 1s; }

/* Reviewing: the magnifier sweeps and her eyes follow it. */
.juli--reviewer { --look-x: 2px; --look-y: 3px; --glance: 2.5px; --glance-time: 3.6s; --r-time: 3.6s; --rs-swing: 14deg; --re-swing: -8deg; }

/* Testing: swirling the flask. */
.juli--tester { --look-x: 3px; --look-y: 2px; --glance: 1px; --tilt: 3deg; --r-time: 0.8s; --rs-swing: 0deg; --re-swing: 7deg; }
.juli-bubble { animation: juli-fizz 1.4s ease-in infinite; }
.juli-bubble--late { animation-delay: 0.7s; }

/* Waiting for you: a wave and a tilt of the head. */
.juli--waiting { --tilt: 5deg; --tilt-swing: -4deg; --tilt-time: 2.6s; --r-time: 0.7s; --rs-swing: 0deg; --re-swing: 24deg; }

/* Follow-up: talking it through. */
.juli--follow-up { --tilt: 2deg; --tilt-swing: -4deg; --tilt-time: 2.2s; --r-time: 1.1s; --rs-swing: 8deg; --re-swing: -16deg; }
.juli--follow-up .juli-mouth {
  transform-origin: 128px 115px;
  animation: juli-talk 0.45s ease-in-out infinite;
}

/* Discussion: the crew nod in turn. */
.juli--discussion { --tilt-swing: 5deg; --tilt-time: 1.8s; }

/* Done: one hop with her arms up, then she holds it. */
.juli--done { --tilt-swing: 3deg; --tilt-time: 2.4s; --ls-swing: 8deg; --rs-swing: -8deg; --l-time: 1.2s; --r-time: 1.2s; }
.juli--done .juli-hop { animation: juli-hop 0.9s ease-out 1 both; }
.juli--done .juli-shadow {
  transform-origin: 128px 230px;
  animation: juli-hop-shadow 0.9s ease-out 1 both;
}

/* Stopped: a raised hand, held still. */
.juli--stopped { --rs-swing: 0deg; --ls-swing: 0deg; --tilt-swing: 0.6deg; --glance: 0px; }

/* Something went wrong: a shake of the head, then a shrug. */
.juli--error { --tilt: -4deg; --tilt-swing: 2deg; --look-y: 2px; --glance: 0px; --ls-swing: 0deg; --rs-swing: 0deg; --le-swing: 12deg; --re-swing: -12deg; --l-time: 2.4s; --r-time: 2.4s; }
.juli--error .juli-hop { animation: juli-shake 0.5s ease-in-out 1; }

@keyframes juli-screen { 50% { fill-opacity: 0.95; } }
@keyframes juli-pulse { 50% { opacity: 0.35; } }
@keyframes juli-write {
  0% { stroke-dashoffset: 30; }
  40%, 85% { stroke-dashoffset: 0; }
  100% { stroke-dashoffset: 0; opacity: 0; }
}
@keyframes juli-fizz {
  0% { transform: translateY(0); opacity: 0; }
  20% { opacity: 1; }
  100% { transform: translateY(-22px); opacity: 0; }
}
@keyframes juli-talk { 50% { transform: scaleY(0.45); } }
@keyframes juli-hop {
  0% { transform: translateY(0); }
  45% { transform: translateY(-26px); }
  100% { transform: translateY(-10px); }
}
@keyframes juli-hop-shadow {
  0% { transform: scale(1); }
  45% { transform: scale(0.7); }
  100% { transform: scale(0.86); }
}
@keyframes juli-shake {
  20%, 60% { transform: translateX(-4px); }
  40%, 80% { transform: translateX(4px); }
}

/* Still: the pose without the motion. "Done" keeps its lift off the ground. */
.juli-figure--still,
.juli-figure--still * { animation: none !important; }
.juli--done.juli-figure--still .juli-hop { transform: translateY(-10px); }
.juli--done.juli-figure--still .juli-shadow { transform: scale(0.86); }

@media (prefers-reduced-motion: reduce) {
  .juli-figure,
  .juli-figure * { animation: none !important; }
  .juli--done .juli-hop { transform: translateY(-10px); }
  .juli--done .juli-shadow { transform: scale(0.86); }
}
</style>
