import type { Metadata } from "next"
import Link from "next/link"

import { CollectionNav } from "@/app/components/collection-nav"
import { hardwareComparison, type HardwareComparisonRow } from "@/lib/registry"

export const dynamic = "force-dynamic"

export const metadata: Metadata = { title: "Compare hardware · Local AI Registry" }

type SortKey = "name" | "vram" | "bandwidth" | "fp16" | "fp8" | "fp4" | "int8" | "price" | "recipes"

const COLUMNS: Array<{ key: SortKey; label: string }> = [
  { key: "name", label: "Hardware" },
  { key: "vram", label: "VRAM" },
  { key: "bandwidth", label: "Bandwidth" },
  { key: "fp16", label: "FP16 TFLOPS" },
  { key: "fp8", label: "FP8 TFLOPS" },
  { key: "fp4", label: "FP4 TFLOPS" },
  { key: "int8", label: "INT8 TOPS" },
  { key: "price", label: "Lowest new (US)" },
  { key: "recipes", label: "Recipes" },
]

function metric(row: HardwareComparisonRow, key: SortKey): number | string | null {
  if (key === "name") return row.name
  if (key === "vram") return row.vram_gb
  if (key === "bandwidth") return typeof row.bandwidth_gb_per_s === "object" && row.bandwidth_gb_per_s !== null ? row.bandwidth_gb_per_s.max : row.bandwidth_gb_per_s
  if (key === "fp16") return row.fp16_tflops
  if (key === "fp8") return row.fp8_tflops
  if (key === "fp4") return row.fp4_tflops
  if (key === "int8") return row.int8_tflops
  if (key === "price") return row.lowest_new_usd
  return row.recipe_count
}

function cell(value: number | null, sparse = false): string {
  if (value === null) return "—"
  return `${value.toLocaleString("en-US")}${sparse ? " *" : ""}`
}

function bandwidth(value: HardwareComparisonRow["bandwidth_gb_per_s"]): string {
  if (value === null) return "—"
  if (typeof value === "object") return `${value.min.toLocaleString("en-US")}–${value.max.toLocaleString("en-US")} GB/s`
  return `${value.toLocaleString("en-US")} GB/s`
}

function measured(value: number | null, unit: string, maximumFractionDigits = 0): string {
  if (value === null) return "—"
  return `${value.toLocaleString("en-US", { maximumFractionDigits })} ${unit}`
}

