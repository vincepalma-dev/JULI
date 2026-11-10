/** Colour themes: CSS variables on :root, remembered in this browser only. */

export const THEMES = [
  { id: 'midnight', name: 'Midnight', desc: 'Deep dark with cyan accents', bg: '#0a0e1a', panel: '#0d1321', accent: '#06b6d4', border: '#1a2744', text: '#94a3b8' },
  { id: 'cayman', name: 'Cayman', desc: 'Ocean teal', bg: '#0d1117', panel: '#111822', accent: '#27d4a5', border: '#1a3a35', text: '#9eb3a8' },
  { id: 'slate', name: 'Slate', desc: 'Cool grey', bg: '#1a1d23', panel: '#21252b', accent: '#7c8aff', border: '#2d333b', text: '#adbac7' },
  { id: 'hacker', name: 'Hacker', desc: 'Terminal green on black', bg: '#0d0d0d', panel: '#141414', accent: '#39ff14', border: '#1a2e1a', text: '#7dbb7d' },
  { id: 'architect', name: 'Architect', desc: 'Blueprint blue on navy', bg: '#0a1628', panel: '#0f1d32', accent: '#4a9eff', border: '#1c3554', text: '#8ba4c4' },
  { id: 'merlot', name: 'Merlot', desc: 'Wine red', bg: '#1a0a10', panel: '#21101a', accent: '#e84393', border: '#3a1a2a', text: '#b88a9a' },
  { id: 'minimal', name: 'Minimal', desc: 'Near-black and white', bg: '#111111', panel: '#1a1a1a', accent: '#ffffff', border: '#2a2a2a', text: '#888888' },
  { id: 'tactile', name: 'Tactile', desc: 'Warm amber on charcoal', bg: '#1a1510', panel: '#211c14', accent: '#f59e0b', border: '#3a3020', text: '#b8a88a' },
]

const STORAGE_KEY = 'juli-theme'

function hexToRgb(hex) {
  let c = hex.substring(1)
  if (c.length === 3) c = c.split('').map(x => x + x).join('')
  return `${parseInt(c.slice(0, 2), 16)}, ${parseInt(c.slice(2, 4), 16)}, ${parseInt(c.slice(4, 6), 16)}`
}

export function applyTheme(theme) {
  const root = document.documentElement
  for (const [name, value] of [['bg', theme.bg], ['panel', theme.panel], ['accent', theme.accent], ['border', theme.border], ['muted', theme.text]]) {
    root.style.setProperty(`--color-juli-${name}`, value)
    root.style.setProperty(`--color-juli-${name}-rgb`, hexToRgb(value))
  }
  try {
    localStorage.setItem(STORAGE_KEY, theme.id)
  } catch { /* storage blocked: the theme lasts this visit only */ }
}

export function savedThemeId() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY) || ''
    // Older versions stored the whole theme as JSON.
    return saved.startsWith('{') ? JSON.parse(saved).id : saved
  } catch {
    return ''
  }
}

export function restoreTheme() {
  const theme = THEMES.find(t => t.id === savedThemeId())
  if (theme) applyTheme(theme)
}
