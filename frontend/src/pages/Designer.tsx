import clsx from 'clsx'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Spin } from '../components/ai'
import { Modal } from '../components/Modal'
import { Badge, Button, ErrorBox, Field, Input, Loading, Segmented, Select } from '../components/ui'
import { api } from '../lib/api'
import type { Job, Line, MachineMeta, MachineSpec, MachineType, PlantSpec, Room } from '../lib/types'
import { useAsync } from '../lib/useAsync'
import { TwinCanvas } from '../twin/TwinCanvas'

const PALETTE = ['#3b82f6', '#f97316', '#10b981', '#eab308', '#ec4899', '#22c55e', '#8b5cf6', '#ef4444', '#06b6d4', '#a855f7', '#84cc16', '#f43f5e']
const GROUPS: { serves: MachineType['serves']; label: string }[] = [
  { serves: 'line', label: 'Production' }, { serves: 'shared', label: 'Shared utilities' }, { serves: 'building', label: 'Building' },
]

function slug(text: string) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'machine'
}

interface Draft { from: unknown; spec: PlantSpec; problems: string[]; dirty: boolean }

export default function Designer() {
  const { plantId = 'new_plant' } = useParams()
  const navigate = useNavigate()
  const library = useAsync(() => api.get<MachineType[]>('/library'), [])
  const loaded = useAsync(() => api.get<{ spec: PlantSpec; problems: string[] }>(`/plants/${plantId}/spec`), [plantId])
  // Local edits belong to the spec they were made on: loading a different plant starts from its saved design.
  const [draft, setDraft] = useState<Draft | null>(null)
  const base = loaded.data
  const current: Draft | null = draft && draft.from === base ? draft
    : base ? { from: base, spec: base.spec, problems: base.problems, dirty: false } : null
  const { spec = null, problems = [], dirty = false } = current ?? {}
  const change = (patch: Partial<Draft>) => setDraft((d) => {
    const start = d && d.from === base ? d : base ? { from: base, spec: base.spec, problems: base.problems, dirty: false } : null
    return start && { ...start, ...patch }
  })
  const setSpec = (next: PlantSpec) => change({ spec: next })
  const setProblems = (next: string[]) => change({ problems: next })
  const setDirty = (next: boolean) => change({ dirty: next })
  const [selected, setSelected] = useState<string | null>(null)
  const [placing, setPlacing] = useState<MachineType | null>(null)
  const [tab, setTab] = useState<'machine' | 'lines' | 'rooms' | 'plant'>('machine')
  const [saving, setSaving] = useState(false)
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [copyName, setCopyName] = useState<string | null>(null)


  const types = useMemo(() => Object.fromEntries((library.data ?? []).map((t) => [t.id, t])), [library.data])
  const machines: MachineMeta[] = useMemo(() => (spec?.machines ?? []).map((m, i) => {
    const t = types[m.type]
    return {
      id: m.id, name: m.name, line: m.line, group: '', type: m.type, type_label: t?.label ?? m.type, shape: t?.shape ?? 'cabinet',
      size: t?.size ?? [1.6, 1.4, 1.2], rated_kw: m.rated_kw, x: m.x, y: m.y, rotation: m.rotation,
      color: PALETTE[i % PALETTE.length], peak_kw: m.rated_kw,
    }
  }), [spec, types])

  if (loaded.error) return <div className="p-8"><ErrorBox error={loaded.error} /></div>
  if (!spec || !library.data) return <Loading label="Opening the designer…" />
  const readOnly = spec.reference

  const update = (patch: Partial<PlantSpec>) => { setSpec({ ...spec, ...patch }); setDirty(true) }
  const updateMachine = (id: string, patch: Partial<MachineSpec>) =>
    update({ machines: spec.machines.map((m) => (m.id === id ? { ...m, ...patch } : m)) })
  const selectedMachine = spec.machines.find((m) => m.id === selected) ?? null

  const place = (x: number, y: number) => {
    if (!placing || readOnly) return
    const base = slug(placing.label)
    let id = base
    for (let n = 2; spec.machines.some((m) => m.id === id); n++) id = `${base}_${n}`
    const line = placing.serves === 'line' ? (spec.lines[0]?.id ?? 'A') : placing.serves
    const machine: MachineSpec = { id, name: placing.label, type: placing.id, line, rated_kw: placing.default_kw, x, y, rotation: 0 }
    update({ machines: [...spec.machines, machine] })
    setSelected(id)
    setTab('machine')
    setPlacing(null)
  }

  const save = async (): Promise<boolean> => {
    setSaving(true)
    setError(null)
    try {
      const res = await api.put<{ spec: PlantSpec; problems: string[] }>(`/plants/${plantId}/spec`, spec)
      setProblems(res.problems)
      setDirty(false)
      return true
    } catch (e) {
      setError(e)
      return false
    } finally {
      setSaving(false)
    }
  }

  const train = async () => {
    if (!readOnly && !(await save())) return
    try {
      setJob(await api.post<Job>(`/plants/${plantId}/train`))
    } catch (e) {
      setError(e)
    }
  }

  const saveCopy = async () => {
    const created = await api.post<PlantSpec>('/plants', { template: 'demo', name: copyName || `${spec.name} (copy)` })
    setCopyName(null)
    navigate(`/designer/${created.id}`)
  }

  return (
    <div className="flex min-h-full flex-col lg:h-full">
      {/* Top bar */}
      <div className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-5 py-3">
        <div className="min-w-0">
          <div className="text-[12px] font-medium text-fg-3">Plant designer</div>
          <input value={spec.name} disabled={readOnly} onChange={(e) => update({ name: e.target.value })}
            className="w-full max-w-72 bg-transparent text-[16px] font-semibold text-fg outline-none disabled:opacity-90" />
        </div>
        {readOnly && <Badge tone="warn">Reference plant: read only</Badge>}
        {dirty && <Badge>Unsaved changes</Badge>}
        {problems.length > 0 && !readOnly && (
          <span className="group relative">
            <Badge tone="bad">{problems.length} to fix</Badge>
            <span className="absolute left-0 top-7 z-50 hidden w-80 rounded-lg border border-line-strong bg-surface p-3 text-xs text-fg shadow-xl group-hover:block">
              {problems.map((p) => <div key={p} className="py-0.5">• {p}</div>)}
            </span>
          </span>
        )}
        <div className="flex w-full flex-wrap items-center gap-2 sm:ml-auto sm:w-auto">
          {readOnly ? (
            <Button onClick={() => setCopyName(`${spec.name} (my copy)`)}>Save as a copy to edit</Button>
          ) : (
            <Button loading={saving} onClick={save} disabled={!dirty}>Save</Button>
          )}
          <Button variant="primary" onClick={train} disabled={!readOnly && problems.length > 0 && !dirty}>
            Simulate &amp; train
          </Button>
        </div>
      </div>
      {error ? <div className="px-5 pt-3"><ErrorBox error={error} /></div> : null}

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Library */}
        <aside className="order-2 max-h-72 shrink-0 overflow-y-auto border-t border-line bg-surface p-4 lg:order-none lg:max-h-none lg:w-60 lg:border-r lg:border-t-0">
          <div className="mb-3 text-[13px] font-semibold text-fg">Machine library</div>
          <p className="mb-4 text-[12px] leading-relaxed text-fg-3">Pick a machine, then click the floor to place it. Drag machines to move them.</p>
          {GROUPS.map((group) => (
            <div key={group.serves} className="mb-4">
              <div className="mb-1.5 text-[12px] font-medium text-fg-4">{group.label}</div>
              {library.data!.filter((t) => t.serves === group.serves).map((t) => (
                <button key={t.id} disabled={readOnly} title={t.description}
                  onClick={() => setPlacing(placing?.id === t.id ? null : t)}
                  className={clsx('mb-1 flex w-full items-center justify-between rounded-lg border px-2.5 py-2 text-left text-[13px] transition disabled:opacity-50',
                    placing?.id === t.id ? 'border-brand-line bg-brand-soft text-brand' : 'border-transparent text-fg hover:border-line-strong hover:bg-subtle')}>
                  <span>{t.label}</span>
                  <span className="num text-[11px] text-fg-4">{t.default_kw} kW</span>
                </button>
              ))}
            </div>
          ))}
        </aside>

        {/* Floor */}
        <div className="relative order-1 h-[55vh] min-h-[340px] min-w-0 overflow-hidden bg-[#eef1f5] lg:order-none lg:h-auto lg:flex-1">
          <TwinCanvas className="absolute inset-0" spec={spec} machines={machines} gizmo labels selected={selected} onSelect={setSelected}
            editable={!readOnly} placing={!!placing} onFloorClick={place}
            onMove={(id, x, y) => updateMachine(id, { x, y })} />
          {placing && (
            <div className="pointer-events-none absolute left-1/2 top-4 -translate-x-1/2 rounded-full border border-brand-line bg-white px-4 py-2 text-[13px] text-brand shadow-sm">
              Click on the floor to place the {placing.label.toLowerCase()}
            </div>
          )}
          <div className="pointer-events-none absolute bottom-4 left-4 right-4 hidden rounded-lg border border-line bg-white/90 px-3 py-2 text-[12px] text-fg-3 sm:right-auto sm:block">
            {spec.machines.length} machines · {spec.lines.length} lines · {spec.rooms.length} rooms · floor {spec.floor_w} × {spec.floor_d} m · drag to orbit, scroll to zoom
          </div>
        </div>

        {/* Inspector */}
        <aside className="order-3 shrink-0 overflow-y-auto border-t border-line bg-surface p-4 lg:order-none lg:w-[340px] lg:border-l lg:border-t-0">
          <Segmented value={tab} onChange={setTab} options={[
            { value: 'machine', label: 'Machine' }, { value: 'lines', label: 'Lines' }, { value: 'rooms', label: 'Rooms' }, { value: 'plant', label: 'Plant' }]} />
          <fieldset disabled={readOnly} className="mt-4 space-y-3 disabled:opacity-80">
            {tab === 'machine' && (selectedMachine ? (
              <MachineInspector m={selectedMachine} spec={spec} types={library.data!} onChange={(p) => updateMachine(selectedMachine.id, p)}
                onDelete={() => { update({ machines: spec.machines.filter((m) => m.id !== selectedMachine.id) }); setSelected(null) }} />
            ) : (
              <div className="rounded-xl border border-dashed border-line-strong p-6 text-center text-[13px] text-fg-3">
                Click a machine to edit it, or pick one from the library to add it.
              </div>
            ))}
            {tab === 'lines' && <LinesEditor lines={spec.lines} onChange={(lines) => update({ lines })} />}
            {tab === 'rooms' && <RoomsEditor rooms={spec.rooms} onChange={(rooms) => update({ rooms })} />}
            {tab === 'plant' && <PlantSettings spec={spec} onChange={update} />}
          </fieldset>
        </aside>
      </div>

      {job && <TrainingModal plantId={plantId} job={job} onClose={() => setJob(null)} onOpen={() => navigate(`/p/${plantId}/twin`)} />}
      {copyName !== null && (
        <Modal title="Save as a copy" onClose={() => setCopyName(null)}>
          <Field label="Name for your copy"><Input value={copyName} onChange={(e) => setCopyName(e.target.value)} /></Field>
          <div className="mt-4 flex justify-end"><Button variant="primary" onClick={saveCopy}>Create copy</Button></div>
        </Modal>
      )}
    </div>
  )
}

