import { useCallback, useEffect, useState } from 'react'

import { api, stream } from './api'

/** Is Gemini connected (server key or the user's own)? Re-checks when the key changes. */
export function useAiStatus() {
  const [connected, setConnected] = useState<boolean | null>(null)
  useEffect(() => {
    const check = () => api.get<{ connected: boolean }>('/ai/status').then((s) => setConnected(s.connected)).catch(() => setConnected(false))
    check()
    window.addEventListener('meterzero:key', check)
    return () => window.removeEventListener('meterzero:key', check)
  }, [])
  return connected
}

/** Run a streamed AI request: collects the steps as they arrive, then the final payload. */
export function useAiRun<T>() {
  const [steps, setSteps] = useState<string[]>([])
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async (path: string, body?: unknown) => {
    setSteps([])
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      await stream(path, body, (event) => {
        if (event.type === 'step') setSteps((s) => [...s, event.text])
        else if (event.type === 'error') setError(event.text)
        else if (event.type === 'done') setResult(event as unknown as T)
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }, [])

  return { steps, running, result, error, run, setResult }
}
