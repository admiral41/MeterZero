import { createContext, useContext } from 'react'

import type { PlantPayload } from './types'

export interface PlantState {
  plantId: string
  plant: PlantPayload | null
  loading: boolean
  error: unknown
  untrained: boolean
  reload: () => void
}

export const PlantContext = createContext<PlantState | null>(null)

/** The plant in the URL, loaded once for every page under /p/:plantId. */
export function usePlant(): PlantState {
  const state = useContext(PlantContext)
  if (!state) throw new Error('usePlant must be used inside a PlantProvider')
  return state
}
