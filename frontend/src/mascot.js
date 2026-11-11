/**
 * Juli's looks: what she can wear, how she idles and how she works. Her own
 * look is remembered in this browser only, like the theme; each agent's look
 * is saved with the agent.
 */
import { reactive, ref } from 'vue'

// sleeve, hand, leg and shoe colour the parts every outfit shares.
export const OUTFITS = [
  { id: 'lab-coat', name: 'Lab coat', sleeve: '#f1f5f9' },
  { id: 'hoodie', name: 'Hoodie', sleeve: '#a78bfa' },
  { id: 'blazer', name: 'Blazer', sleeve: '#475569' },
  { id: 'space-suit', name: 'Space suit', sleeve: '#e2e8f0', hand: '#fb923c', leg: '#e2e8f0', shoe: '#fb923c' },
  { id: 'pajamas', name: 'Pajamas', sleeve: '#bfdbfe', leg: '#bfdbfe', shoe: '#f9a8d4' },
  { id: 'overalls', name: 'Overalls', sleeve: '#fde68a', leg: '#3b82f6', shoe: '#92400e' },
  { id: 'raincoat', name: 'Raincoat', sleeve: '#facc15', shoe: '#ef4444' },
  { id: 'varsity', name: 'Varsity jacket', sleeve: '#f8fafc', leg: '#1e3a8a', shoe: '#f8fafc' },
  { id: 'apron', name: 'Apron', sleeve: '#f8fafc' },
  { id: 'tracksuit', name: 'Tracksuit', sleeve: '#14b8a6', leg: '#14b8a6', shoe: '#f8fafc' },
  { id: 'rider', name: 'Motorcycle rider', sleeve: '#4b5563', hand: '#9ca3af', leg: '#1e293b', shoe: '#6b7280' },
]

export const ACCESSORIES = [
  { id: 'none', name: 'None' },
  { id: 'cap', name: 'Cap' },
  { id: 'beanie', name: 'Beanie' },
  { id: 'headphones', name: 'Headphones' },
  { id: 'party-hat', name: 'Party hat' },
  { id: 'scarf', name: 'Scarf' },
]

export const IDLES = [
  { id: 'calm', name: 'Calm', desc: 'Breathes and looks around' },
  { id: 'wave', name: 'Wave', desc: 'Waves hello now and then' },
  { id: 'stretch', name: 'Stretch', desc: 'Arms up, with a yawn' },
  { id: 'coffee', name: 'Coffee', desc: 'Sips from a mug' },
  { id: 'curious', name: 'Curious', desc: 'Peers about and adjusts her glasses' },
  { id: 'dance', name: 'Dance', desc: 'A little side-step' },
  { id: 'juggle', name: 'Juggle', desc: 'Keeps three balls in the air' },
  { id: 'read', name: 'Read', desc: 'Turns the pages of a book' },
  { id: 'phone', name: 'Phone', desc: 'Scrolls and smiles' },
  { id: 'nap', name: 'Nap', desc: 'Dozes off' },
  { id: 'ride', name: 'Ride', desc: 'Cruises on her motorcycle' },
  { id: 'shuffle', name: 'Shuffle', desc: 'A different one every so often' },
]

// The pose an agent works in. "auto" goes by its role.
export const POSES = [
  { id: 'auto', name: 'By role' },
  { id: 'planner', name: 'Planning' },
  { id: 'coder', name: 'Coding' },
  { id: 'reviewer', name: 'Reviewing' },
  { id: 'tester', name: 'Testing' },
  { id: 'docs', name: 'Writing docs' },
  { id: 'devops', name: 'Fixing' },
  { id: 'security', name: 'Guarding' },
  { id: 'analyst', name: 'Analysing' },
]

const DEFAULT_LOOK = { outfit: 'lab-coat', accessory: 'none', idle: 'calm' }
const LISTS = { outfit: OUTFITS, accessory: ACCESSORIES, idle: IDLES }
const STORAGE_KEY = 'juli-mascot'

const known = (part, id) => LISTS[part].some(item => item.id === id)

/** Juli's own look. Every Juli without a look of its own follows it. */
export const mascotLook = reactive({ ...DEFAULT_LOOK })

export function setLook(part, id) {
  if (!known(part, id)) return
  mascotLook[part] = id
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(mascotLook))
  } catch { /* storage blocked: the look lasts this visit only */ }
}

export function restoreMascot() {
  let saved = {}
  try {
    saved = JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}
  } catch { /* nothing saved, or not ours: keep the defaults */ }
  for (const part of Object.keys(DEFAULT_LOOK)) {
    mascotLook[part] = known(part, saved[part]) ? saved[part] : DEFAULT_LOOK[part]
  }
}

/** A full look from a partial one (an agent's settings, or props): anything unset, "default" or unknown follows Juli. */
export function lookOf(look = {}) {
  const part = name => (known(name, look[name]) ? look[name] : mascotLook[name])
  return { outfit: part('outfit'), accessory: part('accessory'), idle: part('idle') }
}

/** An agent's Juli: its look, wearing the agent's colour. */
export function agentLook(cfg) {
  return cfg ? { ...lookOf(cfg), accent: cfg.color || '' } : {}
}

// ─── Shuffle: one clock for every Juli on the page ───

const SHUFFLED = IDLES.map(i => i.id).filter(id => id !== 'shuffle')
const SHUFFLE_MS = 20_000
export const shuffledIdle = ref('calm')
let timer = null

/** Start the shuffle clock, once. It stays off when the viewer prefers reduced motion. */
export function startShuffle() {
  if (timer || typeof window === 'undefined') return
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
  timer = setInterval(() => {
    shuffledIdle.value = SHUFFLED[(SHUFFLED.indexOf(shuffledIdle.value) + 1) % SHUFFLED.length]
  }, SHUFFLE_MS)
}
