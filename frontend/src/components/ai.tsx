import clsx from 'clsx'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'

import type { ToolCall } from '../lib/types'

export function Markdown({ children }: { children: string }) {
  return <div className="prose-ai text-[14px]"><ReactMarkdown>{children}</ReactMarkdown></div>
}

export function Spin({ className }: { className?: string }) {
  return <span className={clsx('inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent', className)} />
}

/** The AI's steps as they stream in: each lookup it made, the latest one still running. */
export function AiSteps({ steps, running, title = 'Working', compact }: { steps: string[]; running: boolean; title?: string; compact?: boolean }) {
  const [open, setOpen] = useState(false)
  if (!steps.length && !running) return null
  const shown = compact && !running && !open ? [] : steps
  return (
    <div className={clsx('rounded-xl border border-violet-200 bg-violet-50/50', compact ? 'px-3 py-2' : 'p-4')}>
      <button type="button" onClick={() => setOpen((v) => !v)} disabled={!compact || running}
        className="flex w-full items-center gap-2 text-left text-[13px] font-medium text-violet-800">
        {running && <Spin className="text-violet-600" />}
        {running ? `${title}…` : `Checked ${steps.length} figure${steps.length === 1 ? '' : 's'}`}
        {compact && !running && <span className="ml-auto text-[12px] font-normal text-violet-700">{open ? 'Hide' : 'Show'}</span>}
      </button>
      {shown.length > 0 && (
        <ol className="mt-2 space-y-1.5">
          {shown.map((step, i) => (
            <li key={i} className="flex gap-2.5 text-[13px] leading-snug text-fg">
              <span className="num w-4 shrink-0 text-right text-[12px] text-violet-500">{i + 1}</span>
              <span className={clsx(running && i === shown.length - 1 && 'text-fg-3')}>{step}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/** Every number the AI used, so anyone can check it. */
export function Evidence({ calls }: { calls: ToolCall[] }) {
  const [open, setOpen] = useState(false)
  if (!calls?.length) return null
  return (
    <div className="mt-3">
      <button onClick={() => setOpen((v) => !v)} className="text-[12.5px] text-fg-3 underline-offset-2 hover:text-fg hover:underline">
        {open ? 'Hide' : 'Show'} where these numbers came from ({calls.length} lookup{calls.length === 1 ? '' : 's'})
      </button>
      {open && (
        <div className="mt-2 max-h-80 space-y-2 overflow-y-auto">
          {calls.map((call, i) => (
            <pre key={i} className="overflow-x-auto rounded-lg border border-line bg-subtle p-3 text-[11.5px] leading-relaxed text-fg-2">
              <span className="text-brand">{call.tool}</span>({JSON.stringify(call.args)}){'\n'}
              {JSON.stringify(call.result, null, 1).slice(0, 1500)}
            </pre>
          ))}
        </div>
      )}
    </div>
  )
}

export function SavedNote({ when }: { when: string }) {
  return <div className="text-[12.5px] text-fg-3">Showing the last saved result, from {when}.</div>
}
