import { useState } from 'react'

import { Card, CardTitle, Select, Stat } from '../../components/ui'
import { useAssistantContext } from '../../lib/assistant'
import { usePlant } from '../../lib/plant'
import { PhotoPicker } from './PhotoReader'
import { useReader } from './usePhotoReader'

/** A machine's rating plate, compared with what MeterZero sees it draw. */
export function Nameplate() {
  const r = useReader('nameplate')
  const { plant } = usePlant()
  const machines = plant?.machines.filter((m) => m.id !== 'other') ?? []
  const [machine, setMachine] = useState('compressor')
  const plate = r.result as { manufacturer: string; model: string; machine_type: string; rated_power_kw: number; voltage_v: number; current_a: number; year: string } | null
  const chosen = machines.find((m) => m.id === machine) ?? machines[0]
  const ratio = plate && chosen ? chosen.peak_kw / Math.max(plate.rated_power_kw, 0.01) : 0
  useAssistantContext('Bills & paperwork', 'Looking at a machine nameplate photo.', ['Is this machine the right size for its job?'])
  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <div className="xl:col-span-5"><PhotoPicker r={r} label="Nameplate" /></div>
      <Card className="xl:col-span-7">
        <CardTitle>What the plate says</CardTitle>
        {!plate && <div className="text-[14px] text-fg-3">Read the photo to see the plate's details here.</div>}
        {plate && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <Stat label="Rated power" value={`${plate.rated_power_kw} kW`} sub={plate.machine_type} />
              <Stat label="Made by" value={<span className="text-lg">{plate.manufacturer || '–'}</span>} sub={[plate.model, plate.year].filter(Boolean).join(' · ')} />
            </div>
            <label className="mt-5 block text-[13px] font-medium text-fg-2">Which machine is this?</label>
            <Select value={chosen?.id} onChange={(e) => setMachine(e.target.value)} className="mt-1.5">
              {machines.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </Select>
            {chosen && (
              <div className={`mt-4 rounded-lg border p-4 text-[14px] leading-relaxed ${ratio > 1.15 ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'}`}>
                {ratio > 1.15
                  ? `MeterZero sees peaks of ${chosen.peak_kw.toFixed(1)} kW, above the ${plate.rated_power_kw} kW rating. It may be overloaded, or mixed with another load.`
                  : ratio < 0.3
                    ? `MeterZero's peak (${chosen.peak_kw.toFixed(1)} kW) is far below the ${plate.rated_power_kw} kW rating: it's oversized for its job or rarely runs flat out.`
                    : `Consistent: rated ${plate.rated_power_kw} kW, MeterZero sees peaks of ${chosen.peak_kw.toFixed(1)} kW (${Math.round(ratio * 100)}% of rating).`}
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  )
}
