import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { AiSteps, Evidence, Markdown } from '../components/ai'
import { NotTrained } from '../components/NotTrained'
import { Badge, Button, Card, CardTitle, ErrorBox, Field, Loading, Page, PageHeader, Select, Stat } from '../components/ui'
import { AXIS, TIP } from '../lib/chart'
import { api } from '../lib/api'
import { useAssistantContext } from '../lib/assistant'
import { BAND_COLOR, fmt } from '../lib/format'
import { usePlant } from '../lib/plant'
import type { Prices, Repair, ShiftPlan, ToolCall } from '../lib/types'
import { useAiRun, useAiStatus } from '../lib/useAi'
import { useAsync } from '../lib/useAsync'
import { BeforeAfter } from './Savings'

const FIND_BEST = 'Find the cheapest change to this week\'s production schedule. Try at least five options with ' +
  'plan_schedule_shift (different lines and products, earlier and later, 1-6 hours). Reject options that clash with other ' +
  'batches. Compare the best one with fixing any waste alerts (plan_fix_waste). Recommend what to do first, with the monthly ' +
  'saving and its likely range, and the practical catch. Write for a plant manager: short, plain words.'

export default function WhatIf() {
  const { plant, plantId, untrained } = usePlant()
  const prices = useAsync(() => api.get<Prices>(`/plants/${plantId}/prices`), [plantId])
  const repairs = useAsync(() => api.get<Repair[]>(`/plants/${plantId}/repairs`), [plantId])
  const lines = plant?.spec.lines ?? []
  const [line, setLine] = useState('')
  const [product, setProduct] = useState('')
  const [hours, setHours] = useState(-2)
  const [plan, setPlan] = useState<ShiftPlan | null>(null)
  const [planError, setPlanError] = useState<unknown>(null)
  const chosenLine = line || lines[lines.length - 1]?.id || ''

  useEffect(() => {
    if (!chosenLine || hours === 0) return
    const timer = setTimeout(() => {
      api.get<ShiftPlan>(`/plants/${plantId}/shift?line=${chosenLine}&hours=${hours}&product=${encodeURIComponent(product)}`)
        .then((p) => { setPlan(p); setPlanError(null) }).catch(setPlanError)
    }, 180)
    return () => clearTimeout(timer)
  }, [plantId, chosenLine, product, hours, prices.data])

  useAssistantContext('What if', plan ? `Trying: ${plan.change}, which would change the bill by ${fmt.money(plan.monthly_saving, prices.data?.currency ?? '')} a month.` : '',
    ['What is the catch with this change?', 'Is there a better change than this one?', 'How do I explain this change to the shift supervisors?'])

  if (untrained) return <NotTrained />
  if (!plant || !prices.data) return <Loading />
  const currency = prices.data.currency
  const peak = prices.data.bands.find((b) => b.name === 'peak')

  return (
    <Page>
      <PageHeader title="What if" subtitle="Try a change before you make it: move a production line earlier or later, or fix a machine, and see what it does to the bill." />

      <div className="grid gap-4 xl:grid-cols-12">
        <Card className="xl:col-span-8">
          <CardTitle sub="Pick a line and drag the slider">Move a production line</CardTitle>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Line">
              <Select value={chosenLine} onChange={(e) => { setLine(e.target.value); setProduct('') }}>
                {lines.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.id})</option>)}
              </Select>
            </Field>
            <Field label="Product">
              <Select value={product} onChange={(e) => setProduct(e.target.value)}>
                <option value="">All products</option>
                {lines.find((l) => l.id === chosenLine)?.products.map((p) => <option key={p.name}>{p.name}</option>)}
              </Select>
            </Field>
            <Field label={hours === 0 ? 'No change' : `${Math.abs(hours)} hour${Math.abs(hours) === 1 ? '' : 's'} ${hours < 0 ? 'earlier' : 'later'}`}>
              <input type="range" min={-6} max={6} step={0.5} value={hours} onChange={(e) => setHours(Number(e.target.value))}
                className="mt-2.5 w-full accent-[#0c304a]" />
              <div className="mt-1 flex justify-between text-[12px] text-fg-4"><span>6 h earlier</span><span>6 h later</span></div>
            </Field>
          </div>
          {planError ? <div className="mt-4"><ErrorBox error={planError} /></div> : null}
          {plan && hours !== 0 && (
            <>
              <div className="mt-5 rounded-lg border border-line bg-subtle px-4 py-3 text-[15px] leading-relaxed text-fg">
                {plan.change.replace('Start', 'Starting')} would {plan.monthly_saving >= 0 ? 'save about' : 'cost about'}{' '}
                <b className={plan.monthly_saving >= 0 ? 'font-semibold text-emerald-700' : 'font-semibold text-red-700'}>{fmt.money(Math.abs(plan.monthly_saving), currency)} a month</b>
                {plan.monthly_saving >= 0 && <span className="text-fg-3"> (likely {fmt.range(plan.monthly_saving, plan.monthly_saving_plus_minus_90pct, currency)})</span>}.
              </div>
              <div className="mt-4 grid grid-cols-3 gap-4">
                <Stat size="sm" label="Highest demand" value={fmt.kw(plan.peak_kw_after, 0)} sub={`was ${fmt.kw(plan.peak_kw_before, 0)}`} />
                <Stat size="sm" label="Clashes" value={plan.batches_that_clash_with_other_batches || 'None'} tone={plan.batches_that_clash_with_other_batches ? 'bad' : 'ok'}
                  sub="batches overlapping on a line" />
                <Stat size="sm" label="Outside hours" value={plan.batches_needing_staff_outside_current_hours} sub="batches needing staff" />
              </div>
              <div className="mt-5"><BeforeAfter plan={plan} /></div>
            </>
          )}
        </Card>

        <div className="space-y-4 xl:col-span-4">
          <Card>
            <CardTitle sub="Machines using energy they shouldn't">Repairs</CardTitle>
            {repairs.data?.length === 0 && <div className="text-[14px] text-fg-2">Nothing to repair.</div>}
            <div className="divide-y divide-line">
              {repairs.data?.map((r) => (
                <div key={r.machine} className="py-3 first:pt-0 last:pb-0">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-medium text-fg">Fix the {r.name.toLowerCase()}</span>
                    <span className="num font-semibold text-emerald-700">{fmt.money(r.monthly_saving, r.currency)}<span className="text-[12px] font-normal text-fg-3"> /mo</span></span>
                  </div>
                  <div className="mt-1 text-[13.5px] text-fg-2">{r.excess_kw} kW extra, day and night. {fmt.money(r.yearly_saving, r.currency)} a year.</div>
                </div>
              ))}
            </div>
          </Card>
          <Card>
            <CardTitle right={<Link to={`/p/${plantId}/settings`} className="text-[13px] font-medium text-brand hover:underline">Change</Link>}>Prices used</CardTitle>
            <div className="space-y-2">
              {prices.data.bands.map((b) => (
                <div key={b.name} className="flex items-center justify-between text-[14px]">
                  <span className="flex items-center gap-2 capitalize text-fg"><span className="h-2 w-2 rounded-full" style={{ background: BAND_COLOR[b.name] }} />{b.name}
                    <span className="num text-[12.5px] text-fg-4">{fmt.hours(b.start, b.end)}</span></span>
                  <span className="num text-fg">{currency}{b.price.toFixed(2)} /kWh</span>
                </div>
              ))}
              <div className="flex items-center justify-between border-t border-line pt-2 text-[14px]">
                <span className="text-fg">Demand charge</span>
                <span className="num text-fg">{currency}{prices.data.demand_charge} /kW</span>
              </div>
            </div>
          </Card>
        </div>

        <Card className="xl:col-span-12">
          <CardTitle hint="Average power for each hour, coloured by the price band you pay then." sub="Average power each hour, coloured by price">When the plant uses electricity</CardTitle>
          <div className="mb-4 grid grid-cols-3 gap-4">
            <Stat size="sm" label="Monthly bill" value={fmt.money(prices.data.monthly_bill, currency)} />
            <Stat size="sm" label="Bought at the peak price" value={fmt.pct(peak?.share ?? 0)} tone="bad" />
            <Stat size="sm" label="Demand charge" value={fmt.money(prices.data.demand_cost, currency)} sub={`for ${fmt.kw(prices.data.peak_kw, 0)} at the busiest moment`} />
          </div>
          <div className="h-60">
            <ResponsiveContainer>
              <BarChart data={prices.data.hourly_kw.map((kw, h) => ({ h: String(h).padStart(2, '0'), kw }))} margin={{ left: -14 }}>
                <CartesianGrid stroke="#eef0f3" vertical={false} />
                <XAxis dataKey="h" {...AXIS} />
                <YAxis {...AXIS} unit=" kW" />
                <Tooltip contentStyle={TIP} formatter={(v) => `${v} kW`} labelFormatter={(h) => `${h}:00`} />
                <Bar dataKey="kw" radius={[3, 3, 0, 0]}>
                  {prices.data.hourly_kw.map((_, h) => {
                    const band = prices.data!.bands.find((b) => (b.start < b.end ? h >= b.start && h < b.end : h >= b.start || h < b.end))
                    return <Cell key={h} fill={BAND_COLOR[band?.name ?? 'normal'] ?? '#9ca3af'} fillOpacity={0.75} />
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <BestChange plantId={plantId} />
      </div>
    </Page>
  )
}

function BestChange({ plantId }: { plantId: string }) {
  const connected = useAiStatus()
  const ai = useAiRun<{ text: string; tool_calls: ToolCall[] }>()
  return (
    <Card className="xl:col-span-12">
      <CardTitle right={<Badge tone="ai">Gemini</Badge>} sub="It tries many changes, drops the ones that clash with production, and recommends one">
        Let Gemini find the best change
      </CardTitle>
      <div className="flex flex-wrap items-center gap-3">
        <Button loading={ai.running} disabled={!connected}
          onClick={() => ai.run(`/plants/${plantId}/ai/ask`, { question: FIND_BEST, conversation: `whatif-${Date.now()}` })}>
          Find the best change
        </Button>
        {!connected && <span className="text-[13px] text-fg-3">Needs a Gemini key: add one in <Link to={`/p/${plantId}/settings`} className="text-brand hover:underline">Settings</Link> to use this.</span>}
      </div>
      {ai.error && <div className="mt-3"><ErrorBox error={ai.error} /></div>}
      {(ai.running || ai.steps.length > 0) && <div className="mt-4"><AiSteps steps={ai.steps} running={ai.running} title="Trying different schedules" /></div>}
      {ai.result && (
        <div className="mt-4 max-w-4xl">
          <Markdown>{ai.result.text}</Markdown>
          <Evidence calls={ai.result.tool_calls} />
        </div>
      )}
    </Card>
  )
}
