import { Link } from 'react-router-dom'

import { usePlant } from '../lib/plant'

export function NotTrained() {
  const { plantId } = usePlant()
  return (
    <div className="grid h-full place-items-center p-10">
      <div className="panel max-w-md p-8 text-center">
        <h2 className="text-lg font-semibold text-fg">This plant hasn't been trained yet</h2>
        <p className="mt-2 text-sm leading-relaxed text-fg-2">
          Open it in the Plant designer and press <b>Simulate &amp; train</b>. MeterZero generates its data and learns it in about a minute.
        </p>
        <Link to={`/designer/${plantId}`} className="mt-5 inline-flex rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong">
          Open the designer
        </Link>
      </div>
    </div>
  )
}
