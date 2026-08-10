/**
 * MicButton — Large press-to-talk button with ripple rings
 * States: idle | listening | thinking | speaking
 */
import { useRef, useEffect } from 'react'

const MIC_ICON = (
  <svg width="42" height="42" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="9" y="2" width="6" height="12" rx="3" fill="currentColor"/>
    <path
      d="M5 10a7 7 0 0 0 14 0"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      fill="none"
    />
    <line x1="12" y1="17" x2="12" y2="22" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    <line x1="8"  y1="22" x2="16" y2="22" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
  </svg>
)

const STOP_ICON = (
  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>
  </svg>
)

export default function MicButton({ appState, onPressStart, onPressEnd, disabled }) {
  const isListening = appState === 'listening'
  const isActive = isListening

  const labelMap = {
    idle:      'ஒன்று பேசு — தொட்டு பேசுங்கள்',
    listening: 'கேட்கிறேன்... நிறுத்த மீண்டும் தொடுங்கள்',
    thinking:  'யோசிக்கிறேன்...',
    speaking:  'பேசுகிறேன்...',
  }

  const handleClick = () => {
    if (disabled) return
    if (isListening) {
      onPressEnd?.()
    } else if (appState === 'idle') {
      onPressStart?.()
    }
  }

  return (
    <div className="mic-container fade-up-3">
      {/* Ripple rings — visible only when listening */}
      <div className={`mic-ring ${isActive ? 'active' : ''}`} />
      <div className={`mic-ring ${isActive ? 'active' : ''}`} />
      <div className={`mic-ring ${isActive ? 'active' : ''}`} />

      <button
        id="mic-button"
        className={`mic-button ${appState}`}
        onClick={handleClick}
        disabled={disabled && !isListening}
        aria-label={labelMap[appState] || 'Microphone'}
        aria-pressed={isListening}
      >
        <span className="mic-icon">
          {isListening ? STOP_ICON : MIC_ICON}
        </span>
      </button>

      <p className="mic-label">{labelMap[appState]}</p>
    </div>
  )
}
