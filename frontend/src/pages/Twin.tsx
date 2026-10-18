import clsx from 'clsx'
import { useEffect, useState } from 'react'

import { NotTrained } from '../components/NotTrained'
import { Badge, ErrorBox, Loading, Select } from '../components/ui'
import { api } from '../lib/api'
import { useAssistantContext } from '../lib/assistant'
import { fmt } from '../lib/format'
import { usePlant } from '../lib/plant'
import type { Timeline } from '../lib/types'
import { useAsync } from '../lib/useAsync'
import { toScene } from '../twin/layout'
import { type CameraCommand, TwinCanvas, type View } from '../twin/TwinCanvas'
import { Clock, Panel, ToolButton, ToolGroup } from '../twin/editor/Chrome'
import { Hierarchy } from '../twin/editor/Hierarchy'
import { MachineInspector, PlantInspector } from '../twin/editor/Inspector'
import { Scrubber } from '../twin/editor/Timeline'
import { usePlayer } from '../twin/usePlayer'

const MOMENTS = [
  { label: 'Night', minute: 90 },
  { label: 'Shift start', minute: 350 },
  { label: 'Afternoon', minute: 870 },
  { label: 'Evening peak', minute: 1080 },
]
const SPEEDS = [1, 5, 15, 60]
const VIEWS: { value: View; label: string }[] = [
  { value: 'perspective', label: 'Perspective' }, { value: 'top', label: 'Top' }, { value: 'front', label: 'Front' }, { value: 'side', label: 'Side' },
]

