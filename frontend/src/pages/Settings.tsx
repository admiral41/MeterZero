import { useState } from 'react'

import { Badge, Button, Card, CardTitle, Field, Input, Loading, Page, PageHeader } from '../components/ui'
import clsx from 'clsx'

import { api, geminiKey, setGeminiKey } from '../lib/api'
import { BAND_COLOR, fmt, setLocale } from '../lib/format'
import { resetTour } from '../lib/tour'
import { usePlant } from '../lib/plant'
import type { Prices } from '../lib/types'
import { useAiStatus } from '../lib/useAi'
import { useAsync } from '../lib/useAsync'


export default function Settings() {
  const { plantId, plant } = usePlant()
  const prices = useAsync(() => api.get<Prices>(`/plants/${plantId}/prices`), [plantId])
  return (
    <Page>
      <PageHeader title="Settings" subtitle="Where the plant is, how its electricity is priced, and the Gemini connection." />
      <div className="grid gap-4 xl:grid-cols-2">
        {prices.data && <RegionCard key={prices.data.region} plantId={plantId} current={prices.data.region} onChanged={prices.reload} />}
        <GeminiCard />
        {prices.data ? <PricesCard key={JSON.stringify(prices.data.bands) + prices.data.demand_charge} plantId={plantId} plantName={plant?.spec.name ?? plantId} prices={prices.data} onSaved={prices.reload} />
          : <Card><Loading /></Card>}
        <Card>
          <CardTitle>Welcome guide</CardTitle>
          <p className="text-[14px] leading-relaxed text-fg-2">The six-step introduction shown on first visit.</p>
          <Button className="mt-4" onClick={() => { resetTour(); window.location.reload() }}>
            Show it again
          </Button>
        </Card>
        <Card>
          <CardTitle>About this data</CardTitle>
          <p className="text-[14px] leading-relaxed text-fg-2">
            The demo plants are simulated, with a hidden meter on every machine so each figure can be checked. Bills and logbook pages
            in the samples are clearly marked examples, not real documents.
          </p>
        </Card>
      </div>
    </Page>
  )
}

function GeminiCard() {
  const connected = useAiStatus()
  const [key, setKey] = useState(geminiKey())
  const [saved, setSaved] = useState(false)
  return (
    <Card>
      <CardTitle right={<Badge tone={connected ? 'ok' : 'default'}>{connected ? 'Connected' : 'Not connected'}</Badge>}>Gemini</CardTitle>
      <p className="text-[14px] leading-relaxed text-fg-2">
        The AI features use Google Gemini. Paste your own API key, or run the server with <code className="rounded bg-subtle px-1.5 py-0.5 text-[12.5px]">GEMINI_API_KEY</code> set.
        Your key stays in this browser and is only sent to your own MeterZero server.
      </p>
      <div className="mt-4">
        <Field label="Gemini API key">
          <Input type="password" value={key} onChange={(e) => { setKey(e.target.value); setSaved(false) }} placeholder="Paste a key from Google AI Studio" />
        </Field>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={() => { setGeminiKey(key.trim()); setSaved(true) }}>Save key</Button>
        {geminiKey() && <Button variant="ghost" onClick={() => { setGeminiKey(''); setKey(''); setSaved(false) }}>Forget key</Button>}
        {saved && <span className="text-[13px] text-emerald-700">Saved.</span>}
        <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" className="ml-auto text-[13px] text-brand hover:underline">
          Get a free key from Google AI Studio
        </a>
      </div>
    </Card>
  )
}

