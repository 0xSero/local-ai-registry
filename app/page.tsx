import Link from "next/link"

import { RegistrySearch } from "@/app/components/registry-search"
import {
  getFacets,
  getSpeedSweep,
  queryCompatibility,
  type CompatibilityFilters,
  type CompatibilityResult,
} from "@/lib/registry"
import type { SpeedRow } from "@/registry/schema/types"

export const dynamic = "force-dynamic"

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

type EvidenceRow = SpeedRow & {
  sweepId: string
}

type SpeedDisplay = {
  label: string
  value: number
} | null

function numberField(record: Record<string, unknown>, key: string): number | null {
  const value = record[key]
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function stringField(record: Record<string, unknown>, key: string): string | null {
  const value = record[key]
  return typeof value === "string" && value.trim() ? value : null
}

function formatTokens(value: number | null): string {
  if (value === null) return "Context unknown"
  if (value >= 1024) {
    const thousands = value / 1024
    return `${Number.isInteger(thousands) ? thousands : thousands.toFixed(1)}K context`
  }
  return `${value.toLocaleString()} context`
}

function formatRate(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 })
}

function evidenceRows(result: CompatibilityResult): EvidenceRow[] {
  return result.recipe.speed_sweeps_ids.flatMap((sweepId) => {
    const sweep = getSpeedSweep(sweepId)
    return sweep ? sweep.rows.map((row) => ({ ...row, sweepId })) : []
  })
}

function primarySpeed(rows: EvidenceRow[]): SpeedDisplay {
  const measured = rows.flatMap((row) => {
    if (typeof row.decode_tok_s_per_stream === "number") {
      return [{ label: "decode / stream", value: row.decode_tok_s_per_stream }]
    }
    if (typeof row.decode_tok_s === "number") return [{ label: "decode", value: row.decode_tok_s }]
    if (typeof row.prefill_tok_s === "number") return [{ label: "prefill", value: row.prefill_tok_s }]
    return []
  })
  return measured.sort((a, b) => b.value - a.value)[0] ?? null
}

function recipeHref(params: URLSearchParams, recipeId: string): string {
  const selected = new URLSearchParams(params)
  selected.set("recipe", recipeId)
  const query = selected.toString()
  return query ? `/?${query}` : "/"
}

