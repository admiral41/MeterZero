import { useEffect, type ReactNode } from 'react'

export function Modal({ title, onClose, children, width = 'max-w-lg' }: { title: ReactNode; onClose: () => void; children: ReactNode; width?: string }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-[100] grid place-items-center bg-slate-900/40 p-4" onMouseDown={onClose}>
      <div role="dialog" aria-modal className={`panel w-full ${width} p-6 shadow-2xl`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-fg">{title}</h2>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-[13px] text-fg-3 hover:bg-muted hover:text-fg">Close</button>
        </div>
        {children}
      </div>
    </div>
  )
}
