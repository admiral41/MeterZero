import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'

import { api, ApiError } from '../lib/api'
import { PlantContext } from '../lib/plant'
import type { PlantPayload } from '../lib/types'
import { useAsync } from '../lib/useAsync'

export function PlantProvider({ children }: { children: ReactNode }) {
  const { plantId = 'demo' } = useParams()
  const { data, error, loading, reload } = useAsync(() => api.get<PlantPayload>(`/plants/${plantId}`), [plantId])
  const untrained = error instanceof ApiError && error.status === 409
  return (
    <PlantContext.Provider value={{ plantId, plant: data, loading, error: untrained ? null : error, untrained, reload }}>
      {children}
    </PlantContext.Provider>
  )
}
