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
async function startRecording(mediaRecorderRef, chunksRef) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
  chunksRef.current = []
  recorder.ondataavailable = (e) => {
    if (e.data.size > 0) chunksRef.current.push(e.data)
  }
  recorder.start()
  mediaRecorderRef.current = recorder
  return stream
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
  const [agentMessage, setAgentMessage] = useState('வணக்கம்! தொட்டு பேசுங்கள்.')
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
    setAgentMessage('இணைக்கிறேன்...')

    try {
      const res = await fetch(`${API_BASE}/session/start`, { method: 'POST' })
      const data = await res.json()

      setSessionId(data.session_id)
      setDebugData((d) => ({ ...d, sessionId: data.session_id, state: data.state }))
      setAudioB64(data.audio_base64)
      setAppState('speaking')
    } catch (err) {
      console.error('[startSession]', err)
      setAgentMessage('இணைப்பு தோல்வி. மீண்டும் முயற்சிக்கவும்.')
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
      streamRef.current = await navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then((s) => s)
      await startRecording(mediaRecorderRef, chunksRef)
      setAppState('listening')
      setAgentMessage('கேட்கிறேன்...')
    } catch (err) {
      console.error('[mic] Permission denied:', err)
      setAgentMessage('மைக்ரோஃபோன் அனுமதி தேவை.')
    }
  }, [appState, sessionId, startSession])

  // ── Mic press end / send turn ────────────────────────────────
  const handleMicEnd = useCallback(async () => {
    if (appState !== 'listening') return
    setAppState('thinking')
    setAgentMessage('யோசிக்கிறேன்...')

    await stopRecording(mediaRecorderRef, streamRef)
    const blob = buildAudioBlob(chunksRef)

    const formData = new FormData()
    formData.append('audio', blob, 'turn.webm')

    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/turn`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()

      setAgentMessage(data.agent_text)
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
      setAgentMessage('பிழை ஏற்பட்டது. மீண்டும் முயற்சிக்கவும்.')
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
      setAgentMessage('விண்ணப்பம் வெற்றிகரமாக சமர்ப்பிக்கப்பட்டது! நன்றி.')
      setAppState('idle')
      return
    }
    setAppState('idle')
    // Provide a brief prompt hint
    if (sessionId && !done) {
      setAgentMessage('பதில் சொல்ல தொட்டு பேசுங்கள்.')
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
          <p className="header-subtitle">ஒன்று பேசு — முதியோர் நல விண்ணப்பம்</p>
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
