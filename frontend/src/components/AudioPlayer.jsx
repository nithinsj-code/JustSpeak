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
    // Sniff audio format or allow browser auto-detection
    const isWav = byteArray[0] === 82 && byteArray[1] === 73 && byteArray[2] === 70 && byteArray[3] === 70 // 'RIFF'
    const mimeType = isWav ? 'audio/wav' : 'audio/mpeg'
    const blob = new Blob([byteArray], { type: mimeType })
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
