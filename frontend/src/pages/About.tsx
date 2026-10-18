import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Card, Page, PageHeader } from '../components/ui'

const FLOW = [
  { title: 'One meter and the schedule', text: 'The main meter\'s reading every minute, the production log (or a photo of the paper one), and prices from the electricity bill.' },
  { title: 'The MeterZero engine', text: 'Learns how each machine behaves, splits the meter so every minute adds up, gives each figure a likely range, spots waste and prices every change.' },
  { title: 'Gemini on top', text: 'Reads photos, audits the week with 15 tools, answers questions by text or voice, and writes summaries and repair requests.' },
  { title: 'You act on it', text: 'A 3D digital twin, a ranked list of what to fix, what-if pricing, a bill check, and proof against hidden meters.' },
]

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="mb-4 text-[17px] font-semibold text-fg">{title}</h2>
      {children}
    </section>
  )
}

function Item({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <div className="font-semibold text-fg">{title}</div>
      <div className="mt-1.5 text-[14px] leading-relaxed text-fg-2">{children}</div>
    </Card>
  )
}

export default function About() {
  return (
    <Page>
      <PageHeader title="How it works"
        subtitle="Most factories pay one electricity bill and can't say which machine or product it went on. MeterZero works that out from the one meter they already have, and Gemini turns it into decisions." />

      <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {FLOW.map((step, i) => (
          <li key={step.title} className="panel p-5">
            <div className="num text-[13px] font-semibold text-brand">Step {i + 1}</div>
            <div className="mt-1 font-semibold text-fg">{step.title}</div>
            <p className="mt-1.5 text-[14px] leading-relaxed text-fg-2">{step.text}</p>
          </li>
        ))}
      </ol>

      <Section title="Where Gemini is used">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Item title="Reading paperwork">Vision with structured output turns bills, handwritten logbooks and nameplates into checked fields.</Item>
          <Item title="An auditor that acts">Function calling: Gemini plans a review, makes up to 25 lookups, compares options and returns findings the app turns into cards.</Item>
          <Item title="An assistant on every page">The floating assistant knows what you're looking at: the machine selected in the twin, the bill on screen, the change you're trying.</Item>
          <Item title="Plain answers">Chat, voice questions and weekly summaries. It never sees the hidden meters, and every answer shows the numbers it used.</Item>
        </div>
      </Section>

      <Section title="Why trust it">
        <div className="grid gap-4 md:grid-cols-3">
          <Item title="Checked against hidden meters">On days it never saw: 88% accurate from one meter, 95% with two well-placed extra meters.</Item>
          <Item title="Honest ranges">“Likely between” holds about 9 times in 10, tuned on one week and tested on another.</Item>
          <Item title="Works on any plant">Design a plant from 15 machine types, simulate it and watch MeterZero learn it: about 90% accurate on the bakery and garment templates.</Item>
        </div>
      </Section>

      <Section title="A five-minute demo">
        <Card>
          <ol className="list-decimal space-y-2 pl-5 text-[14px] leading-relaxed text-fg-2">
            <li><Link className="font-medium text-brand hover:underline" to="/p/demo/overview">Overview</Link>: one meter, a week, and what to fix first.</li>
            <li><Link className="font-medium text-brand hover:underline" to="/p/demo/twin">Digital twin</Link>: press play, jump to Night, click the machine flagged in red, then ask Gemini why.</li>
            <li><Link className="font-medium text-brand hover:underline" to="/p/demo/documents">Bills & paperwork</Link>: February's bill was overcharged; December's had a power factor surcharge.</li>
            <li><Link className="font-medium text-brand hover:underline" to="/p/demo/savings">Find savings</Link>: run the Gemini review and watch it work.</li>
            <li><Link className="font-medium text-brand hover:underline" to="/plants">All plants</Link>: create a bakery, simulate it and train MeterZero in about a minute.</li>
          </ol>
        </Card>
      </Section>

      <Section title="Built on Google Cloud">
        <Card>
          <p className="max-w-4xl text-[14px] leading-relaxed text-fg-2">
            One container on <b className="font-medium text-fg">Cloud Run</b>: a FastAPI server with the MeterZero engine and Gemini (an AI Studio key or Vertex AI),
            serving this React and Three.js app.
          </p>
        </Card>
      </Section>
    </Page>
  )
}
