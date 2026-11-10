<template>
  <div class="space-y-3">
    <template v-for="(block, i) in blocks" :key="i">
      <div v-if="block.type === 'code'" class="overflow-hidden rounded-lg border border-juli-border bg-black/30">
        <div class="flex items-center gap-2 border-b border-juli-border px-3 py-1.5">
          <span class="font-mono text-xs text-slate-400">{{ block.path || block.lang || 'code' }}</span>
          <button type="button" class="ml-auto inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-slate-400 hover:text-white" @click="copy(block.code, i)">
            <Icon :name="copied === i ? 'check' : 'copy'" class="h-3.5 w-3.5" />
            {{ copied === i ? 'Copied' : 'Copy' }}
          </button>
        </div>
        <pre class="overflow-x-auto px-3 py-2.5 font-mono text-xs leading-relaxed text-slate-200">{{ block.code }}</pre>
      </div>
      <p v-else class="prose-msg">{{ block.text }}</p>
    </template>
  </div>
</template>

<script setup>
// Message text with fenced code blocks shown as code. An unclosed fence (text
// still streaming in) stays plain text until it closes.
import { ref, computed } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({ text: { type: String, default: '' } })
const copied = ref(-1)

const blocks = computed(() => {
  const out = []
  for (const part of props.text.split(/(```[^\n]*\n[\s\S]*?```)/g)) {
    const m = part.match(/^```([^\n]*)\n([\s\S]*?)```$/)
    if (m) {
      const info = m[1].trim()
      const path = info.match(/path=(\S+)/)?.[1] || ''
      out.push({ type: 'code', lang: info.split(/\s+/)[0] || '', path, code: m[2].replace(/\n$/, '') })
    } else if (part.trim()) {
      out.push({ type: 'text', text: part.replace(/^\n+|\n+$/g, '') })
    }
  }
  return out
})

async function copy(code, i) {
  try {
    await navigator.clipboard.writeText(code)
    copied.value = i
    setTimeout(() => { if (copied.value === i) copied.value = -1 }, 1500)
  } catch { /* clipboard blocked */ }
}
</script>
