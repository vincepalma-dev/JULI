<template>
  <dialog
    ref="dialog"
    class="side-panel"
    :class="{ 'side-panel--wide': wide }"
    :aria-labelledby="titleId"
    @cancel.prevent="$emit('close')"
    @close="$emit('close')"
    @click="closeOnBackdrop"
  >
    <div v-if="open" class="flex h-full flex-col">
      <header class="flex items-center gap-3 border-b border-juli-border px-4 py-3 sm:px-5">
        <Icon :name="icon" class="h-5 w-5 shrink-0 text-juli-accent" />
        <h2 :id="titleId" class="flex-1 text-base font-semibold text-white">{{ title }}</h2>
        <button type="button" class="icon-btn" aria-label="Close" @click="$emit('close')">
          <Icon name="x" class="h-5 w-5" />
        </button>
      </header>
      <slot name="tabs" />
      <div class="flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-5">
        <slot />
      </div>
      <slot name="footer" />
    </div>
  </dialog>
</template>

<script setup>
// A right-hand sheet on the native <dialog>: focus stays inside, Escape closes,
// the page behind is inert, and focus returns to the opener on close.
import { ref, watch, onMounted } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  icon: { type: String, default: 'info' },
  wide: { type: Boolean, default: false },
})
defineEmits(['close'])

const titleId = `panel-title-${Math.random().toString(36).slice(2, 9)}`
const dialog = ref(null)

function sync(open) {
  const el = dialog.value
  if (!el) return
  if (open && !el.open) el.showModal()
  else if (!open && el.open) el.close()
}

function closeOnBackdrop(event) {
  if (event.target === dialog.value) dialog.value.close()
}

watch(() => props.open, sync)
onMounted(() => sync(props.open))
</script>

<style scoped>
.side-panel {
  margin: 0 0 0 auto;
  padding: 0;
  width: 100%;
  max-width: 34rem;
  height: 100dvh;
  max-height: 100dvh;
  border: 0;
  border-left: 1px solid rgba(var(--color-juli-border-rgb), 1);
  background: var(--color-juli-panel);
  color: #e2e8f0;
}

.side-panel--wide {
  max-width: 60rem;
}

.side-panel::backdrop {
  background: rgb(0 0 0 / 0.55);
}

.side-panel[open] {
  animation: panel-in 0.2s cubic-bezier(0.2, 0.8, 0.2, 1);
}

@keyframes panel-in {
  from { transform: translateX(24px); opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .side-panel[open] { animation: none; }
}
</style>
