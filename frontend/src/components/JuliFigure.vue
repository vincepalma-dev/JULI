<template>
  <g class="juli-figure" :class="classes" :style="vars">
    <ellipse class="juli-shadow" cx="128" cy="230" rx="44" ry="9" fill="#06b6d4" fill-opacity="0.18" />
    <g class="juli-hop">
      <g v-if="scene.carried !== 'motorcycle'" stroke="#1a1625" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round">
        <rect class="juli-leg" x="106" y="196" width="16" height="30" rx="7" />
        <rect class="juli-leg" x="134" y="196" width="16" height="30" rx="7" />
        <!-- Only outfits that come with shoes: in the others her legs end plain, as they always have -->
        <template v-if="wear.shoe">
          <rect class="juli-shoe" x="102" y="216" width="24" height="13" rx="6" stroke-width="5.5" />
          <rect class="juli-shoe" x="130" y="216" width="24" height="13" rx="6" stroke-width="5.5" />
        </template>
      </g>

      <g class="juli-upper">
        <JuliOutfit part="body" :outfit="outfit" :accessory="accessory" />

        <g class="juli-head" stroke="#1a1625" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round">
          <g v-if="!tuckedBun" class="juli-bun">
            <circle cx="102" cy="52" r="24" fill="#3d2722" />
            <path class="juli-accent-stroke" d="M90 58 A16 16 0 0 1 116 64" fill="none" stroke-width="5" />
          </g>
          <path d="M84 80 C80 40 176 40 172 80 C178 114 162 130 128 130 C94 130 78 114 84 80 Z" fill="#fcd5b8" />
          <ellipse cx="100" cy="110" rx="8.5" ry="4.8" fill="#eeb492" stroke="none" />
          <ellipse cx="156" cy="110" rx="8.5" ry="4.8" fill="#eeb492" stroke="none" />
          <circle class="juli-lens" cx="109" cy="94" r="16" fill="#cffafe" fill-opacity="0.5" stroke="none" />
          <circle class="juli-lens" cx="147" cy="94" r="16" fill="#cffafe" fill-opacity="0.5" stroke="none" />
          <g class="juli-eyes">
            <!-- Happy eyes arc up, closed eyes arc down -->
            <g v-if="face.eyes !== 'open'" fill="none" stroke-width="5">
              <path :d="face.eyes === 'happy' ? 'M102 97 Q109 88 116 97' : 'M102 94 Q109 101 116 94'" />
              <path :d="face.eyes === 'happy' ? 'M140 97 Q147 88 154 97' : 'M140 94 Q147 101 154 94'" />
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
          <path class="juli-mouth" v-bind="mouth(face.mouth)" />
          <!-- A second mouth some idle styles change to for a moment -->
          <path v-if="scene.mouth2" class="juli-mouth2" v-bind="mouth(scene.mouth2)" />
          <path d="M84 80 C82 40 174 40 172 80 Q150 64 128 74 Q106 62 84 80 Z" fill="#3d2722" />
          <path d="M84 78 C72 102 80 124 92 140 C98 128 90 104 92 82 Z" fill="#3d2722" />
          <path d="M172 78 C184 102 176 124 164 140 C158 128 166 104 164 82 Z" fill="#3d2722" />
          <JuliOutfit part="head" :outfit="outfit" :accessory="accessory" />
        </g>

        <JuliOutfit part="neck" :outfit="outfit" :accessory="accessory" />

        <!-- Things in front of her: the hands come to them -->
        <g v-if="scene.carried === 'laptop'" stroke="#1a1625" stroke-width="6.5" stroke-linejoin="round">
          <rect x="94" y="181" width="68" height="10" rx="4" fill="#cbd5e1" />
          <rect x="100" y="146" width="56" height="38" rx="6" fill="#06b6d4" />
          <rect class="juli-laptop-light" x="123" y="159" width="10" height="10" rx="2.5" fill="#ecfeff" stroke="none" />
        </g>
        <g v-else-if="scene.carried === 'clipboard'" class="juli-clipboard" stroke="#1a1625" stroke-linecap="round" stroke-linejoin="round">
          <rect x="42" y="150" width="38" height="46" rx="5" fill="#ffffff" stroke-width="6" />
          <rect class="juli-accent-fill" x="52" y="145" width="18" height="9" rx="3" stroke-width="4" />
          <g class="juli-accent-stroke juli-writing" fill="none" stroke-width="3.5">
            <path d="M51 165 H71" />
            <path d="M51 174 H71" />
            <path d="M51 183 H64" />
          </g>
        </g>
        <g v-else-if="scene.carried === 'notebook'" stroke="#1a1625" stroke-linecap="round" stroke-linejoin="round">
          <rect x="98" y="148" width="60" height="44" rx="5" fill="#ffffff" stroke-width="6" />
          <rect class="juli-accent-fill" x="98" y="148" width="60" height="10" rx="4" stroke-width="6" />
          <g class="juli-accent-stroke juli-writing" fill="none" stroke-width="3">
            <path d="M108 168 H136" />
            <path d="M108 176 H136" />
            <path d="M108 184 H124" />
          </g>
        </g>
        <g v-else-if="scene.carried === 'book'" stroke="#1a1625" stroke-linecap="round" stroke-linejoin="round">
          <path class="juli-accent-fill" d="M92 152 H164 V194 H92 Z" stroke-width="6" />
          <path d="M97 150 Q113 144 128 152 Q143 144 159 150 V188 Q143 182 128 190 Q113 182 97 188 Z" fill="#ffffff" stroke-width="5" />
          <path d="M128 152 V190" fill="none" stroke-width="3.5" />
          <path d="M104 160 H120 M104 168 H120 M104 176 H116 M136 160 H152 M136 168 H152" fill="none" stroke="#cbd5e1" stroke-width="2.6" />
          <path class="juli-page" d="M128 152 Q143 144 159 150 V188 Q143 182 128 190 Z" fill="#f1f5f9" stroke-width="4" />
        </g>
        <g v-else-if="scene.carried === 'gear'" class="juli-gear">
          <circle cx="60" cy="172" r="19" fill="none" stroke="#1a1625" stroke-width="15" stroke-dasharray="7.46" />
          <circle cx="60" cy="172" r="19" fill="none" stroke="#94a3b8" stroke-width="9" stroke-dasharray="7.46" />
          <circle cx="60" cy="172" r="15" fill="#94a3b8" stroke="#1a1625" stroke-width="5" />
          <circle cx="60" cy="172" r="5" fill="#1a1625" />
        </g>
        <g v-else-if="scene.carried === 'shield'" class="juli-shield" stroke="#1a1625" stroke-linecap="round" stroke-linejoin="round">
          <path class="juli-accent-fill" d="M80 150 H128 V172 Q128 196 104 206 Q80 196 80 172 Z" stroke-width="6.5" />
          <path d="M93 174 L101 183 L116 164" fill="none" stroke="#ffffff" stroke-width="6" />
        </g>
        <!-- Her motorcycle, seen from the front: she sits on it with her boots on the pegs -->
        <g v-else-if="scene.carried === 'motorcycle'" stroke="#1a1625" stroke-linecap="round" stroke-linejoin="round">
          <rect class="juli-shoe" x="78" y="208" width="24" height="14" rx="6" stroke-width="5.5" />
          <rect class="juli-shoe" x="154" y="208" width="24" height="14" rx="6" stroke-width="5.5" />
          <path d="M106 198 L92 210 M150 198 L164 210" fill="none" stroke-width="22" />
          <path class="juli-leg-line" d="M106 198 L92 210 M150 198 L164 210" fill="none" stroke-width="9.5" />
          <path d="M106 176 L112 216 M150 176 L144 216" fill="none" stroke-width="11" />
          <path d="M106 176 L112 216 M150 176 L144 216" fill="none" stroke="#9ca3af" stroke-width="4.5" />
          <rect x="114" y="190" width="28" height="52" rx="13" fill="#111827" stroke-width="6" />
          <path class="juli-tread" d="M128 200 V236" fill="none" stroke="#4b5563" stroke-width="5" stroke-dasharray="6 7" />
          <path class="juli-accent-fill" d="M108 200 Q128 180 148 200 V208 Q128 192 108 208 Z" stroke-width="5" />
          <path class="juli-accent-fill" d="M94 178 Q128 152 162 178 L155 198 Q128 206 101 198 Z" stroke-width="6" />
          <circle class="juli-headlight" cx="128" cy="181" r="12" fill="#fef08a" stroke-width="5.5" />
          <path d="M78 178 L62 164 M178 178 L194 164" fill="none" stroke-width="4.5" />
          <circle cx="60" cy="161" r="7" fill="#cbd5e1" stroke-width="4.5" />
          <circle cx="196" cy="161" r="7" fill="#cbd5e1" stroke-width="4.5" />
          <path d="M76 179 Q128 163 180 179" fill="none" stroke-width="12" />
          <path d="M76 179 Q128 163 180 179" fill="none" stroke="#9ca3af" stroke-width="5" />
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
                <g v-if="arm.side === 'r' && scene.held" transform="translate(0 22)">
                  <g class="juli-held" stroke="#1a1625">
                    <path v-if="scene.held === 'pen'" class="juli-accent-stroke" d="M-5 9 L7 -14" fill="none" stroke-width="5.5" />
                    <g v-else-if="scene.held === 'magnifier'">
                      <path d="M0 0 L-14 -14" fill="none" stroke-width="12" />
                      <path class="juli-accent-stroke" d="M0 0 L-14 -14" fill="none" stroke-width="5.5" />
                      <circle cx="-25" cy="-25" r="16" fill="#fecaca" fill-opacity="0.75" stroke-width="5.5" />
                      <path d="M-33 -28 A10 10 0 0 1 -25 -35" fill="none" stroke="#ffffff" stroke-width="3" />
                    </g>
                    <g v-else-if="scene.held === 'flask'" class="juli-flask">
                      <path d="M-5 -42 V-28 L-18 -4 H18 L5 -28 V-42 Z" fill="#ffffff" stroke-width="5" />
                      <path class="juli-accent-fill" d="M-10.5 -15 H10.5 L15 -6.5 H-15 Z" stroke="none" />
                      <path d="M-8 -42 H8" fill="none" stroke-width="5" />
                      <circle class="juli-accent-fill juli-bubble" cx="-2" cy="-20" r="2.6" stroke="none" />
                      <circle class="juli-accent-fill juli-bubble juli-bubble--late" cx="3" cy="-18" r="2" stroke="none" />
                    </g>
                    <g v-else-if="scene.held === 'wrench'">
                      <path d="M0 6 V-24" fill="none" stroke-width="12" />
                      <path class="juli-accent-stroke" d="M0 6 V-24" fill="none" stroke-width="5.5" />
                      <circle cx="0" cy="-32" r="10" fill="#cbd5e1" stroke-width="5" />
                      <polygon points="-4.5,-44 4.5,-44 0,-31" fill="#1a1625" stroke="none" />
                    </g>
                    <g v-else-if="scene.held === 'mug'">
                      <path d="M12 -21 Q27 -14 12 -6" fill="none" stroke-width="5" />
                      <rect x="-13" y="-28" width="26" height="30" rx="5" fill="#f8fafc" stroke-width="5" />
                      <rect class="juli-accent-fill" x="-10.5" y="-20" width="21" height="6" stroke="none" />
                      <path class="juli-bubble" d="M-5 -34 q-3 -5 0 -9" fill="none" stroke="#e2e8f0" stroke-width="3" />
                      <path class="juli-bubble juli-bubble--late" d="M5 -34 q3 -5 0 -9" fill="none" stroke="#e2e8f0" stroke-width="3" />
                    </g>
                    <g v-else-if="scene.held === 'phone'">
                      <rect x="-9" y="-26" width="18" height="32" rx="4" fill="#1e293b" stroke-width="4.5" />
                      <rect class="juli-laptop-light" x="-5.5" y="-22" width="11" height="19" rx="1.5" fill="#a5f3fc" stroke="none" />
                    </g>
                  </g>
                </g>
                <circle class="juli-hand" cy="22" r="7" stroke="#1a1625" stroke-width="5.5" />
              </g>
            </g>
          </g>
        </g>

        <!-- Juggling: each ball goes across at a steady pace while it rises and falls -->
        <g v-if="scene.balls" stroke="#1a1625" stroke-width="4.5">
          <g v-for="fill in BALLS" :key="fill" class="juli-ball-x">
            <circle class="juli-ball-y" :class="{ 'juli-accent-fill': !fill }" cx="77" cy="158" r="7.5" :fill="fill || undefined" />
          </g>
        </g>
      </g>
    </g>
  </g>
