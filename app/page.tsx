import Link from "next/link"

import { DataTree } from "@/app/components/data-tree"
import { ModalCloseButton, RecordModal } from "@/app/components/record-modal"
import { RegistrySearch, type SearchFilter } from "@/app/components/registry-search"
import {
  collectionCounts,
  getEntityDetail,
  getFacets,
  getSpeedSweep,
  listHardware,
  listModels,
  listPrices,
  listSpeedSweeps,
  marketPriceCount,
  queryCompatibility,
  type CompatibilityFilters,
  type CompatibilityResult,
  type PriceResult,
} from "@/lib/registry"
import type { SpeedRow, SpeedSweep } from "@/registry/schema/types"

export const dynamic = "force-dynamic"

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

type Topic = "recipes" | "hardware" | "models" | "prices" | "speed-sweeps"

type EvidenceRow = SpeedRow & {
  sweepId: string
}

type RowTag = {
  label: string
  name: string
  value: string
}

const TOPICS: Array<{ key: Topic; label: string; countKey: string | null; description: string }> = [
  { key: "recipes", label: "Recipes", countKey: "recipe", description: "Browse model × hardware compatibility by hardware or by model, with engine, launch status, and evidence." },
  { key: "hardware", label: "Hardware", countKey: "hardware", description: "Accelerator specifications connected to compatible models, recipes, and regional prices." },
  { key: "models", label: "Models", countKey: "model", description: "Canonical models connected to artifacts, supported hardware, and recipes." },
  { key: "prices", label: "Prices", countKey: "price", description: "Fresh regional listing observations in native currency. Candidate matches remain inspectable." },
  { key: "speed-sweeps", label: "Speed Sweeps", countKey: "speed_sweeps", description: "Measured inference evidence connected back to the recipe that produced it." },
]

const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  currency: "USD",
  maximumFractionDigits: 0,
  style: "currency",
})

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

