import clsx from 'clsx'
import { useEffect, useRef, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

import { api } from '../lib/api'
import type { PlantSummary } from '../lib/types'
import { useAiStatus } from '../lib/useAi'
import { Dot } from './ui'

const SECTIONS = (plantId: string) => [
  { title: 'Operate', items: [
    { to: `/p/${plantId}/overview`, label: 'Overview' },
    { to: `/p/${plantId}/twin`, label: 'Digital twin' },
    { to: `/p/${plantId}/savings`, label: 'Find savings', ai: true },
    { to: `/p/${plantId}/whatif`, label: 'What if' },
    { to: `/p/${plantId}/assistant`, label: 'Ask MeterZero', ai: true },
  ] },
  { title: 'Data', items: [
    { to: `/p/${plantId}/documents`, label: 'Bills & paperwork', ai: true },
    { to: `/p/${plantId}/accuracy`, label: 'Accuracy' },
  ] },
  { title: 'Build', items: [
    { to: `/designer/${plantId}`, label: 'Plant designer' },
    { to: '/plants', label: 'All plants' },
  ] },
  { title: 'Workspace', items: [
    { to: `/p/${plantId}/settings`, label: 'Settings' },
    { to: '/about', label: 'How it works' },
  ] },
]

export function Logo() {
  return <img src="/brand/logo.png" alt="MeterZero" className="h-8 w-auto" />
}

export function Sidebar({ plantId, onNavigate }: { plantId: string; onNavigate?: () => void }) {
  const [plants, setPlants] = useState<PlantSummary[]>([])
  const [open, setOpen] = useState(false)
  const connected = useAiStatus()
  const menu = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.get<PlantSummary[]>('/plants').then(setPlants).catch(() => setPlants([]))
  }, [plantId])

  useEffect(() => {
    const close = (e: MouseEvent) => menu.current && !menu.current.contains(e.target as Node) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const current = plants.find((p) => p.id === plantId)
  const go = (to: string) => { setOpen(false); navigate(to); onNavigate?.() }

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r border-line bg-surface">
      <div className="flex h-16 shrink-0 items-center px-5"><Logo /></div>

      {/* Plant switcher */}
      <div ref={menu} className="relative shrink-0 px-3 pb-3">
        <button onClick={() => setOpen((o) => !o)}
          className="w-full rounded-lg border border-line px-3 py-1.5 text-left transition-colors hover:bg-subtle">
          <div className="text-[11.5px] text-fg-3">Plant</div>
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-[13.5px] font-medium text-fg">{current?.name ?? plantId}</span>
            <span className="text-[11px] text-fg-4">{open ? '▲' : '▼'}</span>
          </div>
        </button>
        {open && (
          <div className="absolute left-3 right-3 top-full z-50 mt-1 overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-lg">
            {plants.map((p) => (
              <button key={p.id} onClick={() => go(p.trained ? `/p/${p.id}/overview` : `/designer/${p.id}`)}
                className={clsx('flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13.5px] hover:bg-subtle', p.id === plantId && 'bg-brand-soft')}>
                <Dot color={p.training ? '#d97706' : p.trained ? '#16a34a' : '#9ca3af'} />
                <span className="min-w-0 flex-1 truncate text-fg">{p.name}</span>
                {!p.trained && !p.training && <span className="text-[11px] text-fg-4">not trained</span>}
              </button>
            ))}
            <button onClick={() => go('/plants')} className="w-full border-t border-line px-3 py-2 text-left text-[13.5px] font-medium text-brand hover:bg-subtle">
              New plant…
            </button>
          </div>
        )}
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {SECTIONS(plantId).map((section) => (
          <div key={section.title} className="mt-3 first:mt-1">
            <div className="mb-0.5 px-3 text-[11.5px] font-medium uppercase tracking-wide text-fg-4">{section.title}</div>
            {section.items.map((item) => (
              <NavLink key={item.to} to={item.to} onClick={onNavigate}
                className={({ isActive }) => clsx('flex items-center justify-between rounded-md px-3 py-[7px] text-[14px] transition-colors',
                  isActive ? 'bg-brand-soft font-medium text-brand' : 'text-fg-2 hover:bg-subtle hover:text-fg')}>
                {item.label}
                {'ai' in item && <span className="rounded px-1 text-[10.5px] font-semibold text-violet-600">AI</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <NavLink to={`/p/${plantId}/settings`} onClick={onNavigate}
        className="flex shrink-0 items-center gap-2 border-t border-line px-5 py-3 text-[12.5px] text-fg-3 hover:text-fg">
        <Dot color={connected ? '#16a34a' : '#9ca3af'} />
        {connected ? 'Gemini connected' : 'Gemini not connected'}
      </NavLink>
    </aside>
  )
}