</template>

<script setup>
/**
 * One Juli, drawn as a rig of SVG parts that CSS moves: head, eyes, mouth, and
 * two arms that bend at the shoulder and elbow. A scene (a working state, or
 * an idle style) sets a pose and what she holds, and CSS adds motion around
 * the pose, so with animation off she still holds it. JuliOutfit dresses her.
 * Lives inside JuliMascot's <svg>.
 */
import { computed } from 'vue'
import JuliOutfit from './JuliOutfit.vue'
import { OUTFITS } from '../mascot.js'

const props = defineProps({
  state: { type: String, default: 'idle' },
  outfit: { type: String, default: 'lab-coat' },
  accessory: { type: String, default: 'none' },
  idle: { type: String, default: 'calm' },
  still: { type: Boolean, default: false },
  // Overrides the state's accent colour (an agent's colour; the crew in "discussion").
  accent: { type: String, default: '' },
  // Seconds to hold back the head's motion, so a group doesn't nod in step.
  delay: { type: Number, default: 0 },
})

const ARMS = [{ side: 'l', x: 92 }, { side: 'r', x: 164 }]
const BALLS = ['', '#fbbf24', '#f472b6'] // the first takes the accent colour

// The lanyard, badge stripe and hair clip. Idle, she wears the theme's accent.
const ACCENTS = {
  idle: 'var(--color-juli-accent, #06b6d4)', waiting: '#0d9488', done: '#10b981', stopped: '#f59e0b', error: '#ef4444',
  planner: '#6366f1', coder: '#06b6d4', 'coder-thinking': '#06b6d4', 'coder-typing': '#06b6d4',
  reviewer: '#ef4444', tester: '#f59e0b', docs: '#8b5cf6', discussion: '#0d9488', 'follow-up': '#0891b2',
  devops: '#10b981', security: '#ef4444', analyst: '#3b82f6',
}

