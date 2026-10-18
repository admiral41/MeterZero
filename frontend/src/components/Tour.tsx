import { useState } from 'react'

import { markTourSeen } from '../lib/tour'
import { Modal } from './Modal'
import { Button } from './ui'

const STEPS = [
  { title: 'One meter for the whole factory',
    text: 'Most factories only get the electricity company\'s meter: one number for the whole site. Nobody knows which machine or product the money went on.' },
  { title: 'See every machine, live',
    text: 'MeterZero splits that one reading into machines, with a likely range for each. The Digital twin shows it in 3D: watch electricity flow through the cables to every machine.' },
  { title: 'Gemini finds the savings',
    text: 'Google\'s Gemini reviews the week like an energy auditor: it spots waste, prices repairs and schedule changes, and answers questions in plain words, using only MeterZero\'s numbers.' },
  { title: 'Paper becomes data',
    text: 'Photograph your electricity bill or a handwritten logbook. Gemini reads it, MeterZero checks every line: overcharges, power factor surcharges, demand charges, and what each product really cost.' },
  { title: 'Design any plant',
    text: 'In the Plant designer, place machines from a library, set up lines and products, then simulate and train. MeterZero learns your plant in about a minute.' },
  { title: 'Checked, not guessed',
    text: 'The demo plants have hidden meters on every machine, so every figure can be checked: 88% accurate from one meter, and the ranges hold 9 times in 10.' },
]


export function Tour({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0)
  const close = () => {
    markTourSeen()
    onClose()
  }
  const { title, text } = STEPS[step]
  return (
    <Modal title="Welcome to MeterZero" onClose={close} width="max-w-xl">
      <div className="mb-5 flex gap-1.5">
        {STEPS.map((_, i) => (
          <div key={i} className={`h-1 flex-1 rounded-full ${i <= step ? 'bg-brand' : 'bg-muted'}`} />
        ))}
      </div>
      <div className="flex gap-4">
        <div>
          <h3 className="text-lg font-semibold text-fg">{title}</h3>
          <p className="mt-2 leading-relaxed text-fg-2">{text}</p>
        </div>
      </div>
      <div className="mt-7 flex items-center justify-between">
        <span className="text-xs text-fg-4">Step {step + 1} of {STEPS.length}</span>
        <div className="flex gap-2">
          {step > 0 && <Button variant="ghost" onClick={() => setStep(step - 1)}>Back</Button>}
          {step < STEPS.length - 1 ? (
            <>
              <Button variant="ghost" onClick={close}>Skip</Button>
              <Button variant="primary" onClick={() => setStep(step + 1)}>Next</Button>
            </>
          ) : (
            <Button variant="primary" onClick={close}>Start exploring</Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
