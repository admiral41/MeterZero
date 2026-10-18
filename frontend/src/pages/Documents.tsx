import { useState } from 'react'

import { NotTrained } from '../components/NotTrained'
import { Badge, Page, PageHeader, Segmented } from '../components/ui'
import { usePlant } from '../lib/plant'
import { Bills } from './paperwork/Bills'
import { Logbook } from './paperwork/Logbook'
import { Nameplate } from './paperwork/Nameplate'

type Kind = 'bill' | 'logbook' | 'nameplate'

export default function Documents() {
  const { untrained } = usePlant()
  const [kind, setKind] = useState<Kind>('bill')
  if (untrained) return <NotTrained />
  return (
    <Page>
      <PageHeader title="Bills & paperwork" badges={<Badge tone="ai">Gemini vision</Badge>}
        subtitle="Electricity bills, production logbooks and machine nameplates are still on paper. Gemini reads a photo; MeterZero checks every line against what it measured, and finds what the paper hides."
        actions={<Segmented value={kind} onChange={setKind} options={[
          { value: 'bill', label: 'Electricity bills' }, { value: 'logbook', label: 'Production logbook' }, { value: 'nameplate', label: 'Machine nameplate' }]} />} />
      {kind === 'bill' && <Bills />}
      {kind === 'logbook' && <Logbook />}
      {kind === 'nameplate' && <Nameplate />}
    </Page>
  )
}