// Arm angles in degrees: left shoulder, left elbow, right shoulder, right elbow.
// 0 hangs straight down; positive turns clockwise. The elbow is relative to the upper arm.
const REST = [18, -16, -18, 16]

// What each state shows: the pose, what she carries in front of her (carried)
// or in her right hand (held, with how far it leans from upright), and her face.
const SCENES = {
  coder: { pose: [13, -50, -13, 50], carried: 'laptop', mouth: 'flat' },
  'coder-typing': { pose: [13, -50, -13, 50], carried: 'laptop', mouth: 'flat' },
  'coder-thinking': { pose: [13, -50, -156, -112], carried: 'laptop', mouth: 'flat' },
  planner: { pose: [-8, 51, -100, -112], carried: 'clipboard', held: 'pen', lean: 20 },
  reviewer: { pose: [18, -16, -65, 92], held: 'magnifier' },
  tester: { pose: [18, -16, -2, -72], held: 'flask', mouth: 'open' },
  docs: { pose: [14, -46, -11, 95], carried: 'notebook', held: 'pen', lean: 20 },
  devops: { pose: [-8, 51, -73, -99], carried: 'gear', held: 'wrench', lean: 25 },
  security: { pose: [12, -45, -42, -121], carried: 'shield' },
  analyst: { pose: [35, -87, -92, -72] },
  waiting: { pose: [18, -16, -54, -116] },
  done: { pose: [122, 45, -122, -45], eyes: 'happy', mouth: 'grin' },
  stopped: { pose: [18, -16, -42, -121] },
  error: { pose: [21, 87, -21, -87], mouth: 'frown' },
  'follow-up': { pose: [18, -16, -4, -119], mouth: 'open' },
}

