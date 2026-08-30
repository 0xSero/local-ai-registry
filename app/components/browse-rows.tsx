import Link from "next/link"
import type { ReactNode } from "react"

import { hrefWithFilter, hrefWithRecord } from "@/app/lib/catalog"
import {
  getSpeedSweep,
  marketPriceCount,
  recipeCountForHardware,
  runtimeGroup,
  type CompatibilityResult,
  type PriceResult,
} from "@/lib/registry"
import type { Benchmark, Hardware, Model, SpeedSweep } from "@/registry/schema/types"

export type RowTag = {
  label: string
  name: string
  value: string
}

const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  currency: "USD",
  maximumFractionDigits: 0,
  style: "currency",
})

function numberField(record: Record<string, unknown>, key: string): number | null {
  const value = record[key]
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function formatTokens(value: number | null): string {
  if (value === null) return "Unknown context"
  if (value >= 1024) {
    const thousands = value / 1024
    return `${Number.isInteger(thousands) ? thousands : thousands.toFixed(1)}K`
  }
  return value.toLocaleString()
}

function formatRate(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 })
}

function formatAmount(amount: number, currency: string): string {
  return currency === "USD" ? USD_FORMATTER.format(amount) : `${currency} ${amount.toLocaleString()}`
}

function peakSpeed(rows: Array<{ decode_tok_s_per_stream?: number | null; decode_tok_s?: number | null; prefill_tok_s?: number | null }>): number | null {
  const values = rows.flatMap((row) => {
    const value = row.decode_tok_s_per_stream ?? row.decode_tok_s ?? row.prefill_tok_s
    return typeof value === "number" ? [value] : []
  })
  return values.length > 0 ? Math.max(...values) : null
}

function recipeEvidence(result: CompatibilityResult) {
  return result.recipe.speed_sweeps_ids.flatMap((sweepId) => {
    const sweep = getSpeedSweep(sweepId)
    return sweep ? sweep.rows : []
  })
}

function TaxonomyTags({ state, tags }: { state: URLSearchParams; tags: RowTag[] }) {
  return (
    <span className="taxonomy-tags">
      {tags.slice(0, 4).map((tag) => (
        <Link aria-label={`Filter by ${tag.label}`} href={hrefWithFilter(state, tag.name, tag.value)} key={`${tag.name}:${tag.value}`}>
          {tag.label}
        </Link>
      ))}
    </span>
  )
}

function BrowserRow({
  children,
  className,
  href,
  label,
  state,
  status,
  tags,
}: {
  children: ReactNode
  className: string
  href: string
  label: string
  state: URLSearchParams
  status?: "validated" | "candidate"
  tags: RowTag[]
}) {
  return (
    <article className={`browser-row ${className}`}>
      <Link aria-label={label} className="row-open" href={href} scroll={false} />
      {status && <span className={`status-mark ${status}`} aria-hidden="true" />}
      {children}
      <TaxonomyTags state={state} tags={tags} />
      <svg aria-hidden="true" className="row-arrow" viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
    </article>
  )
}

