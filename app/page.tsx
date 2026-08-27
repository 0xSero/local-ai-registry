import Link from "next/link"

import { DataTree } from "@/app/components/data-tree"
import { ModalCloseButton, RecordModal } from "@/app/components/record-modal"
import { RegistrySearch } from "@/app/components/registry-search"
import {
  collectionCounts,
  getEntityDetail,
  getFacets,
  getSpeedSweep,
  listHardware,
  listModels,
  listSpeedSweeps,
  queryCompatibility,
  type CompatibilityFilters,
  type CompatibilityResult,
} from "@/lib/registry"
import type { SpeedRow, SpeedSweep } from "@/registry/schema/types"

export const dynamic = "force-dynamic"

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

type Topic = "recipes" | "hardware" | "models" | "speed-sweeps"

type EvidenceRow = SpeedRow & {
  sweepId: string
}

const TOPICS: Array<{ key: Topic; label: string; countKey: string }> = [
  { key: "recipes", label: "Recipes", countKey: "recipe" },
  { key: "hardware", label: "Hardware", countKey: "hardware" },
  { key: "models", label: "Models", countKey: "model" },
  { key: "speed-sweeps", label: "Speed Sweeps", countKey: "speed_sweeps" },
]

function validTopic(value: string): Topic | "" {
  return TOPICS.some((topic) => topic.key === value) ? value as Topic : ""
}

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

function recipeEvidence(result: CompatibilityResult): EvidenceRow[] {
  return result.recipe.speed_sweeps_ids.flatMap((sweepId) => {
    const sweep = getSpeedSweep(sweepId)
    return sweep ? sweep.rows.map((row) => ({ ...row, sweepId })) : []
  })
}

function peakRecipeSpeed(result: CompatibilityResult): number | null {
  const values = recipeEvidence(result).flatMap((row) => {
    const value = row.decode_tok_s_per_stream ?? row.decode_tok_s ?? row.prefill_tok_s
    return typeof value === "number" ? [value] : []
  })
  return values.length > 0 ? Math.max(...values) : null
}

function peakSweepSpeed(sweep: SpeedSweep): number | null {
  const values = sweep.rows.flatMap((row) => {
    const value = row.decode_tok_s_per_stream ?? row.decode_tok_s ?? row.prefill_tok_s
    return typeof value === "number" ? [value] : []
  })
  return values.length > 0 ? Math.max(...values) : null
}

function hrefWithRecord(state: URLSearchParams, id: string): string {
  const selected = new URLSearchParams(state)
  selected.set("record", id)
  return `/?${selected.toString()}`
}

function stateHref(state: URLSearchParams): string {
  const query = state.toString()
  return query ? `/?${query}` : "/"
}

function recordTitle(detail: Record<string, unknown>, fallback: string): string {
  if (typeof detail.name === "string") return detail.name
  if (typeof detail.repository === "string") return detail.repository
  const model = detail.model
  if (model && typeof model === "object" && "name" in model && typeof model.name === "string") return model.name
  if (typeof detail.id === "string") return detail.id
  return fallback
}

function RecipeRows({ data, state }: { data: CompatibilityResult[]; state: URLSearchParams }) {
  return (
    <div className="browser-list recipe-browser-list">
      {data.map((result) => {
        const context = numberField(result.recipe.serving, "max_context_tokens")
        const speed = peakRecipeSpeed(result)
        const status = result.launchable
          ? "validated"
          : result.recipe.launch.kind === "reference" ? "reference" : "candidate"
        return (
          <Link className="browser-row recipe-browser-row" href={hrefWithRecord(state, result.id)} key={result.id} scroll={false}>
            <span className={`status-mark ${result.launchable ? "validated" : "candidate"}`} aria-hidden="true" />
            <span className="row-primary">
              <strong>{result.model.name}</strong>
              <small>{result.model_instance.weights.precision ?? result.model_instance.weights.format ?? "Unknown precision"}</small>
            </span>
            <span><strong>{result.hardware.name}</strong><small>{result.recipe.hardware_count} × {result.hardware.memory.vram_gb} GB</small></span>
            <span><strong>{result.recipe.engine.name}</strong><small>{result.recipe.launch.kind}</small></span>
            <span><strong>{formatTokens(context)}</strong><small>context</small></span>
            <span><strong>{speed === null ? "—" : `${formatRate(speed)} tok/s`}</strong><small>{result.speed_evidence.available ? "measured" : "no evidence"}</small></span>
            <span className={`row-status ${result.launchable ? "validated" : "candidate"}`}>{status}</span>
            <svg aria-hidden="true" className="row-arrow" viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
          </Link>
        )
      })}
    </div>
  )
}