// Idle styles. `pose2` is a second pose she moves to and back from: `move` says
// how ("visit" it briefly each loop, or "swap" back and forth).
const IDLES = {
  wave: { pose2: [18, -16, -97, -72], move: 'visit' },
  stretch: { pose2: [144, 31, -144, -31], move: 'visit', mouth2: 'yawn' },
  coffee: { pose: [18, -16, -37, 132], pose2: [18, -16, 69, 97], move: 'visit', held: 'mug' },
  curious: { pose2: [18, -16, -148, -49], move: 'visit' },
  dance: { pose: [65, 82, -15, -58], pose2: [15, 58, -65, -82], move: 'swap', mouth: 'grin' },
  juggle: { pose: [-17, 110, 17, -110], balls: true },
  read: { pose: [13, -50, -13, 50], pose2: [13, -50, 10, 101], move: 'visit', carried: 'book' },
  phone: { pose: [18, -16, -37, 132], held: 'phone', lean: -8, mouth2: 'grin' },
  nap: { eyes: 'closed', mouth: 'flat' },
  ride: { pose: [71, -84, -71, 84], carried: 'motorcycle' },
}

const MOUTHS = {
  smile: 'M121 112 Q128 119 135 112',
  grin: 'M119 110 Q128 124 137 110 Z',
  flat: 'M123 115 H134',
  frown: 'M122 117 Q128 111 134 117',
}
// Open mouths are filled shapes, not lines.
const OPEN_MOUTHS = {
  open: 'M124.4 115 a3.6 4.4 0 1 0 7.2 0 a3.6 4.4 0 1 0 -7.2 0 Z',
  yawn: 'M122.5 116 a5.5 7 0 1 0 11 0 a5.5 7 0 1 0 -11 0 Z',
}
function mouth(name) {
  return OPEN_MOUTHS[name]
    ? { d: OPEN_MOUTHS[name], fill: '#1a1625', stroke: 'none' }
    : { d: MOUTHS[name], fill: 'none', 'stroke-width': 4.2 }
}

