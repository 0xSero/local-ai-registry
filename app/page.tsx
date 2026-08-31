import Link from "next/link"

import {
  BenchmarkRows,
  HardwareRows,
  ModelRows,
  PriceRows,
  RecipeRows,
  SweepRows,
} from "@/app/components/browse-rows"
import { CollectionNav } from "@/app/components/collection-nav"
import { RecordBody } from "@/app/components/record-body"
import { ModalCloseButton, RecordModal } from "@/app/components/record-modal"
import { RegistrySearch, type SearchFilter } from "@/app/components/registry-search"
import {
  TOPIC_FILTERS,
  TOPICS,
  isTopic,
  stateHref,
  topicHref,
  topicSpec,
  type Topic,
} from "@/app/lib/catalog"
import { recordTitle } from "@/app/lib/record-view"
import {
  collectionCounts,
  getEntityDetail,
  getFacets,
  listHardware,
  listBenchmarks,
  listModels,
  listPrices,
  listSpeedSweeps,
  queryCompatibility,
  type CompatibilityFilters,
} from "@/lib/registry"

export const dynamic = "force-dynamic"

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

function facetOptions(values: Array<string | number>, allLabel: string, format: (value: string | number) => string = String): SearchFilter["options"] {
  return [{ label: allLabel, value: "" }, ...values.map((value) => ({ label: format(value), value: String(value) }))]
}

function param(params: Record<string, string | string[] | undefined>, key: string): string {
  const selected = params[key]
  return Array.isArray(selected) ? selected[0] : selected ?? ""
}

