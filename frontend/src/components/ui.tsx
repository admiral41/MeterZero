import clsx from 'clsx'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

import { Spin } from './ai'

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={clsx('panel p-5', className)}>{children}</section>
}

/** A label with an explanation on hover: dotted underline, no icon. */
function Hint({ text, children }: { text?: string; children: ReactNode }) {
  if (!text) return <>{children}</>
  return (
    <span className="group relative cursor-help underline decoration-line-strong decoration-dotted underline-offset-4" tabIndex={0}>
      {children}
      <span className="pointer-events-none absolute left-0 top-full z-50 mt-2 hidden w-72 rounded-lg border border-line bg-surface p-3 text-[12.5px] font-normal normal-case leading-relaxed tracking-normal text-fg-2 no-underline shadow-lg group-hover:block group-focus:block">
        {text}
      </span>
    </span>
  )
}

export function CardTitle({ children, hint, right, sub }: { children: ReactNode; hint?: string; right?: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold text-fg"><Hint text={hint}>{children}</Hint></h2>
        {sub && <div className="mt-0.5 text-[13px] text-fg-3">{sub}</div>}
      </div>
      {right}
    </div>
  )
}

const TONE_TEXT = { default: 'text-fg', ok: 'text-emerald-700', bad: 'text-red-600', warn: 'text-amber-700' }

export function Stat({ label, value, sub, tone = 'default', hint, size = 'md' }: {
  label: string; value: ReactNode; sub?: ReactNode; tone?: keyof typeof TONE_TEXT; hint?: string; size?: 'sm' | 'md'
}) {
  return (
    <div className="min-w-0">
      <div className="text-[13px] text-fg-3"><Hint text={hint}>{label}</Hint></div>
      <div className={clsx('num mt-1 font-semibold leading-tight tracking-tight', size === 'sm' ? 'text-[20px]' : 'text-[26px]', TONE_TEXT[tone])}>{value}</div>
      {sub && <div className="mt-1 text-[13px] leading-snug text-fg-3">{sub}</div>}
    </div>
  )
}

/** Several stats in one card, divided by thin lines. */
export function StatStrip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx('panel grid divide-line sm:grid-cols-2 sm:divide-x xl:grid-cols-4 [&>*]:px-5 [&>*]:py-4', className)}>
      {children}
    </div>
  )
}

export function Badge({ children, tone = 'default', className }: { children: ReactNode; tone?: 'default' | 'accent' | 'ok' | 'warn' | 'bad' | 'ai' | 'sim'; className?: string }) {
  const styles = {
    default: 'bg-muted text-fg-2 border-line',
    accent: 'bg-brand-soft text-brand border-brand-line',
    ok: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    warn: 'bg-amber-50 text-amber-800 border-amber-200',
    bad: 'bg-red-50 text-red-700 border-red-200',
    ai: 'bg-violet-50 text-violet-700 border-violet-200',
    sim: 'bg-amber-50 text-amber-800 border-amber-200',
  }[tone]
  return <span className={clsx('inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-2 py-0.5 text-[12px] font-medium', styles, className)}>{children}</span>
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; loading?: boolean; size?: 'sm' | 'md'; icon?: ReactNode
}

export function Button({ variant = 'secondary', loading, size = 'md', className, children, disabled, icon, ...rest }: ButtonProps) {
  const styles = {
    primary: 'bg-brand text-white hover:bg-brand-strong',
    secondary: 'bg-surface text-fg border border-line-strong hover:bg-subtle',
    ghost: 'text-fg-2 hover:bg-muted hover:text-fg',
    danger: 'bg-surface text-red-700 border border-red-200 hover:bg-red-50',
  }[variant]
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'px-3 py-1.5 text-[13px]' : 'px-4 py-2 text-[14px]',
        styles,
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Spin /> : icon}
      {children}
    </button>
  )
}

function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-fg-3">
      <Spin className="text-brand" /> {label}
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex h-64 items-center justify-center">
      <Spinner label={label} />
    </div>
  )
}

export function ErrorBox({ error }: { error: unknown }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      {error instanceof Error ? error.message : String(error)}
    </div>
  )
}

export function Segmented<T extends string>({ value, options, onChange, className }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={clsx('inline-flex max-w-full overflow-x-auto rounded-lg border border-line bg-muted p-0.5', className)}>
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={clsx('whitespace-nowrap rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
            o.value === value ? 'bg-surface text-fg shadow-sm' : 'text-fg-3 hover:text-fg')}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-fg-2"><Hint text={hint}>{label}</Hint></span>
      {children}
    </label>
  )
}

const FIELD = 'w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-fg outline-none placeholder:text-fg-4 focus:border-brand focus:ring-2 focus:ring-brand-soft disabled:bg-subtle'

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx(FIELD, props.className)} />
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={clsx(FIELD, 'pr-8', props.className)} />
}

export function Dot({ color, pulse }: { color: string; pulse?: boolean }) {
  return <span className={clsx('inline-block h-2 w-2 shrink-0 rounded-full', pulse && 'pulse-bad')} style={{ background: color }} />
}

export function PageHeader({ title, subtitle, actions, badges }: { title: string; subtitle?: ReactNode; actions?: ReactNode; badges?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[22px] font-semibold tracking-tight text-fg sm:text-[24px]">{title}</h1>
          {badges}
        </div>
        {subtitle && <p className="mt-1.5 max-w-4xl text-[15px] leading-relaxed text-fg-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** Page wrapper: uses the whole width, with responsive padding. */
export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx('w-full px-4 py-6 sm:px-6 lg:px-8 lg:py-7 2xl:px-10', className)}>{children}</div>
}

/** A ranked list row: what, why, and what it's worth. */
export function Arrow() {
  return <span aria-hidden className="text-fg-4 transition group-hover:translate-x-0.5 group-hover:text-brand">→</span>
}
