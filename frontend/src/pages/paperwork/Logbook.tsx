import clsx from 'clsx'
import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Badge, Card, CardTitle, ErrorBox } from '../../components/ui'
import { AXIS, TIP } from '../../lib/chart'
import { api } from '../../lib/api'
import { useAssistantContext } from '../../lib/assistant'
import { PhotoPicker } from './PhotoReader'
import { useReader } from './usePhotoReader'

interface Row { line: string; product: string; start: string; end: string; units: number; note: string }
interface LogbookResult {
  problems: string[]
  check: { line: string; product: string; 'system start': string; 'system end': string; 'read from photo': string; 'units match': boolean }[]
  batches: { line: string; product: string; start: string; end: string; units: number; kwh: number; plus_minus: number; true_kwh: number }[]
}

/** A handwritten production page: Gemini reads the rows, MeterZero checks them and prices each product. */
export function Logbook() {
  const r = useReader('logbook')
  const page = r.result as { date: string; rows: Row[] } | null
  const [edited, setEdited] = useState<{ page: unknown; rows: Row[] } | null>(null)
  const rows = edited && edited.page === page ? edited.rows : page?.rows ?? []
  const setRows = (next: Row[]) => setEdited({ page, rows: next })
  const [checked, setChecked] = useState<LogbookResult | null>(null)
  const [error, setError] = useState<unknown>(null)
  useAssistantContext('Bills & paperwork', 'Looking at a handwritten production logbook page.', ['What does this logbook page tell us about energy per product?'])

  useEffect(() => {
    if (!page) return
    const timer = setTimeout(() => {
      api.post<LogbookResult>(`/plants/${r.plantId}/logbook`, { date: page.date, rows }).then(setChecked).catch(setError)
    }, 300)
    return () => clearTimeout(timer)
  }, [rows, page, r.plantId])

  const products = useMemo(() => {
    const map = new Map<string, { kwh: number; units: number; true: number }>()
    for (const b of checked?.batches ?? []) {
      const cur = map.get(b.product) ?? { kwh: 0, units: 0, true: 0 }
      map.set(b.product, { kwh: cur.kwh + b.kwh, units: cur.units + b.units, true: cur.true + b.true_kwh })
    }
    return [...map.entries()].map(([product, v]) => ({ product, perItem: v.kwh / v.units, truePerItem: v.true / v.units }))
  }, [checked])
  const matched = checked?.check.filter((c) => c['read from photo'] === '✓').length ?? 0
  const expected = checked?.check.filter((c) => c['system start'] !== '-').length ?? 0

  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <div className="xl:col-span-5"><PhotoPicker r={r} label="Logbook page" /></div>
      <div className="space-y-4 xl:col-span-7">
        <Card>
          <CardTitle hint="Click any cell to correct it; MeterZero re-checks straight away."
            sub={page ? `${rows.length} rows dated ${page.date}` : undefined}>What Gemini read</CardTitle>
          {!page && <div className="text-[14px] text-fg-3">Read the photo to see its rows here.</div>}
          {page && (
            <div className="max-h-80 overflow-auto rounded-lg border border-line">
              <table className="w-full text-[13.5px]">
                <thead className="sticky top-0 bg-surface text-left text-[12.5px] text-fg-3">
                  <tr>{['Line', 'Product', 'Start', 'End', 'Qty', 'Note'].map((h) => <th key={h} className="px-2 py-2 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={i} className="border-t border-line">
                      {(['line', 'product', 'start', 'end', 'units', 'note'] as const).map((field) => (
                        <td key={field} className="px-1 py-1">
                          <input value={String(row[field] ?? '')}
                            onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, [field]: field === 'units' ? Number(e.target.value) || 0 : e.target.value } : x)))}
                            className="w-full rounded bg-transparent px-1.5 py-1 text-fg outline-none focus:bg-subtle" />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {checked?.problems.map((p) => <div key={p} className="mt-2 text-[13px] text-amber-700">{p}</div>)}
          {error ? <ErrorBox error={error} /> : null}
        </Card>
        {checked && checked.check.length > 0 && (
          <Card>
            <CardTitle right={<Badge tone={matched === expected ? 'ok' : 'warn'}>{matched} of {expected} match</Badge>}>Checked against the plant's records</CardTitle>
            <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
              {checked.check.map((c, i) => {
                const ok = c['read from photo'] === '✓'
                return (
                  <div key={i} className="flex items-center gap-2 text-[13.5px] text-fg-2">
                    <span className={clsx('w-12 shrink-0 text-[12px] font-medium', ok ? 'text-emerald-700' : 'text-red-600')}>{ok ? 'Match' : 'Differs'}</span>
                    <span className="text-fg">Line {c.line} · {c.product}</span>
                    <span className="num text-fg-4">{c['system start']}–{c['system end']}</span>
                    {!ok && <span className="text-red-700">{c['read from photo'].replace('✗ ', '')}</span>}
                  </div>
                )
              })}
            </div>
          </Card>
        )}
        {products.length > 0 && (
          <Card>
            <CardTitle hint="Blue: MeterZero, from the photographed page. Grey: the hidden meters, for checking.">Energy for each product, from this page</CardTitle>
            <div className="h-60">
              <ResponsiveContainer>
                <BarChart data={products} margin={{ left: -6 }}>
                  <CartesianGrid stroke="#eef0f3" vertical={false} />
                  <XAxis dataKey="product" {...AXIS} />
                  <YAxis scale="log" domain={['auto', 'auto']} {...AXIS} tickFormatter={(v) => v.toFixed(2)} />
                  <Tooltip contentStyle={TIP} formatter={(v) => `${Number(v).toFixed(3)} kWh per item`} />
                  <Bar dataKey="perItem" name="MeterZero" fill="#2563eb" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="truePerItem" name="Hidden meters" fill="#d1d5db" radius={[3, 3, 0, 0]} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
