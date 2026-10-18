import { type ReactNode, useMemo } from 'react'
import { Area, AreaChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Button, Dot } from '../../components/ui'
import { TIP } from '../../lib/chart'
import { api } from '../../lib/api'
import { askAssistant } from '../../lib/assistant'
import { fmt, STATE_LABEL } from '../../lib/format'
import type { MachineMeta, Timeline } from '../../lib/types'
import { useAsync } from '../../lib/useAsync'

// The right-hand panel: the whole plant when nothing is selected, or one machine in detail.

function Section({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="border-b border-line px-4 py-3.5 last:border-b-0">
      {title && <div className="mb-2 text-[12.5px] font-semibold text-fg-2">{title}</div>}
      {children}
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-[12px] text-fg-3">{label}</div>
      <div className="mt-0.5 text-fg">{children}</div>
    </div>
  )
}

export function PlantInspector({ timeline, minute, machines, onSelect }: { timeline: Timeline; minute: number; machines: MachineMeta[]; onSelect: (id: string) => void }) {
  const kw = timeline.meter[minute] ?? 0
  const price = timeline.price_by_hour[Math.floor(minute / 60)] ?? 0
  const today = useMemo(() => {
    let kwh = 0
    let cost = 0
    for (let i = 0; i <= minute; i++) {
      kwh += (timeline.meter[i] ?? 0) / 60
      cost += ((timeline.meter[i] ?? 0) * (timeline.price_by_hour[Math.floor(i / 60)] ?? 0)) / 60
    }
    return { kwh, cost }
  }, [timeline, minute])
  const active = timeline.alerts.filter((a) => minute >= a.from && minute < a.to)
  const recent = timeline.events.filter((e) => e.minute <= minute).slice(-8).reverse()
  const running = machines.filter((m) => (timeline.machines[m.id]?.state[minute] ?? 0) === 2).length
  return (
    <>
      <Section title="Plant">
        <div className="grid grid-cols-3 gap-3">
          <Field label="Site now"><span className="num text-[18px] font-semibold">{kw.toFixed(0)}</span> <span className="text-[12px] text-fg-3">kW</span></Field>
          <Field label="Costing"><span className="num text-[18px] font-semibold">{timeline.currency}{(kw * price).toFixed(0)}</span> <span className="text-[12px] text-fg-3">/h</span></Field>
          <Field label="Today so far"><span className="num text-[18px] font-semibold">{timeline.currency}{today.cost.toFixed(0)}</span></Field>
        </div>
        <div className="mt-2 text-[12.5px] text-fg-3">{Math.round(today.kwh).toLocaleString()} kWh so far · {running} of {machines.length} machines running</div>
      </Section>
      {active.length > 0 && (
        <Section title="Alerts">
          {active.map((a) => {
            const m = machines.find((x) => x.id === a.machine)
            return (
              <button key={a.machine} onClick={() => onSelect(a.machine)}
                className="mb-2 w-full rounded-md border border-l-4 border-red-200 border-l-red-500 bg-red-50 px-3 py-2 text-left text-[13px] leading-snug text-red-800 last:mb-0">
                <b className="font-medium">{m?.name}</b> is drawing {a.observed_kw.toFixed(1)} kW at night (normally {a.usual_kw.toFixed(1)}). Something may be left on or leaking.
              </button>
            )
          })}
        </Section>
      )}
      <Section title="Events">
        {recent.length === 0 && <div className="text-[13px] text-fg-3">Quiet so far today.</div>}
        {recent.map((e, i) => (
          <div key={`${e.minute}-${i}`} className="flex gap-3 border-t border-line py-1.5 text-[13px] first:border-t-0">
            <span className="num shrink-0 text-fg-4">{fmt.clock(e.minute)}</span>
            <span className="text-fg">{e.text}</span>
          </div>
        ))}
      </Section>
      <Section><div className="text-[12.5px] text-fg-3">Select a machine in the scene or the hierarchy to inspect it.</div></Section>
    </>
  )
}

