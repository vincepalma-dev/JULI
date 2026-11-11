import { afterEach, describe, expect, it, vi } from 'vitest'
import { agentLook, lookOf, mascotLook, restoreMascot, setLook, shuffledIdle, startShuffle } from '../src/mascot.js'

afterEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  restoreMascot() // back to the defaults for the next test
})

describe("Juli's own look", () => {
  it('starts in the lab coat, calm', () => {
    expect({ ...mascotLook }).toEqual({ outfit: 'lab-coat', accessory: 'none', idle: 'calm' })
  })

  it('is remembered in this browser', () => {
    setLook('outfit', 'rider')
    setLook('idle', 'ride')
    mascotLook.outfit = 'lab-coat' // as after a reload
    restoreMascot()
    expect({ ...mascotLook }).toEqual({ outfit: 'rider', accessory: 'none', idle: 'ride' })
  })

  it('ignores a look it does not know', () => {
    setLook('outfit', 'tuxedo')
    expect(mascotLook.outfit).toBe('lab-coat')
    localStorage.setItem('juli-mascot', JSON.stringify({ outfit: 'tuxedo', accessory: 'cap', idle: 7 }))
    restoreMascot()
    expect({ ...mascotLook }).toEqual({ outfit: 'lab-coat', accessory: 'cap', idle: 'calm' })
    localStorage.setItem('juli-mascot', 'not json')
    restoreMascot()
    expect(mascotLook.accessory).toBe('none')
  })
})

describe('an agent\'s look', () => {
  it("follows Juli's for anything unset, default or unknown", () => {
    setLook('outfit', 'hoodie')
    expect(lookOf({ outfit: 'default', accessory: 'scarf', idle: 'moonwalk' })).toEqual({ outfit: 'hoodie', accessory: 'scarf', idle: 'calm' })
    expect(lookOf()).toEqual({ outfit: 'hoodie', accessory: 'none', idle: 'calm' })
  })

  it("wears the agent's colour", () => {
    expect(agentLook({ outfit: 'blazer', color: '#ef4444' })).toEqual({ outfit: 'blazer', accessory: 'none', idle: 'calm', accent: '#ef4444' })
    expect(agentLook(undefined)).toEqual({}) // a speaker outside the crew
  })
})

describe('shuffle', () => {
  it('moves every shuffling Juli to the next idle style on one clock', () => {
    vi.useFakeTimers()
    startShuffle()
    startShuffle() // a second Juli: still one clock
    expect(shuffledIdle.value).toBe('calm')
    vi.advanceTimersByTime(20_000)
    expect(shuffledIdle.value).toBe('wave')
    vi.advanceTimersByTime(20_000)
    expect(shuffledIdle.value).toBe('stretch')
  })
})