const scene = computed(() => (props.state === 'idle' ? IDLES[props.idle] : SCENES[props.state]) || {})
const face = computed(() => ({ eyes: scene.value.eyes || 'open', mouth: scene.value.mouth || 'smile' }))
const wear = computed(() => OUTFITS.find(o => o.id === props.outfit) || OUTFITS[0])
// A beanie or the rider's helmet covers her bun.
const tuckedBun = computed(() => props.outfit === 'rider' || (props.accessory === 'beanie' && props.outfit !== 'space-suit'))

const classes = computed(() => [
  `juli--${props.state}`,
  props.state === 'idle' && `juli-idle--${props.idle}`,
  props.state === 'idle' && scene.value.move && `juli-move--${scene.value.move}`,
  { 'juli-figure--still': props.still },
])

const vars = computed(() => {
  const pose = scene.value.pose || REST
  const pose2 = scene.value.pose2 || pose
  return {
    '--juli-accent': props.accent || ACCENTS[props.state] || ACCENTS.idle,
    '--juli-delay': `${props.delay}s`,
    '--juli-sleeve': wear.value.sleeve,
    '--juli-hand': wear.value.hand || '#fcd5b8',
    '--juli-leg': wear.value.leg || '#334155',
    '--juli-shoe': wear.value.shoe || '#334155',
    '--ls': `${pose[0]}deg`,
    '--le': `${pose[1]}deg`,
    '--rs': `${pose[2]}deg`,
    '--re': `${pose[3]}deg`,
    '--ls2': `${pose2[0]}deg`,
    '--le2': `${pose2[1]}deg`,
    '--rs2': `${pose2[2]}deg`,
    '--re2': `${pose2[3]}deg`,
    '--lean': `${scene.value.lean || 0}deg`,
  }
})
</script>

<style scoped>
.juli-accent-stroke { stroke: var(--juli-accent); }
.juli-accent-fill { fill: var(--juli-accent); }
.juli-sleeve { stroke: var(--juli-sleeve); }
.juli-hand { fill: var(--juli-hand); }
.juli-leg { fill: var(--juli-leg); }
.juli-leg-line { stroke: var(--juli-leg); }
.juli-shoe { fill: var(--juli-shoe); }

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

/* Turned back by the arm's angles, so it stays upright. */
.juli-held { transform: rotate(calc(var(--lean) - var(--rs) - var(--re))); }

