/**
 * JustSpeak — Voice-First AI Pension Assistant
 * Sleek Siri-Style Voice Interaction UI
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Mic, Volume2, VolumeX, Sparkles, Loader2, Globe, CheckCircle2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import AudioPlayer from './components/AudioPlayer'
import DebugPanel from './components/DebugPanel'
import AIVoiceParticles from './components/AIVoiceParticles'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ─── Audio Recording Helpers ─────────────────────────────────
async function startRecording(stream, mediaRecorderRef, chunksRef) {
  const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
  chunksRef.current = []
  recorder.ondataavailable = (e) => {
    if (e.data.size > 0) chunksRef.current.push(e.data)
  }
  recorder.start()
  mediaRecorderRef.current = recorder
}

function stopRecording(mediaRecorderRef, streamRef) {
  return new Promise((resolve) => {
    const recorder = mediaRecorderRef.current
    if (!recorder) return resolve(null)
    recorder.onstop = () => resolve(null)
    recorder.stop()
    streamRef.current?.getTracks().forEach((t) => t.stop())
  })
}

function buildAudioBlob(chunksRef) {
  return new Blob(chunksRef.current, { type: 'audio/webm' })
}

export default function App() {
  // App state: 'idle' | 'listening' | 'thinking' | 'speaking'
  const [appState, setAppState] = useState('idle')
  const [sessionId, setSessionId] = useState(null)
  const [lang, setLang] = useState('ta') // 'ta' | 'en'
  const [agentMessage, setAgentMessage] = useState('வணக்கம்! பேச தொடங்குங்கள்.')
  const [audioB64, setAudioB64] = useState(null)
  const [started, setStarted] = useState(false)
  const [done, setDone] = useState(false)
  const [referenceNumber, setReferenceNumber] = useState(null)
  const [convState, setConvState] = useState('GREETING')
  const [slotsConfig, setSlotsConfig] = useState([])
  const [currentSlot, setCurrentSlot] = useState(null)
  const [slotsData, setSlotsData] = useState({})
  const [turnId, setTurnId] = useState(0)

  // Siri UI visual state
  const [volume, setVolume] = useState(0)
  const [duration, setDuration] = useState(0)
  const [particles, setParticles] = useState([])
  const [waveformData, setWaveformData] = useState(Array(32).fill(0))

  // Debug panel state
  const [debugOpen, setDebugOpen] = useState(false)
  const [debugData, setDebugData] = useState({})

  // Refs
  const mediaRecorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const timerIntervalRef = useRef(null)
  const waveformIntervalRef = useRef(null)
  const animationRef = useRef(null)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)

  // ── Ambient Particles ──────────────────────────────────────
  useEffect(() => {
    const newParticles = []
    for (let i = 0; i < 24; i++) {
      newParticles.push({
        id: i,
        x: Math.random() * 400,
        y: Math.random() * 600,
        size: Math.random() * 3 + 1,
        opacity: Math.random() * 0.35 + 0.1,
        velocity: {
          x: (Math.random() - 0.5) * 0.4,
          y: (Math.random() - 0.5) * 0.4,
        },
      })
    }
    setParticles(newParticles)
  }, [])

  useEffect(() => {
    const animateParticles = () => {
      setParticles((prev) =>
        prev.map((p) => ({
          ...p,
          x: (p.x + p.velocity.x + 400) % 400,
          y: (p.y + p.velocity.y + 600) % 600,
          opacity: Math.max(0.1, Math.min(0.5, p.opacity + (Math.random() - 0.5) * 0.02)),
        }))
      )
      animationRef.current = requestAnimationFrame(animateParticles)
    }

    animationRef.current = requestAnimationFrame(animateParticles)
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current)
    }
  }, [])

  // ── Waveform & Timer loop ──────────────────────────────────
  useEffect(() => {
    if (appState === 'listening' || appState === 'speaking') {
      // Start duration timer
      timerIntervalRef.current = setInterval(() => {
        setDuration((prev) => prev + 1)
      }, 1000)

      // Start waveform & volume animation
      waveformIntervalRef.current = setInterval(() => {
        if (analyserRef.current) {
          const buffer = new Uint8Array(analyserRef.current.frequencyBinCount)
          analyserRef.current.getByteFrequencyData(buffer)
          const sliceSize = Math.floor(buffer.length / 32)
          const bars = []
          let sum = 0
          for (let i = 0; i < 32; i++) {
            const val = buffer[i * sliceSize] || 0
            bars.push(Math.max(6, (val / 255) * 80))
            sum += val
          }
          setWaveformData(bars)
          setVolume(Math.min(100, Math.round((sum / (32 * 255)) * 120)))
        } else {
          // Dynamic simulation fallback
          const bars = Array(32)
            .fill(0)
            .map(() => Math.random() * (appState === 'listening' ? 75 : 65) + 8)
          setWaveformData(bars)
          setVolume(Math.round(Math.random() * 40 + 40))
        }
      }, 100)
    } else {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current)
      if (waveformIntervalRef.current) clearInterval(waveformIntervalRef.current)
      setWaveformData(Array(32).fill(4))
      setVolume(0)
      if (appState === 'idle') {
        setDuration(0)
      }
    }

    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current)
      if (waveformIntervalRef.current) clearInterval(waveformIntervalRef.current)
    }
  }, [appState])

  // ── Keyboard shortcut: Ctrl+D for Debug Panel ──────────────
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
        e.preventDefault()
        setDebugOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // ── Start Session ──────────────────────────────────────────
  const startSession = useCallback(
    async (selectedLang = lang) => {
      if (started) return
      setStarted(true)
      setAppState('thinking')
      setAgentMessage(selectedLang === 'ta' ? 'இணைக்கிறேன்...' : 'Connecting...')

      try {
        const res = await fetch(`${API_BASE}/session/start?lang=${selectedLang}`, {
          method: 'POST',
        })
        if (!res.ok) throw new Error(`Server returned ${res.status}`)
        const data = await res.json()

        setSessionId(data.session_id)
        setConvState(data.state)
        if (data.slots_config) setSlotsConfig(data.slots_config)
        setDebugData((d) => ({
          ...d,
          sessionId: data.session_id,
          state: data.state,
          lang: selectedLang,
        }))
        setAudioB64(data.audio_base64)
        setTurnId((t) => t + 1)
        setAppState('speaking')
      } catch (err) {
        console.error('[startSession]', err)
        setAgentMessage(
          selectedLang === 'ta'
            ? 'இணைப்பு தோல்வி. மீண்டும் முயற்சிக்கவும்.'
            : 'Connection failed. Please try again.'
        )
        setAppState('idle')
        setStarted(false)
      }
    },
    [started, lang]
  )

  // ── Mic press start ────────────────────────────────────────
  const handleMicStart = useCallback(async () => {
    if (!sessionId) {
      await startSession()
      return
    }
    if (appState !== 'idle') return

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Connect Web Audio Analyser
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext
        if (AudioCtx) {
          const ctx = new AudioCtx()
          audioContextRef.current = ctx
          const source = ctx.createMediaStreamSource(stream)
          const analyser = ctx.createAnalyser()
          analyser.fftSize = 64
          source.connect(analyser)
          analyserRef.current = analyser
        }
      } catch (e) {
        console.warn('[AudioContext] Not available:', e)
      }

      await startRecording(stream, mediaRecorderRef, chunksRef)
      setAppState('listening')
      setAgentMessage(lang === 'ta' ? 'கேட்கிறேன்...' : 'Listening...')
    } catch (err) {
      console.error('[mic] Permission denied:', err)
      setAgentMessage(
        lang === 'ta'
          ? 'மைக்ரோஃபோன் அனுமதி தேவை.'
          : 'Microphone permission is required.'
      )
    }
  }, [appState, sessionId, startSession, lang])

  // ── Mic press end / send turn ──────────────────────────────
  const handleMicEnd = useCallback(async () => {
    if (appState !== 'listening') return
    setAppState('thinking')
    setAgentMessage(lang === 'ta' ? 'யோசிக்கிறேன்...' : 'Processing...')

    await stopRecording(mediaRecorderRef, streamRef)
    const blob = buildAudioBlob(chunksRef)

    // Clean up audio context
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {})
      audioContextRef.current = null
      analyserRef.current = null
    }

    const formData = new FormData()
    formData.append('audio', blob, 'turn.webm')

    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/turn`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) throw new Error(`Server returned ${res.status}`)
      const data = await res.json()

      setAgentMessage(
        data.agent_text ||
          (lang === 'ta' ? 'தொட்டு பேசவும்.' : 'Tap to speak your answer.')
      )
      setAudioB64(data.audio_base64)
      setTurnId((t) => t + 1)
      setAppState('speaking')

      setConvState(data.state)
      setCurrentSlot(data.current_slot)
      setSlotsData(data.slots || {})
      setDebugData((d) => ({
        ...d,
        state: data.state,
        currentSlot: data.current_slot,
        slots: data.slots,
        lastTranscript: data.transcript,
        lastAgentText: data.agent_text,
        lastConfidence: data.confidence,
      }))

      if (data.state === 'SUBMIT') {
        await handleSubmit()
      }
    } catch (err) {
      console.error('[turn]', err)
      setAgentMessage(
        lang === 'ta'
          ? 'பிழை ஏற்பட்டது. மீண்டும் முயற்சிக்கவும்.'
          : 'An error occurred. Tap to try again.'
      )
      setAppState('idle')
    }
  }, [appState, sessionId, lang])

  // ── Submit application ─────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (!sessionId) return
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/submit`, {
        method: 'POST',
      })
      const data = await res.json()
      setReferenceNumber(data.reference_number)
      setAgentMessage(data.message)
      setAudioB64(data.audio_base64)
      setTurnId((t) => t + 1)
      setAppState('speaking')
      setDone(true)
      setDebugData((d) => ({ ...d, state: 'DONE' }))
    } catch (err) {
      console.error('[submit]', err)
    }
  }, [sessionId])

  // ── Audio playback ended ───────────────────────────────────
  const handleAudioEnded = useCallback(() => {
    if (done) {
      setAgentMessage(
        lang === 'ta'
          ? 'விண்ணப்பம் வெற்றிகரமாக சமர்ப்பிக்கப்பட்டது! நன்றி.'
          : 'Application submitted successfully! Thank you.'
      )
      setAppState('idle')
      return
    }
    setAppState('idle')
    if (sessionId && !done) {
      setAgentMessage(
        lang === 'ta' ? 'பதில் சொல்ல தொட்டு பேசுங்கள்.' : 'Tap to speak your answer.'
      )
    }
  }, [done, sessionId, lang])

  // ── Toggle button click ────────────────────────────────────
  const handleToggleListening = () => {
    if (!sessionId && !started) {
      startSession()
    } else if (appState === 'idle') {
      handleMicStart()
    } else if (appState === 'listening') {
      handleMicEnd()
    }
  }

  // ── Language Toggle ────────────────────────────────────────
  const handleLanguageToggle = (newLang) => {
    if (newLang === lang) return
    setLang(newLang)
    if (!started) {
      setAgentMessage(
        newLang === 'ta'
          ? 'வணக்கம்! பேச தொடங்குங்கள்.'
          : 'Hello! Tap the circle to speak.'
      )
    }
  }

  // Formatting helpers
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  const getStatusText = () => {
    if (appState === 'listening') return lang === 'ta' ? 'கேட்கிறேன்...' : 'Listening...'
    if (appState === 'thinking') return lang === 'ta' ? 'யோசிக்கிறேன்...' : 'Processing...'
    if (appState === 'speaking') return lang === 'ta' ? 'பேசுகிறேன்...' : 'Speaking...'
    return lang === 'ta' ? 'தொட்டு பேசுங்கள்' : 'Tap to speak'
  }

  const getStatusColor = () => {
    if (appState === 'listening') return 'text-blue-400'
    if (appState === 'thinking') return 'text-yellow-400'
    if (appState === 'speaking') return 'text-green-400'
    return 'text-zinc-400'
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[#0B0F19] text-white relative overflow-hidden font-sans select-none">
      {/* Ambient Floating Particles */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {particles.map((p) => (
          <motion.div
            key={p.id}
            className="absolute rounded-full bg-blue-400"
            style={{
              width: `${p.size}px`,
              height: `${p.size}px`,
              left: `${p.x}px`,
              top: `${p.y}px`,
              opacity: p.opacity,
            }}
            animate={{ scale: [1, 1.4, 1] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
          />
        ))}
      </div>

      {/* Ambient Glow Center */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <motion.div
          className="w-[32rem] h-[32rem] rounded-full bg-gradient-to-r from-blue-600/10 via-purple-600/10 to-pink-600/10 blur-3xl"
          animate={{
            scale: appState === 'listening' ? [1, 1.25, 1] : [1, 1.08, 1],
            opacity: appState === 'listening' ? [0.3, 0.65, 0.3] : [0.15, 0.25, 0.15],
          }}
          transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
        />
      </div>

      {/* Top Header & Language Switcher */}
      <header className="absolute top-6 inset-x-0 px-8 flex items-center justify-between z-20 max-w-4xl mx-auto">
        <div className="flex items-center space-x-2">
          <div className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse" />
          <span className="font-semibold tracking-wide text-sm text-zinc-300">
            JustSpeak <span className="text-zinc-500 font-normal">· ஒன்று பேசு</span>
          </span>
        </div>

        {/* Language Switcher Pill */}
        <div className="flex items-center bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-full p-1 shadow-lg">
          <Globe className="w-3.5 h-3.5 text-zinc-400 ml-2 mr-1" />
          <button
            onClick={() => handleLanguageToggle('ta')}
            className={cn(
              'px-3 py-1 text-xs font-medium rounded-full transition-all duration-200',
              lang === 'ta'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-500/30'
                : 'text-zinc-400 hover:text-zinc-200'
            )}
          >
            தமிழ்
          </button>
          <button
            onClick={() => handleLanguageToggle('en')}
            className={cn(
              'px-3 py-1 text-xs font-medium rounded-full transition-all duration-200',
              lang === 'en'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-500/30'
                : 'text-zinc-400 hover:text-zinc-200'
            )}
          >
            English
          </button>
        </div>
      </header>

      {/* Main Siri-style Voice Interaction Orb */}
      <main className="relative z-10 flex flex-col items-center space-y-8 max-w-lg w-full px-6 text-center">
        {/* 3D Particle Swarm AI Voice Centerpiece */}
        <div className="relative w-80 h-80 flex items-center justify-center">
          {/* 3D Three.js Particle Swarm Canvas */}
          <AIVoiceParticles
            appState={appState}
            volume={volume}
            onClick={handleToggleListening}
            className="absolute inset-0 z-10"
          />

          {/* Central Glassmorphic Core Action Button */}
          <motion.button
            onClick={handleToggleListening}
            aria-label="AI Voice Interaction Button"
            className={cn(
              'relative z-20 w-24 h-24 rounded-full flex items-center justify-center backdrop-blur-xl border transition-all duration-300 shadow-2xl',
              'bg-[#101422]/70',
              appState === 'listening'
                ? 'border-cyan-400/80 shadow-[0_0_40px_rgba(6,182,212,0.6)]'
                : appState === 'thinking'
                ? 'border-amber-400/80 shadow-[0_0_40px_rgba(245,158,11,0.6)]'
                : appState === 'speaking'
                ? 'border-emerald-400/80 shadow-[0_0_40px_rgba(16,185,129,0.6)]'
                : 'border-blue-500/40 hover:border-blue-400/80 shadow-[0_0_25px_rgba(59,130,246,0.3)]'
            )}
            whileHover={{ scale: 1.08 }}
            whileTap={{ scale: 0.94 }}
          >
            <AnimatePresence mode="wait">
              {appState === 'thinking' ? (
                <motion.div
                  key="thinking"
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                >
                  <Loader2 className="w-10 h-10 text-amber-400 animate-spin" />
                </motion.div>
              ) : appState === 'speaking' ? (
                <motion.div
                  key="speaking"
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                >
                  <Volume2 className="w-10 h-10 text-emerald-400" />
                </motion.div>
              ) : appState === 'listening' ? (
                <motion.div
                  key="listening"
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                >
                  <Mic className="w-10 h-10 text-cyan-300 animate-pulse" />
                </motion.div>
              ) : (
                <motion.div
                  key="idle"
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                >
                  <Mic className="w-10 h-10 text-blue-400" />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.button>
        </div>

        {/* 32-Band Audio Waveform Visualizer */}
        <div className="flex items-center justify-center space-x-1.5 h-16 w-full max-w-sm">
          {waveformData.map((height, index) => (
            <motion.div
              key={index}
              className={cn(
                'w-1 rounded-full transition-all duration-200',
                appState === 'listening'
                  ? 'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]'
                  : appState === 'thinking'
                  ? 'bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.6)]'
                  : appState === 'speaking'
                  ? 'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]'
                  : 'bg-zinc-800'
              )}
              animate={{
                height: `${Math.max(4, height * 0.75)}px`,
                opacity: appState === 'listening' || appState === 'speaking' ? 1 : 0.25,
              }}
              transition={{ duration: 0.08, ease: 'easeOut' }}
            />
          ))}
        </div>

        {/* Status Text & Timer */}
        <div className="text-center space-y-2">
          <motion.p
            className={cn('text-xl font-medium tracking-wide transition-colors', getStatusColor())}
            animate={{ opacity: [1, 0.75, 1] }}
            transition={{
              duration: 2,
              repeat: appState !== 'idle' ? Infinity : 0,
            }}
          >
            {getStatusText()}
          </motion.p>

          {/* Spoken Dialogue Text Bubble */}
          {agentMessage && (
            <p className="text-base text-zinc-200 font-normal leading-relaxed max-w-md px-4 py-2 bg-zinc-900/60 border border-zinc-800/80 rounded-2xl backdrop-blur-md shadow-inner">
              {agentMessage}
            </p>
          )}

          {/* Monospace Duration Timer */}
          <p className="text-sm text-zinc-400 font-mono pt-1">
            {formatTime(duration)}
          </p>

          {/* Volume Indicator Bar */}
          {volume > 0 && (
            <motion.div
              className="flex items-center justify-center space-x-2 pt-1"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <VolumeX className="w-4 h-4 text-zinc-400" />
              <div className="w-28 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-blue-500 rounded-full shadow-[0_0_6px_rgba(59,130,246,0.8)]"
                  animate={{ width: `${volume}%` }}
                  transition={{ duration: 0.1 }}
                />
              </div>
              <Volume2 className="w-4 h-4 text-zinc-400" />
            </motion.div>
          )}
        </div>

        {/* Completed Submission Card */}
        {referenceNumber && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="w-full bg-emerald-950/40 border border-emerald-500/30 rounded-2xl p-4 text-center space-y-1 shadow-lg backdrop-blur-md"
          >
            <div className="flex items-center justify-center space-x-2 text-emerald-400 font-medium">
              <CheckCircle2 className="w-5 h-5" />
              <span>{lang === 'ta' ? 'விண்ணப்ப குறிப்பு எண்' : 'Application Reference'}</span>
            </div>
            <p className="font-mono text-2xl font-bold tracking-widest text-emerald-300">
              {referenceNumber}
            </p>
          </motion.div>
        )}

        {/* Bottom AI Branding */}
        <motion.div
          className="flex items-center space-x-2 text-xs text-zinc-400 pt-2"
          animate={{ opacity: [0.5, 0.9, 0.5] }}
          transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Sparkles className="w-3.5 h-3.5 text-blue-400" />
          <span>AI Voice Assistant</span>
        </motion.div>
        </main>

        {/* Dynamic Pension Scheme Application Form */}
        <AnimatePresence>
          {['SLOT_FILLING', 'CONFIRMATION', 'SUBMIT', 'DONE'].includes(convState) && (
            <motion.div
              initial={{ opacity: 0, x: 50, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 50, scale: 0.95 }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className="w-full max-w-4xl bg-zinc-900/60 backdrop-blur-2xl border border-zinc-700/50 rounded-3xl p-8 xl:p-10 shadow-[0_0_50px_rgba(0,0,0,0.5)]"
            >
              <div className="flex items-center space-x-4 mb-8">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                  <CheckCircle2 className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h2 className="text-2xl md:text-3xl font-semibold text-zinc-100 tracking-tight">
                    {lang === 'ta' ? 'முதியோர் உதவித்தொகை விண்ணப்பம்' : 'Old Age Pension Application'}
                  </h2>
                  <p className="text-zinc-400 text-sm mt-1">
                    {lang === 'ta' ? 'உங்கள் குரல் மூலம் விவரங்கள் சேகரிக்கப்படுகின்றன' : 'Collecting details via voice assistant'}
                  </p>
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {slotsConfig.map((slot) => {
                  const isActive = currentSlot === slot.key;
                  const slotValue = slotsData[slot.key]?.value || '';
                  const isSkipped = slotsData[slot.key]?.skipped;
                  const displayValue = isSkipped ? (lang === 'ta' ? 'தவிர்க்கப்பட்டது' : 'Skipped') : slotValue;
                  const isFilled = !!displayValue;
                  
                  return (
                    <motion.div 
                      key={slot.key} 
                      layout
                      className={cn(
                        "flex flex-col space-y-2 p-5 rounded-2xl transition-all duration-500 relative overflow-hidden",
                        isActive ? "bg-blue-950/40 border border-blue-500/50 shadow-inner" 
                        : isFilled ? "bg-zinc-800/40 border border-zinc-700/40" 
                        : "bg-zinc-900/40 border border-zinc-800/50 opacity-60"
                      )}
                    >
                      {/* Active highlight glow */}
                      {isActive && (
                        <motion.div 
                          className="absolute inset-0 bg-gradient-to-r from-blue-500/10 to-transparent pointer-events-none"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ duration: 0.5 }}
                        />
                      )}

                      <label className={cn(
                        "text-sm font-medium relative z-10 transition-colors duration-300",
                        isActive ? "text-blue-400" : isFilled ? "text-zinc-300" : "text-zinc-500"
                      )}>
                        {lang === 'ta' ? slot.label_ta : slot.label_en}
                      </label>
                      <div className="flex items-center space-x-3 relative z-10">
                        <div className={cn(
                          "flex-1 px-4 py-3 rounded-xl text-base font-medium transition-all duration-300 border",
                          isActive ? "bg-blue-900/20 border-blue-500/30 text-blue-50 shadow-[0_0_15px_rgba(59,130,246,0.15)]" 
                          : isFilled ? "bg-zinc-800/80 border-zinc-700/50 text-zinc-200"
                          : "bg-zinc-900/80 border-zinc-800/80 text-zinc-600"
                        )}>
                          {displayValue || (lang === 'ta' ? 'காத்திருக்கிறது...' : 'Waiting...')}
                        </div>
                        
                        <AnimatePresence mode="wait">
                          {isActive && (
                            <motion.div
                              initial={{ opacity: 0, scale: 0.5 }}
                              animate={{ opacity: 1, scale: 1 }}
                              exit={{ opacity: 0, scale: 0.5 }}
                            >
                              <div className="w-10 h-10 rounded-full bg-blue-500/10 flex items-center justify-center">
                                <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
                              </div>
                            </motion.div>
                          )}
                          {isFilled && !isActive && (
                            <motion.div
                              initial={{ opacity: 0, scale: 0.5 }}
                              animate={{ opacity: 1, scale: 1 }}
                              exit={{ opacity: 0, scale: 0.5 }}
                            >
                              <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center">
                                <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    </motion.div>
                  );
                })}
              </div>

              {convState === 'DONE' && (
                 <motion.div
                   initial={{ opacity: 0, y: 20 }}
                   animate={{ opacity: 1, y: 0 }}
                   className="mt-8 p-6 rounded-2xl bg-gradient-to-r from-emerald-900/40 to-teal-900/40 border border-emerald-500/30 flex items-center justify-between"
                 >
                   <div>
                     <h3 className="text-emerald-400 font-semibold text-lg">
                       {lang === 'ta' ? 'விண்ணப்பம் வெற்றிகரமாக சமர்ப்பிக்கப்பட்டது!' : 'Application Submitted Successfully!'}
                     </h3>
                     <p className="text-emerald-200/70 text-sm mt-1">
                       {lang === 'ta' ? 'உங்கள் குறிப்பு எண்:' : 'Your Reference Number:'} <span className="font-mono font-bold text-emerald-300 ml-1">{referenceNumber}</span>
                     </p>
                   </div>
                   <div className="w-14 h-14 rounded-full bg-emerald-500/20 flex items-center justify-center shadow-[0_0_30px_rgba(16,185,129,0.3)]">
                     <CheckCircle2 className="w-8 h-8 text-emerald-400" />
                   </div>
                 </motion.div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Hidden Audio Player for Spoken Agent Responses */}
      <AudioPlayer audioBase64={audioB64} turnId={turnId} onEnded={handleAudioEnded} />

      {/* Judges Debug Panel (Ctrl+D) */}
      <DebugPanel
        isOpen={debugOpen}
        onClose={() => setDebugOpen(false)}
        debugData={debugData}
      />

      {/* Debug Shortcut Hint */}
      <p className="absolute bottom-4 right-6 text-[11px] text-zinc-400 tracking-wider">
        Ctrl+D · debug
      </p>
    </div>
  )
}