export default async function Home({ searchParams }: PageProps) {
  const params = await searchParams
  const value = (key: string) => param(params, key)
  const topicValue = value("topic")
  const topic: Topic | "" = isTopic(topicValue) ? topicValue : ""
  const query = value("q")
  const validation = value("validation")
  const recipeBrowse = value("by") === "model" ? "model" : "hardware"
  const offset = Math.max(0, Number(value("offset")) || 0)
  const limit = topic === "recipes" ? 24 : 32
  const pagination = { limit, offset }
  const facets = getFacets()
  const counts = collectionCounts()
  const spec = topic ? topicSpec(topic) : undefined

  const recipeFilters: CompatibilityFilters = {
    engine: value("engine"),
    evidence: value("evidence"),
    hardware_id: value("hardware_id"),
    launchable: validation === "validated" ? "true" : validation === "candidate" ? "false" : "",
    min_vram_gb: value("min_vram_gb"),
    model_id: value("model_id"),
    q: query,
    runtime: value("runtime"),
    sort_by: recipeBrowse,
  }
  const overviewRecipes = queryCompatibility({ launchable: "true" }, { limit: 8, offset: 0 })
  const recipeResults = topic === "recipes" ? queryCompatibility(recipeFilters, pagination) : { data: [], total: 0 }
  const hardwareResults = topic === "hardware" ? listHardware({
    backend: value("backend"),
    has_recipes: value("has_recipes"),
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
  const sweepResults = topic === "speed-sweep" ? listSpeedSweeps({ q: query, recipe_id: value("recipe_id") }, pagination) : { data: [], total: 0 }
  const benchmarkResults = topic === "benchmark" ? listBenchmarks({ q: query, category: value("category") }, pagination) : { data: [], total: 0 }
  const matchCounts = !topic && query
    ? {
        recipes: queryCompatibility({ q: query }, { limit: 1, offset: 0 }).total,
        hardware: listHardware({ q: query }, { limit: 1, offset: 0 }).total,
        models: listModels({ q: query }, { limit: 1, offset: 0 }).total,
        prices: listPrices({ q: query }, { limit: 1, offset: 0 }).total,
        benchmark: listBenchmarks({ q: query }, { limit: 1, offset: 0 }).total,
        "speed-sweep": undefined as number | undefined,
      }
    : null

  const viewState = new URLSearchParams()
  if (topic) viewState.set("topic", topic)
  if (topic === "recipes") viewState.set("by", recipeBrowse)
  if (query) viewState.set("q", query)
  for (const key of topic ? TOPIC_FILTERS[topic] : []) {
    const selected = value(key)
    if (selected) viewState.set(key, selected)
  }
  if (offset > 0) viewState.set("offset", String(offset))

  const selectedId = value("record")
  const selectedRecord = topic && selectedId ? getEntityDetail(topic, selectedId) : undefined
  const closeHref = stateHref(viewState)
  const totals: Record<Topic, number> = {
    recipes: recipeResults.total,
    hardware: hardwareResults.total,
    models: modelResults.total,
    prices: priceResults.total,
    benchmark: benchmarkResults.total,
    "speed-sweep": sweepResults.total,
  }
  const total = topic ? totals[topic] : 0

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
    { label: "Runtime", name: "runtime", value: value("runtime"), options: [
      { label: "Any runtime", value: "" },
      { label: "Docker / compose", value: "docker" },
      { label: "Native / no docker", value: "native" },
      { label: "Evidence only", value: "reference" },
    ] },
    { label: "Evidence", name: "evidence", value: value("evidence"), options: facetOptions(["true", "false"], "Any evidence", (item) => item === "true" ? "Measured speed attached" : "No measured speed") },
  ]
  const topicFilters = topic === "recipes"
    ? recipeSearchFilters
    : topic === "hardware"
      ? [
          { label: "Vendor", name: "vendor", value: value("vendor"), options: facetOptions(facets.hardware.vendor, "Any vendor") },
          { label: "Backend", name: "backend", value: value("backend"), options: facetOptions(facets.hardware.backend, "Any backend") },
          { label: "Memory", name: "min_vram_gb", value: value("min_vram_gb"), options: facetOptions(facets.hardware.vram_gb, "Any memory", (item) => `At least ${item} GB`) },
          { label: "Pricing", name: "priced_only", value: value("priced_only"), options: facetOptions(["true"], "All hardware", () => "Priced only") },
          { label: "Recipes", name: "has_recipes", value: value("has_recipes"), options: facetOptions(["true", "false"], "All hardware", (item) => item === "true" ? "Has recipes" : "No recipes yet") },
        ]
      : topic === "models"
        ? [
            { label: "Family", name: "family", value: value("family"), options: facetOptions(facets.models.family, "Any family") },
            { label: "Architecture", name: "architecture", value: value("architecture"), options: facetOptions(facets.models.architecture, "Any architecture") },
          ]
        : topic === "prices"
          ? [
              { label: "Region", name: "region", value: value("region"), options: facetOptions(facets.prices.region, "Any region") },
              { label: "Category", name: "category", value: value("category"), options: facetOptions(facets.prices.category, "Any category") },
              { label: "Condition", name: "condition", value: value("condition"), options: facetOptions(facets.prices.condition, "Any condition") },
              { label: "Retailer", name: "retailer", value: value("retailer"), options: facetOptions(facets.prices.retailer, "Any retailer") },
              { label: "Availability", name: "in_stock", value: value("in_stock"), options: facetOptions(["true", "false", "unknown"], "Any availability", (item) => item === "true" ? "In stock" : item === "false" ? "Out of stock" : "Unknown stock") },
            ]
          : topic === "benchmark"
            ? [{ label: "Category", name: "category", value: value("category"), options: facetOptions(facets.benchmarks.category, "Any category") }]
            : []

  return (
    <main className="registry-main">
      <CollectionNav current={topic} query={query} />

      {!topic ? (
        <>
          <header className="overview-heading"><span className="mono-label">READ-ONLY / SOURCE-BACKED</span><h1>Registry index</h1></header>
          <section className="overview-search" aria-label="Search the registry"><RegistrySearch filters={[]} query={query} topic="" /></section>
          <nav aria-label="Registry topic counts" className="topic-index">
            {TOPICS.map((item, index) => {
              const count = matchCounts
                ? matchCounts[item.key]
                : item.key === "prices" ? priceTotal : item.countKey ? counts[item.countKey] : undefined
              return (
                <Link href={topicHref(item.key, query)} key={item.key}>
                  <span className="mono-label">0{index + 1}</span><strong>{item.label}</strong><span>{typeof count === "number" ? count.toLocaleString() : "—"}</span>
                </Link>
              )
            })}
          </nav>
          {query ? (
            <p className="topic-description">Matching records stay in their collection. Open Leaderboards for public scores such as Terminal-Bench 2.1, or Speed Sweeps for measured tok/s.</p>
          ) : (
            <section className="overview-recipes">
              <div className="section-heading"><div><span className="mono-label">VALIDATED / LAUNCH-SAFE</span><h2>Launch-safe recipes</h2></div><Link href="/?topic=recipes&validation=validated">View all</Link></div>
              <RecipeRows by="model" data={overviewRecipes.data} state={new URLSearchParams("topic=recipes&by=model&validation=validated")} />
            </section>
          )}
        </>
      ) : (
        <>
          <header className="topic-heading"><div><span className="mono-label">COLLECTION / {topic.toUpperCase()}</span><h1>{spec?.label}</h1><p className="topic-description">{spec?.description}</p></div><span className="topic-total">{total.toLocaleString()} records</span></header>
          <section className="topic-search" aria-label={`${spec?.label} search`}><RegistrySearch filters={topicFilters} query={query} topic={topic} /></section>
          {topic === "recipes" && <RecipeRows by={recipeBrowse} data={recipeResults.data} state={viewState} />}
          {topic === "hardware" && <HardwareRows data={hardwareResults.data} state={viewState} />}
          {topic === "models" && <ModelRows data={modelResults.data} state={viewState} />}
          {topic === "prices" && <PriceRows data={priceResults.data} state={viewState} />}
          {topic === "benchmark" && <BenchmarkRows data={benchmarkResults.data} state={viewState} />}
          {topic === "speed-sweep" && <SweepRows data={sweepResults.data} state={viewState} />}
          {total === 0 && <div className="empty-state"><h2>No records found.</h2><p>Clear the search or remove a filter.</p></div>}
          {(offset > 0 || offset + limit < total) && (
            <nav aria-label={`${spec?.label} pages`} className="pagination">
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
            <div><span className="mono-label">{topic.toUpperCase()} / RECORD</span><h2 id="record-modal-title">{recordTitle(selectedRecord, selectedId)}</h2><code>{selectedId}</code></div>
            <ModalCloseButton className="modal-close" closeHref={closeHref} label="Close record details">Close</ModalCloseButton>
          </header>
          <div className="record-modal-body">
            <RecordBody collection={topic} record={selectedRecord} variant="overlay" />
          </div>
          <footer className="record-modal-footer">
            <a href={`/api/v1/${topic}/${selectedId}`}>JSON API</a>
            <Link href={`/${topic}/${selectedId}`}>Permanent record URL</Link>
          </footer>
        </RecordModal>
      )}
    </main>
  )
}
