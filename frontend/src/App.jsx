/**
 * JustSpeak — Main App
 * Voice-first Tamil pension application agent
 *
 * App states: idle | listening | thinking | speaking
 * Keyboard shortcut: Ctrl+D → toggle debug panel
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import './index.css'

import MicButton    from './components/MicButton'
import StateIndicator from './components/StateIndicator'
import AudioPlayer  from './components/AudioPlayer'
import DebugPanel   from './components/DebugPanel'

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
    recorder.onstop = () => resolve()
    recorder.stop()
    streamRef.current?.getTracks().forEach((t) => t.stop())
  })
}

function buildAudioBlob(chunksRef) {
  return new Blob(chunksRef.current, { type: 'audio/webm' })
}

// ─── App Component ────────────────────────────────────────────
export default function App() {
  // App state machine
  const [appState, setAppState]       = useState('idle')     // idle|listening|thinking|speaking
  const [sessionId, setSessionId]     = useState(null)
  const [agentMessage, setAgentMessage] = useState('Hello! Tap to speak.')
  const [audioB64, setAudioB64]       = useState(null)
  const [started, setStarted]         = useState(false)
  const [done, setDone]               = useState(false)

  // Debug panel
  const [debugOpen, setDebugOpen]     = useState(false)
  const [debugData, setDebugData]     = useState({})

  // Recording refs
  const mediaRecorderRef = useRef(null)
  const streamRef        = useRef(null)
  const chunksRef        = useRef([])

  // ── Ctrl+D to toggle debug ──────────────────────────────────
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

  // ── Session start ────────────────────────────────────────────
  const startSession = useCallback(async () => {
    if (started) return
    setStarted(true)
    setAppState('thinking')
    setAgentMessage('Connecting...')

    try {
      const res = await fetch(`${API_BASE}/session/start`, { method: 'POST' })
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`)
      }
      const data = await res.json()

      setSessionId(data.session_id)
      setDebugData((d) => ({ ...d, sessionId: data.session_id, state: data.state }))
      setAudioB64(data.audio_base64)
      setAppState('speaking')
    } catch (err) {
      console.error('[startSession]', err)
      setAgentMessage('Connection failed. Please try again.')
      setAppState('idle')
      setStarted(false)
    }
  }, [started])

  // ── Mic press start ──────────────────────────────────────────
  const handleMicStart = useCallback(async () => {
    if (!sessionId) {
      // First tap → start session
      await startSession()
      return
    }
    if (appState !== 'idle') return

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      await startRecording(stream, mediaRecorderRef, chunksRef)
      setAppState('listening')
      setAgentMessage('Listening...')
    } catch (err) {
      console.error('[mic] Permission denied:', err)
      setAgentMessage('Microphone permission is required.')
    }
  }, [appState, sessionId, startSession])

  // ── Mic press end / send turn ────────────────────────────────
  const handleMicEnd = useCallback(async () => {
    if (appState !== 'listening') return
    setAppState('thinking')
    setAgentMessage('Thinking...')

    await stopRecording(mediaRecorderRef, streamRef)
    const blob = buildAudioBlob(chunksRef)

    const formData = new FormData()
    formData.append('audio', blob, 'turn.webm')

    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/turn`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`)
      }

      const data = await res.json()

      setAgentMessage(data.agent_text || 'Tap to speak your answer.')
      setAudioB64(data.audio_base64)
      setAppState('speaking')

      // Update debug data
      setDebugData((d) => ({
        ...d,
        state:           data.state,
        currentSlot:     data.current_slot,
        slots:           data.slots,
        lastTranscript:  data.transcript,
        lastAgentText:   data.agent_text,
        lastConfidence:  data.confidence,
      }))

      // If state is SUBMIT, trigger auto-submit
      if (data.state === 'SUBMIT') {
        await handleSubmit()
      }
    } catch (err) {
      console.error('[turn]', err)
      setAgentMessage('An error occurred. Tap to try again.')
      setAppState('idle')
    }
  }, [appState, sessionId])

  // ── Submit ───────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (!sessionId) return
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/submit`, {
        method: 'POST',
      })
      const data = await res.json()
      setAgentMessage(data.message)
      setAudioB64(data.audio_base64)
      setAppState('speaking')
      setDone(true)
      setDebugData((d) => ({ ...d, state: 'DONE' }))
    } catch (err) {
      console.error('[submit]', err)
    }
  }, [sessionId])

  // ── Audio ended → back to idle ───────────────────────────────
  const handleAudioEnded = useCallback(() => {
    if (done) {
      setAgentMessage('Application submitted successfully! Thank you.')
      setAppState('idle')
      return
    }
    setAppState('idle')
    // Provide a brief prompt hint
    if (sessionId && !done) {
      setAgentMessage('Tap to speak your answer.')
    }
  }, [done, sessionId])

  // ── First tap: if no session, start one ─────────────────────
  const handleMicClick = useCallback(() => {
    if (!sessionId && !started) {
      startSession()
    } else if (appState === 'idle') {
      handleMicStart()
    } else if (appState === 'listening') {
      handleMicEnd()
    }
  }, [sessionId, started, appState, startSession, handleMicStart, handleMicEnd])

  const isBusy = appState === 'thinking' || appState === 'speaking'

  return (
    <div className="app">
      {/* Background layers */}
      <div className="app-bg" />
      <div className={`ambient-glow ${appState}`} />

      {/* Main content */}
      <main className="app-content" role="main">
        {/* Header */}
        <header className="header fade-up-1">
          <h1 className="header-logo">JustSpeak</h1>
          <p className="header-subtitle">Voice-First Pension Application</p>
        </header>

        <div className="divider" />

        {/* State indicator */}
        <StateIndicator
          appState={appState}
          agentMessage={agentMessage}
        />

        {/* Mic button */}
        <MicButton
          appState={appState}
          onPressStart={handleMicStart}
          onPressEnd={handleMicEnd}
          disabled={isBusy}
        />
        {/* Override to single-click handler */}
        {/* (handled in handleMicClick, wired via MicButton onPressStart/End) */}
      </main>

      {/* Hidden audio player */}
      <AudioPlayer
        audioBase64={audioB64}
        onEnded={handleAudioEnded}
      />

      {/* Debug panel */}
      <DebugPanel
        isOpen={debugOpen}
        onClose={() => setDebugOpen((v) => !v)}
        debugData={debugData}
      />

      {/* Debug hint */}
      <p className="debug-toggle-hint">Ctrl+D · debug</p>
    </div>
  )
}