export function MachineInspector({ meta, timeline, minute, plantId, day, onClose, onFocus }: {
  meta: MachineMeta; timeline: Timeline; minute: number; plantId: string; day: string; onClose: () => void; onFocus: () => void
}) {
  const series = timeline.machines[meta.id]
  const explain = useAsync(() => api.get<{ learned_kwh: number; adjustment_kwh: number; final_kwh: number; plus_minus: number; drivers: string[] }>(
    `/plants/${plantId}/explain/${meta.id}?day=${day}`), [plantId, meta.id, day])
  const data = useMemo(() => {
    const rows = []
    for (let i = 0; i < series.kw.length; i += 5) rows.push({ m: i, kw: series.kw[i], band: [series.low[i], series.high[i]], hidden: series.hidden[i] })
    return rows
  }, [series])
  const state = series.state[minute] ?? 0
  const batch = timeline.batches.find((b) => b.line === meta.line && minute >= b.start && minute < b.end)
  const alert = timeline.alerts.find((a) => a.machine === meta.id && minute >= a.from && minute < a.to)
  const kw = series.kw[minute] ?? 0
  return (
    <>
      <Section>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2"><Dot color={meta.color} /><span className="truncate text-[15px] font-semibold text-fg">{meta.name}</span></div>
            <div className="mt-0.5 text-[12.5px] text-fg-3">{meta.type_label || meta.type} · {meta.group}</div>
          </div>
          <button onClick={onClose} className="rounded px-1.5 py-0.5 text-[12.5px] text-fg-3 hover:bg-muted hover:text-fg">Deselect</button>
        </div>
        {alert && (
          <div className="mt-3 rounded-md border border-l-4 border-red-200 border-l-red-500 bg-red-50 px-3 py-2 text-[13px] text-red-800">
            Drawing {alert.observed_kw.toFixed(1)} kW at night; normally {alert.usual_kw.toFixed(1)} kW.
          </div>
        )}
      </Section>
      <Section title="Now">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Power"><span className="num text-[20px] font-semibold">{kw.toFixed(1)}</span> <span className="text-[12px] text-fg-3">kW</span>
            <div className="num text-[12px] text-fg-3">likely {series.low[minute]?.toFixed(1)}–{series.high[minute]?.toFixed(1)}</div></Field>
          <Field label="State"><span className={alert ? 'font-medium text-red-700' : ''}>{alert ? 'Wasting energy' : STATE_LABEL[state]}</span>
            {batch && <div className="text-[12px] text-fg-3">Making {batch.product}</div>}</Field>
          <Field label="Rated"><span className="num">{meta.rated_kw} kW</span></Field>
          <Field label="Peak seen"><span className="num">{meta.peak_kw.toFixed(1)} kW</span></Field>
        </div>
      </Section>
      <Section title="Today">
        <div className="h-28">
          <ResponsiveContainer>
            <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -26 }}>
              <XAxis dataKey="m" type="number" domain={[0, 1440]} ticks={[0, 360, 720, 1080, 1440]} tickFormatter={(v) => fmt.clock(v).slice(0, 2)} tick={{ fill: '#6b7280', fontSize: 11 }} stroke="#e5e7eb" />
              <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} stroke="#e5e7eb" />
              <Tooltip contentStyle={TIP} labelFormatter={(v) => fmt.clock(Number(v))} formatter={(v) => (Array.isArray(v) ? `${v[0]}–${v[1]} kW` : `${v} kW`)} />
              <Area dataKey="band" stroke="none" fill={meta.color} fillOpacity={0.15} isAnimationActive={false} name="Likely range" />
              <Area dataKey="kw" stroke={meta.color} strokeWidth={1.5} fill="none" isAnimationActive={false} name="MeterZero" />
              <Line dataKey="hidden" stroke="#d97706" strokeWidth={1} strokeDasharray="3 3" dot={false} isAnimationActive={false} name="Hidden meter" />
              <ReferenceLine x={minute} stroke="#2563eb" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-1 flex gap-4 text-[12px] text-fg-3">
          <span className="flex items-center gap-1.5"><span className="h-0.5 w-3" style={{ background: meta.color }} />MeterZero</span>
          <span className="flex items-center gap-1.5"><span className="w-3 border-t border-dashed border-amber-500" />Hidden meter</span>
        </div>
        {explain.data && (
          <p className="mt-3 text-[13px] leading-relaxed text-fg-2">
            <b className="font-medium text-fg">{explain.data.final_kwh.toFixed(0)} kWh today.</b> From the schedule and the meter's pattern MeterZero expected {explain.data.learned_kwh.toFixed(0)} kWh
            {Math.abs(explain.data.adjustment_kwh) >= 0.5 ? `, then moved it ${explain.data.adjustment_kwh > 0 ? 'up' : 'down'} ${Math.abs(explain.data.adjustment_kwh).toFixed(0)} kWh so everything adds up to the main meter.` : ', which already matched the main meter.'}
          </p>
        )}
      </Section>
      <Section>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="primary" onClick={() => askAssistant(alert
            ? `The ${meta.name.toLowerCase()} is drawing ${alert.observed_kw.toFixed(1)} kW at ${fmt.clock(minute)} on ${timeline.weekday}, normally ${alert.usual_kw.toFixed(1)}. What is likely wrong, what does it cost, and what should maintenance check?`
            : `Why is the ${meta.name.toLowerCase()} using ${kw.toFixed(1)} kW at ${fmt.clock(minute)} on ${timeline.weekday}? Is that normal?`)}>
            Ask MeterZero about this
          </Button>
          <Button size="sm" onClick={onFocus}>Focus</Button>
        </div>
      </Section>
    </>
  )
}
