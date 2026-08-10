/**
 * DebugPanel — judges-only slide-in panel (Ctrl+D to toggle)
 * Shows: state, transcript, confidence, slots
 */
import { useEffect } from 'react'

export default function DebugPanel({ isOpen, onClose, debugData }) {
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
        e.preventDefault()
        onClose?.()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const {
    sessionId,
    state,
    currentSlot,
    slots = {},
    lastTranscript,
    lastAgentText,
    lastConfidence,
    retryCount,
  } = debugData || {}

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 99,
            background: 'rgba(0,0,0,0.4)',
          }}
          onClick={onClose}
        />
      )}

      <div className={`debug-panel ${isOpen ? 'open' : ''}`} role="complementary" aria-label="Debug Panel">
        <div className="debug-header">
          <h3>🔍 Debug Panel</h3>
          <button className="debug-close" onClick={onClose} aria-label="Close debug panel">✕</button>
        </div>

        <div className="debug-body">
          {/* Session */}
          <div className="debug-section">
            <h4>Session</h4>
            <span className="debug-chip">{sessionId ? sessionId.slice(0, 8) + '…' : '—'}</span>
          </div>

          {/* State */}
          <div className="debug-section">
            <h4>State Machine</h4>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <span className="debug-chip">{state || '—'}</span>
              {currentSlot && (
                <span className="debug-chip" style={{ background: 'rgba(245,166,35,0.15)', color: '#F5A623' }}>
                  slot: {currentSlot}
                </span>
              )}
              {retryCount > 0 && (
                <span className="debug-chip" style={{ background: 'rgba(220,50,50,0.15)', color: '#ff7070' }}>
                  retries: {retryCount}
                </span>
              )}
            </div>
          </div>

          {/* Last turn */}
          <div className="debug-section">
            <h4>Last Turn</h4>
            {lastTranscript && (
              <>
                <p style={{ fontSize: '0.65rem', color: 'var(--c-amber)', marginBottom: '4px' }}>User said:</p>
                <p className="debug-transcript">"{lastTranscript}"</p>
              </>
            )}
            {lastConfidence && (
              <span
                className={`debug-confidence ${lastConfidence}`}
                style={{ display: 'inline-block', marginTop: '6px' }}
              >
                confidence: {lastConfidence}
              </span>
            )}
            {lastAgentText && (
              <>
                <p style={{ fontSize: '0.65rem', color: 'var(--c-jade-light)', margin: '8px 0 4px' }}>Agent said:</p>
                <p className="debug-transcript" style={{ color: 'var(--c-jade-light)' }}>
                  "{lastAgentText}"
                </p>
              </>
            )}
          </div>

          {/* Slots */}
          <div className="debug-section">
            <h4>Collected Slots</h4>
            {Object.keys(slots).length === 0 ? (
              <p style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.3)' }}>No slots filled yet</p>
            ) : (
              Object.entries(slots).map(([key, slot]) => (
                <div key={key} className="debug-slot-row">
                  <span className="debug-slot-key">{key}</span>
                  <span className="debug-slot-value">
                    {slot.value || (slot.skipped ? '(skipped)' : '—')}
                  </span>
                  {slot.confidence && (
                    <span className={`debug-confidence ${slot.confidence}`}>
                      {slot.confidence}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Raw JSON */}
          <div className="debug-section">
            <h4>Raw State</h4>
            <pre className="debug-json">
              {JSON.stringify({ state, currentSlot, retryCount, slots }, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </>
  )
}