.juli-mouth2 { opacity: 0; }

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

/* ─── Working states ─── */

/* Typing: eyes on the screen, hands tapping in turn, the screen lighting her glasses. */
.juli--coder-typing { --look-y: 3px; --glance: 1.5px; --glance-time: 3s; --tilt: 0deg; --tilt-swing: 1deg; --l-time: 0.3s; --r-time: 0.36s; --ls-swing: 0deg; --rs-swing: 0deg; --le-swing: -9deg; --re-swing: 9deg; }
.juli--coder-typing .juli-lens { animation: juli-screen 1.8s ease-in-out infinite; }
.juli-laptop-light { animation: juli-pulse 1.2s ease-in-out infinite; }
.juli--coder .juli-laptop-light { animation: none; }

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

/* Fixing: turning the wrench while the gear goes round. */
.juli--devops { --look-x: -3px; --look-y: 2px; --glance: 1.5px; --tilt: -3deg; --r-time: 0.7s; --rs-swing: 0deg; --re-swing: 24deg; --ls-swing: 0deg; }
.juli-gear {
  transform-box: fill-box;
  transform-origin: center;
  animation: juli-spin 5s linear infinite;
}

/* Guarding: shield up, a hand out, eyes sweeping. */
.juli--security { --glance: 4.5px; --glance-time: 3s; --tilt-swing: 3deg; --tilt-time: 3s; --rs-swing: 0deg; --ls-swing: 0deg; }
.juli-shield { animation: juli-breathe 1.8s ease-in-out infinite; }

/* Analysing: pointing at the chart beside her. */
.juli--analyst { --look-x: 4px; --look-y: -2px; --glance: 1.5px; --tilt: 4deg; --r-time: 1.3s; --rs-swing: 0deg; --re-swing: -12deg; --ls-swing: 0deg; }

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
@keyframes juli-spin { to { transform: rotate(360deg); } }
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

/* ─── Idle styles ─── */

/* Visit: rest for most of the loop, go to the second pose for a moment near its end. */
.juli-move--visit .juli-arm--l { animation: juli-visit-arm-l var(--idle-time, 6s) ease-in-out infinite; }
.juli-move--visit .juli-arm--r { animation: juli-visit-arm-r var(--idle-time, 6s) ease-in-out infinite; }
.juli-move--visit .juli-fore--l { animation: juli-visit-fore-l var(--idle-time, 6s) ease-in-out infinite; }
.juli-move--visit .juli-fore--r { animation: juli-visit-fore-r var(--idle-time, 6s) ease-in-out infinite; }
.juli-move--visit .juli-held { animation: juli-visit-held var(--idle-time, 6s) ease-in-out infinite; }

@keyframes juli-visit-arm-l { 0%, 62%, 100% { transform: rotate(var(--ls)); } 72%, 90% { transform: rotate(var(--ls2)); } }
@keyframes juli-visit-arm-r { 0%, 62%, 100% { transform: rotate(var(--rs)); } 72%, 90% { transform: rotate(var(--rs2)); } }
@keyframes juli-visit-fore-l { 0%, 62%, 100% { transform: rotate(var(--le)); } 72%, 90% { transform: rotate(var(--le2)); } }
@keyframes juli-visit-fore-r { 0%, 62%, 100% { transform: rotate(var(--re)); } 72%, 90% { transform: rotate(var(--re2)); } }
@keyframes juli-visit-held {
  0%, 62%, 100% { transform: rotate(calc(var(--lean) - var(--rs) - var(--re))); }
  72%, 90% { transform: rotate(calc(var(--lean) - var(--rs2) - var(--re2))); }
}
/* What else happens during the visit: eyes close, the mouth changes, she rises. */
@keyframes juli-visit-eyes { 0%, 66%, 96%, 100% { transform: scaleY(1); } 72%, 90% { transform: scaleY(0.08); } }
@keyframes juli-visit-show { 0%, 66%, 95%, 100% { opacity: 0; } 72%, 90% { opacity: 1; } }
@keyframes juli-visit-hide { 0%, 66%, 95%, 100% { opacity: 1; } 72%, 90% { opacity: 0; } }
@keyframes juli-visit-rise { 0%, 62%, 100% { transform: translateY(0); } 72%, 90% { transform: translateY(-5px); } }

