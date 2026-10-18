import clsx from 'clsx'
import { useMemo } from 'react'

import { Dot } from '../../components/ui'
import { STATE_COLOR } from '../../lib/format'
import type { MachineMeta, PlantSpec, Timeline } from '../../lib/types'

/** Every machine, grouped like the plant, with its live state and kW. Click to select, double-click to focus. */
export function Hierarchy({ spec, machines, timeline, minute, selected, onSelect, onFocus }: {
  spec: PlantSpec; machines: MachineMeta[]; timeline: Timeline; minute: number; selected: string | null
  onSelect: (id: string) => void; onFocus: (id: string) => void
}) {
  const groups = useMemo(() => {
    const map = new Map<string, MachineMeta[]>()
    for (const m of machines) map.set(m.group, [...(map.get(m.group) ?? []), m])
    return [...map.entries()]
  }, [machines])
  return (
    <div className="py-1.5 text-[13px]">
      <div className="flex items-center justify-between px-3 py-1.5">
        <span className="font-medium text-fg">Main meter</span>
        <span className="num text-fg-2">{Math.round(timeline.meter[minute] ?? 0)} kW</span>
      </div>
      {groups.map(([group, items]) => (
        <div key={group} className="mt-1">
          <div className="px-3 py-1 text-[11.5px] font-medium uppercase tracking-wide text-fg-4">{group}</div>
          {items.map((m) => {
            const kw = timeline.machines[m.id]?.kw[minute] ?? 0
            const state = timeline.machines[m.id]?.state[minute] ?? 0
            const alert = timeline.alerts.some((a) => a.machine === m.id && minute >= a.from && minute < a.to)
            return (
              <button key={m.id} onClick={() => onSelect(m.id)} onDoubleClick={() => onFocus(m.id)} title="Double-click to focus"
                className={clsx('flex w-full items-center gap-2 py-1.5 pl-5 pr-3 text-left transition',
                  selected === m.id ? 'bg-brand-soft text-brand' : 'text-fg hover:bg-subtle')}>
                <Dot color={alert ? '#dc2626' : STATE_COLOR[state]} pulse={alert} />
                <span className={clsx('min-w-0 flex-1 truncate', alert && 'font-medium text-red-700')}>{m.name}</span>
                <span className="num shrink-0 text-[12.5px] text-fg-3">{kw.toFixed(1)}</span>
              </button>
            )
          })}
        </div>
      ))}
      <div className="mt-2 border-t border-line px-3 pt-2 text-[12px] text-fg-4">
        {spec.rooms.length} rooms · floor {spec.floor_w} × {spec.floor_d} m
      </div>
    </div>
  )
}
