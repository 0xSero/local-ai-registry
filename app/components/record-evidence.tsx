import Link from "next/link"

import { getSpeedSweep } from "@/lib/registry"

type EvidenceRow = {
  concurrency: number | null
  context_tokens: number | null
  decode: number | null
  key: string
  prefill: number | null
  status: string
  sweepId?: string
  ttft: number | null
}

function asRows(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object" && !Array.isArray(item)) : []
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function formatRate(value: number | null): string {
  return value === null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: 1 })
}

function evidenceFromSweep(id: string): EvidenceRow[] {
  const sweep = getSpeedSweep(id)
  if (!sweep) return []
  return sweep.rows.map((row, index) => ({
    concurrency: row.concurrency,
    context_tokens: row.context_tokens,
    decode: row.decode_tok_s_per_stream ?? row.decode_tok_s,
    key: `${id}:${index}`,
    prefill: row.prefill_tok_s,
    status: row.status,
    sweepId: id,
    ttft: row.ttft_ms_p50,
  }))
}

function evidenceFromRecord(record: Record<string, unknown>): EvidenceRow[] {
  const ids = Array.isArray(record.speed_sweep_ids) ? record.speed_sweep_ids.filter((item): item is string => typeof item === "string") : []
  if (ids.length > 0) return ids.flatMap(evidenceFromSweep)
  return asRows(record.rows).map((row, index) => ({
    concurrency: number(row.concurrency),
    context_tokens: number(row.context_tokens),
    decode: number(row.decode_tok_s_per_stream) ?? number(row.decode_tok_s),
    key: `row:${index}`,
    prefill: number(row.prefill_tok_s),
    status: typeof row.status === "string" ? row.status : typeof row.root === "string" ? row.root : "",
    ttft: number(row.ttft_ms_p50),
  }))
}

function benchmarkRows(record: Record<string, unknown>): Array<{ key: string; model: string; score: string }> {
  return asRows(record.rows).slice(0, 24).map((row, index) => ({
    key: `${String(row.root ?? row.model ?? index)}:${index}`,
    model: String(row.root ?? row.model ?? row.name ?? "Unknown"),
    score: number(row.score) === null ? "—" : String(number(row.score)),
  }))
}

export function RecordEvidence({ collection, record }: { collection: string; record: Record<string, unknown> }) {
  if (collection === "benchmark") {
    const rows = benchmarkRows(record)
    if (rows.length === 0) return null
    return (
      <section aria-label="Leaderboard scores" className="record-evidence">
        <p className="eyebrow">Scores</p>
        <table className="flag-table">
          <thead><tr><th>Model</th><th>Score</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}><td>{row.model}</td><td>{row.score}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
    )
  }

  if (collection !== "recipes" && collection !== "speed-sweep") return null
  const rows = evidenceFromRecord(record)
  if (rows.length === 0) return null
  return (
    <section aria-label="Measured speed" className="record-evidence">
      <p className="eyebrow">Measured speed</p>
      <table className="flag-table">
        <thead>
          <tr>
            <th>Concurrency</th>
            <th>Context</th>
            <th>Prefill</th>
            <th>Decode</th>
            <th>TTFT ms</th>
            <th>Status</th>
            {collection === "recipes" && <th>Sweep</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td>{row.concurrency ?? "—"}</td>
              <td>{row.context_tokens?.toLocaleString() ?? "—"}</td>
              <td>{formatRate(row.prefill)}</td>
              <td>{formatRate(row.decode)}</td>
              <td>{formatRate(row.ttft)}</td>
              <td>{row.status || "—"}</td>
              {collection === "recipes" && (
                <td>{row.sweepId ? <Link href={`/speed-sweep/${row.sweepId}`}>{row.sweepId}</Link> : "—"}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