export default async function ComparePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams
  const sortParam = Array.isArray(params.sort) ? params.sort[0] : params.sort
  const sort: SortKey = COLUMNS.some((column) => column.key === sortParam) ? (sortParam as SortKey) : "recipes"
  const vendorParam = Array.isArray(params.vendor) ? params.vendor[0] : params.vendor ?? ""

  let rows = hardwareComparison()
  const vendors = [...new Set(rows.map((row) => row.vendor))].sort()
  if (vendorParam) rows = rows.filter((row) => row.vendor === vendorParam)
  rows.sort((left, right) => {
    if (sort === "name") return left.name.localeCompare(right.name, undefined, { numeric: true })
    const a = metric(left, sort) as number | null
    const b = metric(right, sort) as number | null
    return (b ?? -1) - (a ?? -1) || left.name.localeCompare(right.name)
  })
  const measuredRows = [...rows]
    .filter((row) => row.speed_sweep_count > 0)
    .sort(
      (left, right) =>
        right.evidence_point_count - left.evidence_point_count
        || right.speed_sweep_count - left.speed_sweep_count
        || left.name.localeCompare(right.name),
    )

  const href = (key: SortKey) => `/compare?sort=${key}${vendorParam ? `&vendor=${vendorParam}` : ""}`

  return (
    <main className="detail-page">
      <CollectionNav current="hardware" />
      <header className="topic-heading">
        <div>
          <span className="mono-label">COLLECTION / COMPARE</span>
          <h1>Compare hardware</h1>
          <p className="topic-description">
            Every accelerator side by side: memory, vendor-published throughput, the lowest live US listing, and how
            many launch recipes the registry holds. Click a column to rank by it; * marks structured-sparsity figures
            where the vendor publishes no dense number.
          </p>
        </div>
        <span className="topic-total">
          {rows.length.toLocaleString("en-US")} devices · {measuredRows.length.toLocaleString("en-US")} measured
        </span>
      </header>
      <nav aria-label="Vendor filter" className="breadcrumbs">
        <Link href={`/compare?sort=${sort}`}>{vendorParam ? "all vendors" : "· all vendors"}</Link>
        {vendors.map((vendor) => (
          <Link href={`/compare?sort=${sort}&vendor=${vendor}`} key={vendor}>{vendorParam === vendor ? `· ${vendor}` : vendor}</Link>
        ))}
      </nav>
      <section aria-label="Published hardware specifications" className="record-evidence">
        <p className="eyebrow">Published specifications</p>
        <p className="trust-note">
          Vendor-published compute figures. Missing precision columns remain blank instead of being estimated from a
          different datatype or sparse mode.
        </p>
        <div className="compare-table-scroll">
          <table className="flag-table">
            <thead>
              <tr>
                {COLUMNS.map((column) => (
                  <th key={column.key} scope="col">
                    <Link href={href(column.key)}>{sort === column.key ? `▾ ${column.label}` : column.label}</Link>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td><Link href={`/hardware/${row.id}`}>{row.name}</Link></td>
                  <td>{row.vram_gb.toLocaleString("en-US")} GB</td>
                  <td>{bandwidth(row.bandwidth_gb_per_s)}</td>
                  <td>{cell(row.fp16_tflops, row.fp16_sparse)}</td>
                  <td>{cell(row.fp8_tflops, row.fp8_sparse)}</td>
                  <td>{cell(row.fp4_tflops, row.fp4_sparse)}</td>
                  <td>{cell(row.int8_tflops, row.int8_sparse)}</td>
                  <td>{row.lowest_new_usd === null ? "—" : `$${row.lowest_new_usd.toLocaleString("en-US", { maximumFractionDigits: 0 })}`}</td>
                  <td>{row.recipe_count.toLocaleString("en-US")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section aria-label="Measured local inference" className="record-evidence">
        <p className="eyebrow">Measured local inference</p>
        <p className="trust-note">
          Best observed values across the registry&apos;s cited speed sweeps. The Model variants column counts
          distinct model-instance records. Model, quantization, engine, context, and concurrency differ between runs;
          use these as an evidence index, not an equal-workload ranking.
        </p>
        {measuredRows.length === 0 ? (
          <p className="trust-note">No speed evidence is available for this vendor.</p>
        ) : (
          <div className="compare-table-scroll">
            <table className="flag-table">
              <thead>
                <tr>
                  <th scope="col">Hardware</th>
                  <th scope="col">Sweeps</th>
                  <th scope="col">Points</th>
                  <th scope="col">Model variants</th>
                  <th scope="col">Peak prefill</th>
                  <th scope="col">Peak decode</th>
                  <th scope="col">Best TTFT</th>
                  <th scope="col">Max observed context</th>
                  <th scope="col">Peak observed VRAM</th>
                </tr>
              </thead>
              <tbody>
                {measuredRows.map((row) => (
                  <tr key={row.id}>
                    <td><Link href={`/hardware/${row.id}`}>{row.name}</Link></td>
                    <td>{row.speed_sweep_count.toLocaleString("en-US")}</td>
                    <td>{row.evidence_point_count.toLocaleString("en-US")}</td>
                    <td>{row.measured_model_count.toLocaleString("en-US")}</td>
                    <td>{measured(row.peak_prefill_tok_s, "tok/s", 1)}</td>
                    <td>{measured(row.peak_decode_tok_s, "tok/s", 1)}</td>
                    <td>{measured(row.fastest_ttft_ms, "ms", 1)}</td>
                    <td>{measured(row.max_observed_context_tokens, "tokens")}</td>
                    <td>{measured(row.peak_observed_vram_gb, "GB", 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}
