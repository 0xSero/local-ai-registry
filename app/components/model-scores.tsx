import Link from "next/link"

import { getModelBenchmarkScores } from "@/lib/registry"

export function ModelScores({ modelId }: { modelId: string }) {
  const scores = getModelBenchmarkScores(modelId)
  if (scores.length === 0) return null
  const rows = [...scores].sort(
    (left, right) =>
      (left.category ?? "").localeCompare(right.category ?? "") ||
      left.benchmark_id.localeCompare(right.benchmark_id),
  )
  return (
    <section aria-label="Public leaderboard scores" className="record-evidence">
      <p className="eyebrow">Leaderboard scores</p>
      <p className="trust-note">
        Scraped public quality scores joined to this model by its Hugging Face repository. They describe the listed
        variant, not any specific local quantization, and are never speed measurements.
      </p>
      <table className="flag-table">
        <thead>
          <tr>
            <th>Benchmark</th>
            <th>Category</th>
            <th>Score</th>
            <th>Rank</th>
            <th>Scored variant</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.benchmark_id}-${index}`}>
              <td><Link href={`/benchmark/${row.benchmark_id}`}>{row.benchmark_id}</Link></td>
              <td>{row.category ?? "—"}</td>
              <td>{row.score ?? "—"}</td>
              <td>{row.rank ?? "—"}</td>
              <td>{row.variant ?? "—"}</td>
              <td>{row.conf ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