function InlineRecipeDetail({ result, rows }: { result: CompatibilityResult; rows: EvidenceRow[] }) {
  const { hardware, model_instance: instance, recipe } = result
  const launch = recipe.launch as Record<string, unknown>
  const serving = recipe.serving
  const container = recipe.launch.container
  const entrypoint = stringField(launch, "entrypoint")
  const explicitCommand = stringField(launch, "launch_command")
  const args = Array.isArray(launch.arguments)
    ? launch.arguments.filter((value): value is string => typeof value === "string")
    : []
  const launchLine = explicitCommand ?? ([entrypoint, ...args].filter(Boolean).join(" ") || null)
  const maxContext = numberField(serving, "max_context_tokens")
  const maxConcurrency = numberField(serving, "max_concurrency")
  const tensorParallel = numberField(serving, "tensor_parallel")
  const sources = container.source.filter((source) => source.url || source.repository)

  return (
    <section className="recipe-detail" aria-label={`Selected recipe details for ${result.model.name} on ${hardware.name}`}>
      {!result.launchable && (
        <p className="boundary-note">
          This record is {recipe.status === "candidate" ? "a candidate" : "reference-only"}. Its source data is visible, but it is not marked launch-safe.
        </p>
      )}
      <div className="detail-columns">
        <section>
          <h4>Hugging Face</h4>
          <a href={instance.hugging_face_url} rel="noreferrer" target="_blank">
            {instance.repository}
            <span className="external-mark" aria-hidden="true">↗</span>
          </a>
          <p>{instance.huggingface.link_type === "repository" ? "Exact repository" : "Search fallback, not an exact repository"} · {instance.huggingface.status}</p>
          {instance.revision && <p>Revision <code>{instance.revision}</code></p>}
        </section>

        <section>
          <h4>Container provenance</h4>
          <p>{container.runtime ?? "No container runtime"} · {container.state}</p>
          {container.image && <code className="breakable">{container.image}</code>}
          {!container.image && container.digest && <code className="breakable">{container.digest}</code>}
          {sources.map((source, index) => {
            const href = source.url ?? source.repository
            return href ? <a className="source-link" href={href} key={`${href}-${index}`} rel="noreferrer" target="_blank">Provenance source <span aria-hidden="true">↗</span></a> : null
          })}
        </section>

        <section>
          <h4>Launch details</h4>
          <dl className="compact-data">
            <div><dt>Kind</dt><dd>{recipe.launch.kind}</dd></div>
            <div><dt>Engine</dt><dd>{recipe.engine.name}{recipe.engine.version ? ` ${recipe.engine.version}` : ""}</dd></div>
            <div><dt>Hardware</dt><dd>{recipe.hardware_count} × {hardware.name}</dd></div>
            <div><dt>Context</dt><dd>{maxContext === null ? "Unknown" : maxContext.toLocaleString()}</dd></div>
            <div><dt>Concurrency</dt><dd>{maxConcurrency ?? "Unknown"}</dd></div>
            {tensorParallel !== null && <div><dt>Tensor parallel</dt><dd>{tensorParallel}</dd></div>}
          </dl>
          {launchLine && <div className="launch-line"><span>{explicitCommand ? "Launch command" : "Entrypoint + arguments"}</span><code>{launchLine}</code></div>}
        </section>

        <section>
          <h4>Measured speed</h4>
          {rows.length > 0 ? (
            <div className="speed-table-wrap">
              <table>
                <thead><tr><th>Context</th><th>C</th><th>Output</th><th>Rate</th></tr></thead>
                <tbody>
                  {rows.map((row, index) => {
                    const rate = row.decode_tok_s_per_stream ?? row.decode_tok_s ?? row.prefill_tok_s
                    const rateKind = typeof row.decode_tok_s_per_stream === "number"
                      ? "decode/stream"
                      : typeof row.decode_tok_s === "number" ? "decode" : "prefill"
                    return (
                      <tr key={`${row.sweepId}-${index}`}>
                        <td>{row.context_tokens?.toLocaleString() ?? "—"}</td>
                        <td>{row.concurrency ?? "—"}</td>
                        <td>{row.output_tokens?.toLocaleString() ?? "—"}</td>
                        <td>{typeof rate === "number" ? `${formatRate(rate)} ${rateKind}` : "—"}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : <p>No measured speed is attached to this recipe.</p>}
          {recipe.speed_sweeps_ids.map((id) => <Link className="source-link" href={`/speed-sweeps/${id}`} key={id}>Open measured evidence</Link>)}
        </section>
      </div>
      <div className="detail-footer">
        <code>{result.id}</code>
        <Link href={`/recipes/${result.id}`}>Open complete record</Link>
        <a href={`/api/v1/recipes/${result.id}`}>JSON API</a>
      </div>
    </section>
  )
}

export default async function Home({ searchParams }: PageProps) {
  const params = await searchParams
  const value = (key: string) => {
    const selected = params[key]
    return Array.isArray(selected) ? selected[0] : selected ?? ""
  }
  const query = value("q") || [value("model"), value("hardware")].filter(Boolean).join(" ")
  const validation = value("validation")
  const filters: CompatibilityFilters = {
    engine: value("engine"),
    evidence: value("evidence"),
    hardware: value("q") ? "" : value("hardware"),
    launchable: validation === "validated" ? "true" : validation === "candidate" ? "false" : value("launchable"),
    min_vram_gb: value("min_vram_gb"),
    model: value("q") ? "" : value("model"),
    q: value("q"),
    status: value("status"),
  }
  const offset = Math.max(0, Number(value("offset")) || 0)
  const limit = 24
  const results = queryCompatibility(filters, { limit, offset })
  const facets = getFacets()
  const displayResults = [...results.data].sort((a, b) => Number(b.launchable) - Number(a.launchable))
  const selectedId = displayResults.some((result) => result.id === value("recipe"))
    ? value("recipe")
    : displayResults[0]?.id
  const evidenceByRecipe = new Map(displayResults.map((result) => [result.id, evidenceRows(result)]))

  const searchState = new URLSearchParams()
  for (const key of ["q", "validation", "engine", "min_vram_gb", "evidence", "model", "hardware", "launchable", "status"]) {
    const selected = value(key)
    if (selected) searchState.set(key, selected)
  }
  const previousParams = new URLSearchParams(searchState)
  previousParams.set("offset", String(Math.max(0, offset - limit)))
  const nextParams = new URLSearchParams(searchState)
  nextParams.set("offset", String(offset + limit))
  const hasSearch = searchState.size > 0

  return (
    <main className="registry-main">
      <section className="search-area" aria-labelledby="registry-results-heading">
        <RegistrySearch
          engines={facets.recipes.engine}
          evidence={value("evidence")}
          memory={value("min_vram_gb")}
          query={query}
          selectedEngine={value("engine")}
          validation={validation}
          vramOptions={facets.hardware.vram_gb}
        />
      </section>

      <section className="results" aria-live="polite">
        <div className="results-heading">
          <h1 id="registry-results-heading">{results.total.toLocaleString()} compatible recipe{results.total === 1 ? "" : "s"}</h1>
          {hasSearch && <Link className="clear-link" href="/">Clear filters</Link>}
        </div>

        {results.data.length === 0 ? (
          <div className="empty-state">
            <h2>No recipes match this search.</h2>
            <p>Try fewer terms or remove one filter.</p>
          </div>
        ) : (
          <div className="result-list">
            {displayResults.map((result) => {
              const { hardware, model, model_instance: instance, recipe } = result
              const selected = result.id === selectedId
              const rows = evidenceByRecipe.get(result.id) ?? []
              const speed = primarySpeed(rows)
              const capacity = hardware.memory.vram_gb * recipe.hardware_count
              const weightSize = instance.weights.size_gb
              const memoryPercent = typeof weightSize === "number" && capacity > 0
                ? Math.min(100, Math.round((weightSize / capacity) * 100))
                : null
              const context = numberField(recipe.serving, "max_context_tokens")
              const concurrency = numberField(recipe.serving, "max_concurrency")
              const trustLabel = result.launchable
                ? "Validated, launch-safe"
                : recipe.launch.kind === "reference"
                  ? "Reference only, not launch-safe"
                  : "Candidate, not launch-safe"

              return (
                <article className={`result-unit${selected ? " selected" : ""}`} key={result.id}>
                  <div className="result-row">
                    <div className="model-cell">
                      <span className={`status-dot ${result.launchable ? "validated" : "candidate"}`} aria-hidden="true" />
                      <div>
                        <Link href={`/models/${model.id}`}>{model.name}</Link>
                        <span className="sr-only">{trustLabel}</span>
                        <small>{instance.weights.precision ?? instance.weights.format ?? "Precision unknown"}</small>
                      </div>
                    </div>
                    <div className="hardware-cell">
                      <Link href={`/hardware/${hardware.id}`}>{hardware.name}</Link>
                      <small>{recipe.hardware_count > 1 ? `${recipe.hardware_count} × ` : ""}{hardware.memory.vram_gb} GB {hardware.memory.vram_type ?? ""}</small>
                    </div>
                    <div className="engine-cell">
                      <span>{recipe.engine.name}</span>
                      <small>{recipe.engine.version ?? recipe.launch.kind}</small>
                    </div>
                    <div className={`memory-cell ${result.launchable ? "validated" : "candidate"}`}>
                      <div className="memory-bar" aria-hidden="true"><span style={memoryPercent === null ? undefined : { width: `${memoryPercent}%` }} /></div>
                      <small>{typeof weightSize === "number" ? `${weightSize.toLocaleString()} GB weights / ${capacity.toLocaleString()} GB` : `${capacity.toLocaleString()} GB capacity · weight size unknown`}</small>
                    </div>
                    <div className="context-cell">
                      <span>{formatTokens(context)}</span>
                      <small>{concurrency === null ? "Concurrency unknown" : `C${concurrency} max`}</small>
                    </div>
                    <div className="speed-cell">
                      <span>{speed ? `${formatRate(speed.value)} tok/s` : "No measurement"}</span>
                      <small>{speed?.label ?? "No speed evidence"}</small>
                    </div>
                    <Link
                      aria-expanded={selected}
                      aria-label={`${selected ? "Collapse" : "Show"} recipe details for ${model.name} on ${hardware.name}`}
                      className="row-toggle"
                      href={selected ? `/?${searchState.toString()}` : recipeHref(searchState, result.id)}
                      scroll={false}
                    >
                      <svg aria-hidden="true" viewBox="0 0 20 20"><path d={selected ? "m4 12 6-6 6 6" : "m7 4 6 6-6 6"} /></svg>
                    </Link>
                  </div>
                  {selected && <InlineRecipeDetail result={result} rows={rows} />}
                </article>
              )
            })}
          </div>
        )}

        {(offset > 0 || offset + limit < results.total) && (
          <nav className="pagination" aria-label="Recipe result pages">
            {offset > 0 ? <Link href={`/?${previousParams}`}>Previous</Link> : <span />}
            <span>{offset + 1}–{Math.min(offset + limit, results.total)} of {results.total}</span>
            {offset + limit < results.total ? <Link href={`/?${nextParams}`}>Next</Link> : <span />}
          </nav>
        )}
      </section>
    </main>
  )
}
