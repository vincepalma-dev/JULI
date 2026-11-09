<template>
  <transition name="slide">
    <div v-if="open" class="fixed inset-y-0 left-0 w-80 glass z-50 shadow-glass-lg flex flex-col border-r border-juli-border">
      <!-- Header -->
      <div class="p-4 border-b border-juli-border flex items-center justify-between shrink-0">
        <h2 class="text-lg font-bold text-white flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5 text-juli-accent">
            <path d="M3 4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-5.828A2 2 0 0 1 9.757 5.414l-1.172-1.171A2 2 0 0 0 7.172 3.657L3 4Z" />
          </svg>
          Projects
        </h2>
        <button @click="$emit('close')" class="text-juli-muted hover:text-white transition-colors text-lg">
          &times;
        </button>
      </div>

      <!-- New Project / Content -->
      <div class="flex-1 overflow-y-auto p-4 space-y-4">
        <div>
          <label class="block text-xs font-semibold text-juli-muted uppercase tracking-wider mb-2">New Project</label>
          <div class="flex gap-2">
            <input 
              v-model="newProjectName" 
              placeholder="e.g. Protocol 84" 
              class="flex-1 glass-input rounded-md px-3 py-1.5 text-sm"
              @keyup.enter="handleCreate"
            />
            <button @click="handleCreate" class="px-3 py-1.5 rounded-md glass text-sm font-medium hover:text-juli-accent hover:border-juli-accent/30 transition-colors">
              Add
            </button>
          </div>
        </div>

        <div class="space-y-2 mt-4">
          <label class="block text-xs font-semibold text-juli-muted uppercase tracking-wider mb-2">History</label>
          <div v-if="projects.length === 0" class="text-sm text-juli-muted text-center py-4">
            No projects found.
          </div>
          
          <div 
            v-for="proj in projects" 
            :key="proj.id"
            class="p-3 rounded-lg border transition-all cursor-pointer group flex items-center justify-between"
            :class="[
              activeProjectId === proj.id 
                ? 'bg-juli-accent/10 border-juli-accent/40 shadow-glow-sm' 
                : 'glass-light hover:border-juli-accent/20'
            ]"
            @click="$emit('select-project', proj.id)"
          >
            <div class="min-w-0">
              <p class="text-sm font-medium text-white truncate" :class="{ 'text-juli-accent': activeProjectId === proj.id }">
                {{ proj.name }}
              </p>
              <p class="text-[10px] text-juli-muted mt-1">{{ formatDate(proj.updated_at) }}</p>
            </div>
            <button 
              @click.stop="$emit('delete-project', proj.id)" 
              class="opacity-0 group-hover:opacity-100 p-1.5 rounded bg-white/5 hover:bg-red-500/20 text-juli-muted hover:text-red-400 transition-all shrink-0 ml-2"
              title="Delete Project"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
                <path fill-rule="evenodd" d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.52.149.023a.75.75 0 0 0 .23-1.482A41.03 41.03 0 0 0 14 4.193V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4ZM8.58 7.72a.75.75 0 0 0-1.5.06l.3 7.5a.75.75 0 1 0 1.5-.06l-.3-7.5Zm4.34.06a.75.75 0 1 0-1.5-.06l-.3 7.5a.75.75 0 1 0 1.5.06l.3-7.5Z" clip-rule="evenodd" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  projects: { type: Array, default: () => [] },
  activeProjectId: { type: String, default: null }
})

const emit = defineEmits(['close', 'create-project', 'select-project', 'delete-project'])

const newProjectName = ref('')

function handleCreate() {
  const name = newProjectName.value.trim()
  if (name) {
    emit('create-project', name)
    newProjectName.value = ''
  }
}

function formatDate(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return d.toLocaleString()
}
</script>

<style scoped>
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(-100%);
}
</style>
