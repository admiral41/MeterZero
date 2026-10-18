import clsx from 'clsx'
import { useEffect, useRef, useState } from 'react'

import { AiSteps, Evidence, Markdown, SavedNote, Spin } from '../components/ai'
import { Avatar } from '../components/AssistantDock'
import { NotTrained } from '../components/NotTrained'
import { Link } from 'react-router-dom'

import { Badge, Button, Card, CardTitle, ErrorBox, PageHeader, Segmented } from '../components/ui'
import { api, stream } from '../lib/api'
import { usePlant } from '../lib/plant'
import type { ToolCall } from '../lib/types'
import { useAiRun, useAiStatus } from '../lib/useAi'

const PROMPTS: Record<string, string[]> = {
  'Plant manager': ['What should I fix first this week, and what is it worth?', 'Give me this morning\'s check in three lines.',
    'Which product costs us the most energy per item, and why?'],
  Maintenance: ['Is any machine using energy when it shouldn\'t?', 'Write a repair request for the biggest problem.',
    'Which machine should get a meter next, and why?'],
  Finance: ['What does electricity cost us per month, and where does it go?', 'What is the cheapest schedule change we could make?',
    'How much would fixing the waste save in a year?'],
  Sustainability: ['What is our CO2 per item for each product?', 'How much energy goes into making nothing?',
    'How much CO2 would fixing the waste avoid in a year?'],
}

interface Message { role: 'user' | 'assistant'; text: string; steps?: string[]; calls?: ToolCall[]; pending?: boolean; error?: string }

export default function Assistant() {
  const { plantId, untrained } = usePlant()
  const connected = useAiStatus()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [role, setRole] = useState('Plant manager')
  const [conversation] = useState(() => `chat-${Date.now()}`)
  const bottom = useRef<HTMLDivElement>(null)
  const busy = messages.some((m) => m.pending)

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const ask = async (question: string) => {
    if (!question.trim() || busy) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', text: question }, { role: 'assistant', text: '', steps: [], pending: true }])
    const update = (patch: Partial<Message>) =>
      setMessages((m) => m.map((msg, i) => (i === m.length - 1 ? { ...msg, ...patch, steps: patch.steps ?? msg.steps } : msg)))
    const steps: string[] = []
    try {
      await stream(`/plants/${plantId}/ai/ask`, { question, conversation }, (event) => {
        if (event.type === 'step') { steps.push(event.text); update({ steps: [...steps] }) }
        else if (event.type === 'error') update({ error: event.text, pending: false })
        else if (event.type === 'done') update({ text: String(event.text ?? ''), calls: event.tool_calls as ToolCall[], pending: false })
      })
    } catch (e) {
      update({ error: e instanceof Error ? e.message : String(e), pending: false })
    }
  }

  if (untrained) return <NotTrained />

  return (
    <div className="grid min-h-full gap-4 px-4 py-6 sm:px-6 lg:px-8 lg:py-7 xl:h-full xl:grid-cols-[minmax(0,1fr)_400px] 2xl:px-10">
      <div className="flex min-h-0 flex-col">
        <PageHeader title="Ask MeterZero" badges={<Badge tone="ai">Powered by Gemini</Badge>}
          subtitle="Ask about the plant in plain words, by typing or speaking. Answers use MeterZero's numbers, and you can always see which ones." />
        <Card className="flex min-h-[520px] flex-1 flex-col !p-0 xl:min-h-0">
          <div className="flex-1 space-y-5 overflow-y-auto p-6">
            {messages.length === 0 && (
              <div className="grid h-full place-items-center text-center">
                <div>
                  <div className="mx-auto mb-3 w-fit"><Avatar size={72} /></div>
                  <div className="text-[15px] text-fg">Ask anything about energy, machines, products, waste or costs.</div>
                  <div className="mt-1 text-[14px] text-fg-3">Type below, press Speak, or pick a question.</div>
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={clsx('flex gap-3', m.role === 'user' && 'justify-end')}>
                {m.role === 'assistant' && <Avatar size={32} />}
                <div className={clsx('max-w-[78%]', m.role === 'user' ? 'rounded-2xl rounded-br-sm bg-brand px-4 py-2.5 text-[14px] text-white' : 'min-w-0 max-w-3xl flex-1')}>
                  {m.role === 'user' ? m.text : (
                    <>
                      {(m.pending || (m.steps?.length ?? 0) > 0) && <AiSteps steps={m.steps ?? []} running={!!m.pending} title="Checking the numbers" compact />}
                      {m.error && <ErrorBox error={m.error} />}
                      {m.text && <div className="mt-3"><Markdown>{m.text}</Markdown></div>}
                      {m.calls && <Evidence calls={m.calls} />}
                    </>
                  )}
                </div>
              </div>
            ))}
            <div ref={bottom} />
          </div>
          <div className="border-t border-line p-4">
            {connected === false && <div className="mb-2 text-[13px] text-fg-3">The assistant needs a Gemini key. <Link to={`/p/${plantId}/settings`} className="text-brand hover:underline">Add a key in Settings</Link>.</div>}
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(input) }}>
              <input value={input} onChange={(e) => setInput(e.target.value)} disabled={!connected || busy}
                placeholder="Ask about machines, products, waste or costs…"
                className="flex-1 rounded-xl border border-line-strong bg-surface px-4 py-3 text-sm text-fg outline-none placeholder:text-fg-4 focus:border-brand disabled:opacity-60" />
              <VoiceButton disabled={!connected || busy} onText={ask} />
              <Button type="submit" variant="primary" disabled={!connected || busy || !input.trim()}>Ask</Button>
            </form>
          </div>
        </Card>
      </div>

      <div className="space-y-4 xl:overflow-y-auto xl:pt-[76px]">
        <Card>
          <CardTitle>Not sure what to ask?</CardTitle>
          <Segmented value={role} onChange={setRole} options={Object.keys(PROMPTS).map((r) => ({ value: r, label: r.split(' ')[0] }))} />
          <div className="mt-3 space-y-2">
            {PROMPTS[role].map((q) => (
              <button key={q} disabled={!connected || busy} onClick={() => ask(q)}
                className="w-full rounded-lg border border-line px-3.5 py-2.5 text-left text-[13.5px] text-fg transition hover:border-violet-300 hover:bg-violet-50/40 disabled:opacity-50">
                {q}
              </button>
            ))}
          </div>
        </Card>
        <WeeklySummary plantId={plantId} connected={!!connected} />
      </div>
    </div>
  )
}

