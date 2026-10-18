import { useCallback, useEffect, useRef, useState } from 'react'

/** Plays a day back: `minute` is a ref the 3D scene reads every frame; `display` updates the UI ~10×/s. */
export function usePlayer(start = 870) {
  const minute = useRef(start)
  const [display, setDisplay] = useState(start)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(5) // simulated minutes per real second

  useEffect(() => {
    let frame = 0
    let last = performance.now()
    let shown = performance.now()
    const tick = (now: number) => {
      const dt = (now - last) / 1000
      last = now
      if (playing) {
        minute.current += dt * speed
        if (minute.current >= 1439) {
          minute.current = 1439
          setPlaying(false)
        }
      }
      if (now - shown > 100) {
        shown = now
        setDisplay(minute.current)
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, speed])

  const seek = useCallback((m: number) => {
    minute.current = Math.max(0, Math.min(1439, m))
    setDisplay(minute.current)
  }, [])

  return { minute, display, playing, setPlaying, speed, setSpeed, seek }
}
