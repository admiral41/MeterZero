import { useMemo, useState } from 'react'
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { NotTrained } from '../components/NotTrained'
import { Badge, Card, CardTitle, Dot, ErrorBox, Loading, Page, PageHeader, Select, Stat, StatStrip } from '../components/ui'
import { AXIS, TIP } from '../lib/chart'
import { useAssistantContext } from '../lib/assistant'
import { api } from '../lib/api'
import { fmt } from '../lib/format'
import { usePlant } from '../lib/plant'
import type { Accuracy as AccuracyData, Timeline } from '../lib/types'
import { useAsync } from '../lib/useAsync'


export default function Accuracy() {
  const { plant, plantId, untrained } = usePlant()
  const { data, error, loading } = useAsync(() => api.get<AccuracyData>(`/plants/${plantId}/accuracy`), [plantId])
  useAssistantContext('Accuracy', "Comparing MeterZero's figures with hidden meters on every machine.",
    ['Which machine is MeterZero least sure about, and why?', 'How much should I trust these numbers?', 'Where should the next meter go?'])
  if (untrained) return <NotTrained />
  if (error) return <Page><ErrorBox error={error} /></Page>
  if (loading || !data || !plant) return <Loading label="Checking the figures…" />
  const final = data.ladder[data.ladder.length - 1]
  const best = data.budget.find((b) => b.recommended >= 0.95) ?? data.budget[data.budget.length - 1]

  return (
    <Page>
      <PageHeader title="How accurate is it?" badges={<Badge tone="ok">Checked</Badge>}
        subtitle="Every machine in this plant has a hidden meter MeterZero never sees. Here its figures are compared with those meters, on days it never learned from." />

      <StatStrip>
        <Stat label="Accuracy from one meter" value={fmt.pct(final.accuracy)} sub="kWh put on the right machine"
          hint="Counts every kWh assigned to the wrong machine; 100% would be perfect." />
        <Stat label={`With ${best.sensors} extra meter${best.sensors === 1 ? '' : 's'}`} value={fmt.pct(best.recommended)} tone="ok"
          sub={data.budget.slice(1, best.sensors + 1).map((b) => b.added).join(' + ')} />
        <Stat label="Ranges that held" value={fmt.pct(data.coverage.minute)} sub="aim: 90%, minute by minute"
          hint="When MeterZero says 'likely between', the real value should be inside about 9 times in 10." />
        <Stat label="Ranges that held, per batch" value={fmt.pct(data.coverage.batch)} sub={`per machine-day ${fmt.pct(data.coverage.daily)}`} />
      </StatStrip>

      <DayCheck />

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle hint="How much each step of the method adds.">How the method builds up</CardTitle>
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={data.ladder} margin={{ left: -10 }}>
                <CartesianGrid stroke="#e5e7eb" vertical={false} />
                <XAxis dataKey="model" {...AXIS} interval={0} />
                <YAxis domain={[0.5, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} {...AXIS} />
                <Tooltip contentStyle={TIP} formatter={(v) => fmt.pct(Number(v), 1)} />
                <Bar dataKey="accuracy" fill="#2563eb" radius={[6, 6, 0, 0]} label={{ position: 'top', fill: '#4b5563', fontSize: 12, formatter: (v: unknown) => fmt.pct(Number(v)) }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <CardTitle hint="Adding meters where MeterZero is least sure, versus at random (average of many tries).">Extra meters: where they help most</CardTitle>
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={data.budget} margin={{ left: -10, right: 10 }}>
                <CartesianGrid stroke="#e5e7eb" vertical={false} />
                <XAxis dataKey="sensors" {...AXIS} label={{ value: 'extra meters', fill: '#6b7280', fontSize: 11, position: 'insideBottom', offset: -2 }} />
                <YAxis domain={[0.8, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} {...AXIS} />
                <Tooltip contentStyle={TIP} formatter={(v) => fmt.pct(Number(v), 1)} labelFormatter={(v) => `${v} extra meter(s)`} />
                <Line dataKey="recommended" name="Where MeterZero suggests" stroke="#2563eb" strokeWidth={2.5} dot={{ r: 4 }} isAnimationActive={false} />
                <Line dataKey="random" name="At random" stroke="#9ca3af" strokeDasharray="4 3" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card className="overflow-x-auto">
          <CardTitle>By machine</CardTitle>
          <table className="w-full text-[13.5px]">
            <thead className="text-left text-[12.5px] text-fg-3">
              <tr><th className="pb-2 font-medium">Machine</th><th className="pb-2 text-right font-medium">MeterZero</th><th className="pb-2 text-right font-medium">Hidden meter</th><th className="pb-2 text-right font-medium">Off by</th><th className="pb-2 text-right font-medium">In range</th></tr>
            </thead>
            <tbody>
              {data.by_machine.map((m) => (
                <tr key={m.id} className="border-t border-line">
                  <td className="py-2 text-fg"><span className="flex items-center gap-2"><Dot color={plant.machines.find((x) => x.id === m.id)?.color ?? '#64748b'} />{m.name}</span></td>
                  <td className="num py-2 text-right text-fg">{fmt.kwh(m.estimated_kwh)}</td>
                  <td className="num py-2 text-right text-fg-2">{fmt.kwh(m.true_kwh)}</td>
                  <td className={`num py-2 text-right ${Math.abs(m.error_pct) < 5 ? 'text-emerald-700' : 'text-amber-700'}`}>{m.error_pct > 0 ? '+' : ''}{m.error_pct.toFixed(1)}%</td>
                  <td className="num py-2 text-right text-fg-2">{fmt.pct(m.inside_range)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card className="overflow-x-auto">
          <CardTitle>Energy per item, by product</CardTitle>
          <table className="w-full text-[13.5px]">
            <thead className="text-left text-[12.5px] text-fg-3">
              <tr><th className="pb-2 font-medium">Product</th><th className="pb-2 text-right font-medium">MeterZero</th><th className="pb-2 text-right font-medium">Hidden meters</th><th className="pb-2 text-right font-medium">Off by</th></tr>
            </thead>
            <tbody>
              {data.products.map((p) => (
                <tr key={p.product} className="border-t border-line">
                  <td className="py-2 text-fg">{p.product} <span className="text-fg-4">· line {p.line}</span></td>
                  <td className="num py-2 text-right text-fg">{p.estimated.toFixed(3)} <span className="text-fg-4">± {p.plus_minus.toFixed(3)}</span></td>
                  <td className="num py-2 text-right text-fg-2">{p.true.toFixed(3)}</td>
                  <td className={`num py-2 text-right ${Math.abs(p.error_pct) < 5 ? 'text-emerald-700' : 'text-amber-700'}`}>{p.error_pct > 0 ? '+' : ''}{p.error_pct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 text-[12px] text-fg-4">kWh per item made, over the test week.</div>
        </Card>
      </div>

      <Card className="mt-4">
        <CardTitle>What to keep in mind</CardTitle>
        <ul className="list-disc space-y-1.5 pl-5 text-[14px] leading-relaxed text-fg-2">
          <li><b className="text-fg">These plants are simulated</b>, with hidden meters, so every result can be checked. Real plants are messier; check on site.</li>
          <li><b className="text-fg">Machines that switch on and off in similar ways</b> (chillers, compressors, heaters) are the hardest to tell apart. That's why MeterZero suggests a meter there first.</li>
          <li><b className="text-fg">MeterZero learns each machine from a few weeks of history</b>, so a new plant needs temporary meters for that time.</li>
          <li><b className="text-fg">The AI explains; it doesn't measure.</b> It only repeats MeterZero's numbers, and every answer shows which ones.</li>
        </ul>
      </Card>
    </Page>
  )
}

/** Pick a day and a machine: MeterZero's figure, its likely range, and the hidden meter, minute by minute. */
function DayCheck() {
  const { plant, plantId } = usePlant()
  const [day, setDay] = useState(plant!.default_day)
  const [machine, setMachine] = useState(plant!.machines[0].id)
  const { data } = useAsync(() => api.get<Timeline>(`/plants/${plantId}/timeline?day=${day}`), [plantId, day])
  const meta = plant!.machines.find((m) => m.id === machine)!
  const rows = useMemo(() => {
    const s = data?.machines[machine]
    if (!s) return []
    const out = []
    for (let i = 0; i < s.kw.length; i += 5) out.push({ t: fmt.clock(i), kw: s.kw[i], band: [s.low[i], s.high[i]], hidden: s.hidden[i] })
    return out
  }, [data, machine])
  const totals = useMemo(() => {
    const s = data?.machines[machine]
    if (!s) return null
    const est = s.kw.reduce((a, b) => a + b, 0) / 60
    const real = s.hidden.reduce((a, b) => a + b, 0) / 60
    const inside = s.kw.filter((_, i) => s.hidden[i] >= s.low[i] && s.hidden[i] <= s.high[i]).length / s.kw.length
    return { est, real, inside }
  }, [data, machine])
  return (
    <Card className="mt-4">
      <CardTitle right={
        <div className="flex gap-2">
          <Select value={machine} onChange={(e) => setMachine(e.target.value)} className="!w-auto !py-1.5 text-[13px]">
            {plant!.machines.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </Select>
          <Select value={day} onChange={(e) => setDay(e.target.value)} className="!w-auto !py-1.5 text-[13px]">
            {plant!.days.map((d) => <option key={d} value={d}>{fmt.day(d)}</option>)}
          </Select>
        </div>}>Check one machine, one day</CardTitle>
      {totals && (
        <div className="mb-4 grid grid-cols-3 gap-4">
          <Stat size="sm" label="MeterZero said" value={fmt.kwh(totals.est)} />
          <Stat size="sm" label="Hidden meter read" value={fmt.kwh(totals.real)} sub={`off by ${Math.abs((totals.est / Math.max(totals.real, 0.01) - 1) * 100).toFixed(1)}%`} />
          <Stat size="sm" label="Time inside the range" value={fmt.pct(totals.inside)} sub="aim: about 90%" />
        </div>
      )}
      <div className="h-64">
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ left: -10, right: 8 }}>
            <CartesianGrid stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="t" {...AXIS} interval={23} />
            <YAxis {...AXIS} unit=" kW" />
            <Tooltip contentStyle={TIP} formatter={(v) => (Array.isArray(v) ? `${v[0]}–${v[1]} kW` : `${v} kW`)} />
            <Area dataKey="band" name="Likely range" stroke="none" fill={meta.color} fillOpacity={0.18} isAnimationActive={false} />
            <Line dataKey="kw" name="MeterZero" stroke={meta.color} strokeWidth={1.8} dot={false} isAnimationActive={false} />
            <Line dataKey="hidden" name="Hidden meter" stroke="#d97706" strokeWidth={1.2} strokeDasharray="3 3" dot={false} isAnimationActive={false} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}
