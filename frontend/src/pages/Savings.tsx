import { type ReactNode, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { AiSteps, Evidence, Markdown, SavedNote } from '../components/ai'
import { NotTrained } from '../components/NotTrained'
import { Badge, Button, Card, CardTitle, ErrorBox, Loading, Page, PageHeader } from '../components/ui'
import { AXIS, TIP } from '../lib/chart'
import { api } from '../lib/api'
import { useAssistantContext } from '../lib/assistant'
import { fmt } from '../lib/format'
import { usePlant } from '../lib/plant'
import type { Accuracy, Action, Finding, Overview, ShiftPlan, ToolCall } from '../lib/types'
import { useAiRun, useAiStatus } from '../lib/useAi'
import { useAsync } from '../lib/useAsync'

interface Review { report: string; findings: { headline: string; findings: Finding[] }; tool_calls: ToolCall[] }
const SURE: Record<string, string> = { high: 'Very likely', medium: 'Fairly likely', low: 'Worth checking' }
const KIND: Record<string, string> = { waste: 'Waste', repair: 'Repair', schedule: 'Schedule', sensor: 'Metering' }

export default function Savings() {
  const { plantId, untrained } = usePlant()
  const connected = useAiStatus()
  const ai = useAiRun<Review & { type: string }>()
  const [saved, setSaved] = useState<{ payload: Review; recorded_at: string } | null>(null)
  const overview = useAsync(() => api.get<Overview>(`/plants/${plantId}/overview`), [plantId])
  const currency = overview.data?.kpis.currency ?? '$'

  useEffect(() => {
    api.get<{ payload: Review; recorded_at: string }>(`/plants/${plantId}/ai/saved/investigation`).then(setSaved).catch(() => setSaved(null))
  }, [plantId, ai.result])

  useAssistantContext('Find savings', 'Looking at the ways to save money this week.',
    ['Which of these savings is the easiest to do?', 'What would all of these save in a year?', 'Write a repair request for the biggest problem.'])

  if (untrained) return <NotTrained />
  const review: Review | null = ai.result ?? saved?.payload ?? null
  const total = overview.data?.actions.reduce((s, a) => s + a.monthly_saving, 0) ?? 0

  return (
    <Page>
      <PageHeader title="Find savings"
        subtitle="MeterZero ranks what to fix from the numbers alone. Gemini then audits the week like an energy consultant: it checks prices, tries alternatives, drops ideas that clash with production and shows its evidence."
        actions={<Button variant="primary" loading={ai.running} disabled={!connected} onClick={() => ai.run(`/plants/${plantId}/ai/review`)}>
          {review ? 'Run the Gemini review again' : 'Run a Gemini review'}
        </Button>} />

      {connected === false && (
        <div className="mb-4 rounded-lg border border-line bg-surface px-4 py-3 text-[14px] text-fg-2">
          The AI review needs a Gemini key. <Link to={`/p/${plantId}/settings`} className="font-medium text-brand hover:underline">Add a key in Settings</Link>.
          Everything below works without it.
        </div>
      )}
      {ai.error && <div className="mb-4"><ErrorBox error={ai.error} /></div>}
      {(ai.running || ai.steps.length > 0) && <div className="mb-4"><AiSteps steps={ai.steps} running={ai.running} title="Reviewing the week" /></div>}

      {review && !ai.running ? (
        <div className="space-y-4">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Badge tone="ai">Gemini review</Badge>
              {!ai.result && saved && <SavedNote when={saved.recorded_at} />}
            </div>
            <p className="mt-3 text-[17px] leading-relaxed text-fg">{review.findings.headline}</p>
          </Card>
          <div className="grid gap-4 2xl:grid-cols-2">
            {review.findings.findings.map((finding, i) => (
              <Item key={i} n={i + 1} kind={finding.kind} title={finding.title} saving={finding.monthly_saving} plusMinus={finding.saving_plus_minus}
                currency={currency} badge={<Badge tone={finding.confidence === 'high' ? 'ok' : finding.confidence === 'medium' ? 'warn' : 'default'}>{SURE[finding.confidence] ?? finding.confidence}</Badge>}
                body={<>
                  <p><b className="font-medium text-fg">Why:</b> {finding.evidence}</p>
                  <p className="mt-1"><b className="font-medium text-fg">What to do:</b> {finding.action}</p>
                </>}>
                {finding.kind === 'waste' && finding.machine && <NightChart plantId={plantId} machine={finding.machine} />}
                {finding.kind === 'schedule' && <ReviewShiftChart plantId={plantId} calls={review.tool_calls} />}
                {finding.kind === 'sensor' && <SensorChart plantId={plantId} />}
              </Item>
            ))}
          </div>
          <Card>
            <CardTitle>The full written review</CardTitle>
            <div className="max-w-4xl"><Markdown>{review.report}</Markdown></div>
            <Evidence calls={review.tool_calls} />
          </Card>
        </div>
      ) : !ai.running && (
        overview.data ? (
          <>
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-[16px] font-semibold text-fg">What MeterZero found on its own</h2>
              <span className="text-[14px] text-fg-2">Together worth about <b className="num font-semibold text-emerald-700">{fmt.money(total, currency)} a month</b></span>
            </div>
            <div className="grid gap-4 2xl:grid-cols-2">
              {overview.data.actions.map((action, i) => (
                <Item key={i} n={i + 1} kind={action.kind} title={action.title} saving={action.monthly_saving} plusMinus={action.plus_minus}
                  currency={currency} body={<p>{action.why}</p>}>
                  <ActionChart plantId={plantId} action={action} />
                </Item>
              ))}
            </div>
          </>
        ) : <Loading />
      )}
    </Page>
  )
}

function Item({ n, kind, title, saving, plusMinus, currency, badge, body, children }: {
  n: number; kind: string; title: string; saving: number; plusMinus: number; currency: string
  badge?: ReactNode; body: ReactNode; children?: ReactNode
}) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] font-medium text-fg-3">{n}. {KIND[kind] ?? kind}</div>
          <h3 className="mt-0.5 text-[16px] font-semibold text-fg">{title}</h3>
          <div className="mt-1.5 max-w-3xl text-[14px] leading-relaxed text-fg-2">{body}</div>
        </div>
        <div className="text-right">
          {saving > 0 ? (
            <>
              <div className="num text-[22px] font-semibold text-emerald-700">{fmt.money(saving, currency)}<span className="text-[12px] font-normal text-fg-3"> /mo</span></div>
              {plusMinus > 0 && <div className="num text-[12px] text-fg-3">likely {fmt.range(saving, plusMinus, currency)}</div>}
            </>
          ) : <div className="text-[13px] text-brand">Better accuracy</div>}
          {badge && <div className="mt-2">{badge}</div>}
        </div>
      </div>
      {children && <div className="mt-4 border-t border-line pt-4">{children}</div>}
    </Card>
  )
}