function MachineInspector({ m, spec, types, onChange, onDelete }: {
  m: MachineSpec; spec: PlantSpec; types: MachineType[]; onChange: (p: Partial<MachineSpec>) => void; onDelete: () => void
}) {
  const type = types.find((t) => t.id === m.type)
  return (
    <>
      <Field label="Name"><Input value={m.name} onChange={(e) => onChange({ name: e.target.value })} /></Field>
      <Field label="Type" hint={type?.description}>
        <Select value={m.type} onChange={(e) => {
          const t = types.find((x) => x.id === e.target.value)!
          onChange({ type: t.id, line: t.serves === 'line' ? (spec.lines[0]?.id ?? 'A') : t.serves, rated_kw: t.default_kw })
        }}>
          {types.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </Select>
      </Field>
      {type?.serves === 'line' ? (
        <Field label="Production line"><Select value={m.line} onChange={(e) => onChange({ line: e.target.value })}>
          {spec.lines.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.id})</option>)}
        </Select></Field>
      ) : (
        <div className="text-[12px] text-fg-3">{type?.serves === 'shared' ? 'Serves every production line.' : 'Part of the building, not a line.'}</div>
      )}
      <Field label={`Rated power: ${m.rated_kw} kW`}>
        <input type="range" min={0.5} max={120} step={0.5} value={m.rated_kw} onChange={(e) => onChange({ rated_kw: Number(e.target.value) })} className="w-full accent-[#0c304a]" />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="x (m)"><Input type="number" step={0.5} value={m.x} onChange={(e) => onChange({ x: Number(e.target.value) })} /></Field>
        <Field label="y (m)"><Input type="number" step={0.5} value={m.y} onChange={(e) => onChange({ y: Number(e.target.value) })} /></Field>
      </div>
      <div className="flex gap-2 pt-1">
        <Button size="sm" onClick={() => onChange({ rotation: (m.rotation + 90) % 360 })}>Rotate</Button>
        <Button size="sm" variant="danger" onClick={onDelete}>Delete</Button>
      </div>
      <div className="text-[11px] text-fg-4">Id: {m.id}</div>
    </>
  )
}

