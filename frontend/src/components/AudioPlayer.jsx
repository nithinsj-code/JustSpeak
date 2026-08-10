/**
 * AudioPlayer — hidden audio element that auto-plays agent responses
 */
import { useEffect, useRef } from 'react'

export default function AudioPlayer({ audioBase64, onEnded }) {
  const audioRef = useRef(null)

  useEffect(() => {
    if (!audioBase64 || !audioRef.current) return

    // Decode base64 → Blob → Object URL
    const byteChars = atob(audioBase64)
    const byteNums = new Array(byteChars.length)
    for (let i = 0; i < byteChars.length; i++) {
      byteNums[i] = byteChars.charCodeAt(i)
    }
    const byteArray = new Uint8Array(byteNums)
    const blob = new Blob([byteArray], { type: 'audio/wav' })
    const url = URL.createObjectURL(blob)

    audioRef.current.src = url
    audioRef.current.play().catch(err => {
      console.warn('[AudioPlayer] Autoplay blocked:', err)
      onEnded?.()
    })

    return () => URL.revokeObjectURL(url)
  }, [audioBase64])

  return (
    <audio
      ref={audioRef}
      style={{ display: 'none' }}
      onEnded={onEnded}
      aria-hidden="true"
    />
  )
}
