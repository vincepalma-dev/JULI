<template>
  <SidePanel :open="open" title="Projects" icon="folder" @close="$emit('close')">
    <form class="flex gap-2" @submit.prevent="create">
      <label for="new-project" class="sr-only">New project name</label>
      <input id="new-project" v-model="name" maxlength="100" class="field" placeholder="New project name…" autocomplete="off" />
      <button type="submit" class="btn btn-primary shrink-0" :disabled="!name.trim()"><Icon name="plus" class="h-4 w-4" />Create</button>
    </form>

    <h3 class="mb-2 mt-6 text-xs font-medium text-slate-400">Your projects</h3>
    <p v-if="!projects.length" class="text-sm text-slate-400">No projects yet.</p>
    <ul class="space-y-2">
      <li v-for="p in projects" :key="p.id" class="surface flex items-center gap-2 p-1.5" :class="p.id === activeProjectId ? '!border-cyan-400/40' : ''">
        <template v-if="confirming === p.id">
          <p class="flex-1 px-2 text-sm text-red-200">Delete {{ p.name }} with all its runs and messages? Its workspace files stay on disk.</p>
          <button type="button" class="btn btn-danger" @click="remove(p.id)">Delete</button>
          <button type="button" class="btn btn-secondary" @click="confirming = null">Keep</button>
        </template>
        <template v-else>
          <button type="button" class="min-w-0 flex-1 rounded-lg px-2 py-1.5 text-left hover:bg-white/[0.04]" :aria-current="p.id === activeProjectId ? 'true' : undefined" @click="$emit('select-project', p.id)">
            <span class="block text-sm font-medium text-slate-100" style="overflow-wrap: anywhere">{{ p.name }}</span>
            <span class="block text-xs text-slate-400">{{ p.id === activeProjectId ? 'Open now · ' : '' }}Updated {{ formatDate(p.updated_at) }}</span>
          </button>
          <button type="button" class="icon-btn hover:!text-red-300" :aria-label="`Delete ${p.name}`" @click="confirming = p.id">
            <Icon name="trash" class="h-4 w-4" />
          </button>
        </template>
      </li>
    </ul>
  </SidePanel>
</template>

<script setup>
import { ref } from 'vue'
import Icon from './Icon.vue'
import SidePanel from './SidePanel.vue'

defineProps({
  open: { type: Boolean, default: false },
  projects: { type: Array, default: () => [] },
  activeProjectId: { type: String, default: null },
})
const emit = defineEmits(['close', 'create-project', 'select-project', 'delete-project'])

const name = ref('')
const confirming = ref(null)

function create() {
  const value = name.value.trim()
  if (!value) return
  emit('create-project', value)
  name.value = ''
}

function remove(id) {
  confirming.value = null
  emit('delete-project', id)
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-PH', { dateStyle: 'medium', timeStyle: 'short' })
}
</script>
