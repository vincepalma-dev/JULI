<template>
  <!-- Body: what she wears, drawn before her head (a hood or helmet sits behind it) -->
  <g v-if="part === 'body'" stroke="#1a1625" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round">
    <template v-if="outfit === 'hoodie'">
      <ellipse cx="128" cy="130" rx="50" ry="24" fill="#8b5cf6" />
      <path :d="BODY" fill="#a78bfa" />
      <path d="M112 134 Q128 152 144 134 Z" fill="#7c3aed" stroke-width="5" />
      <path d="M108 176 H148 L152 197 H104 Z" fill="#8b5cf6" stroke-width="5" />
      <g class="juli-accent-stroke" fill="none" stroke-width="4.5">
        <path d="M120 142 L118 160" />
        <path d="M136 142 L138 160" />
      </g>
    </template>

    <template v-else-if="outfit === 'blazer'">
      <rect x="98" y="132" width="60" height="68" rx="16" fill="#f8fafc" />
      <path d="M114 133 L94 138 Q87 168 91 199 L119 199 L125 160 Z" fill="#475569" />
      <path d="M142 133 L162 138 Q169 168 165 199 L137 199 L131 160 Z" fill="#475569" />
      <polygon points="114,133 103,151 122,160" fill="#334155" />
      <polygon points="142,133 153,151 134,160" fill="#334155" />
      <polyline class="juli-accent-stroke" points="118,136 128,172 138,136" fill="none" stroke-width="4.5" />
      <rect x="118" y="170" width="20" height="25" rx="4" fill="#ffffff" stroke-width="4.5" />
      <rect class="juli-accent-fill" x="122" y="175" width="12" height="6" rx="2" stroke="none" />
    </template>

    <template v-else-if="outfit === 'space-suit'">
      <circle cx="128" cy="84" r="66" fill="#bae6fd" fill-opacity="0.22" stroke-width="5.5" />
      <path :d="BODY" fill="#e2e8f0" />
      <path d="M90 189 H166" fill="none" stroke="#fb923c" stroke-width="5" />
      <rect x="110" y="156" width="36" height="24" rx="5" fill="#1e293b" stroke-width="4.5" />
      <circle class="juli-accent-fill juli-light" cx="119" cy="168" r="4" stroke="none" />
      <path d="M128 164 H139 M128 172 H139" fill="none" stroke="#fb923c" stroke-width="3" />
    </template>

    <template v-else-if="outfit === 'pajamas'">
      <path :d="BODY" fill="#bfdbfe" />
      <g fill="#ffffff" stroke="none">
        <circle cx="103" cy="158" r="3" /><circle cx="116" cy="186" r="3" /><circle cx="100" cy="184" r="2.4" />
        <circle cx="153" cy="182" r="3" /><circle cx="146" cy="152" r="2.4" /><circle cx="114" cy="166" r="2.4" />
      </g>
      <polygon points="116,134 128,149 108,147" fill="#93c5fd" stroke-width="4.5" />
      <polygon points="140,134 128,149 148,147" fill="#93c5fd" stroke-width="4.5" />
      <circle cx="128" cy="162" r="2.8" fill="#1e3a8a" stroke="none" />
      <circle cx="128" cy="177" r="2.8" fill="#1e3a8a" stroke="none" />
      <rect class="juli-accent-fill" x="137" y="160" width="15" height="13" rx="3" stroke-width="4" />
    </template>

    <template v-else-if="outfit === 'overalls'">
      <path :d="BODY" fill="#fde68a" />
      <path d="M95 146 H161 M93 157 H107 M149 157 H163" fill="none" stroke="#f59e0b" stroke-width="3" />
      <path d="M112 136 L115 154 M144 136 L141 154" fill="none" stroke="#2563eb" stroke-width="7" />
      <path d="M89 178 H167 L168 196 Q168 202 162 202 H94 Q88 202 88 196 Z" fill="#3b82f6" />
      <rect x="108" y="152" width="40" height="32" rx="5" fill="#3b82f6" />
      <path d="M119 166 H137 V176 H119 Z" fill="none" stroke="#1d4ed8" stroke-width="2.8" />
      <circle class="juli-accent-fill" cx="114" cy="158" r="3.4" stroke-width="2.5" />
      <circle class="juli-accent-fill" cx="142" cy="158" r="3.4" stroke-width="2.5" />
    </template>

    <template v-else-if="outfit === 'raincoat'">
      <path d="M102 134 H154 Q164 136 166 150 L172 198 Q172 204 166 204 H90 Q84 204 84 198 L90 150 Q92 136 102 134 Z" fill="#facc15" />
      <path d="M128 150 V203 M95 180 H110 M146 180 H161" fill="none" stroke="#ca8a04" stroke-width="3" />
      <path d="M106 134 Q128 158 150 134 Q128 145 106 134 Z" fill="#eab308" stroke-width="4.5" />
      <path class="juli-accent-stroke" d="M121 162 H135 M121 176 H135 M121 190 H135" fill="none" stroke-width="5" />
    </template>

    <template v-else-if="outfit === 'varsity'">
      <path :d="BODY" fill="#dc2626" />
      <path d="M128 150 V190" fill="none" stroke="#991b1b" stroke-width="3" />
      <path d="M90 194 H166" fill="none" stroke="#f8fafc" stroke-width="5" />
      <path d="M110 136 Q128 152 146 136" fill="none" stroke="#f8fafc" stroke-width="6" />
      <!-- The letter on her chest -->
      <path d="M140 158 H152 M146 158 V170 Q146 176 139 174" fill="none" stroke="#f8fafc" stroke-width="8" />
      <path class="juli-accent-stroke" d="M140 158 H152 M146 158 V170 Q146 176 139 174" fill="none" stroke-width="3.5" />
    </template>

    <template v-else-if="outfit === 'apron'">
      <path :d="BODY" fill="#f8fafc" />
      <path d="M115 135 V152 M141 135 V152" fill="none" stroke="#166534" stroke-width="5" />
      <path d="M110 150 H146 V168 H163 L167 197 Q167 202 162 202 H94 Q89 202 89 197 L93 168 H110 Z" fill="#16a34a" />
      <path d="M114 180 H142 V192 H114 Z" fill="none" stroke="#14532d" stroke-width="3" />
      <circle class="juli-accent-fill" cx="128" cy="162" r="5.5" stroke="#f8fafc" stroke-width="2.5" />
    </template>

    <template v-else-if="outfit === 'tracksuit'">
      <path :d="BODY" fill="#14b8a6" />
      <path d="M96 152 L94 198 M160 152 L162 198" fill="none" stroke="#f8fafc" stroke-width="4" />
      <path d="M128 148 V201" fill="none" stroke="#0f766e" stroke-width="3" />
      <path d="M110 134 Q128 149 146 134 L147 142 Q128 158 109 142 Z" fill="#0d9488" stroke-width="4.5" />
      <circle class="juli-accent-fill" cx="128" cy="158" r="4" stroke-width="2.5" />
    </template>

    <template v-else-if="outfit === 'rider'">
      <path :d="BODY" fill="#4b5563" />
      <polygon points="112,134 102,152 122,158" fill="#374151" stroke-width="5" />
      <polygon points="144,134 154,152 134,158" fill="#374151" stroke-width="5" />
      <path d="M124 158 L132 200" fill="none" stroke="#d1d5db" stroke-width="3" />
      <path class="juli-accent-stroke" d="M92 172 H121 M135 172 H164" fill="none" stroke-width="5" />
      <path d="M90 194 H166" fill="none" stroke="#1f2937" stroke-width="5" />
      <rect x="122" y="189" width="12" height="10" rx="2" fill="#d1d5db" stroke-width="3" />
    </template>

    <!-- Lab coat over a dark top -->
    <template v-else>
      <rect x="98" y="132" width="60" height="68" rx="16" fill="#1e293b" />
      <path d="M114 133 L94 138 Q86 170 92 202 L116 202 Z" fill="#f1f5f9" />
      <path d="M142 133 L162 138 Q170 170 164 202 L140 202 Z" fill="#f1f5f9" />
      <polygon points="114,133 100,154 113,162" fill="#cbd5e1" />
      <polygon points="142,133 156,154 143,162" fill="#cbd5e1" />
      <polyline class="juli-accent-stroke" points="118,136 128,172 138,136" fill="none" stroke-width="4.5" />
      <rect x="118" y="170" width="20" height="25" rx="4" fill="#ffffff" stroke-width="4.5" />
      <rect class="juli-accent-fill" x="122" y="175" width="12" height="6" rx="2" stroke="none" />
    </template>
  </g>

  <!-- Head: what sits on it, drawn inside the head so it tilts with her -->
  <g v-else-if="part === 'head' && !helmet" stroke="#1a1625" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round">
    <!-- The rider's open-face helmet, visor up -->
    <template v-if="outfit === 'rider'">
      <path class="juli-accent-fill" d="M76 100 C66 22 190 22 180 100 L180 112 Q180 122 170 122 H166 V86 Q128 62 90 86 V122 H86 Q76 122 76 112 Z" />
      <path d="M88 82 Q128 54 168 82 L166 68 Q128 42 90 68 Z" fill="#1e293b" stroke-width="5" />
      <path d="M100 66 Q112 57 124 55" fill="none" stroke="#94a3b8" stroke-width="3.5" />
    </template>
    <template v-else-if="accessory === 'cap'">
      <path class="juli-accent-fill" d="M148 62 Q184 58 198 74 Q174 82 148 76 Z" />
      <path class="juli-accent-fill" d="M86 66 C86 26 170 26 170 66 Q128 54 86 66 Z" />
      <circle cx="128" cy="38" r="4" fill="#f8fafc" stroke="none" />
    </template>
    <template v-else-if="accessory === 'beanie'">
      <circle cx="128" cy="30" r="11" fill="#f8fafc" stroke-width="5.5" />
      <path class="juli-accent-fill" d="M82 70 C80 26 176 26 174 70 Z" />
      <rect x="79" y="60" width="98" height="19" rx="9" fill="#f8fafc" />
      <path d="M96 64 V75 M112 64 V75 M128 64 V75 M144 64 V75 M160 64 V75" fill="none" stroke="#cbd5e1" stroke-width="3" />
    </template>
    <template v-else-if="accessory === 'headphones'">
      <path d="M80 98 C72 20 184 20 176 98" fill="none" stroke-width="13" />
      <path d="M80 98 C72 20 184 20 176 98" fill="none" stroke="#94a3b8" stroke-width="6" />
      <rect class="juli-accent-fill" x="68" y="82" width="20" height="36" rx="9" stroke-width="5.5" />
      <rect class="juli-accent-fill" x="168" y="82" width="20" height="36" rx="9" stroke-width="5.5" />
    </template>
    <template v-else-if="accessory === 'party-hat'">
      <polygon points="152,6 128,52 172,58" fill="#f472b6" stroke-width="6" />
      <path class="juli-accent-stroke" d="M143 30 L159 32 M136 44 L165 47" fill="none" stroke-width="4.5" />
      <circle cx="152" cy="7" r="6.5" fill="#fde047" stroke-width="5" />
    </template>
  </g>

  <!-- Neck: a scarf, or the helmet's collar and glass, drawn over her head -->
  <g v-else-if="part === 'neck'" stroke="#1a1625" stroke-linecap="round" stroke-linejoin="round">
    <template v-if="helmet">
      <rect x="101" y="126" width="54" height="15" rx="7" fill="#94a3b8" stroke-width="5" />
      <circle cx="128" cy="84" r="66" fill="#e0f2fe" fill-opacity="0.1" stroke="none" />
      <path d="M78 62 A54 54 0 0 1 106 32" fill="none" stroke="#ffffff" stroke-opacity="0.85" stroke-width="5" />
    </template>
    <template v-else-if="accessory === 'scarf'">
      <rect class="juli-accent-fill" x="136" y="132" width="15" height="34" rx="5" stroke-width="5.5" />
      <path d="M139 158 H148" fill="none" stroke="#f8fafc" stroke-width="3" />
      <rect class="juli-accent-fill" x="99" y="123" width="58" height="17" rx="8.5" stroke-width="5.5" />
      <path d="M114 127 V136 M128 127 V136 M142 127 V136" fill="none" stroke="#f8fafc" stroke-opacity="0.7" stroke-width="3" />
    </template>
  </g>
</template>

<script setup>
/**
 * What Juli wears, in three layers JuliFigure draws at different depths: her
 * body's outfit, what sits on her head, and what goes round her neck. The
 * arms, hands, legs and shoes are JuliFigure's, coloured to match (mascot.js).
 */
import { computed } from 'vue'

const props = defineProps({
  part: { type: String, required: true }, // body, head or neck
  outfit: { type: String, default: 'lab-coat' },
  accessory: { type: String, default: 'none' },
})

// The torso most outfits share.
const BODY = 'M100 134 H156 Q166 136 166 150 L168 196 Q168 202 162 202 H94 Q88 202 88 196 L90 150 Q90 136 100 134 Z'

// The space suit's helmet takes the place of anything else on her head or neck.
// (The rider's helmet only takes the place of other headwear.)
const helmet = computed(() => props.outfit === 'space-suit')
</script>

<style scoped>
.juli-accent-stroke { stroke: var(--juli-accent); }
.juli-accent-fill { fill: var(--juli-accent); }

.juli-light { animation: juli-light 1.6s ease-in-out infinite; }
@keyframes juli-light { 50% { opacity: 0.3; } }

@media (prefers-reduced-motion: reduce) {
  .juli-light { animation: none; }
}
</style>
