<template>
  <canvas
    ref="canvas"
    class="fixed inset-0 pointer-events-none"
    aria-hidden="true"
    style="z-index: 0;"
  ></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const canvas = ref(null)
let animationId = null
let onResize = null
// With reduced motion, the particles are drawn once and stay still.
const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches

onMounted(() => {
  const ctx = canvas.value.getContext('2d')
  let width, height
  const particles = []
  const PARTICLE_COUNT = 60
  const CONNECTION_DISTANCE = 120
  const MOUSE = { x: -1000, y: -1000 }

  function resize() {
    width = canvas.value.width = window.innerWidth
    height = canvas.value.height = window.innerHeight
  }

  function createParticle() {
    return {
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      radius: Math.random() * 1.5 + 0.5,
      opacity: Math.random() * 0.4 + 0.1,
    }
  }

  function init() {
    resize()
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push(createParticle())
    }
  }

  function draw() {
    ctx.clearRect(0, 0, width, height)

    // Draw connections
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x
        const dy = particles[i].y - particles[j].y
        const dist = Math.sqrt(dx * dx + dy * dy)

        if (dist < CONNECTION_DISTANCE) {
          const alpha = (1 - dist / CONNECTION_DISTANCE) * 0.08
          ctx.strokeStyle = `rgba(6, 182, 212, ${alpha})`
          ctx.lineWidth = 0.5
          ctx.beginPath()
          ctx.moveTo(particles[i].x, particles[i].y)
          ctx.lineTo(particles[j].x, particles[j].y)
          ctx.stroke()
        }
      }
    }

    // Draw particles
    for (const p of particles) {
      // Particle glow
      const gradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.radius * 4)
      gradient.addColorStop(0, `rgba(6, 182, 212, ${p.opacity * 0.6})`)
      gradient.addColorStop(1, 'rgba(6, 182, 212, 0)')
      ctx.fillStyle = gradient
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.radius * 4, 0, Math.PI * 2)
      ctx.fill()

      // Particle core
      ctx.fillStyle = `rgba(6, 182, 212, ${p.opacity})`
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
      ctx.fill()

      // Update position
      p.x += p.vx
      p.y += p.vy

      // Wrap around edges
      if (p.x < -10) p.x = width + 10
      if (p.x > width + 10) p.x = -10
      if (p.y < -10) p.y = height + 10
      if (p.y > height + 10) p.y = -10
    }

    if (!still) animationId = requestAnimationFrame(draw)
  }

  onResize = () => {
    resize()
    if (still) draw()
  }
  window.addEventListener('resize', onResize)
  init()
  draw()
})

onUnmounted(() => {
  if (animationId) cancelAnimationFrame(animationId)
  if (onResize) window.removeEventListener('resize', onResize)
})
</script>
