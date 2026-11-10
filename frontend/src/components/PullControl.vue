<template>
  <div class="space-y-2">
    <!-- A licence to accept before the download -->
    <div v-if="license" class="rounded-lg border border-amber-400/30 bg-amber-400/[0.06] p-2.5 text-xs text-amber-100">
      <p>
        {{ tag }} needs the
        <a :href="license.url" target="_blank" rel="noopener noreferrer" class="underline underline-offset-2">{{ license.name }}</a>.
        Read it, then accept to download.
      </p>
      <button type="button" class="btn btn-primary mt-2 !min-h-0 !py-1 text-xs" @click="$emit('accept')">Accept and download</button>
    </div>

    <div v-else-if="pulling" class="space-y-1">
      <div class="h-1.5 overflow-hidden rounded-full bg-white/10" role="progressbar" :aria-valuenow="percent ?? undefined" aria-valuemin="0" aria-valuemax="100" :aria-label="`Downloading ${tag}`">
        <div class="h-full rounded-full bg-cyan-400 transition-[width]" :style="{ width: `${percent ?? 5}%` }"></div>
      </div>
      <div class="flex items-center gap-2 text-xs text-slate-400">
        <span class="flex-1">{{ percent != null ? `${percent}%` : '' }} {{ progress.detail }}</span>
        <button type="button" class="btn btn-secondary !min-h-0 !py-0.5 text-xs" @click="$emit('cancel')">Cancel</button>
      </div>
    </div>

    <template v-else>
      <p v-if="progress?.status === 'error'" class="text-xs text-red-300">Download failed: {{ progress.error }}</p>
      <p v-else-if="progress?.status === 'cancelled'" class="text-xs text-slate-400">Download cancelled. Downloading again resumes it.</p>
      <button v-if="!installed" type="button" class="btn btn-secondary w-full !min-h-0 !py-1.5 text-xs" :disabled="blocked" @click="$emit('pull')">
        <Icon name="download" class="h-3.5 w-3.5" />{{ progress?.status === 'cancelled' || progress?.status === 'error' ? 'Resume download' : 'Download' }}
      </button>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({
  tag: { type: String, required: true },
  installed: { type: Boolean, default: false },
  blocked: { type: Boolean, default: false }, // won't fit on this machine
  progress: { type: Object, default: null }, // { status, detail, completed, total, error }
  license: { type: Object, default: null },
})
defineEmits(['pull', 'cancel', 'accept'])

const pulling = computed(() => props.progress?.status === 'pulling')
const percent = computed(() => {
  const p = props.progress
  return p && p.total ? Math.min(100, Math.round((p.completed / p.total) * 100)) : null
})
</script>
