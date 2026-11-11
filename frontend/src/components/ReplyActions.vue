<template>
  <p class="mt-1.5 flex flex-wrap items-center gap-x-1 gap-y-1 text-xs text-slate-400">
    <button type="button" class="-ml-1.5 inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:text-white" title="Copy this reply" @click="copy">
      <Icon :name="copied ? 'check' : 'copy'" class="h-3.5 w-3.5" />
      {{ copied ? 'Copied' : 'Copy' }}
    </button>
    <button type="button" class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:text-white" title="Download this reply as a Markdown file" @click="saveText(text, filename, 'text/markdown')">
      <Icon name="download" class="h-3.5 w-3.5" />
      Download
    </button>
    <button v-if="zipProject" type="button" class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:text-white disabled:opacity-60" title="Download the project's files as a zip" :disabled="zipping" @click="downloadFiles">
      <Icon name="folder" class="h-3.5 w-3.5" />
      {{ zipping ? 'Preparing…' : 'Download files' }}
    </button>
    <span v-if="error" role="alert" class="text-red-300">{{ error }}</span>
  </p>
</template>

<script setup>
// Under a reply: copy its text, download it as a Markdown file and, at the
// end of a run that wrote files, download the project's files as a zip.
import { ref } from 'vue'
import Icon from './Icon.vue'
import { apiDownload, saveText } from '../api.js'

const props = defineProps({
  text: { type: String, default: '' },
  filename: { type: String, required: true }, // for the Markdown download
  zipProject: { type: String, default: null }, // a project id: also offer its files
})

const copied = ref(false)
const zipping = ref(false)
const error = ref('')

async function copy() {
  try {
    await navigator.clipboard.writeText(props.text)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* clipboard blocked */ }
}

async function downloadFiles() {
  zipping.value = true
  error.value = ''
  try {
    await apiDownload(`/api/projects/${props.zipProject}/workspace/zip`, `juli-${props.zipProject.slice(0, 8)}.zip`)
  } catch (e) {
    error.value = e.message
  } finally {
    zipping.value = false
  }
}
</script>
