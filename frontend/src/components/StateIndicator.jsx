/**
 * StateIndicator — shows current app state badge + waveform visualizer
 */

const STATE_LABELS = {
  idle:      'காத்திருக்கிறேன்',
  listening: 'கேட்கிறேன்',
  thinking:  'யோசிக்கிறேன்',
  speaking:  'பேசுகிறேன்',
}

const STATE_LABELS_EN = {
  idle:      'READY',
  listening: 'LISTENING',
  thinking:  'THINKING',
  speaking:  'SPEAKING',
}

function Waveform({ visible, type }) {
  if (!visible) return null
  return (
    <div className={`waveform ${type}`}>
      {Array.from({ length: 9 }).map((_, i) => (
        <div key={i} className="waveform-bar" />
      ))}
    </div>
  )
}

export default function StateIndicator({ appState, agentMessage }) {
  return (
    <div className="state-indicator fade-up-2">
      <div className={`state-badge ${appState}`}>
        <span className="state-dot" />
        {STATE_LABELS_EN[appState] || 'READY'}
      </div>

      <Waveform
        visible={appState === 'listening' || appState === 'speaking'}
        type={appState}
      />

      {agentMessage && (
        <p className="state-message">{agentMessage}</p>
      )}
    </div>
  )
}