/* Swap: back and forth between the two poses. */
.juli-move--swap .juli-arm--l { animation: juli-swap-arm-l var(--idle-time, 1.2s) ease-in-out infinite; }
.juli-move--swap .juli-arm--r { animation: juli-swap-arm-r var(--idle-time, 1.2s) ease-in-out infinite; }
.juli-move--swap .juli-fore--l { animation: juli-swap-fore-l var(--idle-time, 1.2s) ease-in-out infinite; }
.juli-move--swap .juli-fore--r { animation: juli-swap-fore-r var(--idle-time, 1.2s) ease-in-out infinite; }
@keyframes juli-swap-arm-l { 50% { transform: rotate(var(--ls2)); } }
@keyframes juli-swap-arm-r { 50% { transform: rotate(var(--rs2)); } }
@keyframes juli-swap-fore-l { 50% { transform: rotate(var(--le2)); } }
@keyframes juli-swap-fore-r { 50% { transform: rotate(var(--re2)); } }

/* Wave: the forearm waggles while her hand is up. */
.juli-idle--wave { --idle-time: 5s; --tilt-swing: 3deg; }
.juli-idle--wave .juli-fore--r { animation-name: juli-wave; }
@keyframes juli-wave {
  0%, 62%, 100% { transform: rotate(var(--re)); }
  72%, 90% { transform: rotate(var(--re2)); }
  76.5%, 85.5% { transform: rotate(calc(var(--re2) - 26deg)); }
  81% { transform: rotate(calc(var(--re2) + 8deg)); }
}

/* Stretch: up on her toes, eyes shut, a yawn. */
.juli-idle--stretch { --idle-time: 9s; }
.juli-idle--stretch .juli-upper { animation: juli-visit-rise var(--idle-time) ease-in-out infinite; }
.juli-idle--stretch .juli-blink,
.juli-idle--coffee .juli-blink { animation: juli-visit-eyes var(--idle-time) ease-in-out infinite; }
.juli-idle--stretch .juli-mouth,
.juli-idle--phone .juli-mouth { animation: juli-visit-hide var(--idle-time) ease-in-out infinite; }
.juli-idle--stretch .juli-mouth2,
.juli-idle--phone .juli-mouth2 { animation: juli-visit-show var(--idle-time) ease-in-out infinite; }

/* Coffee: a sip, eyes shut. */
.juli-idle--coffee { --idle-time: 7s; }

/* Curious: peers left and right, then pushes her glasses up. */
.juli-idle--curious { --idle-time: 8s; --glance: 5px; --glance-time: 3.4s; }
.juli-idle--curious .juli-head { animation: juli-peer var(--idle-time) ease-in-out infinite; }
@keyframes juli-peer {
  0%, 50%, 100% { transform: rotate(0deg); }
  14%, 24% { transform: translateX(-4px) rotate(-7deg); }
  34%, 44% { transform: translateX(4px) rotate(7deg); }
}

/* Dance: a side-step, arms swinging in turn. */
.juli-idle--dance { --idle-time: 1.1s; --tilt-swing: 7deg; --tilt-time: 1.1s; --tilt: -3.5deg; }
.juli-idle--dance .juli-hop {
  transform-origin: 128px 226px;
  animation: juli-sway 1.1s ease-in-out infinite;
}
@keyframes juli-sway {
  0%, 100% { transform: translateX(-6px) rotate(-3deg); }
  50% { transform: translateX(6px) rotate(3deg); }
}