function VoiceButton({ disabled, onText }: { disabled: boolean; onText: (text: string) => void }) {
  const [state, setState] = useState<'idle' | 'recording' | 'hearing'>('idle')
  const recorder = useRef<MediaRecorder | null>(null)

  const start = async () => {
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true })
      const chunks: Blob[] = []
      const rec = new MediaRecorder(media)
      rec.ondataavailable = (e) => chunks.push(e.data)
      rec.onstop = async () => {
        media.getTracks().forEach((t) => t.stop())
        setState('hearing')
        const form = new FormData()
        form.append('audio', new Blob(chunks, { type: rec.mimeType || 'audio/webm' }), 'question.webm')
        try {
          const { text } = await api.upload<{ text: string }>('/ai/transcribe', form)
          if (text) onText(text)
        } finally {
          setState('idle')
        }
      }
      recorder.current = rec
      rec.start()
      setState('recording')
    } catch {
      setState('idle')
    }
  }

  return (
    <button type="button" disabled={disabled || state === 'hearing'} title="Ask out loud"
      onClick={() => (state === 'recording' ? recorder.current?.stop() : start())}
      className={clsx('flex items-center gap-2 rounded-lg border px-3.5 text-[14px] font-medium transition disabled:opacity-50',
        state === 'recording' ? 'border-red-300 bg-red-50 text-red-700' : 'border-line-strong bg-surface text-fg-2 hover:bg-subtle')}>
      {state === 'recording' ? 'Stop' : state === 'hearing' ? <><Spin /> Listening</> : 'Speak'}
    </button>
  )
}

function WeeklySummary({ plantId, connected }: { plantId: string; connected: boolean }) {
  const ai = useAiRun<{ text: string; tool_calls: ToolCall[] }>()
  const [saved, setSaved] = useState<{ payload: { text: string; tool_calls: ToolCall[] }; recorded_at: string } | null>(null)
  useEffect(() => {
    api.get<{ payload: { text: string; tool_calls: ToolCall[] }; recorded_at: string }>(`/plants/${plantId}/ai/saved/briefing`).then(setSaved).catch(() => setSaved(null))
  }, [plantId, ai.result])
  const report = ai.result ?? saved?.payload
  const download = () => {
    const url = URL.createObjectURL(new Blob([report?.text ?? ''], { type: 'text/markdown' }))
    const a = Object.assign(document.createElement('a'), { href: url, download: 'meterzero-weekly-summary.md' })
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <Card>
      <CardTitle>This week's summary</CardTitle>
      <p className="text-[13px] text-fg-2">One page for the plant manager: where the energy went, waste, the cheapest change, the next meter and three actions.</p>
      <div className="mt-3 flex gap-2">
        <Button size="sm" variant="primary" loading={ai.running} disabled={!connected} onClick={() => ai.run(`/plants/${plantId}/ai/briefing`)}>Write it</Button>
        {report && <Button size="sm" onClick={download}>Download</Button>}
      </div>
      {(ai.running || ai.steps.length > 0) && <div className="mt-3"><AiSteps steps={ai.steps} running={ai.running} title="Writing the summary" compact /></div>}
      {ai.error && <ErrorBox error={ai.error} />}
      {report && !ai.running && (
        <div className="mt-3 max-h-[420px] overflow-y-auto rounded-lg border border-line p-4">
          {!ai.result && saved && <div className="mb-2"><SavedNote when={saved.recorded_at} /></div>}
          <Markdown>{report.text}</Markdown>
        </div>
      )}
    </Card>
  )
}
