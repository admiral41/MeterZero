const LOCALE = 'meterzero.locale'

/** Number and date formats follow the plant's region (set in Settings). */
export function locale(): string | undefined {
  try {
    return localStorage.getItem(LOCALE) ?? undefined
  } catch {
    return undefined
  }
}

export function setLocale(value: string) {
  try {
    localStorage.setItem(LOCALE, value)
  } catch {
    /* fine */
  }
}

const num = (v: number) => v.toLocaleString(locale())

export const fmt = {
  kwh: (v: number | null | undefined) => (v == null ? '–' : `${num(Math.round(v))} kWh`),
  kw: (v: number | null | undefined, digits = 1) => (v == null ? '–' : `${v.toFixed(digits)} kW`),
  money: (v: number | null | undefined, currency: string) =>
    v == null ? '–' : `${currency}${num(Math.round(v))}`,
  pct: (v: number | null | undefined, digits = 0) => (v == null ? '–' : `${(v * 100).toFixed(digits)}%`),
  range: (value: number, plusMinus: number, currency = '') =>
    `${currency}${num(Math.max(Math.round(value - plusMinus), 0))}–${currency}${num(Math.round(value + plusMinus))}`,
  clock: (minute: number) => {
    const m = Math.max(0, Math.min(1439, Math.floor(minute)))
    return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
  },
  hours: (start: number, end: number) => `${String(start).padStart(2, '0')}:00–${String(end).padStart(2, '0')}:00`,
  day: (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' }),
}

export const BAND_COLOR: Record<string, string> = { peak: '#dc2626', normal: '#9ca3af', 'off-peak': '#16a34a' }

export const STATE_LABEL = ['Off', 'Idle', 'Running'] as const
export const STATE_COLOR = ['#9ca3af', '#d97706', '#16a34a'] as const
