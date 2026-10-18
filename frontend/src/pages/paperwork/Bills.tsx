import clsx from 'clsx'
import { useEffect, useState } from 'react'
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Spin } from '../../components/ai'
import { Badge, Button, Card, CardTitle, ErrorBox, Loading, Stat } from '../../components/ui'
import { AXIS, TIP } from '../../lib/chart'
import { api } from '../../lib/api'
import { askAssistant, useAssistantContext } from '../../lib/assistant'
import { fmt } from '../../lib/format'
import { usePlant } from '../../lib/plant'
import { useAiStatus } from '../../lib/useAi'
import { useAsync } from '../../lib/useAsync'

type Reading = Record<string, number | string>
interface Month { month: string; image: string; reading: Reading; currency: string; per_kwh: number; peak_share: number; problems: number; recoverable: number }
interface BillFinding { kind: string; tone: 'bad' | 'warn' | 'info' | 'ok'; title: string; detail: string; amount: number }
interface BillResult {
  currency: string; days: number; applied: boolean; findings: BillFinding[]
  check: { bill_kwh_per_day: number; meter_kwh_per_day: number; difference: number }
  by_machine: { id: string; name: string; color: string; amount: number; share: number }[]
  by_product: { name: string; amount: number; share: number }[]
}

const monthName = (m: string, long = false) =>
  new Date(`${m}-01T00:00:00`).toLocaleString('en', { month: long ? 'long' : 'short', year: 'numeric' })
const TONE = {
  bad: 'border-l-red-500 bg-red-50/60', warn: 'border-l-amber-500 bg-amber-50/50', info: 'border-l-blue-400 bg-subtle', ok: 'border-l-emerald-500 bg-subtle',
}
const TONE_LABEL = { bad: 'Problem', warn: 'Worth a look', info: 'Note', ok: 'Checked' }

