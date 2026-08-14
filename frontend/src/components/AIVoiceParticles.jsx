/**
 * AIVoiceParticles — 3D Particle Swarm AI Voice Visualizer
 * Built with Three.js & InstancedMesh, tailored to JustSpeak dark UI theme.
 */

import React, { useEffect, useRef } from 'react'
import * as THREE from 'three'

export default function AIVoiceParticles({
  appState = 'idle',      // 'idle' | 'listening' | 'thinking' | 'speaking'
  volume = 0,             // 0 - 100
  onClick,
  className = '',
}) {
  const containerRef = useRef(null)
  const sceneRef = useRef(null)
  const rendererRef = useRef(null)
  const frameIdRef = useRef(null)
  const stateRef = useRef({ appState, volume })

  // Keep stateRef up to date without re-initializing WebGL scene
  useEffect(() => {
    stateRef.current = { appState, volume }
  }, [appState, volume])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const width = container.clientWidth || 320
    const height = container.clientHeight || 320

    // ── 1. Setup Scene, Camera & Renderer ────────────────────────
    const scene = new THREE.Scene()
    sceneRef.current = scene

    const camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 1000)
    camera.position.set(0, 0, 85)

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(width, height)
    renderer.setClearColor(0x000000, 0)
    container.appendChild(renderer.domElement)
    rendererRef.current = renderer

    // ── 2. Particle Swarm Config ────────────────────────────────
    const COUNT = 7500
    const dummy = new THREE.Object3D()
    const color = new THREE.Color()
    const target = new THREE.Vector3()

    const geometry = new THREE.TetrahedronGeometry(0.35)
    const material = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.85,
    })

    const instancedMesh = new THREE.InstancedMesh(geometry, material, COUNT)
    instancedMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
    scene.add(instancedMesh)

    // Store particle base coords & velocities
    const positions = new Float32Array(COUNT * 3)
    const targetPositions = new Float32Array(COUNT * 3)
    const baseAngles = new Float32Array(COUNT * 2) // phi, theta

    // Palette Colors matching JustSpeak Theme
    const COLOR_IDLE_BASE   = new THREE.Color(0x3B82F6) // Electric Blue
    const COLOR_IDLE_ALT    = new THREE.Color(0x6366F1) // Indigo
    const COLOR_LISTEN_BASE = new THREE.Color(0x00E5FF) // Cyan Glow
    const COLOR_LISTEN_ALT  = new THREE.Color(0x3B82F6) // Blue
    const COLOR_THINK_BASE  = new THREE.Color(0xF59E0B) // Amber Gold
    const COLOR_THINK_ALT   = new THREE.Color(0xEC4899) // Pink / Violet
    const COLOR_SPEAK_BASE  = new THREE.Color(0x10B981) // Emerald Green
    const COLOR_SPEAK_ALT   = new THREE.Color(0x06B6D4) // Turquoise

    // Initialize Fibonacci sphere coordinates
    for (let i = 0; i < COUNT; i++) {
      const phi = Math.acos(-1 + (2 * i) / COUNT)
      const theta = Math.sqrt(COUNT * Math.PI) * phi
      baseAngles[i * 2] = phi
      baseAngles[i * 2 + 1] = theta

      // Random starting scattered positions
      const rx = (Math.random() - 0.5) * 80
      const ry = (Math.random() - 0.5) * 80
      const rz = (Math.random() - 0.5) * 80

      positions[i * 3] = rx
      positions[i * 3 + 1] = ry
      positions[i * 3 + 2] = rz

      instancedMesh.setColorAt(i, COLOR_IDLE_BASE)
    }
    instancedMesh.instanceColor.needsUpdate = true

    // ── 3. Animation Loop ────────────────────────────────────────
    const clock = new THREE.Clock()
    let rotationAngle = 0

    const animate = () => {
      frameIdRef.current = requestAnimationFrame(animate)

      const delta = clock.getDelta()
      const time = clock.getElapsedTime()
      const { appState: currState, volume: currVol } = stateRef.current

      // Dynamic rotation speed based on voice state
      let rotSpeed = 0.5
      let baseRadius = 24
      let waveFrequency = 3.0
      let waveAmplitude = 1.8
      let cBase = COLOR_IDLE_BASE
      let cAlt = COLOR_IDLE_ALT

      if (currState === 'listening') {
        rotSpeed = 1.4 + (currVol / 100) * 1.5
        baseRadius = 25 + (currVol / 100) * 10
        waveFrequency = 6.0
        waveAmplitude = 3.2 + (currVol / 100) * 4.5
        cBase = COLOR_LISTEN_BASE
        cAlt = COLOR_LISTEN_ALT
      } else if (currState === 'thinking') {
        rotSpeed = 2.8
        baseRadius = 22 + Math.sin(time * 5) * 2.5
        waveFrequency = 8.0
        waveAmplitude = 3.5
        cBase = COLOR_THINK_BASE
        cAlt = COLOR_THINK_ALT
      } else if (currState === 'speaking') {
        rotSpeed = 1.2
        baseRadius = 26 + Math.sin(time * 3.5) * 3.5
        waveFrequency = 4.5
        waveAmplitude = 2.8 + Math.sin(time * 4) * 2
        cBase = COLOR_SPEAK_BASE
        cAlt = COLOR_SPEAK_ALT
      }

      rotationAngle += delta * rotSpeed
      instancedMesh.rotation.y = rotationAngle
      instancedMesh.rotation.x = Math.sin(time * 0.4) * 0.25

      // Update individual particles
      for (let i = 0; i < COUNT; i++) {
        const phi = baseAngles[i * 2]
        const theta = baseAngles[i * 2 + 1]

        // Spherical surface deformation / voice ripple
        const noise = Math.sin(phi * waveFrequency + time * 3.2) *
                      Math.cos(theta * (waveFrequency * 0.6) + time * 2.5) * waveAmplitude

        const r = baseRadius + noise

        const tx = r * Math.sin(phi) * Math.cos(theta)
        const ty = r * Math.cos(phi)
        const tz = r * Math.sin(phi) * Math.sin(theta)

        // Smooth Lerp positions
        const i3 = i * 3
        positions[i3] += (tx - positions[i3]) * 0.08
        positions[i3 + 1] += (ty - positions[i3 + 1]) * 0.08
        positions[i3 + 2] += (tz - positions[i3 + 2]) * 0.08

        dummy.position.set(positions[i3], positions[i3 + 1], positions[i3 + 2])

        // Scale individual particles dynamically on speaking
        const pScale = 0.8 + (Math.sin(time * 2 + i * 0.05) * 0.25)
        dummy.scale.set(pScale, pScale, pScale)
        dummy.updateMatrix()

        instancedMesh.setMatrixAt(i, dummy.matrix)

        // Gradient color blending across height & state
        const heightFactor = (ty + baseRadius) / (baseRadius * 2)
        color.copy(cBase).lerp(cAlt, THREE.MathUtils.clamp(heightFactor + Math.sin(time + i * 0.01) * 0.2, 0, 1))
        instancedMesh.setColorAt(i, color)
      }

      instancedMesh.instanceMatrix.needsUpdate = true
      if (instancedMesh.instanceColor) {
        instancedMesh.instanceColor.needsUpdate = true
      }

      renderer.render(scene, camera)
    }

    animate()

    // ── 4. Resize Handling ───────────────────────────────────────
    const handleResize = () => {
      if (!container || !rendererRef.current) return
      const newW = container.clientWidth || 320
      const newH = container.clientHeight || 320
      camera.aspect = newW / newH
      camera.updateProjectionMatrix()
      rendererRef.current.setSize(newW, newH)
    }

    window.addEventListener('resize', handleResize)

    // ── 5. Cleanup ──────────────────────────────────────────────
    return () => {
      window.removeEventListener('resize', handleResize)
      if (frameIdRef.current) cancelAnimationFrame(frameIdRef.current)
      geometry.dispose()
      material.dispose()
      renderer.dispose()
      if (container && renderer.domElement) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [])

  return (
    <div
      ref={containerRef}
      onClick={onClick}
      className={`relative flex items-center justify-center cursor-pointer select-none transition-transform duration-300 active:scale-95 ${className}`}
      style={{ width: '100%', height: '100%' }}
      title="Tap to speak"
    />
  )
}
