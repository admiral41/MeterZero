import { useEffect, useMemo, useState } from 'react'

import { api } from '../../lib/api'
import { usePlant } from '../../lib/plant'
import { useAiStatus } from '../../lib/useAi'

export type PhotoKind = 'logbook' | 'nameplate'

/** Choose the example photo or your own, read it with Gemini, and keep the last saved reading. */
export function useReader(kind: PhotoKind) {
  const { plantId } = usePlant()
  const connected = useAiStatus()
  const [file, setFile] = useState<File | null>(null)
  const [reading, setReading] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : `/api/samples/${kind}`), [file, kind])

  useEffect(() => {
    api.get<{ payload: Record<string, unknown>; recorded_at: string }>(`/plants/${plantId}/ai/saved/${kind}`)
      .then((r) => { setResult(r.payload); setSavedAt(r.recorded_at) }).catch(() => undefined)
  }, [plantId, kind])

  const read = async () => {
    setReading(true)
    setError(null)
    const form = new FormData()
    if (file) form.append('file', file)
    else form.append('sample', 'true')
    try {
      setResult(await api.upload<Record<string, unknown>>(`/plants/${plantId}/ai/read/${kind}`, form))
      setSavedAt(null)
    } catch (e) {
      setError(e)
    } finally {
      setReading(false)
    }
  }
  return { plantId, connected, file, setFile, preview, read, reading, error, result, setResult, savedAt }
}

export type PhotoReader = ReturnType<typeof useReader>
