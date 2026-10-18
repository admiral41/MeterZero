// Shapes returned by the MeterZero API (server/views.py).

export interface PlantSummary {
  id: string
  name: string
  description: string
  reference: boolean
  machines: number
  lines: number
  trained: boolean
  training: boolean
}

export interface Room { id: string; name: string; x: number; y: number; w: number; d: number }
export interface Product { name: string; load: number; rate: number }
export interface Line { id: string; name: string; products: Product[] }
export interface MachineSpec {
  id: string; name: string; type: string; line: string; rated_kw: number; x: number; y: number; rotation: number
}
export interface PlantSpec {
  id: string; name: string; description: string; reference: boolean; days: number; seed: number
  shift_start: number; shift_end: number; saturday_end: number
  floor_w: number; floor_d: number; panel_x: number; panel_y: number; cable_y: number | null
  rooms: Room[]; lines: Line[]; machines: MachineSpec[]
  fault: { machine: string; start_day: number; kind: string } | null
}

export interface MachineType {
  id: string; label: string; description: string; serves: 'line' | 'shared' | 'building'
  default_kw: number; size: [number, number, number]; shape: string
}

export interface MachineMeta {
  id: string; name: string; line: string; group: string; type: string; type_label: string; shape: string
  size: [number, number, number]; rated_kw: number; x: number; y: number; rotation: number; color: string; peak_kw: number
}

export interface PlantPayload {
  spec: PlantSpec
  machines: MachineMeta[]
  days: string[]
  default_day: string
  period: [string, string]
}

export interface MachineSeries { kw: number[]; low: number[]; high: number[]; hidden: number[]; state: number[] }
export interface Timeline {
  day: string; weekday: string; minutes: number; meter: number[]
  machines: Record<string, MachineSeries>; lights: number[]
  batches: { line: string; product: string; units: number; start: number; end: number }[]
  alerts: { machine: string; from: number; to: number; usual_kw: number; observed_kw: number }[]
  events: { minute: number; text: string }[]
  price_by_hour: number[]; band_by_hour: string[]; currency: string
}

export interface Kpis {
  energy_kwh: number; monthly_bill: number; peak_kw: number; idle_kwh: number; idle_share: number
  accuracy: number; accuracy_with_sensors: number; sensors_needed: number; coverage: number; currency: string
}
export interface Action { kind: string; machine: string; title: string; why: string; monthly_saving: number; plus_minus: number; shift?: { line: string; hours: number } | null }
export interface Overview {
  name: string; kpis: Kpis; actions: Action[]
  morning: { day: string; weekday: string; days: string[]; lines: { kind: string; text: string; good: boolean | null }[] }
  flows: { nodes: { name: string; color: string; kind: string }[]; links: { source: number; target: number; value: number }[] }
  machines: { id: string; name: string; color: string; group: string; kwh: number; share: number; plus_minus: number }[]
  repairs: Repair[]
  review: { headline: string; recorded_at: string } | null
  period: [string, string]
}
export interface Repair {
  machine: string; name: string; excess_kw: number; monthly_kwh_wasted: number; monthly_saving: number
  monthly_saving_plus_minus_90pct: number; yearly_saving: number; currency: string; since: string; nights: number
  usual_kw: number; observed_kw: number; text: string
}

export interface Prices {
  currency: string; demand_charge: number; region: string; demand_unit: string; co2_kg_per_kwh: number
  bands: { name: string; start: number; end: number; price: number; share: number; cost: number }[]
  monthly_bill: number; peak_kw: number; demand_cost: number; hourly_kw: number[]; price_by_hour: number[]
}
export interface ShiftPlan {
  change: string; batches_moved: number; kwh_moved_per_week: number; monthly_saving: number
  monthly_saving_plus_minus_90pct: number; monthly_bill_before: number; monthly_bill_after: number
  peak_kw_before: number; peak_kw_after: number; batches_that_clash_with_other_batches: number
  batches_needing_staff_outside_current_hours: number; currency: string; before: number[]; after: number[]
}

export interface Accuracy {
  ladder: { model: string; accuracy: number }[]
  coverage_curve: { claimed: number; actual: number }[]
  coverage: { minute: number; daily: number; batch: number }
  by_machine: { id: string; name: string; mae_kw: number; true_kwh: number; estimated_kwh: number; error_pct: number; inside_range: number }[]
  budget: { sensors: number; added: string; recommended: number; random: number }[]
  sensor_check: { machine: string; expected: number; actual: number }[]
  products: { product: string; line: string; estimated: number; plus_minus: number; true: number; error_pct: number; units: number }[]
}

export interface Finding {
  title: string; kind: string; machine: string; evidence: string; monthly_saving: number
  saving_plus_minus: number; confidence: string; action: string
}
export interface ToolCall { tool: string; args: Record<string, unknown> | unknown[]; result: unknown }

export interface Job { plant_id: string; state: string; steps: string[]; started?: number; finished?: number | null; error?: string }