function formatAmount(amount: number, currency: string): string {
  return currency === "USD" ? USD_FORMATTER.format(amount) : `${currency} ${amount.toLocaleString()}`
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

function hrefWithFilter(state: URLSearchParams, name: string, value: string): string {
  const selected = new URLSearchParams(state)
  selected.delete("record")
  selected.delete("offset")
  selected.set(name, value)
  return `/?${selected.toString()}`
}

function stateHref(state: URLSearchParams): string {
  const query = state.toString()
  return query ? `/?${query}` : "/"
}

function recordTitle(detail: Record<string, unknown>, fallback: string): string {
  if (typeof detail.name === "string") return detail.name
  if (typeof detail.repository === "string") return detail.repository
  const product = detail.product
  if (product && typeof product === "object" && "name" in product && typeof product.name === "string") return product.name
  const model = detail.model
  if (model && typeof model === "object" && "name" in model && typeof model.name === "string") return model.name
  if (typeof detail.id === "string") return detail.id
  return fallback
}

function facetOptions(values: Array<string | number>, allLabel: string, format: (value: string | number) => string = String): SearchFilter["options"] {
  return [{ label: allLabel, value: "" }, ...values.map((value) => ({ label: format(value), value: String(value) }))]
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

function RecipeRows({ by, data, state }: { by: "hardware" | "model"; data: CompatibilityResult[]; state: URLSearchParams }) {
  return (
    <div className="browser-list recipe-browser-list">
      {data.map((result) => {
        const context = numberField(result.recipe.serving, "max_context_tokens")
        const speed = peakRecipeSpeed(result)
        const validation = result.launchable ? "validated" : "candidate"
        const tags: RowTag[] = [
          { label: validation, name: "validation", value: validation },
          { label: result.recipe.engine.name, name: "engine", value: result.recipe.engine.name },
          { label: result.speed_evidence.available ? "measured" : "unmeasured", name: "evidence", value: String(result.speed_evidence.available) },
          { label: `${result.hardware.memory.vram_gb} GB+`, name: "min_vram_gb", value: String(result.hardware.memory.vram_gb) },
        ]
        return (
          <article className="browser-row recipe-browser-row" key={result.id}>
            <Link aria-label={`Open ${result.model.name} recipe`} className="row-open" href={hrefWithRecord(state, result.id)} scroll={false} />
            <span className={`status-mark ${result.launchable ? "validated" : "candidate"}`} aria-hidden="true" />
            {by === "hardware" ? (
              <>
                <span className="row-primary"><strong>{result.hardware.name}</strong><small>{result.recipe.hardware_count} × {result.hardware.memory.vram_gb} GB</small></span>
                <span><strong>{result.model.name}</strong><small>{result.model_instance.weights.precision ?? result.model_instance.weights.format ?? "Unknown precision"}</small></span>
              </>
            ) : (
              <>
                <span className="row-primary"><strong>{result.model.name}</strong><small>{result.model_instance.weights.precision ?? result.model_instance.weights.format ?? "Unknown precision"}</small></span>
                <span><strong>{result.hardware.name}</strong><small>{result.recipe.hardware_count} × {result.hardware.memory.vram_gb} GB</small></span>
              </>
            )}
            <span><strong>{result.recipe.engine.name}</strong><small>{result.recipe.launch.kind}</small></span>
            <span><strong>{formatTokens(context)}</strong><small>context</small></span>
            <span><strong>{speed === null ? "—" : `${formatRate(speed)} tok/s`}</strong><small>{result.speed_evidence.available ? "measured" : "no evidence"}</small></span>
            <TaxonomyTags state={state} tags={tags} />
            <svg aria-hidden="true" className="row-arrow" viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
          </article>
        )
      })}
    </div>
  )
}

function PriceRows({ data, state }: { data: PriceResult[]; state: URLSearchParams }) {
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
          <article className="browser-row price-row" key={record.id}>
            <Link aria-label={`Open ${record.product.name} market observations`} className="row-open" href={hrefWithRecord(state, record.id)} scroll={false} />
            <span className="row-primary"><strong>{record.product.name}</strong><small>{record.product.id}</small></span>
            <span><strong>{amount === null ? "No available listing" : formatAmount(amount, record.region.currency)}</strong><small>lowest available · {condition}</small></span>
            <span><strong>{record.region.name}</strong><small>{record.region.currency}</small></span>
            <span><strong>{record.observed_at.slice(0, 10)}</strong><small>observed</small></span>
            <span><strong>{record.summary.listing_count} listings</strong><small>{record.summary.retailer_count} retailers</small></span>
            <TaxonomyTags state={state} tags={tags} />
            <svg aria-hidden="true" className="row-arrow" viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
          </article>
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
  const recipeBrowse = value("by") === "model" ? "model" : "hardware"
  const offset = Math.max(0, Number(value("offset")) || 0)
  const limit = topic === "recipes" ? 24 : 32
  const pagination = { limit, offset }
  const facets = getFacets()
  const counts = collectionCounts()

  const recipeFilters: CompatibilityFilters = {
    engine: value("engine"),
    evidence: value("evidence"),
    hardware_id: value("hardware_id"),
    launchable: validation === "validated" ? "true" : validation === "candidate" ? "false" : "",
    min_vram_gb: value("min_vram_gb"),
    model_id: value("model_id"),
    q: query,
    sort_by: recipeBrowse,
  }
  const overviewRecipes = queryCompatibility({ launchable: "true" }, { limit: 8, offset: 0 })
  const recipeResults = topic === "recipes" ? queryCompatibility(recipeFilters, pagination) : { data: [], total: 0 }
  const hardwareResults = topic === "hardware" ? listHardware({
    backend: value("backend"),
    min_vram_gb: value("min_vram_gb"),
    priced_only: value("priced_only"),
    q: query,
    vendor: value("vendor"),
  }, pagination) : { data: [], total: 0 }
  const modelResults = topic === "models" ? listModels({
    architecture: value("architecture"),
    family: value("family"),
    q: query,
  }, pagination) : { data: [], total: 0 }
  const priceResults = topic === "prices" ? listPrices({
    category: value("category"),
    condition: value("condition"),
    in_stock: value("in_stock"),
    q: query,
    region: value("region"),
    retailer: value("retailer"),
  }, pagination) : { data: [], total: 0 }
  const priceTotal = counts.price ?? (topic === "prices" ? priceResults.total : listPrices({}, { limit: 1, offset: 0 }).total)
  const sweepResults = topic === "speed-sweeps" ? listSpeedSweeps({ q: query }, pagination) : { data: [], total: 0 }

  const filterKeys: Partial<Record<Topic, string[]>> = {
    hardware: ["vendor", "backend", "min_vram_gb", "priced_only"],
    models: ["family", "architecture"],
    prices: ["region", "category", "condition", "retailer", "in_stock"],
    recipes: ["by", "hardware_id", "model_id", "validation", "engine", "evidence"],
  }
  const viewState = new URLSearchParams()
  if (topic) viewState.set("topic", topic)
  if (topic === "recipes") viewState.set("by", recipeBrowse)
  if (query) viewState.set("q", query)
  for (const key of topic ? filterKeys[topic] ?? [] : []) {
    const selected = value(key)
    if (selected) viewState.set(key, selected)
  }
  if (offset > 0) viewState.set("offset", String(offset))

  const detailCollection = topic
  const selectedRecord = detailCollection && value("record") ? getEntityDetail(detailCollection, value("record")) : undefined
  const closeHref = stateHref(viewState)
  const selectedTitle = selectedRecord ? recordTitle(selectedRecord, value("record")) : ""
  const total = topic === "recipes"
    ? recipeResults.total
    : topic === "hardware"
      ? hardwareResults.total
      : topic === "models"
        ? modelResults.total
        : topic === "prices"
          ? priceResults.total
          : topic === "speed-sweeps" ? sweepResults.total : 0
  const topicLabel = TOPICS.find((item) => item.key === topic)?.label
  const topicDescription = TOPICS.find((item) => item.key === topic)?.description

  const pageState = new URLSearchParams(viewState)
  pageState.delete("offset")
  const previousState = new URLSearchParams(pageState)
  previousState.set("offset", String(Math.max(0, offset - limit)))
  const nextState = new URLSearchParams(pageState)
  nextState.set("offset", String(offset + limit))

  const recipeSearchFilters: SearchFilter[] = [
    { label: "Browse", name: "by", value: recipeBrowse, options: [{ label: "By hardware", value: "hardware" }, { label: "By model", value: "model" }] },
    { label: "Hardware", name: "hardware_id", value: value("hardware_id"), options: [{ label: "All hardware", value: "" }, ...listHardware({}, { limit: 200, offset: 0 }).data.map((hardware) => ({ label: hardware.name, value: hardware.id }))] },
    { label: "Model", name: "model_id", value: value("model_id"), options: [{ label: "All models", value: "" }, ...listModels({}, { limit: 200, offset: 0 }).data.map((model) => ({ label: model.name, value: model.id }))] },
    { label: "Status", name: "validation", value: validation, options: facetOptions(["validated", "candidate"], "All statuses", (item) => item === "validated" ? "Validated · launch-safe" : "Candidate or reference") },
    { label: "Engine", name: "engine", value: value("engine"), options: facetOptions(facets.recipes.engine, "Any engine") },
    { label: "Evidence", name: "evidence", value: value("evidence"), options: facetOptions(["true", "false"], "Any evidence", (item) => item === "true" ? "Measured speed attached" : "No measured speed") },
  ]
  const hardwareSearchFilters: SearchFilter[] = [
    { label: "Vendor", name: "vendor", value: value("vendor"), options: facetOptions(facets.hardware.vendor, "Any vendor") },
    { label: "Backend", name: "backend", value: value("backend"), options: facetOptions(facets.hardware.backend, "Any backend") },
    { label: "Memory", name: "min_vram_gb", value: value("min_vram_gb"), options: facetOptions(facets.hardware.vram_gb, "Any memory", (item) => `At least ${item} GB`) },
    { label: "Pricing", name: "priced_only", value: value("priced_only"), options: facetOptions(["true"], "All hardware", () => "Priced only") },
  ]
  const modelSearchFilters: SearchFilter[] = [
    { label: "Family", name: "family", value: value("family"), options: facetOptions(facets.models.family, "Any family") },
    { label: "Architecture", name: "architecture", value: value("architecture"), options: facetOptions(facets.models.architecture, "Any architecture") },
  ]
  const priceSearchFilters: SearchFilter[] = [
    { label: "Region", name: "region", value: value("region"), options: facetOptions(facets.prices.region, "Any region") },
    { label: "Category", name: "category", value: value("category"), options: facetOptions(facets.prices.category, "Any category") },
    { label: "Condition", name: "condition", value: value("condition"), options: facetOptions(facets.prices.condition, "Any condition") },
    { label: "Retailer", name: "retailer", value: value("retailer"), options: facetOptions(facets.prices.retailer, "Any retailer") },
    { label: "Availability", name: "in_stock", value: value("in_stock"), options: facetOptions(["true", "false", "unknown"], "Any availability", (item) => item === "true" ? "In stock" : item === "false" ? "Out of stock" : "Unknown stock") },
  ]
  const topicFilters = topic === "recipes"
    ? recipeSearchFilters
    : topic === "hardware"
      ? hardwareSearchFilters
      : topic === "models"
        ? modelSearchFilters
        : topic === "prices" ? priceSearchFilters : []

  return (
    <main className="registry-main">
      <nav aria-label="Registry collections" className="topic-tabs">
        {TOPICS.map((item) => (
          <Link aria-current={topic === item.key ? "page" : undefined} href={`/?topic=${item.key}`} key={item.key}>{item.label}</Link>
        ))}
      </nav>

      {!topic ? (
        <>
          <header className="overview-heading"><span className="mono-label">READ-ONLY / SOURCE-BACKED</span><h1>Registry index</h1></header>
          <section className="overview-search" aria-label="Search recipes"><RegistrySearch filters={[]} query="" topic="" /></section>
          <nav aria-label="Registry topic counts" className="topic-index">
            {TOPICS.map((item, index) => {
              const count = item.key === "prices" ? priceTotal : item.countKey ? counts[item.countKey] : undefined
              return (
                <Link href={`/?topic=${item.key}`} key={item.key}>
                  <span className="mono-label">0{index + 1}</span><strong>{item.label}</strong><span>{typeof count === "number" ? count.toLocaleString() : "—"}</span>
                </Link>
              )
            })}
          </nav>
          <section className="overview-recipes">
            <div className="section-heading"><div><span className="mono-label">VALIDATED / LAUNCH-SAFE</span><h2>Launch-safe recipes</h2></div><Link href="/?topic=recipes&validation=validated">View all</Link></div>
            <RecipeRows by="model" data={overviewRecipes.data} state={new URLSearchParams("topic=recipes&by=model&validation=validated")} />
          </section>
        </>
      ) : (
        <>
          <header className="topic-heading"><div><span className="mono-label">COLLECTION / {topic.toUpperCase()}</span><h1>{topicLabel}</h1><p className="topic-description">{topicDescription}</p></div><span className="topic-total">{total.toLocaleString()} records</span></header>
          <section className="topic-search" aria-label={`${topicLabel} search`}><RegistrySearch filters={topicFilters} query={query} topic={topic} /></section>

          {topic === "recipes" && <RecipeRows by={recipeBrowse} data={recipeResults.data} state={viewState} />}
          {topic === "hardware" && (
            <div className="browser-list collection-list">
              {hardwareResults.data.map((hardware) => {
                const hasPrices = marketPriceCount(hardware.id) > 0
                const tags: RowTag[] = [
                  { label: hardware.vendor, name: "vendor", value: hardware.vendor },
                  { label: hardware.accelerator_backend, name: "backend", value: hardware.accelerator_backend },
                  { label: `${hardware.memory.vram_gb} GB+`, name: "min_vram_gb", value: String(hardware.memory.vram_gb) },
                  ...(hasPrices ? [{ label: "priced", name: "priced_only", value: "true" }] : []),
                ]
                return (
                  <article className="browser-row collection-row" key={hardware.id}>
                    <Link aria-label={`Open ${hardware.name}`} className="row-open" href={hrefWithRecord(viewState, hardware.id)} scroll={false} />
                    <span className="row-primary"><strong>{hardware.name}</strong><small>{hardware.id}</small></span>
                    <span><strong>{hardware.vendor}</strong><small>{hardware.kind}</small></span>
                    <span><strong>{hardware.memory.vram_gb} GB</strong><small>{hardware.memory.vram_type ?? "Memory type unknown"}</small></span>
                    <span><strong>{hardware.accelerator_backend}</strong><small>backend</small></span>
                    <TaxonomyTags state={viewState} tags={tags} />
                    <svg aria-hidden="true" className="row-arrow" viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
                  </article>
                )
              })}
            </div>
          )}
          {topic === "models" && (
            <div className="browser-list collection-list">
              {modelResults.data.map((model) => {
                const tags: RowTag[] = [
                  { label: model.family, name: "family", value: model.family },
                  { label: model.architecture ?? "unknown", name: "architecture", value: model.architecture ?? "unknown" },
                ]
                return (
                  <article className="browser-row collection-row" key={model.id}>
                    <Link aria-label={`Open ${model.name}`} className="row-open" href={hrefWithRecord(viewState, model.id)} scroll={false} />
                    <span className="row-primary"><strong>{model.name}</strong><small>{model.id}</small></span>
                    <span><strong>{model.family}</strong><small>family</small></span>
                    <span><strong>{model.architecture ?? "Unknown"}</strong><small>architecture</small></span>
                    <span><strong>{model.params ?? "—"}</strong><small>parameters</small></span>
                    <TaxonomyTags state={viewState} tags={tags} />
                    <svg aria-hidden="true" className="row-arrow" viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
                  </article>
                )
              })}
            </div>
          )}
          {topic === "prices" && <PriceRows data={priceResults.data} state={viewState} />}
          {topic === "speed-sweeps" && (
            <div className="browser-list collection-list">
              {sweepResults.data.map((sweep) => {
                const speed = peakSweepSpeed(sweep)
                const tags: RowTag[] = [
                  { label: sweep.recipe_id, name: "q", value: sweep.recipe_id },
                  ...(sweep.measured_at ? [{ label: sweep.measured_at, name: "q", value: sweep.measured_at }] : []),
                ]
                return (
                  <article className="browser-row collection-row" key={sweep.id}>
                    <Link aria-label={`Open ${sweep.id}`} className="row-open" href={hrefWithRecord(viewState, sweep.id)} scroll={false} />
                    <span className="row-primary"><strong>{sweep.id}</strong><small>{sweep.recipe_id}</small></span>
                    <span><strong>{sweep.measured_at ?? "Unknown"}</strong><small>measured</small></span>
                    <span><strong>{sweep.rows.length}</strong><small>points</small></span>
                    <span><strong>{speed === null ? "—" : `${formatRate(speed)} tok/s`}</strong><small>peak recorded</small></span>
                    <TaxonomyTags state={viewState} tags={tags} />
                    <svg aria-hidden="true" className="row-arrow" viewBox="0 0 20 20"><path d="m7 4 6 6-6 6" /></svg>
                  </article>
                )
              })}
            </div>
          )}

          {total === 0 && <div className="empty-state"><h2>No records found.</h2><p>Clear the search or remove a filter.</p></div>}
          {(offset > 0 || offset + limit < total) && (
            <nav aria-label={`${topicLabel} pages`} className="pagination">
              {offset > 0 ? <Link href={stateHref(previousState)}>Previous</Link> : <span />}
              <span>{offset + 1}–{Math.min(offset + limit, total)} of {total}</span>
              {offset + limit < total ? <Link href={stateHref(nextState)}>Next</Link> : <span />}
            </nav>
          )}
        </>
      )}

      {selectedRecord && detailCollection && (
        <RecordModal closeHref={closeHref} titleId="record-modal-title">
          <header className="record-modal-header">
            <div><span className="mono-label">{detailCollection.toUpperCase()} / RECORD</span><h2 id="record-modal-title">{selectedTitle}</h2><code>{value("record")}</code></div>
            <ModalCloseButton className="modal-close" closeHref={closeHref} label="Close record details">Close</ModalCloseButton>
          </header>
          <div className="record-modal-body"><DataTree value={selectedRecord} /></div>
          <footer className="record-modal-footer">
            <a href={`/api/v1/${detailCollection}/${value("record")}`}>JSON API</a>
            <Link href={`/${detailCollection}/${value("record")}`}>Permanent record URL</Link>
          </footer>
        </RecordModal>
      )}
    </main>
  )
}