export default function Twin() {
  const { plant, plantId, loading, error, untrained } = usePlant()
  const [day, setDay] = useState<string | null>(null)
  const chosenDay = day ?? plant?.default_day ?? null
  const timeline = useAsync(
    () => (chosenDay ? api.get<Timeline>(`/plants/${plantId}/timeline?day=${chosenDay}`) : Promise.resolve(null)),
    [plantId, chosenDay],
  )
  const player = usePlayer()
  const [selected, setSelected] = useState<string | null>(null)
  const [labels, setLabels] = useState(true)
  const [hidden, setHidden] = useState(false)
  const [view, setView] = useState<View>('perspective')
  const [camera, setCamera] = useState<CameraCommand | undefined>()

  const t = timeline.data
  const minute = Math.floor(player.display)
  const selectedMeta = plant?.machines.find((m) => m.id === selected) ?? null

  const focus = (id: string | null = selected) => {
    const m = plant?.machines.find((x) => x.id === id)
    if (!m || !plant) return
    const p = toScene(plant.spec, m.x, m.y)
    setCamera({ focus: [p.x, p.z], id: Date.now() })
  }
  const changeView = (v: View) => { setView(v); setCamera({ view: v, id: Date.now() }) }

  // Editor shortcuts: F frames the selection, Space plays and pauses, Esc clears the selection.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(e.target.tagName)) return
      if (e.key === 'f' || e.key === 'F') focus()
      else if (e.key === ' ') { e.preventDefault(); player.setPlaying(!player.playing) }
      else if (e.key === 'Escape') setSelected(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const kwNow = (id: string) => t?.machines[id]?.kw[minute] ?? 0
  const name = selectedMeta?.name.toLowerCase()
  useAssistantContext('Digital twin',
    t ? `Watching ${t.weekday} at ${fmt.clock(minute)}: the site is drawing ${Math.round(t.meter[minute] ?? 0)} kW.${selectedMeta ? ` Selected: ${selectedMeta.name}, ${kwNow(selectedMeta.id).toFixed(1)} kW now.` : ''}` : '',
    selectedMeta
      ? [`Why is the ${name} using this much power right now?`, `Is the ${name} behaving normally today?`, `What would a meter on the ${name} tell us?`]
      : ['What is using the most power right now?', 'Is anything running that shouldn\'t be?', 'What happens at the evening peak?'])

  if (untrained) return <NotTrained />
  if (error) return <div className="p-8"><ErrorBox error={error} /></div>
  if (loading || !plant) return <Loading label="Loading the plant…" />

  return (
    <div className="flex min-h-full flex-col bg-surface xl:h-full">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-3 py-2 sm:px-4">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-[14px] font-semibold text-fg">{plant.spec.name}</span>
          <Badge tone="sim">Simulation</Badge>
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={() => player.setPlaying(!player.playing)} aria-label={player.playing ? 'Pause' : 'Play'} title="Play / pause (Space)"
            className={clsx('grid h-8 w-9 place-items-center rounded-md border transition', player.playing ? 'border-brand-line bg-brand-soft text-brand' : 'border-line-strong text-fg-2 hover:bg-subtle')}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden>
              {player.playing ? <path d="M2 1h3v10H2zM7 1h3v10H7z" /> : <path d="M2.5 1v10l8.5-5z" />}
            </svg>
          </button>
          <ToolGroup value={String(player.speed)} onChange={(v) => player.setSpeed(Number(v))}
            options={SPEEDS.map((s) => ({ value: String(s), label: `${s}×` }))} />
        </div>
        <ToolGroup value={view} onChange={(v) => changeView(v as View)} options={VIEWS} />
        <div className="flex flex-wrap items-center gap-1.5 xl:ml-auto">
          <ToolButton onClick={() => focus()} disabled={!selected} title="Frame the selected machine (F)">Focus</ToolButton>
          <ToolButton active={labels} onClick={() => setLabels((v) => !v)}>Labels</ToolButton>
          <ToolButton active={hidden} onClick={() => setHidden((v) => !v)} title="Show each machine's hidden meter next to MeterZero's figure">Meter check</ToolButton>
          <Select value={chosenDay ?? ''} onChange={(e) => setDay(e.target.value)} className="!h-8 !w-auto !py-0 text-[13px]">
            {plant.days.map((d) => <option key={d} value={d}>{fmt.day(d)}</option>)}
          </Select>
        </div>
      </div>

      <div className="flex flex-1 flex-col xl:grid xl:min-h-0 xl:grid-cols-[240px_minmax(0,1fr)_340px]">
        {/* Hierarchy */}
        <Panel title="Hierarchy" className="order-3 border-t xl:order-none xl:border-r xl:border-t-0">
          {t && <Hierarchy spec={plant.spec} machines={plant.machines} timeline={t} minute={minute} selected={selected}
            onSelect={setSelected} onFocus={(id) => { setSelected(id); focus(id) }} />}
        </Panel>

        {/* Scene and timeline */}
        <div className="order-1 flex min-h-0 min-w-0 flex-col xl:order-none">
          <div className="flex h-9 shrink-0 items-center justify-between border-b border-line bg-subtle px-3">
            <span className="text-[12.5px] font-semibold text-fg-2">Scene</span>
            <span className="hidden text-[12px] text-fg-3 md:block">Drag to orbit · right-drag to pan · scroll to zoom · W A S D to move · F to focus</span>
          </div>
          <div className="relative h-[58vh] min-h-[360px] overflow-hidden bg-[#eef1f5] xl:h-auto xl:flex-1">
            {t ? (
              <TwinCanvas className="absolute inset-0" spec={plant.spec} machines={plant.machines}
                live={{ timeline: t, minute: player.minute }} labels={labels} showHidden={hidden}
                selected={selected} onSelect={setSelected} camera={camera} gizmo />
            ) : <Loading label="Loading the day…" />}
            {t && <Clock timeline={t} minute={minute} />}
          </div>
          {t && (
            <div className="shrink-0 border-t border-line">
              <div className="flex h-9 items-center justify-between gap-3 border-b border-line bg-subtle px-3">
                <span className="text-[12.5px] font-semibold text-fg-2">Timeline</span>
                <div className="flex gap-0.5 overflow-x-auto">
                  {MOMENTS.map((m) => (
                    <button key={m.label} onClick={() => player.seek(m.minute)}
                      className="whitespace-nowrap rounded px-2 py-0.5 text-[12.5px] text-fg-2 hover:bg-muted hover:text-fg">{m.label}</button>
                  ))}
                </div>
              </div>
              <div className="px-3 pb-2 pt-3">
                <Scrubber timeline={t} minute={player.display} onSeek={player.seek} machines={plant.machines} />
              </div>
            </div>
          )}
        </div>

        {/* Inspector */}
        <Panel title="Inspector" className="order-2 border-t xl:order-none xl:border-l xl:border-t-0">
          {t && (selectedMeta ? (
            <MachineInspector meta={selectedMeta} timeline={t} minute={minute} plantId={plantId} day={chosenDay!}
              onClose={() => setSelected(null)} onFocus={() => focus()} />
          ) : (
            <PlantInspector timeline={t} minute={minute} machines={plant.machines} onSelect={setSelected} />
          ))}
        </Panel>
      </div>
    </div>
  )
}
