import clsx from 'clsx'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { Dot } from '../../components/ui'
import { fmt } from '../../lib/format'
import type { Timeline } from '../../lib/types'

// The editor's frame: titled panels, toolbar buttons, and the clock over the scene.

export function Panel({ title, className, children }: { title: string; className?: string; children: ReactNode }) {
  return (
    <section className={clsx('flex min-h-0 flex-col border-line bg-surface', className)}>
      <div className="flex h-9 shrink-0 items-center border-b border-line bg-subtle px-3 text-[12.5px] font-semibold text-fg-2">{title}</div>
      <div className="min-h-0 flex-1 overflow-y-auto pb-16 xl:pb-0">{children}</div>
    </section>
  )
}

export function ToolButton({ active, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button {...rest} className={clsx('h-8 rounded-md border px-2.5 text-[13px] font-medium transition disabled:opacity-40',
      active ? 'border-brand-line bg-brand-soft text-brand' : 'border-line-strong text-fg-2 hover:bg-subtle')}>
      {children}
    </button>
  )
}

export function ToolGroup({ value, options, onChange }: { value: string; options: { value: string; label: string }[]; onChange: (v: string) => void }) {
  return (
    <div className="inline-flex h-8 overflow-hidden rounded-md border border-line-strong">
      {options.map((o, i) => (
        <button key={o.value} onClick={() => onChange(o.value)}
          className={clsx('px-2.5 text-[13px] transition', i > 0 && 'border-l border-line-strong',
            o.value === value ? 'bg-brand-soft font-medium text-brand' : 'text-fg-2 hover:bg-subtle')}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Clock({ timeline, minute }: { timeline: Timeline; minute: number }) {
  const hour = Math.floor(minute / 60)
  const band = timeline.band_by_hour[hour]
  return (
    <div className="pointer-events-none absolute left-3 top-3 rounded-lg border border-line bg-white/95 px-3 py-2 shadow-sm">
      <div className="flex items-baseline gap-2">
        <span className="num text-[22px] font-semibold leading-none text-fg">{fmt.clock(minute)}</span>
        <span className="text-[13px] text-fg-3">{timeline.weekday}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-3 text-[12px] text-fg-2">
        <span>{timeline.lights[minute] ? 'Lights on' : 'Lights off'}</span>
        <span className="flex items-center gap-1.5">
          <Dot color={band === 'peak' ? '#dc2626' : band === 'off-peak' ? '#16a34a' : '#9ca3af'} />
          {band} · {timeline.currency}{timeline.price_by_hour[hour]?.toFixed(2)}/kWh
        </span>
      </div>
    </div>
  )
}
