import type { PointerEvent } from 'react'

import type { MachineMeta, Timeline } from '../../lib/types'

/** The day as a strip: price bands, each line's batches and waste alerts. Click or drag to move the playhead. */
export function Scrubber({ timeline, minute, onSeek, machines }: { timeline: Timeline; minute: number; onSeek: (m: number) => void; machines: MachineMeta[] }) {
  const lines = [...new Set(timeline.batches.map((b) => b.line))].sort()
  const colorFor = (line: string) => machines.find((m) => m.line === line)?.color ?? '#2563eb'
  const seek = (e: PointerEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    onSeek(((e.clientX - rect.left) / rect.width) * 1440)
  }
  const height = 16 + lines.length * 12
  return (
    <div>
      <div className="relative cursor-pointer select-none rounded bg-subtle" style={{ height }}
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); seek(e) }}
        onPointerMove={(e) => e.buttons === 1 && seek(e)}>
        {timeline.band_by_hour.map((band, h) => (
          <div key={h} className="absolute top-0 h-1" style={{ left: `${(h / 24) * 100}%`, width: `${100 / 24}%`,
            background: band === 'peak' ? 'rgba(220,38,38,0.5)' : band === 'off-peak' ? 'rgba(22,163,74,0.45)' : 'rgba(156,163,175,0.3)' }} />
        ))}
        {lines.map((line, row) => timeline.batches.filter((b) => b.line === line).map((b, i) => (
          <div key={`${line}-${i}`} className="absolute h-2 rounded-sm" title={`Line ${line}: ${b.product}`}
            style={{ left: `${(b.start / 1440) * 100}%`, width: `${((b.end - b.start) / 1440) * 100}%`, top: 8 + row * 12, background: colorFor(line), opacity: 0.7 }} />
        )))}
        {timeline.alerts.map((a, i) => (
          <div key={i} className="absolute bottom-0 h-1 bg-red-500" style={{ left: `${(a.from / 1440) * 100}%`, width: `${((a.to - a.from) / 1440) * 100}%` }} />
        ))}
        <div className="absolute inset-y-0 w-0.5 bg-brand" style={{ left: `${(minute / 1440) * 100}%` }}>
          <div className="absolute -top-1 left-1/2 h-2.5 w-2.5 -translate-x-1/2 rounded-full bg-brand" />
        </div>
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-fg-4">
        {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((h) => <span key={h} className="num">{String(h).padStart(2, '0')}:00</span>)}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-fg-3">
        {lines.map((line) => <span key={line} className="flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm" style={{ background: colorFor(line), opacity: 0.7 }} />Line {line}</span>)}
        <span className="flex items-center gap-1.5"><span className="h-1 w-3 bg-red-500/60" />Peak price</span>
        <span className="flex items-center gap-1.5"><span className="h-1 w-3 bg-green-600/50" />Cheap hours</span>
        <span className="flex items-center gap-1.5"><span className="h-1 w-3 bg-red-500" />Waste alert</span>
      </div>
    </div>
  )
}
