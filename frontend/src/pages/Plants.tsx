import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Badge, Button, Card, ErrorBox, Input, Loading, Page, PageHeader } from '../components/ui'
import { api } from '../lib/api'
import type { PlantSpec, PlantSummary } from '../lib/types'
import { useAsync } from '../lib/useAsync'

interface Template { id: string; name: string; description: string; machines: number }

export default function Plants() {
  const plants = useAsync(() => api.get<PlantSummary[]>('/plants'), [])
  const templates = useAsync(() => api.get<Template[]>('/templates'), [])
  const [template, setTemplate] = useState('bakery')
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const navigate = useNavigate()

  const create = async () => {
    setCreating(true)
    try {
      const spec = await api.post<PlantSpec>('/plants', { template, name })
      navigate(`/designer/${spec.id}`)
    } catch (e) {
      setError(e)
    } finally {
      setCreating(false)
    }
  }
  const remove = async (id: string, plantName: string) => {
    if (!window.confirm(`Delete "${plantName}"? Its design and trained data are removed.`)) return
    await api.del(`/plants/${id}`)
    plants.reload()
  }

  if (!plants.data || !templates.data) return <Loading />
  return (
    <Page>
      <PageHeader title="All plants" subtitle="Every plant MeterZero knows. Open one, change its layout, or start a new one from a template." />
      {error ? <div className="mb-4"><ErrorBox error={error} /></div> : null}

      <div className="grid gap-4 xl:grid-cols-12">
        <Card className="overflow-x-auto !p-0 xl:col-span-8">
          <table className="w-full min-w-[640px] text-[14px]">
            <thead className="border-b border-line text-left text-[12.5px] text-fg-3">
              <tr>
                <th className="px-5 py-3 font-medium">Plant</th><th className="px-3 py-3 font-medium">Machines</th>
                <th className="px-3 py-3 font-medium">Lines</th><th className="px-3 py-3 font-medium">Status</th><th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {plants.data.map((p) => (
                <tr key={p.id} className="border-t border-line first:border-t-0">
                  <td className="px-5 py-3.5">
                    <div className="font-medium text-fg">{p.name}</div>
                    <div className="mt-0.5 line-clamp-1 max-w-md text-[13px] text-fg-3">{p.description}</div>
                  </td>
                  <td className="num px-3 py-3.5 text-fg-2">{p.machines}</td>
                  <td className="num px-3 py-3.5 text-fg-2">{p.lines}</td>
                  <td className="px-3 py-3.5">
                    {p.reference ? <Badge tone="accent">Reference</Badge> : p.training ? <Badge tone="warn">Training…</Badge>
                      : p.trained ? <Badge tone="ok">Trained</Badge> : <Badge>Not trained</Badge>}
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="flex justify-end gap-2">
                      {p.trained && <Link to={`/p/${p.id}/overview`}><Button size="sm" variant="primary">Open</Button></Link>}
                      <Link to={`/designer/${p.id}`}><Button size="sm">Design</Button></Link>
                      {!p.reference && <Button size="sm" variant="ghost" onClick={() => remove(p.id, p.name)}>Delete</Button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card className="xl:col-span-4">
          <h2 className="text-[15px] font-semibold text-fg">Start a new plant</h2>
          <p className="mt-1 text-[13.5px] text-fg-3">Pick a starting point, then lay it out in the designer.</p>
          <div className="mt-4 space-y-2">
            {templates.data.map((t) => (
              <label key={t.id} className={`block cursor-pointer rounded-lg border px-4 py-3 transition ${template === t.id ? 'border-brand bg-brand-soft' : 'border-line hover:bg-subtle'}`}>
                <div className="flex items-center gap-3">
                  <input type="radio" name="template" checked={template === t.id} onChange={() => setTemplate(t.id)} className="accent-[#0c304a]" />
                  <span className="font-medium text-fg">{t.id === 'demo' ? 'Copy of the demo plant' : t.name}</span>
                  <span className="ml-auto text-[12.5px] text-fg-4">{t.machines} machines</span>
                </div>
                <p className="mt-1 pl-7 text-[13px] leading-relaxed text-fg-2">{t.description}</p>
              </label>
            ))}
          </div>
          <Input className="mt-4" placeholder="Name your plant" value={name} onChange={(e) => setName(e.target.value)} />
          <Button className="mt-3 w-full" variant="primary" loading={creating} onClick={create}>Create and open the designer</Button>
        </Card>
      </div>
    </Page>
  )
}