function ActionChart({ plantId, action }: { plantId: string; action: Action }) {
  if (action.kind === 'repair') return <NightChart plantId={plantId} machine={action.machine} />
  if (action.kind === 'schedule' && action.shift) return <ShiftChart plantId={plantId} line={action.shift.line} hours={action.shift.hours} />
  if (action.kind === 'sensor') return <SensorChart plantId={plantId} />
  return null
}

function NightChart({ plantId, machine }: { plantId: string; machine: string }) {
  const { data } = useAsync(() => api.get<{ night: string; estimated: number; actual: number | null; period: string }[]>(
    `/plants/${plantId}/overnight/${machine}`), [plantId, machine])
  if (!data?.length) return null
  const usual = data.filter((d) => d.period === 'validation').map((d) => d.estimated)
  const top = Math.max(...usual, 0.5) * 1.25
  return (
    <div>
      <div className="mb-2 text-[13px] text-fg-3">Power used between 11 pm and 5 am, night by night</div>
      <div className="h-48">
        <ResponsiveContainer>
          <ComposedChart data={data.map((d) => ({ ...d, label: fmt.day(d.night) }))} margin={{ left: -14, right: 8 }}>
            <CartesianGrid stroke="#eef0f3" vertical={false} />
            <XAxis dataKey="label" {...AXIS} />
            <YAxis {...AXIS} unit=" kW" />
            <ReferenceArea y1={0} y2={top} fill="#16a34a" fillOpacity={0.06} label={{ value: 'normal', fill: '#15803d', fontSize: 12, position: 'insideTopLeft' }} />
            <Tooltip contentStyle={TIP} />
            <Line dataKey="estimated" name="MeterZero" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
            <Line dataKey="actual" name="Hidden meter (check)" stroke="#d97706" strokeDasharray="4 3" dot={{ r: 2 }} connectNulls isAnimationActive={false} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function ShiftChart({ plantId, line, hours }: { plantId: string; line: string; hours: number }) {
  const { data } = useAsync(() => api.get<ShiftPlan>(`/plants/${plantId}/shift?line=${line}&hours=${hours}`), [plantId, line, hours])
  return data ? <BeforeAfter plan={data} /> : null
}

function ReviewShiftChart({ plantId, calls }: { plantId: string; calls: ToolCall[] }) {
  const shifts = calls.filter((c) => c.tool === 'plan_schedule_shift' && !(c.result as { error?: string })?.error)
  const clean = shifts.filter((c) => (c.result as ShiftPlan).batches_that_clash_with_other_batches === 0)
  const best = [...(clean.length ? clean : shifts)].sort((a, b) => (b.result as ShiftPlan).monthly_saving - (a.result as ShiftPlan).monthly_saving)[0]
  const args = (best?.args ?? {}) as { line?: string; hours?: number; product?: string }
  const { data } = useAsync(
    () => (best ? api.get<ShiftPlan>(`/plants/${plantId}/shift?line=${args.line}&hours=${args.hours}&product=${encodeURIComponent(args.product ?? '')}`) : Promise.resolve(null)),
    [plantId, args.line, args.hours, args.product],
  )
  return data ? <BeforeAfter plan={data} /> : null
}

export function BeforeAfter({ plan }: { plan: ShiftPlan }) {
  const rows = plan.before.map((v, h) => ({ hour: `${String(h).padStart(2, '0')}`, now: v, after: plan.after[h] }))
  return (
    <div>
      <div className="mb-2 text-[13px] text-fg-3">An average day, now and after “{plan.change}”. Red hours are the most expensive, green the cheapest.</div>
      <div className="h-52">
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ left: -14, right: 8 }}>
            <CartesianGrid stroke="#eef0f3" vertical={false} />
            <ReferenceArea x1="17" x2="22" fill="#dc2626" fillOpacity={0.06} />
            <ReferenceArea x1="00" x2="04" fill="#16a34a" fillOpacity={0.06} />
            <XAxis dataKey="hour" {...AXIS} />
            <YAxis {...AXIS} unit=" kW" />
            <Tooltip contentStyle={TIP} />
            <Area dataKey="now" name="Now" stroke="#9ca3af" strokeDasharray="4 3" fill="none" isAnimationActive={false} />
            <Area dataKey="after" name="After the change" stroke="#2563eb" strokeWidth={2} fill="#2563eb" fillOpacity={0.08} isAnimationActive={false} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function SensorChart({ plantId }: { plantId: string }) {
  const { data } = useAsync(() => api.get<Accuracy>(`/plants/${plantId}/accuracy`), [plantId])
  if (!data) return null
  return (
    <div>
      <div className="mb-2 text-[13px] text-fg-3">Accuracy as meters are added, in MeterZero's order and at random</div>
      <div className="h-48">
        <ResponsiveContainer>
          <BarChart data={data.budget.map((b) => ({ ...b, label: b.sensors === 0 ? 'Meter only' : `+${b.added}` }))} margin={{ left: -14 }}>
            <CartesianGrid stroke="#eef0f3" vertical={false} />
            <XAxis dataKey="label" {...AXIS} tick={{ ...AXIS.tick, fontSize: 11 }} interval={0} />
            <YAxis domain={[0.7, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} {...AXIS} />
            <Tooltip contentStyle={TIP} formatter={(v) => fmt.pct(Number(v), 1)} />
            <Bar dataKey="recommended" name="In MeterZero's order" fill="#2563eb" radius={[3, 3, 0, 0]} />
            <Bar dataKey="random" name="At random" fill="#d1d5db" radius={[3, 3, 0, 0]} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