/* Juggle: hands out, tossing in turn, eyes on the balls. */
.juli-idle--juggle { --look-y: -4px; --glance: 4px; --glance-time: 1.8s; --l-time: 0.6s; --r-time: 0.6s; --ls-swing: 0deg; --rs-swing: 0deg; --le-swing: 14deg; --re-swing: -14deg; }
.juli-idle--juggle .juli-fore--r { animation-delay: -0.3s; }
.juli-ball-x { animation: juli-ball-x 1.8s linear infinite; }
.juli-ball-y { animation: juli-ball-y 1.8s infinite; }
.juli-ball-x:nth-child(2), .juli-ball-x:nth-child(2) .juli-ball-y { animation-delay: -0.6s; }
.juli-ball-x:nth-child(3), .juli-ball-x:nth-child(3) .juli-ball-y { animation-delay: -1.2s; }
@keyframes juli-ball-x {
  0% { transform: translateX(0); }
  70% { transform: translateX(102px); }
  100% { transform: translateX(0); }
}
@keyframes juli-ball-y {
  0% { transform: translateY(0); animation-timing-function: ease-out; }
  35% { transform: translateY(-138px); animation-timing-function: ease-in; }
  70% { transform: translateY(0); animation-timing-function: ease-in-out; }
  85% { transform: translateY(8px); }
  100% { transform: translateY(0); }
}

/* Read: eyes moving along the lines, and a page turned now and then. */
.juli-idle--read { --idle-time: 6s; --look-y: 4px; --glance: 3px; --glance-time: 3s; --tilt-swing: 1deg; }
.juli-page {
  transform-origin: 128px 170px;
  opacity: 0;
  animation: juli-page var(--idle-time, 6s) ease-in-out infinite;
}
@keyframes juli-page {
  0%, 70% { transform: scaleX(1); opacity: 0; }
  73% { transform: scaleX(1); opacity: 1; }
  88% { transform: scaleX(-1); opacity: 1; }
  92%, 100% { transform: scaleX(-1); opacity: 0; }
}

/* Phone: scrolling with her thumb, a grin at something. */
.juli-idle--phone { --idle-time: 6s; --look-x: 2px; --look-y: 4px; --glance: 1px; --tilt: 3deg; --tilt-swing: 1deg; --r-time: 0.9s; --rs-swing: 0deg; --re-swing: 4deg; }

/* Nap: head down, slow breaths. */
.juli-idle--nap { --tilt: 9deg; --tilt-swing: 2.5deg; --tilt-time: 4.2s; --ls-swing: 1deg; --rs-swing: -1deg; }
.juli-idle--nap .juli-upper { animation: juli-doze 4.2s ease-in-out infinite; }
@keyframes juli-doze { 50% { transform: translateY(2.5px); } }

/* Ride: the engine shakes her, she leans through the bends, a hand on the throttle. */
.juli-idle--ride { --tilt-swing: -3deg; --tilt-time: 4s; --look-y: 1px; --glance: 2px; --ls-swing: 0deg; --rs-swing: 0deg; --re-swing: 7deg; --r-time: 1.1s; }
.juli-idle--ride .juli-hop {
  transform-origin: 128px 240px;
  animation: juli-lean 4s ease-in-out infinite;
}
.juli-idle--ride .juli-upper { animation: juli-engine 0.16s linear infinite; }
.juli-tread { animation: juli-roll 0.35s linear infinite; }
.juli-headlight { animation: juli-screen 2s ease-in-out infinite; fill-opacity: 0.75; }
@keyframes juli-lean {
  0%, 100% { transform: rotate(-3deg); }
  50% { transform: rotate(3deg); }
}
@keyframes juli-engine { 50% { transform: translateY(0.9px); } }
@keyframes juli-roll { to { stroke-dashoffset: -13; } }

/* ─── Still: the pose without the motion. "Done" keeps its lift off the ground, ─── */
/* and the juggling balls stay spread along their arc. */
.juli-figure--still,
.juli-figure--still :deep(*) { animation: none !important; }
.juli--done.juli-figure--still .juli-hop { transform: translateY(-10px); }
.juli--done.juli-figure--still .juli-shadow { transform: scale(0.86); }
.juli-figure--still .juli-ball-x:nth-child(2) { transform: translate(51px, -138px); }
.juli-figure--still .juli-ball-x:nth-child(3) { transform: translateX(102px); }

@media (prefers-reduced-motion: reduce) {
  .juli-figure,
  .juli-figure * { animation: none !important; }
  .juli--done .juli-hop { transform: translateY(-10px); }
  .juli--done .juli-shadow { transform: scale(0.86); }
  .juli-ball-x:nth-child(2) { transform: translate(51px, -138px); }
  .juli-ball-x:nth-child(3) { transform: translateX(102px); }
}
</style>