export function RecipeRows({ by, data, state }: { by: "hardware" | "model"; data: CompatibilityResult[]; state: URLSearchParams }) {
  return (
    <div className="browser-list recipe-browser-list">
      {data.map((result) => {
        const context = numberField(result.recipe.serving, "max_context_tokens")
        const speed = peakSpeed(recipeEvidence(result))
        const validation = result.launchable ? "validated" : "candidate"
        const runtime = runtimeGroup(result.recipe.launch.kind)
        const tags: RowTag[] = [
          { label: validation, name: "validation", value: validation },
          { label: result.recipe.engine.name, name: "engine", value: result.recipe.engine.name },
          { label: runtime === "docker" ? "docker" : runtime === "native" ? "no docker" : "evidence", name: "runtime", value: runtime },
          { label: result.speed_evidence.available ? "measured" : "unmeasured", name: "evidence", value: String(result.speed_evidence.available) },
          { label: `${result.hardware.memory.vram_gb} GB+`, name: "min_vram_gb", value: String(result.hardware.memory.vram_gb) },
        ]
        const hardware = (
          <span className={by === "hardware" ? "row-primary" : undefined}>
            <strong>{result.hardware.name}</strong>
            <small>{result.recipe.hardware_count} × {result.hardware.memory.vram_gb} GB</small>
          </span>
        )
        const model = (
          <span className={by === "model" ? "row-primary" : undefined}>
            <strong>{result.model.name}</strong>
            <small>{result.model_instance.weights.precision ?? result.model_instance.weights.format ?? "Unknown precision"}</small>
          </span>
        )
        return (
          <BrowserRow
            className="recipe-browser-row"
            href={hrefWithRecord(state, result.id)}
            key={result.id}
            label={`Open ${result.model.name} recipe`}
            state={state}
            status={validation}
            tags={tags}
          >
            {by === "hardware" ? hardware : model}
            {by === "hardware" ? model : hardware}
            <span><strong>{result.recipe.engine.name}</strong><small>{result.recipe.launch.kind}</small></span>
            <span><strong>{formatTokens(context)}</strong><small>context</small></span>
            <span><strong>{speed === null ? "—" : `${formatRate(speed)} tok/s`}</strong><small>{result.speed_evidence.available ? "measured" : "no evidence"}</small></span>
          </BrowserRow>
        )
      })}
    </div>
  )
}

export function PriceRows({ data, state }: { data: PriceResult[]; state: URLSearchParams }) {
  return (
    <div className="browser-list collection-list">
      {data.map((record) => {
        const amount = record.summary.lowest_new ?? record.summary.lowest_refurbished ?? record.summary.lowest_used
        const condition = record.summary.lowest_new !== null
          ? "new"
          : record.summary.lowest_refurbished !== null ? "refurbished" : record.summary.lowest_used !== null ? "used" : "unavailable"
        const tags: RowTag[] = [
          { label: record.region.code, name: "region", value: record.region.code },
          { label: record.product.category, name: "category", value: record.product.category },
          { label: condition, name: "condition", value: condition },
        ]
        return (
          <BrowserRow
            className="price-row"
            href={hrefWithRecord(state, record.id)}
            key={record.id}
            label={`Open ${record.product.name} market observations`}
            state={state}
            tags={tags}
          >
            <span className="row-primary"><strong>{record.product.name}</strong><small>{record.product.id}</small></span>
            <span><strong>{amount === null ? "No available listing" : formatAmount(amount, record.region.currency)}</strong><small>lowest available · {condition}</small></span>
            <span><strong>{record.region.name}</strong><small>{record.region.currency}</small></span>
            <span><strong>{record.observed_at.slice(0, 10)}</strong><small>observed</small></span>
            <span><strong>{record.summary.listing_count} listings</strong><small>{record.summary.retailer_count} retailers</small></span>
          </BrowserRow>
        )
      })}
    </div>
  )
}

export function HardwareRows({ data, state }: { data: Hardware[]; state: URLSearchParams }) {
  return (
    <div className="browser-list collection-list">
      {data.map((hardware) => {
        const hasPrices = marketPriceCount(hardware.id) > 0
        const recipes = recipeCountForHardware(hardware.id)
        const tags: RowTag[] = [
          { label: hardware.vendor, name: "vendor", value: hardware.vendor },
          { label: hardware.accelerator_backend, name: "backend", value: hardware.accelerator_backend },
          { label: `${hardware.memory.vram_gb} GB+`, name: "min_vram_gb", value: String(hardware.memory.vram_gb) },
          ...(hasPrices ? [{ label: "priced", name: "priced_only", value: "true" }] : []),
          { label: recipes > 0 ? `${recipes} recipes` : "no recipes", name: "has_recipes", value: recipes > 0 ? "true" : "false" },
        ]
        return (
          <BrowserRow
            className="collection-row"
            href={hrefWithRecord(state, hardware.id)}
            key={hardware.id}
            label={`Open ${hardware.name}`}
            state={state}
            tags={tags}
          >
            <span className="row-primary"><strong>{hardware.name}</strong><small>{hardware.id}</small></span>
            <span><strong>{hardware.vendor}</strong><small>{hardware.kind}</small></span>
            <span><strong>{hardware.memory.vram_gb} GB</strong><small>{hardware.memory.vram_type ?? "Memory type unknown"}</small></span>
            <span><strong>{recipes.toLocaleString()}</strong><small>{recipes === 1 ? "recipe" : "recipes"}</small></span>
          </BrowserRow>
        )
      })}
    </div>
  )
}

