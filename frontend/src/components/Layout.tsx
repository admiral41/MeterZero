import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { AssistantDock } from './AssistantDock'
import { Logo, Sidebar } from './Sidebar'
import { shouldShowTour } from '../lib/tour'
import { Tour } from './Tour'

/** The plant in the URL (/p/:id/… or /designer/:id), or the demo plant elsewhere. */
function plantFrom(pathname: string) {
  return pathname.match(/^\/(?:p|designer)\/([^/]+)/)?.[1] ?? 'demo'
}

/** Sidebar on wide screens; a top bar with a slide-in menu below laptop width. */
export function Layout() {
  const [drawer, setDrawer] = useState(false)
  const [tour, setTour] = useState(shouldShowTour)
  const { pathname } = useLocation()
  const plantId = plantFrom(pathname)
  const dock = pathname.startsWith('/p/') && !pathname.endsWith('/assistant')


  return (
    <div className="flex h-full flex-col bg-canvas lg:flex-row">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface px-4 lg:hidden">
        <Logo />
        <button onClick={() => setDrawer(true)} className="rounded-md border border-line px-3 py-1.5 text-[13.5px] font-medium text-fg-2 hover:bg-subtle">
          Menu
        </button>
      </header>

      <div className="hidden lg:flex">
        <Sidebar plantId={plantId} />
      </div>

      {drawer && (
        <div className="fixed inset-0 z-[90] lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setDrawer(false)} />
          <div className="relative h-full w-fit shadow-xl">
            <Sidebar plantId={plantId} onNavigate={() => setDrawer(false)} />
          </div>
        </div>
      )}

      <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
      {dock && <AssistantDock plantId={plantId} />}
      {tour && <Tour onClose={() => setTour(false)} />}
    </div>
  )
}
