import Link from "next/link"

import type { RecordFact } from "@/app/lib/record-view"

export function RecordFacts({ facts }: { facts: RecordFact[] }) {
  if (facts.length === 0) return null
  return (
    <section aria-label="Record fields" className="record-facts">
      <p className="eyebrow">Record</p>
      <dl>
        {facts.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>{item.href ? <Link href={item.href}>{item.value}</Link> : item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