export function ModelRows({ data, state }: { data: Model[]; state: URLSearchParams }) {
  return (
    <div className="browser-list collection-list">
      {data.map((model) => {
        const tags: RowTag[] = [
          { label: model.family, name: "family", value: model.family },
          { label: model.architecture ?? "unknown", name: "architecture", value: model.architecture ?? "unknown" },
        ]
        return (
          <BrowserRow
            className="collection-row"
            href={hrefWithRecord(state, model.id)}
            key={model.id}
            label={`Open ${model.name}`}
            state={state}
            tags={tags}
          >
            <span className="row-primary"><strong>{model.name}</strong><small>{model.id}</small></span>
            <span><strong>{model.family}</strong><small>family</small></span>
            <span><strong>{model.architecture ?? "Unknown"}</strong><small>architecture</small></span>
            <span><strong>{model.params ?? "—"}</strong><small>parameters</small></span>
          </BrowserRow>
        )
      })}
    </div>
  )
}

export function BenchmarkRows({ data, state }: { data: Benchmark[]; state: URLSearchParams }) {
  return (
    <div className="browser-list collection-list">
      {data.map((benchmark) => {
        const top = benchmark.rows[0]
        const tags: RowTag[] = [
          ...(benchmark.category ? [{ label: benchmark.category, name: "category", value: benchmark.category }] : []),
        ]
        return (
          <BrowserRow
            className="collection-row"
            href={hrefWithRecord(state, benchmark.id)}
            key={benchmark.id}
            label={`Open ${benchmark.id}`}
            state={state}
            tags={tags}
          >
            <span className="row-primary"><strong>{benchmark.name}</strong><small>{benchmark.id}</small></span>
            <span><strong>{benchmark.category ?? "Unknown"}</strong><small>category</small></span>
            <span><strong>{benchmark.rows.length}</strong><small>scored models</small></span>
            <span><strong>{top ? (top.score === null ? "—" : formatRate(top.score)) : "—"}</strong><small>top score</small></span>
          </BrowserRow>
        )
      })}
    </div>
  )
}

export function SweepRows({ data, state }: { data: SpeedSweep[]; state: URLSearchParams }) {
  return (
    <div className="browser-list collection-list">
      {data.map((sweep) => {
        const speed = peakSpeed(sweep.rows)
        const tags: RowTag[] = [
          { label: sweep.recipe_id, name: "recipe_id", value: sweep.recipe_id },
        ]
        return (
          <BrowserRow
            className="collection-row"
            href={hrefWithRecord(state, sweep.id)}
            key={sweep.id}
            label={`Open ${sweep.id}`}
            state={state}
            tags={tags}
          >
            <span className="row-primary"><strong>{sweep.id}</strong><small>{sweep.recipe_id}</small></span>
            <span><strong>{sweep.measured_at ?? "Unknown"}</strong><small>measured</small></span>
            <span><strong>{sweep.rows.length}</strong><small>points</small></span>
            <span><strong>{speed === null ? "—" : `${formatRate(speed)} tok/s`}</strong><small>peak recorded</small></span>
          </BrowserRow>
        )
      })}
    </div>
  )
}
