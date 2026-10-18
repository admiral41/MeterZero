// Talking to the MeterZero API. The user's own Gemini key (if any) lives only in this browser.

const KEY_STORAGE = 'meterzero.geminiKey'

export function geminiKey(): string {
  try {
    return localStorage.getItem(KEY_STORAGE) ?? ''
  } catch {
    return ''
  }
}

export function setGeminiKey(key: string) {
  try {
    if (key) localStorage.setItem(KEY_STORAGE, key)
    else localStorage.removeItem(KEY_STORAGE)
  } catch {
    /* private mode: the key just won't be remembered */
  }
  window.dispatchEvent(new Event('meterzero:key'))
}

function headers(json = true): HeadersInit {
  const h: Record<string, string> = {}
  if (json) h['Content-Type'] = 'application/json'
  const key = geminiKey()
  if (key) h['X-Gemini-Key'] = key
  return h
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = response.statusText
    try {
      const body = await response.json()
      message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, message)
  }
  return response.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => fetch(`/api${path}`, { headers: headers(false) }).then((r) => handle<T>(r)),
  post: <T>(path: string, body?: unknown) =>
    fetch(`/api${path}`, { method: 'POST', headers: headers(), body: body === undefined ? undefined : JSON.stringify(body) }).then((r) => handle<T>(r)),
  put: <T>(path: string, body: unknown) =>
    fetch(`/api${path}`, { method: 'PUT', headers: headers(), body: JSON.stringify(body) }).then((r) => handle<T>(r)),
  del: <T>(path: string) => fetch(`/api${path}`, { method: 'DELETE', headers: headers(false) }).then((r) => handle<T>(r)),
  upload: <T>(path: string, form: FormData) =>
    fetch(`/api${path}`, { method: 'POST', headers: headers(false), body: form }).then((r) => handle<T>(r)),
}

export type StreamEvent =
  | { type: 'step'; text: string; tool: string }
  | { type: 'done'; [key: string]: unknown }
  | { type: 'error'; text: string }

/** POST and read server-sent events as they arrive (the AI's steps, then its answer). */
export async function stream(path: string, body: unknown, onEvent: (event: StreamEvent) => void): Promise<void> {
  const response = await fetch(`/api${path}`, { method: 'POST', headers: headers(), body: JSON.stringify(body ?? {}) })
  if (!response.ok || !response.body) {
    await handle(response)
    return
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let split
    while ((split = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, split).trim()
      buffer = buffer.slice(split + 2)
      if (chunk.startsWith('data:')) onEvent(JSON.parse(chunk.slice(5)))
    }
  }
}
