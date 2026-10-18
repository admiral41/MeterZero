import { Link, useRouteError } from 'react-router-dom'

/** Shown instead of a blank screen if a page fails to render. */
export function ErrorPage() {
  const error = useRouteError()
  const message = error instanceof Error ? error.message : String(error ?? 'Unknown error')
  return (
    <div className="grid min-h-full place-items-center bg-canvas p-6">
      <div className="panel w-full max-w-md p-8 text-center">
        <img src="/brand/logo.png" alt="MeterZero" className="mx-auto h-8 w-auto" />
        <h1 className="mt-6 text-[18px] font-semibold text-fg">This page ran into a problem</h1>
        <p className="mt-2 text-[14px] leading-relaxed text-fg-2">Your data is safe. Reload the page, or go back to the overview.</p>
        <div className="mt-5 flex justify-center gap-2">
          <button onClick={() => window.location.reload()} className="rounded-lg bg-brand px-4 py-2 text-[14px] font-medium text-white hover:bg-brand-strong">Reload</button>
          <Link to="/" reloadDocument className="rounded-lg border border-line-strong px-4 py-2 text-[14px] font-medium text-fg hover:bg-subtle">Go to the overview</Link>
        </div>
        <details className="mt-5 text-left text-[12px] text-fg-3">
          <summary className="cursor-pointer">Technical details</summary>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-md bg-subtle p-3">{message}</pre>
        </details>
      </div>
    </div>
  )
}