function PricesCard({ plantId, plantName, prices, onSaved }: { plantId: string; plantName: string; prices: Prices; onSaved: () => void }) {
  const [draft, setDraft] = useState(prices)
  const [saving, setSaving] = useState(false)
  const band = (i: number, patch: Partial<Prices['bands'][number]>) =>
    setDraft({ ...draft, bands: draft.bands.map((x, j) => (j === i ? { ...x, ...patch } : x)) })
  const save = async () => {
    setSaving(true)
    await api.put(`/plants/${plantId}/prices`, {
      bands: draft.bands.map((b) => [b.name, b.start, b.end, b.price]), demand_charge: draft.demand_charge, currency: draft.currency,
    })
    setSaving(false)
    onSaved()
  }
  return (
    <Card>
      <CardTitle sub={`For ${plantName}. Loading a bill on Bills & paperwork fills these in for you.`}>Electricity prices</CardTitle>
      <table className="w-full text-[13.5px]">
        <thead className="text-left text-[12.5px] text-fg-3">
          <tr><th className="pb-2 font-medium">Time band</th><th className="pb-2 font-medium">From (hour)</th><th className="pb-2 font-medium">To (hour)</th><th className="pb-2 font-medium">Price per kWh</th></tr>
        </thead>
        <tbody>
          {draft.bands.map((b, i) => (
            <tr key={b.name} className="border-t border-line">
              <td className="py-2 pr-3"><span className="flex items-center gap-2 capitalize text-fg"><span className="h-2 w-2 rounded-full" style={{ background: BAND_COLOR[b.name] }} />{b.name}</span></td>
              <td className="py-2 pr-3"><Input type="number" min={0} max={23} value={b.start} onChange={(e) => band(i, { start: Number(e.target.value) })} className="!py-1.5" /></td>
              <td className="py-2 pr-3"><Input type="number" min={0} max={23} value={b.end} onChange={(e) => band(i, { end: Number(e.target.value) })} className="!py-1.5" /></td>
              <td className="py-2"><Input type="number" step={0.01} value={b.price} onChange={(e) => band(i, { price: Number(e.target.value) })} className="!py-1.5" /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Field label="Demand charge per kW"><Input type="number" value={draft.demand_charge} onChange={(e) => setDraft({ ...draft, demand_charge: Number(e.target.value) })} /></Field>
        <Field label="Currency"><Input value={draft.currency} onChange={(e) => setDraft({ ...draft, currency: e.target.value })} /></Field>
      </div>
      <Button className="mt-4" loading={saving} onClick={save}>Save prices</Button>
    </Card>
  )
}

interface Region {
  id: string; name: string; currency: string; currency_code: string; locale: string
  bands: [string, number, number, number][]; demand_charge: number; demand_unit: string; co2_kg_per_kwh: number; grid_note: string
}

/** Pick the plant's country: sets typical time-of-use prices, currency, demand unit, grid emissions and number formats. */
function RegionCard({ plantId, current, onChanged }: { plantId: string; current: string; onChanged: () => void }) {
  const regions = useAsync(() => api.get<Region[]>('/regions'), [])
  const [choice, setChoice] = useState(current)
  const [saving, setSaving] = useState(false)
  const picked = regions.data?.find((r) => r.id === choice)
  const apply = async () => {
    if (!picked) return
    setSaving(true)
    await api.put(`/plants/${plantId}/region`, { region: picked.id })
    setLocale(picked.locale)
    setSaving(false)
    onChanged()
  }
  return (
    <Card className="xl:col-span-2">
      <CardTitle sub="Sets typical industrial time-of-use prices, the currency, how demand is billed, grid CO2 and number formats. Load a real bill later to use exact prices.">
        Region
      </CardTitle>
      <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-6">
        {regions.data?.map((r) => (
          <button key={r.id} onClick={() => setChoice(r.id)}
            className={clsx('rounded-lg border px-3 py-2.5 text-left transition', choice === r.id ? 'border-brand bg-brand-soft' : 'border-line hover:bg-subtle')}>
            <div className="text-[14px] font-medium text-fg">{r.name}</div>
            <div className="text-[12.5px] text-fg-3">{r.currency_code}{r.id === current ? ' · in use' : ''}</div>
          </button>
        ))}
      </div>
      {picked && (
        <div className="mt-4 grid gap-4 rounded-lg border border-line bg-subtle p-4 text-[13.5px] md:grid-cols-4">
          <div className="md:col-span-2">
            <div className="text-[12.5px] text-fg-3">Time-of-use prices per kWh</div>
            {picked.bands.map(([name, start, end, price]) => (
              <div key={name} className="mt-1 flex justify-between gap-3">
                <span className="capitalize text-fg">{name} <span className="num text-fg-4">{fmt.hours(start, end)}</span></span>
                <span className="num text-fg">{picked.currency}{price < 1 ? price.toFixed(3) : price.toFixed(2)}</span>
              </div>
            ))}
          </div>
          <div>
            <div className="text-[12.5px] text-fg-3">Demand charge</div>
            <div className="num mt-1 text-fg">{picked.currency}{picked.demand_charge.toLocaleString()} per {picked.demand_unit}</div>
            <div className="mt-0.5 text-[12.5px] text-fg-3">highest 15 minutes of the month</div>
          </div>
          <div>
            <div className="text-[12.5px] text-fg-3">Grid emissions</div>
            <div className="num mt-1 text-fg">{picked.co2_kg_per_kwh} kg CO2 per kWh</div>
            <div className="mt-0.5 text-[12.5px] text-fg-3">{picked.grid_note}</div>
          </div>
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button variant="primary" loading={saving} disabled={!picked || choice === current} onClick={apply}>
          {choice === current ? 'In use' : `Use ${picked?.name ?? ''} settings`}
        </Button>
        <span className="text-[13px] text-fg-3">Replaces this plant's prices below. Example rates, not a published tariff.</span>
      </div>
    </Card>
  )
}