/** Six months of bills for the plant's region, each checked line by line; read or upload a bill photo with Gemini. */
export function Bills() {
  const { plantId } = usePlant()
  const connected = useAiStatus()
  const months = useAsync(() => api.get<Month[]>(`/plants/${plantId}/bills`), [plantId])
  const [selected, setSelected] = useState<string | null>(null)
  const [custom, setCustom] = useState<{ reading: Reading; image: string; label: string } | null>(null)
  const [readByAi, setReadByAi] = useState<Reading | null>(null)
  const [reading, setReading] = useState(false)
  const [readError, setReadError] = useState<unknown>(null)
  const [result, setResult] = useState<BillResult | null>(null)
  const [error, setError] = useState<unknown>(null)

  const list = months.data ?? []
  const month = list.find((m) => m.month === selected) ?? list.find((m) => m.problems > 0) ?? list[list.length - 1]
  const bill: Reading | null = custom?.reading ?? readByAi ?? month?.reading ?? null
  const currency = result?.currency ?? month?.currency ?? 'Rs '
  const label = custom?.label ?? (month ? monthName(month.month, true) : '')

  useEffect(() => {
    if (!bill) return
    api.post<BillResult>(`/plants/${plantId}/bill`, bill).then((r) => { setResult(r); setError(null) }).catch(setError)
  }, [bill, plantId])

  const pick = (m: string) => { setSelected(m); setCustom(null); setReadByAi(null); setReadError(null) }

  const readPhoto = async (file?: File) => {
    setReading(true)
    setReadError(null)
    const form = new FormData()
    if (file) form.append('file', file)
    else { form.append('sample', 'true'); form.append('month', month!.month) }
    try {
      const parsed = await api.upload<Reading>(`/plants/${plantId}/ai/read/bill`, form)
      if (file) setCustom({ reading: parsed, image: URL.createObjectURL(file), label: file.name })
      else setReadByAi(parsed)
    } catch (e) {
      setReadError(e)
    } finally {
      setReading(false)
    }
  }

  const problems = result?.findings.filter((f) => f.tone === 'bad' || f.tone === 'warn') ?? []
  useAssistantContext('Bills & paperwork',
    bill ? `Looking at the ${label} electricity bill: ${fmt.money(Number(bill.total_amount), currency)} for ${Number(bill.kwh_total).toLocaleString()} kWh. MeterZero's checks found: ${problems.map((f) => f.title).join('; ') || 'nothing wrong'}.` : '',
    ['Explain this bill in plain words.', 'What should I say to the electricity supplier about this bill?', 'How do I bring the demand charge down?'])

  if (months.error) return <ErrorBox error={months.error} />
  if (!months.data) return <Loading label="Checking the bills…" />
  const totalPaid = list.reduce((s, m) => s + Number(m.reading.total_amount), 0)
  const recoverable = list.reduce((s, m) => s + m.recoverable, 0)
  const chart = list.map((m) => ({ label: monthName(m.month), amount: Number(m.reading.total_amount), perKwh: m.per_kwh }))

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle sub="Sample bills for the demo plant in its region (change it in Settings), already read so this works without AI. Click a month to check it."
          right={<Badge tone="sim">Sample bills</Badge>}>Six months of electricity bills</CardTitle>
        <div className="grid gap-6 xl:grid-cols-12">
          <div className="grid grid-cols-3 gap-4 xl:col-span-3 xl:grid-cols-1 xl:content-start">
            <Stat size="sm" label="Paid in six months" value={fmt.money(totalPaid, currency)} />
            <Stat size="sm" label="Bills with a problem" value={`${list.filter((m) => m.problems).length} of ${list.length}`} tone={recoverable ? 'bad' : 'ok'} />
            <Stat size="sm" label="Overcharged or avoidable" value={fmt.money(recoverable, currency)} tone={recoverable ? 'bad' : 'ok'}
              sub="billing errors and surcharges" />
          </div>
          <div className="h-56 xl:col-span-9">
            <ResponsiveContainer>
              <ComposedChart data={chart} margin={{ left: 4, right: 4 }}>
                <CartesianGrid stroke="#eef0f3" vertical={false} />
                <XAxis dataKey="label" {...AXIS} />
                <YAxis yAxisId="a" {...AXIS} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
                <YAxis yAxisId="r" orientation="right" {...AXIS} domain={['auto', 'auto']} tickFormatter={(v) => v.toFixed(1)} />
                <Tooltip contentStyle={TIP} formatter={(v, name) => (name === 'Amount' ? fmt.money(Number(v), currency) : `${currency}${Number(v).toFixed(2)} per kWh`)} />
                <Bar yAxisId="a" dataKey="amount" name="Amount" fill="#93b4f5" radius={[3, 3, 0, 0]} />
                <Line yAxisId="r" dataKey="perKwh" name="Cost per kWh" stroke="#1d4ed8" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[760px] text-[13.5px]">
            <thead className="text-left text-[12.5px] text-fg-3">
              <tr>
                <th className="py-2 pl-3 font-medium">Month</th><th className="py-2 text-right font-medium">Units</th>
                <th className="py-2 text-right font-medium">At peak price</th><th className="py-2 text-right font-medium">Max demand</th>
                <th className="py-2 text-right font-medium">Power factor</th><th className="py-2 text-right font-medium">Amount</th>
                <th className="py-2 text-right font-medium">Per kWh</th><th className="py-2 pr-3 text-right font-medium">Check</th>
              </tr>
            </thead>
            <tbody>
              {list.map((m) => {
                const active = !custom && m.month === month?.month
                return (
                  <tr key={m.month} onClick={() => pick(m.month)}
                    className={clsx('cursor-pointer border-t border-line transition', active ? 'bg-brand-soft' : 'hover:bg-subtle')}>
                    <td className={clsx('py-2.5 pl-3', active ? 'font-medium text-brand' : 'text-fg')}>{monthName(m.month)}</td>
                    <td className="num py-2.5 text-right text-fg">{Number(m.reading.kwh_total).toLocaleString()}</td>
                    <td className="num py-2.5 text-right text-fg-2">{fmt.pct(m.peak_share)}</td>
                    <td className="num py-2.5 text-right text-fg-2">{Number(m.reading.max_demand_kva).toFixed(0)} {m.reading.demand_unit ?? 'kVA'}</td>
                    <td className={clsx('num py-2.5 text-right', Number(m.reading.power_factor) < 0.9 ? 'font-medium text-red-600' : 'text-fg-2')}>
                      {Number(m.reading.power_factor) ? Number(m.reading.power_factor).toFixed(2) : '–'}
                    </td>
                    <td className="num py-2.5 text-right text-fg">{fmt.money(Number(m.reading.total_amount), m.currency)}</td>
                    <td className="num py-2.5 text-right text-fg-2">{m.per_kwh.toFixed(2)}</td>
                    <td className="py-2.5 pr-3 text-right">
                      {m.problems ? <Badge tone="bad">{fmt.money(m.recoverable, m.currency)} at stake</Badge> : <Badge tone="ok">OK</Badge>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-12">
        <Card className="xl:col-span-5">
          <CardTitle sub={custom ? 'Your photo' : 'Sample photo of this month\'s bill'}>{label}</CardTitle>
          <div className="overflow-hidden rounded-lg border border-line bg-subtle">
            <img src={custom?.image ?? month?.image} alt={`Electricity bill, ${label}`} className="max-h-[560px] w-full object-contain" />
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {!custom && (
              <Button variant="primary" loading={reading} disabled={!connected} onClick={() => readPhoto()}>
                {readByAi ? 'Read again with Gemini' : 'Read this photo with Gemini'}
              </Button>
            )}
            <label className={clsx('inline-flex cursor-pointer items-center rounded-lg border border-line-strong bg-surface px-4 py-2 text-[14px] font-medium text-fg hover:bg-subtle',
              (!connected || reading) && 'pointer-events-none opacity-50')}>
              Upload your own bill
              <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && readPhoto(e.target.files[0])} />
            </label>
            {custom && <Button variant="ghost" onClick={() => setCustom(null)}>Back to the samples</Button>}
          </div>
          <p className="mt-3 text-[13px] leading-relaxed text-fg-3">
            {!connected ? 'Reading photos needs a Gemini key (Settings). The sample bills are already read, so the checks work without it.'
              : readByAi ? 'Showing what Gemini read from the photo.' : 'Showing the sample\'s pre-read values. Read the photo to see Gemini do it.'}
          </p>
          {reading && <div className="mt-2 flex items-center gap-2 text-[13px] text-violet-700"><Spin /> Gemini is reading the bill…</div>}
          {readError ? <div className="mt-3"><ErrorBox error={readError} /></div> : null}
        </Card>

        <div className="space-y-4 xl:col-span-7">
          {error ? <ErrorBox error={error} /> : null}
          {bill && result ? (
            <>
              <Card>
                <CardTitle right={<Button size="sm" onClick={() => askAssistant(`Explain my ${label} electricity bill in plain words, and what I should do about it.`)}>Ask MeterZero about this bill</Button>}
                  sub={`${fmt.money(Number(bill.total_amount), currency)} for ${Number(bill.kwh_total).toLocaleString()} kWh over ${result.days} days`}>
                  Bill check
                </CardTitle>
                <div className="space-y-2.5">
                  {result.findings.map((f, i) => (
                    <div key={i} className={clsx('rounded-lg border border-l-4 border-line px-4 py-3', TONE[f.tone])}>
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <span className="font-medium text-fg">{f.title}</span>
                        <span className="text-[12px] font-medium text-fg-3">{TONE_LABEL[f.tone]}</span>
                      </div>
                      <p className="mt-1 text-[13.5px] leading-relaxed text-fg-2">{f.detail}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
                  <Button variant={result.applied ? 'secondary' : 'primary'} disabled={result.applied}
                    onClick={async () => setResult(await api.post<BillResult>(`/plants/${plantId}/bill?apply=true`, bill))}>
                    {result.applied ? 'Prices now come from this bill' : 'Use this bill\'s prices everywhere'}
                  </Button>
                  {!result.applied && <span className="text-[13px] text-fg-3">Every saving and cost in the app switches to these rates.</span>}
                </div>
              </Card>
              <div className="grid gap-4 2xl:grid-cols-2">
                <Card>
                  <CardTitle hint="Energy charges follow when each machine used power; the demand charge follows who ran at the busiest 15 minutes."
                    sub="What each machine cost on this bill">The bill by machine</CardTitle>
                  <SplitBars rows={result.by_machine.map((m) => ({ name: m.name, amount: m.amount, share: m.share, color: m.color }))} currency={currency} />
                </Card>
                <Card>
                  <CardTitle sub="Including energy that made nothing">The bill by product</CardTitle>
                  <SplitBars rows={result.by_product.map((p) => ({ name: p.name, amount: p.amount, share: p.share,
                    color: p.name === 'Made nothing' ? '#ef4444' : p.name.startsWith('Building') ? '#9ca3af' : '#2563eb' }))} currency={currency} />
                </Card>
              </div>
            </>
          ) : <Card><Loading label="Checking the bill…" /></Card>}
        </div>
      </div>
    </div>
  )
}

function SplitBars({ rows, currency }: { rows: { name: string; amount: number; share: number; color: string }[]; currency: string }) {
  const max = Math.max(...rows.map((r) => r.amount), 1)
  return (
    <div className="space-y-2.5">
      {rows.map((row) => (
        <div key={row.name}>
          <div className="flex items-baseline justify-between gap-3 text-[13.5px]">
            <span className="truncate text-fg">{row.name}</span>
            <span className="num shrink-0 text-fg">{fmt.money(row.amount, currency)} <span className="text-fg-4">{fmt.pct(row.share)}</span></span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full" style={{ width: `${(row.amount / max) * 100}%`, background: row.color }} />
          </div>
        </div>
      ))}
    </div>
  )
}
