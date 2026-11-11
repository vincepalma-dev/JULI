<template>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path v-for="(d, i) in paths" :key="i" :d="d" />
  </svg>
</template>

<script setup>
// Hand-drawn line icons on a 24px grid. Icon-only buttons using these need an aria-label.
import { computed } from 'vue'

const props = defineProps({ name: { type: String, required: true } })

// A circle as a path, so every icon is a list of `d` strings.
const circle = (cx, cy, r) => `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`

const ICONS = {
  x: ['M6 6l12 12M18 6L6 18'],
  plus: ['M12 5v14M5 12h14'],
  check: ['M5 12.5l4.5 4.5L19 7'],
  'chevron-down': ['M6 9l6 6 6-6'],
  'chevron-up': ['M6 15l6-6 6 6'],
  'chevron-right': ['M9 6l6 6-6 6'],
  'chevron-left': ['M15 6l-6 6 6 6'],
  menu: ['M4 7h16M4 12h16M4 17h16'],
  send: ['M12 19V5M6 11l6-6 6 6'],
  stop: ['M7 7h10v10H7z'],
  play: ['M8 5.5v13l11-6.5z'],
  refresh: ['M20 12a8 8 0 1 1-2.34-5.66M20 4v4.5h-4.5'],
  download: ['M12 4v11M7 10l5 5 5-5M5 20h14'],
  upload: ['M12 16V5M7 10l5-5 5 5M5 20h14'],
  folder: ['M3 7.5A1.5 1.5 0 0 1 4.5 6H9l2 2h8.5A1.5 1.5 0 0 1 21 9.5v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z'],
  file: ['M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM14 3v5h5'],
  terminal: ['M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM7 10l3 2.5L7 15M12 15h5'],
  cube: ['M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9'],
  users: [circle(9, 8, 3.5), 'M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6', circle(17, 9, 2.5), 'M16.5 14.2A4.5 4.5 0 0 1 21 18.5'],
  sliders: ['M4 7h9M17 7h3M4 17h3M11 17h9', circle(15, 7, 2), circle(9, 17, 2)],
  code: ['M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14'],
  lock: ['M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3'],
  cloud: ['M7 18h10.5a3.5 3.5 0 0 0 .4-6.98A5.5 5.5 0 0 0 7.2 10 4 4 0 0 0 7 18z'],
  arrows: ['M7 8h13M16 4l4 4-4 4M17 16H4M8 12l-4 4 4 4'],
  alert: ['M12 4l9 16H3zM12 10v4M12 17.2v.3'],
  info: [circle(12, 12, 9), 'M12 11v5M12 7.7v.3'],
  key: [circle(8, 15, 4), 'M11 12l8-8M16 7l2 2'],
  eye: ['M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z', circle(12, 12, 3)],
  'eye-off': ['M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z', circle(12, 12, 3), 'M4 4l16 16'],
  trash: ['M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13M10 11v6M14 11v6'],
  pencil: ['M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4'],
  branch: [circle(6, 6, 2), circle(6, 18, 2), circle(18, 8, 2), 'M6 8v8M18 10v1a4 4 0 0 1-4 4H8'],
  chat: ['M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-7l-4 3.5V16H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z'],
  clock: [circle(12, 12, 9), 'M12 7.5V12l3 2'],
  coin: [circle(12, 12, 9), 'M14.5 9.2c-.5-.8-1.4-1.2-2.5-1.2-1.4 0-2.5.7-2.5 1.9 0 2.6 5 1.3 5 4 0 1.2-1.1 2-2.5 2-1.2 0-2.2-.5-2.7-1.4M12 6.5V8M12 16v1.5'],
  cpu: ['M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4'],
  signal: ['M5 12.5a10 10 0 0 1 14 0M8 15.5a5.5 5.5 0 0 1 8 0M12 19v.01'],
  'signal-off': ['M5 12.5a10 10 0 0 1 14 0M8 15.5a5.5 5.5 0 0 1 8 0M12 19v.01M4 4l16 16'],
  sparkle: ['M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z'],
  shield: ['M12 3l7 3v5.5c0 4.5-3 8-7 9.5-4-1.5-7-5-7-9.5V6z'],
  external: ['M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5'],
  copy: ['M9 9h10v11H9zM5 15V4h10'],
  bolt: ['M13 3L5 13.5h6L10 21l8-10.5h-6z'],
  gauge: ['M4.5 17a8.5 8.5 0 1 1 15 0M12 13l4-4'],
  search: [circle(11, 11, 6), 'M20 20l-4.6-4.6'],
  wrench: ['M14.7 6.3a4 4 0 0 0-5.3 5.3L4 17l3 3 5.4-5.4a4 4 0 0 0 5.3-5.3l-2.5 2.5-2.4-.4-.4-2.4z'],
}

const paths = computed(() => ICONS[props.name] || ICONS.info)
</script>
