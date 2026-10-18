import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'
import { Layer, Rectangle, ResponsiveContainer, Sankey, Tooltip } from 'recharts'

import { NotTrained } from '../components/NotTrained'
import { Arrow, Badge, Button, Card, CardTitle, Dot, ErrorBox, Loading, Page, PageHeader, Segmented, Select, Stat, StatStrip } from '../components/ui'
import { TIP } from '../lib/chart'
import { api } from '../lib/api'
import { useAssistantContext } from '../lib/assistant'
import { fmt } from '../lib/format'
import { usePlant } from '../lib/plant'
import type { Overview as OverviewData } from '../lib/types'
import { useAsync } from '../lib/useAsync'

const FlowScene = lazy(() => import('../twin/FlowScene').then((m) => ({ default: m.FlowScene })))

const ACTION_LINK: Record<string, string> = { repair: 'twin', schedule: 'whatif', sensor: 'accuracy' }
const ACTION_KIND: Record<string, string> = { repair: 'Repair', schedule: 'Schedule', sensor: 'Metering' }

export default function Overview() {
  const { plantId, untrained } = usePlant()
  const [day, setDay] = useState<string | null>(null)
  const [flowView, setFlowView] = useState<'live' | 'chart'>('live')
  const { data, error, loading } = useAsync(
    () => api.get<OverviewData>(`/plants/${plantId}/overview${day ? `?day=${day}` : ''}`), [plantId, day])
  const saving = data?.actions.reduce((sum, a) => sum + a.monthly_saving, 0) ?? 0

  useAssistantContext('Overview', data
    ? `This week the plant used ${fmt.kwh(data.kpis.energy_kwh)}, about ${fmt.money(data.kpis.monthly_bill, data.kpis.currency)} a month. The top action is: ${data.actions[0]?.title ?? 'none'}.`
    : '', ['What should I do first, and why?', 'Why is so much energy used when nothing is made?', 'Summarise this week in three lines.'])

  if (untrained) return <NotTrained />
  if (error) return <Page><ErrorBox error={error} /></Page>
  if (loading && !data) return <Loading label="Working out the week…" />
  if (!data) return null
  const { kpis } = data
  const currency = kpis.currency

  return (
    <Page>
      <PageHeader
        title={data.name}
        badges={<Badge tone="sim">Simulation</Badge>}
        subtitle={<>This week the plant used <b className="font-semibold text-fg">{fmt.kwh(kpis.energy_kwh)}</b>, about <b className="font-semibold text-fg">{fmt.money(kpis.monthly_bill, currency)} a month</b>. MeterZero found ways to save about <b className="font-semibold text-emerald-700">{fmt.money(saving, currency)} a month</b>.</>}
        actions={<>
          <Link to={`/p/${plantId}/twin`}><Button>Open digital twin</Button></Link>
          <Link to={`/p/${plantId}/savings`}><Button variant="primary">Review with Gemini</Button></Link>
        </>}
      />

      <StatStrip>
        <Stat label="Electricity this week" value={fmt.kwh(kpis.energy_kwh)} sub={`Highest demand ${fmt.kw(kpis.peak_kw, 0)}`}
          hint="Everything the main meter recorded during the week shown." />
        <Stat label="Monthly bill" value={fmt.money(kpis.monthly_bill, currency)} sub="Priced by time of day"
          hint="This week scaled to a month, at the plant's electricity prices, plus the demand charge." />
        <Stat label="Made nothing" value={fmt.pct(kpis.idle_share)} sub={`${fmt.kwh(kpis.idle_kwh)} on warm-ups, idling, nights`} tone="bad"
          hint="Energy the machines used outside any batch." />
        <Stat label="Accuracy from one meter" value={fmt.pct(kpis.accuracy)} sub={`${fmt.pct(kpis.accuracy_with_sensors)} with ${kpis.sensors_needed} extra meter${kpis.sensors_needed === 1 ? '' : 's'}`}
          hint="Checked against hidden meters on days MeterZero never saw." />
      </StatStrip>

      <div className="mt-4 grid gap-4 xl:grid-cols-12">
        <Card className="xl:col-span-7">
          <CardTitle hint="Ranked by money. Straight from the numbers, no AI needed." sub="Ranked by what it's worth each month">What to do first</CardTitle>
          <div className="divide-y divide-line rounded-lg border border-line">
            {data.actions.map((action, i) => (
              <Link key={i} to={`/p/${plantId}/${ACTION_LINK[action.kind] ?? 'overview'}`}
                className="group flex items-center gap-4 px-4 py-3.5 transition hover:bg-subtle">
                <span className="num grid h-7 w-7 shrink-0 place-items-center rounded-full bg-muted text-[13px] font-semibold text-fg-2">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-fg">{action.title}</span>
                    <span className="text-[12px] text-fg-4">{ACTION_KIND[action.kind] ?? ''}</span>
                  </div>
                  <div className="mt-0.5 text-[13.5px] leading-snug text-fg-2">{action.why}</div>
                </div>
                <div className="shrink-0 text-right">
                  {action.monthly_saving > 0 ? (
                    <>
                      <div className="num text-[17px] font-semibold text-emerald-700">{fmt.money(action.monthly_saving, currency)}<span className="text-[12px] font-normal text-fg-3"> /mo</span></div>
                      <div className="num text-[12px] text-fg-3">likely {fmt.range(action.monthly_saving, action.plus_minus, currency)}</div>
                    </>
                  ) : <span className="text-[13px] text-brand">Better accuracy</span>}
                </div>
                <Arrow />
              </Link>
            ))}
          </div>
        </Card>

        <div className="space-y-4 xl:col-span-5">
          <Card>
            <CardTitle hint="Read this first each day."
              right={<Select value={data.morning.day} onChange={(e) => setDay(e.target.value)} className="!w-auto !py-1.5 text-[13px]">
                {data.morning.days.map((d) => <option key={d} value={d}>{fmt.day(d)}</option>)}
              </Select>}>Morning check</CardTitle>
            <ul className="space-y-2.5">
              {data.morning.lines.map((line, i) => (
                <li key={i} className="flex gap-3 text-[14px] leading-relaxed text-fg">
                  <span className="mt-2"><Dot color={line.good === null ? '#9ca3af' : line.good ? '#16a34a' : '#dc2626'} /></span>
                  {line.text}
                </li>
              ))}
            </ul>
          </Card>
          <Card>
            <CardTitle right={<Badge tone="ai">Gemini</Badge>}>The AI's take</CardTitle>
            {data.review ? (
              <>
                <p className="text-[14px] leading-relaxed text-fg">{data.review.headline}</p>
                <div className="mt-3 flex items-center justify-between">
                  <span className="text-[12px] text-fg-4">Reviewed {data.review.recorded_at}</span>
                  <Link to={`/p/${plantId}/savings`} className="text-[13.5px] font-medium text-brand hover:underline">Read the review</Link>
                </div>
              </>
            ) : (
              <p className="text-[14px] text-fg-2">
                Gemini hasn't reviewed this week yet. <Link to={`/p/${plantId}/savings`} className="font-medium text-brand hover:underline">Run a review</Link>
              </p>
            )}
          </Card>
        </div>

        <Card className="xl:col-span-8">
          <CardTitle hint="From the main meter, to each machine, to what it made. Hover any stream for its size."
            sub="From the main meter, through each machine, to each product"
            right={<Segmented value={flowView} onChange={setFlowView} options={[{ value: 'live', label: '3D flow' }, { value: 'chart', label: 'Chart' }]} />}>
            Where every kWh went
          </CardTitle>
          {flowView === 'live' ? (
            <Suspense fallback={<div className="h-[460px]"><Loading label="Drawing the flow…" /></div>}>
              <FlowScene data={data.flows} className="h-[340px] overflow-hidden rounded-lg md:h-[460px]" />
            </Suspense>
          ) : <EnergyFlow flows={data.flows} />}
        </Card>

        <Card className="xl:col-span-4">
          <CardTitle hint="Each machine's share of the week, with a likely range." sub="This week, with a likely range">Energy by machine</CardTitle>
          <div className="space-y-3">
            {[...data.machines].sort((a, b) => b.kwh - a.kwh).map((m) => (
              <div key={m.id}>
                <div className="flex items-baseline justify-between gap-3 text-[13.5px]">
                  <span className="truncate text-fg">{m.name}</span>
                  <span className="num shrink-0 text-fg-2">{fmt.kwh(m.kwh)} <span className="text-fg-4">± {m.plus_minus}</span></span>
                </div>
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full" style={{ width: `${Math.min(m.share * 250, 100)}%`, background: m.color }} />
                  </div>
                  <span className="num w-10 text-right text-[12px] text-fg-3">{fmt.pct(m.share)}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </Page>
  )
}

function EnergyFlow({ flows }: { flows: OverviewData['flows'] }) {
  return (
    <div className="h-[460px]">
      <ResponsiveContainer>
        <Sankey data={flows} nodePadding={14} nodeWidth={10} margin={{ top: 10, right: 150, bottom: 10, left: 10 }} iterations={64}
          node={<FlowNode nodes={flows.nodes} />} link={<FlowLink nodes={flows.nodes} />}>
          <Tooltip contentStyle={TIP} formatter={(v) => `${Math.round(Number(v)).toLocaleString()} kWh`} />
        </Sankey>
      </ResponsiveContainer>
    </div>
  )
}

// recharts passes layout props to custom nodes and links
/* eslint-disable @typescript-eslint/no-explicit-any */
function FlowNode({ x, y, width, height, index, payload, nodes }: any) {
  const node = nodes[index] ?? payload
  return (
    <Layer>
      <Rectangle x={x} y={y} width={width} height={height} fill={node.color} radius={2} />
      <text x={x + width + 8} y={y + height / 2} dy={4} fontSize={12.5} fill={node.kind === 'waste' ? '#b91c1c' : '#374151'}>
        {node.name}
      </text>
    </Layer>
  )
}

function FlowLink({ sourceX, sourceY, sourceControlX, targetX, targetY, targetControlX, linkWidth, payload, nodes }: any) {
  const target = nodes.find((n: any) => n.name === payload?.target?.name)
  const source = nodes.find((n: any) => n.name === payload?.source?.name)
  const color = target?.kind === 'waste' ? '#ef4444' : source?.kind === 'meter' ? target?.color : source?.color
  return (
    <path d={`M${sourceX},${sourceY} C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
      fill="none" stroke={color ?? '#64748b'} strokeOpacity={target?.kind === 'waste' ? 0.4 : 0.25} strokeWidth={Math.max(linkWidth, 1)} />
  )
}
