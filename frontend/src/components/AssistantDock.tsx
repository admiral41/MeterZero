import clsx from 'clsx'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { stream } from '../lib/api'
import { useCurrentContext, usePendingQuestion } from '../lib/assistant'
import type { ToolCall } from '../lib/types'
import { useAiStatus } from '../lib/useAi'
import { AiSteps, Evidence, Markdown } from './ai'

interface Message { role: 'user' | 'assistant'; text: string; steps?: string[]; calls?: ToolCall[]; pending?: boolean; error?: string }

const GENERAL = ['What should I fix first this week?', 'Where does most of the money go?', 'Is anything wasting energy right now?']

/** A small chat that floats over every plant page and knows what you're looking at. */
export function AssistantDock({ plantId }: { plantId: string }) {
  const connected = useAiStatus()
  const context = useCurrentContext()
  const pending = usePendingQuestion()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [conversation] = useState(() => `dock-${Date.now()}`)
  const handled = useRef<number | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const busy = messages.some((m) => m.pending)

  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }) }, [messages, open])

  const ask = async (question: string) => {
    if (!question.trim() || busy) return
    setInput('')
    setOpen(true)
    setMessages((m) => [...m, { role: 'user', text: question }, { role: 'assistant', text: '', steps: [], pending: true }])
    const update = (patch: Partial<Message>) =>
      setMessages((m) => m.map((msg, i) => (i === m.length - 1 ? { ...msg, ...patch } : msg)))
    const where = context.page ? `\n\n(Context: I'm on the ${context.page} page. ${context.detail})` : ''
    const steps: string[] = []
    try {
      await stream(`/plants/${plantId}/ai/ask`, { question: question + where, conversation }, (event) => {
        if (event.type === 'step') { steps.push(event.text); update({ steps: [...steps] }) }
        else if (event.type === 'error') update({ error: event.text, pending: false })
        else if (event.type === 'done') update({ text: String(event.text ?? ''), calls: event.tool_calls as ToolCall[], pending: false })
      })
    } catch (e) {
      update({ error: e instanceof Error ? e.message : String(e), pending: false })
    }
  }

  useEffect(() => {
    if (!pending || handled.current === pending.id) return
    handled.current = pending.id
    setOpen(true)
    if (connected) ask(pending.question)
    else setInput(pending.question)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, connected])

  const suggestions = context.suggestions.length ? context.suggestions : GENERAL

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-[80] flex items-center gap-2.5 rounded-full border border-line bg-surface py-1.5 pl-1.5 pr-4 text-[14px] font-medium text-fg shadow-lg transition hover:border-brand-line hover:shadow-xl">
        <Avatar size={34} />
        Ask MeterZero
      </button>
    )
  }

  return (
    <div className="fixed inset-x-3 bottom-3 z-[80] flex max-h-[min(640px,calc(100vh-24px))] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl sm:inset-x-auto sm:right-5 sm:w-[400px]">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <Avatar size={36} />
          <div className="min-w-0">
            <div className="text-[14px] font-semibold text-fg">Ask MeterZero</div>
            <div className="truncate text-[12px] text-fg-3">{context.page ? `Looking at: ${context.page}` : 'Your plant\'s energy assistant'} · powered by Gemini</div>
          </div>
        </div>
        <div className="flex gap-1">
          {messages.length > 0 && <button onClick={() => setMessages([])} disabled={busy} className="rounded-md px-2 py-1 text-[12.5px] text-fg-3 hover:bg-subtle hover:text-fg">Clear</button>}
          <button onClick={() => setOpen(false)} className="rounded-md px-2 py-1 text-[12.5px] text-fg-3 hover:bg-subtle hover:text-fg">Close</button>
        </div>
      </div>

      <div className="min-h-[200px] flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div>
            <p className="text-[13.5px] leading-relaxed text-fg-2">
              {context.detail || 'Ask about machines, products, waste or costs.'}
            </p>
            <div className="mt-3 space-y-2">
              {suggestions.map((q) => (
                <button key={q} onClick={() => ask(q)} disabled={!connected || busy}
                  className="w-full rounded-lg border border-line px-3 py-2 text-left text-[13px] text-fg transition hover:border-brand-line hover:bg-brand-soft disabled:opacity-50">
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={clsx(m.role === 'user' && 'flex justify-end')}>
            {m.role === 'user' ? (
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-brand px-3.5 py-2 text-[13.5px] text-white">{m.text}</div>
            ) : (
              <div className="flex gap-2.5">
                <Avatar size={28} />
                <div className="min-w-0 flex-1">
                {(m.pending || (m.steps?.length ?? 0) > 0) && <AiSteps steps={m.steps ?? []} running={!!m.pending} title="Checking the numbers" compact />}
                {m.error && <div className="mt-2 rounded-lg border border-red-200 bg-red-50 p-3 text-[13px] text-red-800">{m.error}</div>}
                {m.text && <div className="mt-2"><Markdown>{m.text}</Markdown></div>}
                {m.calls && <Evidence calls={m.calls} />}
                </div>
              </div>
            )}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <div className="border-t border-line p-3">
        {connected === false && (
          <div className="mb-2 text-[12.5px] text-fg-3">
            The assistant needs a Gemini key. <Link to={`/p/${plantId}/settings`} className="text-brand hover:underline">Add a key in Settings</Link>.
          </div>
        )}
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(input) }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} disabled={!connected || busy} placeholder="Ask a question…"
            className="min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-3 py-2 text-[13.5px] text-fg outline-none placeholder:text-fg-4 focus:border-brand disabled:bg-subtle" />
          <button type="submit" disabled={!connected || busy || !input.trim()}
            className="rounded-lg bg-brand px-3.5 py-2 text-[13.5px] font-medium text-white hover:bg-brand-strong disabled:opacity-50">Ask</button>
        </form>
      </div>
    </div>
  )
}

/** The assistant's face: a small robot. */
export function Avatar({ size = 32 }: { size?: number }) {
  return (
    <span className="grid shrink-0 place-items-center overflow-hidden rounded-full bg-brand-soft ring-1 ring-brand-line" style={{ width: size, height: size }}>
      <img src="/brand/assistant.png" alt="" width={size * 0.82} height={size * 0.82} className="translate-y-[6%]" />
    </span>
  )
}