function LinesEditor({ lines, onChange }: { lines: Line[]; onChange: (l: Line[]) => void }) {
  const set = (i: number, patch: Partial<Line>) => onChange(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  return (
    <>
      {lines.map((line, i) => (
        <div key={i} className="rounded-xl border border-line bg-subtle p-3">
          <div className="flex gap-2">
            <Input value={line.id} onChange={(e) => set(i, { id: e.target.value.toUpperCase().slice(0, 3) })} className="!w-16" title="Line id" />
            <Input value={line.name} onChange={(e) => set(i, { name: e.target.value })} />
            <button onClick={() => onChange(lines.filter((_, j) => j !== i))} className="shrink-0 text-[12.5px] text-fg-3 hover:text-red-700" title="Remove line">Remove</button>
          </div>
          <div className="mt-2 text-[10px] uppercase tracking-wider text-fg-4">Products · load · units/hour</div>
          {line.products.map((p, k) => (
            <div key={k} className="mt-1 grid grid-cols-[1fr_56px_64px_20px] gap-1.5">
              <Input value={p.name} onChange={(e) => set(i, { products: line.products.map((x, n) => (n === k ? { ...x, name: e.target.value } : x)) })} className="!px-2 !py-1 text-xs" />
              <Input type="number" step={0.1} value={p.load} onChange={(e) => set(i, { products: line.products.map((x, n) => (n === k ? { ...x, load: Number(e.target.value) } : x)) })} className="!px-2 !py-1 text-xs" />
              <Input type="number" value={p.rate} onChange={(e) => set(i, { products: line.products.map((x, n) => (n === k ? { ...x, rate: Number(e.target.value) } : x)) })} className="!px-2 !py-1 text-xs" />
              <button onClick={() => set(i, { products: line.products.filter((_, n) => n !== k) })} className="shrink-0 text-[12.5px] text-fg-3 hover:text-red-700" title="Remove product">Remove</button>
            </div>
          ))}
          <button onClick={() => set(i, { products: [...line.products, { name: `Product ${line.products.length + 1}`, load: 1, rate: 100 }] })}
            className="mt-2 text-[12px] text-brand hover:underline">+ Add product</button>
        </div>
      ))}
      <Button size="sm" onClick={() => onChange([...lines, { id: String.fromCharCode(65 + lines.length), name: `Line ${String.fromCharCode(65 + lines.length)}`, products: [{ name: 'Product 1', load: 1, rate: 100 }] }])}>Add line</Button>
      <div className="text-[11px] leading-relaxed text-fg-4">Load: how hard a product works the line (1 = normal, 1.5 = 50% harder).</div>
    </>
  )
}

function RoomsEditor({ rooms, onChange }: { rooms: Room[]; onChange: (r: Room[]) => void }) {
  const set = (i: number, patch: Partial<Room>) => onChange(rooms.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  return (
    <>
      {rooms.map((room, i) => (
        <div key={i} className="rounded-xl border border-line bg-subtle p-3">
          <div className="flex gap-2">
            <Input value={room.name} onChange={(e) => set(i, { name: e.target.value })} />
            <button onClick={() => onChange(rooms.filter((_, j) => j !== i))} className="shrink-0 text-[12.5px] text-fg-3 hover:text-red-700" title="Remove room">Remove</button>
          </div>
          <div className="mt-2 grid grid-cols-4 gap-1.5">
            {(['x', 'y', 'w', 'd'] as const).map((k) => (
              <label key={k} className="text-[10px] uppercase text-fg-4">{k}
                <Input type="number" step={0.5} value={room[k]} onChange={(e) => set(i, { [k]: Number(e.target.value) } as Partial<Room>)} className="!px-2 !py-1 text-xs" />
              </label>
            ))}
          </div>
        </div>
      ))}
      <Button size="sm" onClick={() => onChange([...rooms, { id: `room_${rooms.length + 1}`, name: `Room ${rooms.length + 1}`, x: 0, y: 0, w: 6, d: 5 }])}>Add room</Button>
    </>
  )
}

function PlantSettings({ spec, onChange }: { spec: PlantSpec; onChange: (p: Partial<PlantSpec>) => void }) {
  return (
    <>
      <Field label="Description"><textarea value={spec.description} onChange={(e) => onChange({ description: e.target.value })}
        className="h-20 w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-brand" /></Field>
      <div className="grid grid-cols-3 gap-2">
        <Field label="Shift starts"><Input type="number" min={0} max={23} value={spec.shift_start} onChange={(e) => onChange({ shift_start: Number(e.target.value) })} /></Field>
        <Field label="Ends"><Input type="number" min={1} max={24} value={spec.shift_end} onChange={(e) => onChange({ shift_end: Number(e.target.value) })} /></Field>
        <Field label="Sat ends" hint="0 = closed on Saturdays"><Input type="number" min={0} max={24} value={spec.saturday_end} onChange={(e) => onChange({ saturday_end: Number(e.target.value) })} /></Field>
      </div>
      <Field label={`Days to simulate: ${spec.days}`} hint="MeterZero learns from the early days and is tested on the last week.">
        <input type="range" min={14} max={42} value={spec.days} onChange={(e) => onChange({ days: Number(e.target.value) })} className="w-full accent-[#0c304a]" />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Floor width (m)"><Input type="number" value={spec.floor_w} onChange={(e) => onChange({ floor_w: Number(e.target.value) })} /></Field>
        <Field label="Floor depth (m)"><Input type="number" value={spec.floor_d} onChange={(e) => onChange({ floor_d: Number(e.target.value) })} /></Field>
        <Field label="Main panel x"><Input type="number" step={0.5} value={spec.panel_x} onChange={(e) => onChange({ panel_x: Number(e.target.value) })} /></Field>
        <Field label="Main panel y"><Input type="number" step={0.5} value={spec.panel_y} onChange={(e) => onChange({ panel_y: Number(e.target.value) })} /></Field>
      </div>
      <Field label="Cable tray runs along y =" hint="Cables run from the panel along this line, then to each machine.">
        <Input type="number" step={0.5} value={spec.cable_y ?? spec.floor_d / 2} onChange={(e) => onChange({ cable_y: Number(e.target.value) })} />
      </Field>
      <div className="rounded-xl border border-line bg-subtle p-3">
        <div className="mb-2 text-[12px] font-medium text-fg">Inject a fault (to test detection)</div>
        <Select value={spec.fault?.machine ?? ''} onChange={(e) => onChange({ fault: e.target.value ? { machine: e.target.value, start_day: spec.fault?.start_day ?? spec.days - 6, kind: 'leak' } : null })}>
          <option value="">No fault</option>
          {spec.machines.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </Select>
        {spec.fault && (
          <Field label={`Starts on day ${spec.fault.start_day}`}>
            <input type="range" min={1} max={spec.days - 1} value={spec.fault.start_day}
              onChange={(e) => onChange({ fault: { ...spec.fault!, start_day: Number(e.target.value) } })} className="w-full accent-[#0c304a]" />
          </Field>
        )}
        <div className="mt-1 text-[11px] text-fg-4">Leaks and doors left open make thermostatic machines work harder; others get left running at night.</div>
      </div>
    </>
  )
}

function TrainingModal({ plantId, job: first, onClose, onOpen }: { plantId: string; job: Job; onClose: () => void; onOpen: () => void }) {
  const [job, setJob] = useState(first)
  useEffect(() => {
    if (job.state === 'done' || job.state === 'failed') return
    const timer = setInterval(() => api.get<Job>(`/plants/${plantId}/job`).then(setJob).catch(() => undefined), 1200)
    return () => clearInterval(timer)
  }, [plantId, job.state])
  const done = job.state === 'done'
  const failed = job.state === 'failed'
  return (
    <Modal title={done ? 'Your plant is ready' : failed ? 'Training failed' : 'Simulating and training…'} onClose={onClose}>
      <div className="space-y-2">
        {job.steps.map((step, i) => (
          <div key={i} className="flex gap-2 text-[13px] text-fg">
            {!done && !failed && i === job.steps.length - 1 ? <Spin className="mt-0.5 text-brand" /> : <span className="text-emerald-600">✓</span>}
            <span className="whitespace-pre-wrap">{step}</span>
          </div>
        ))}
        {!job.steps.length && <div className="flex items-center gap-2 text-sm text-fg-2"><Spin /> Starting…</div>}
      </div>
      {failed && <div className="mt-3"><ErrorBox error={job.error} /></div>}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>{done ? 'Stay here' : 'Hide'}</Button>
        {done && <Button variant="primary" onClick={onOpen}>Open the digital twin</Button>}
      </div>
      {!done && !failed && <div className="mt-2 text-[11px] text-fg-4">Takes about a minute. You can keep working; it runs on the server.</div>}
    </Modal>
  )
}
