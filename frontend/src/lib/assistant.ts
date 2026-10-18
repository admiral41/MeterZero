import { useEffect, useSyncExternalStore } from 'react'

/**
 * What the floating assistant knows about the page you're on: pages describe what's on screen
 * ("Digital twin at 14:30 Thursday, air compressor selected"), so a question like "why is it so
 * high?" means something. Pages can also open the assistant with a question ready to ask.
 */
export interface AssistantContext {
  page: string
  detail: string
  suggestions: string[]
}

type Listener = () => void
const EMPTY: AssistantContext = { page: '', detail: '', suggestions: [] }
let context = EMPTY
let request: { question: string; id: number } | null = null
const listeners = new Set<Listener>()

function emit() {
  listeners.forEach((listener) => listener())
}

function subscribe(listener: Listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Call from a page: tells the assistant what the user is looking at. */
export function useAssistantContext(page: string, detail = '', suggestions: string[] = []) {
  const key = suggestions.join('|')
  useEffect(() => {
    context = { page, detail, suggestions: key ? key.split('|') : [] }
    emit()
    return () => {
      context = EMPTY
      emit()
    }
  }, [page, detail, key])
}

export function useCurrentContext() {
  return useSyncExternalStore(subscribe, () => context)
}

/** Open the assistant and ask straight away. */
export function askAssistant(question: string) {
  request = { question, id: Date.now() }
  emit()
}

export function usePendingQuestion() {
  return useSyncExternalStore(subscribe, () => request)
}