export default async function Home({ searchParams }: PageProps) {
  const params = await searchParams
  const value = (key: string) => {
    const selected = params[key]
    return Array.isArray(selected) ? selected[0] : selected ?? ""
  }

  const topic = validTopic(value("topic"))
  const query = value("q")
  const validation = value("validation")
  const offset = Math.max(0, Number(value("offset")) || 0)
  const limit = topic === "recipes" ? 24 : 32
  const pagination = { limit, offset }
  const facets = getFacets()
  const counts = collectionCounts()

  const recipeFilters: CompatibilityFilters = {
    engine: value("engine"),
    evidence: value("evidence"),
    launchable: validation === "validated" ? "true" : validation === "candidate" ? "false" : "",
    min_vram_gb: value("min_vram_gb"),
    q: query,
  }
  const overviewRecipes = queryCompatibility({ launchable: "true" }, { limit: 8, offset: 0 })
  const recipeResults = topic === "recipes" ? queryCompatibility(recipeFilters, pagination) : { data: [], total: 0 }
  const hardwareResults = topic === "hardware" ? listHardware({ q: query }, pagination) : { data: [], total: 0 }
  const modelResults = topic === "models" ? listModels({ q: query }, pagination) : { data: [], total: 0 }
  const sweepResults = topic === "speed-sweeps" ? listSpeedSweeps({ q: query }, pagination) : { data: [], total: 0 }

  const viewState = new URLSearchParams()
  if (topic) viewState.set("topic", topic)
  if (query) viewState.set("q", query)
  if (topic === "recipes") {
    for (const key of ["validation", "engine", "min_vram_gb", "evidence"]) {
      const selected = value(key)
      if (selected) viewState.set(key, selected)
    }
  }
  if (offset > 0) viewState.set("offset", String(offset))

  const selectedRecord = topic && value("record") ? getEntityDetail(topic, value("record")) : undefined
  const closeHref = stateHref(viewState)
  const selectedTitle = selectedRecord ? recordTitle(selectedRecord, value("record")) : ""
  const total = topic === "recipes"
    ? recipeResults.total
    : topic === "hardware"
      ? hardwareResults.total
      : topic === "models"
        ? modelResults.total
        : topic === "speed-sweeps" ? sweepResults.total : 0
  const topicLabel = TOPICS.find((item) => item.key === topic)?.label

  const pageState = new URLSearchParams(viewState)
  pageState.delete("offset")
  const previousState = new URLSearchParams(pageState)
  previousState.set("offset", String(Math.max(0, offset - limit)))
  const nextState = new URLSearchParams(pageState)
  nextState.set("offset", String(offset + limit))

  return (
    <main className="registry-main">
      <nav aria-label="Registry collections" className="topic-tabs">
        {TOPICS.map((item) => (
          <Link aria-current={topic === item.key ? "page" : undefined} href={`/?topic=${item.key}`} key={item.key}>
            {item.label}
          </Link>
        ))}
      </nav>

      {!topic ? (
        <>
          <header className="overview-heading">
            <span className="mono-label">READ-ONLY / SOURCE-BACKED</span>
            <h1>Registry index</h1>
          </header>
          <section className="overview-search" aria-label="Search recipes">
            <RegistrySearch
              engines={facets.recipes.engine}
              evidence=""
              memory=""
              query=""
              recipeFilters={false}
              selectedEngine=""
              topic=""
              validation=""
              vramOptions={facets.hardware.vram_gb}
            />
          </section>
          <nav aria-label="Registry topic counts" className="topic-index">
            {TOPICS.map((item, index) => {
              const count = counts[item.countKey]
              return (
                <Link href={`/?topic=${item.key}`} key={item.key}>
                  <span className="mono-label">0{index + 1}</span>
                  <strong>{item.label}</strong>
                  <span>{typeof count === "number" ? count.toLocaleString() : "—"}</span>
                </Link>
              )
            })}
          </nav>
          <section className="overview-recipes">
            <div className="section-heading">
              <div><span className="mono-label">VALIDATED / LAUNCH-SAFE</span><h2>Launch-safe recipes</h2></div>
              <Link href="/?topic=recipes&validation=validated">View all</Link>
            </div>
            <RecipeRows data={overviewRecipes.data} state={new URLSearchParams("topic=recipes&validation=validated")} />
          </section>
        </>
      ) : (
        <>
          <header className="topic-heading">
            <div>
              <span className="mono-label">COLLECTION / {topic.toUpperCase()}</span>
              <h1>{topicLabel}</h1>
            </div>
            <span className="topic-total">{total.toLocaleString()} records</span>
          </header>
          <section className="topic-search" aria-label={`${topicLabel} search`}>
            <RegistrySearch
              engines={facets.recipes.engine}
              evidence={value("evidence")}
              memory={value("min_vram_gb")}
              query={query}
              recipeFilters={topic === "recipes"}
              selectedEngine={value("engine")}
              topic={topic}
              validation={validation}
              vramOptions={facets.hardware.vram_gb}
            />
          </section>

          {topic === "recipes" && <RecipeRows data={recipeResults.data} state={viewState} />}

          {topic === "hardware" && (
            <div className="browser-list collection-list">
              {hardwareResults.data.map((hardware) => (
                <Link className="browser-row collection-row" href={hrefWithRecord(viewState, hardware.id)} key={hardware.id} scroll={false}>
                  <span className="row-primary"><strong>{hardware.name}</strong><small>{hardware.id}</small></span>
                  <span><strong>{hardware.vendor}</strong><small>{hardware.kind}</small></span>
                  <span><strong>{hardware.memory.vram_gb} GB</strong><small>{hardware.memory.vram_type ?? "Memory type unknown"}</small></span>
                  <span><strong>{hardware.accelerator_backend}</strong><small>backend</small></span>
                  <svg aria-hidden="true" className="row-arrow" viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
                </Link>
              ))}
            </div>
          )}

          {topic === "models" && (
            <div className="browser-list collection-list">
              {modelResults.data.map((model) => (
                <Link className="browser-row collection-row" href={hrefWithRecord(viewState, model.id)} key={model.id} scroll={false}>
                  <span className="row-primary"><strong>{model.name}</strong><small>{model.id}</small></span>
                  <span><strong>{model.family}</strong><small>family</small></span>
                  <span><strong>{model.architecture ?? "Unknown"}</strong><small>architecture</small></span>
                  <span><strong>{model.params ?? "—"}</strong><small>parameters</small></span>
                  <svg aria-hidden="true" className="row-arrow" viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
                </Link>
              ))}
            </div>
          )}

          {topic === "speed-sweeps" && (
            <div className="browser-list collection-list">
              {sweepResults.data.map((sweep) => {
                const speed = peakSweepSpeed(sweep)
                return (
                  <Link className="browser-row collection-row" href={hrefWithRecord(viewState, sweep.id)} key={sweep.id} scroll={false}>
                    <span className="row-primary"><strong>{sweep.id}</strong><small>{sweep.recipe_id}</small></span>
                    <span><strong>{sweep.measured_at ?? "Unknown"}</strong><small>measured</small></span>
                    <span><strong>{sweep.rows.length}</strong><small>points</small></span>
                    <span><strong>{speed === null ? "—" : `${formatRate(speed)} tok/s`}</strong><small>peak recorded</small></span>
                    <svg aria-hidden="true" className="row-arrow" viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
                  </Link>
                )
              })}
            </div>
          )}

          {total === 0 && <div className="empty-state"><h2>No records found.</h2><p>Clear the search or remove a recipe filter.</p></div>}

          {(offset > 0 || offset + limit < total) && (
            <nav aria-label={`${topicLabel} pages`} className="pagination">
              {offset > 0 ? <Link href={stateHref(previousState)}>Previous</Link> : <span />}
              <span>{offset + 1}–{Math.min(offset + limit, total)} of {total}</span>
              {offset + limit < total ? <Link href={stateHref(nextState)}>Next</Link> : <span />}
            </nav>
          )}
        </>
      )}

      {selectedRecord && topic && (
        <RecordModal closeHref={closeHref} titleId="record-modal-title">
          <header className="record-modal-header">
            <div>
              <span className="mono-label">{topic.toUpperCase()} / RECORD</span>
              <h2 id="record-modal-title">{selectedTitle}</h2>
              <code>{value("record")}</code>
            </div>
            <ModalCloseButton className="modal-close" closeHref={closeHref} label="Close record details">Close</ModalCloseButton>
          </header>
          <div className="record-modal-body">
            <DataTree value={selectedRecord} />
          </div>
          <footer className="record-modal-footer">
            <a href={`/api/v1/${topic}/${value("record")}`}>JSON API</a>
            <Link href={`/${topic}/${value("record")}`}>Permanent record URL</Link>
          </footer>
        </RecordModal>
      )}
    </main>
  )
}
