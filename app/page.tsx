import Link from "next/link"

import { DataTree } from "@/app/components/data-tree"
import {
  collectionCounts,
  getFacets,
  queryCompatibility,
  type CompatibilityFilters,
} from "@/lib/registry"

export const dynamic = "force-dynamic"

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}


export default async function Home({ searchParams }: PageProps) {
  const params = await searchParams
  const value = (key: string) => {
    const selected = params[key]
    return Array.isArray(selected) ? selected[0] : selected ?? ""
  }
  const filters: CompatibilityFilters = {
    chat: value("chat"),
    engine: value("engine"),
    evidence: value("evidence"),
    hardware: value("hardware"),
    hardware_count: value("hardware_count"),
    launchable: value("launchable"),
    min_vram_gb: value("min_vram_gb"),
    model: value("model"),
    precision: value("precision"),
    status: value("status"),
    tools: value("tools"),
    vendor: value("vendor"),
    vision: value("vision"),
  }
  const offset = Math.max(0, Number(value("offset")) || 0)
  const limit = 24
  const results = queryCompatibility(filters, { limit, offset })
  const facets = getFacets()
  const counts = collectionCounts()

  const activeParams = new URLSearchParams()
  for (const [key, selected] of Object.entries(params)) {
    if (typeof selected === "string" && selected && key !== "offset") activeParams.set(key, selected)
  }
  const previousParams = new URLSearchParams(activeParams)
  previousParams.set("offset", String(Math.max(0, offset - limit)))
  const nextParams = new URLSearchParams(activeParams)
  nextParams.set("offset", String(offset + limit))

  return (
    <main>
      <section className="hero">
        <div>
          <p className="eyebrow">Normalized, source-backed, read-only</p>
          <h1>Resolve a model <span aria-hidden="true">×</span> machine.</h1>
          <p className="lede">
            Search the registry&apos;s artifacts, hardware profiles, recipes, and measured evidence.
            Candidate references remain visible, never mislabeled as launch-safe.
          </p>
        </div>
        <dl className="registry-counts" aria-label="Registry collection counts">
          <div><dt>Models</dt><dd>{counts.model.toLocaleString()}</dd></div>
          <div><dt>Artifacts</dt><dd>{counts.model_instance.toLocaleString()}</dd></div>
          <div><dt>Hardware</dt><dd>{counts.hardware.toLocaleString()}</dd></div>
          <div><dt>Recipes</dt><dd>{counts.recipe.toLocaleString()}</dd></div>
        </dl>
      </section>

      <form className="resolver" method="get">
        <div className="resolver-primary">
          <label>
            <span>Model or artifact</span>
            <input defaultValue={filters.model} name="model" placeholder="Qwen, Gemma, GGUF, NVFP4…" />
          </label>
          <span className="operator" aria-hidden="true">×</span>
          <label>
            <span>Hardware</span>
            <input defaultValue={filters.hardware} name="hardware" placeholder="RTX 4090, M4 Max, 96 GB…" />
          </label>
          <button type="submit">Find compatibility</button>
        </div>

        <details className="filters" open={Object.values(filters).some(Boolean)}>
          <summary>Filters derived from registry fields</summary>
          <div className="filter-grid">
            <label>
              <span>Trust status</span>
              <select defaultValue={filters.status} name="status">
                <option value="">Any status</option>
                {facets.recipes.status.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
            <label>
              <span>Launchability</span>
              <select defaultValue={filters.launchable} name="launchable">
                <option value="">Any</option>
                <option value="true">Validated launch contract</option>
                <option value="false">Not launch-safe</option>
              </select>
            </label>
            <label>
              <span>Engine</span>
              <select defaultValue={filters.engine} name="engine">
                <option value="">Any engine</option>
                {facets.recipes.engine.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
            <label>
              <span>Precision</span>
              <select defaultValue={filters.precision} name="precision">
                <option value="">Any precision</option>
                {facets.model_instances.precision.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
            <label>
              <span>Hardware vendor</span>
              <select defaultValue={filters.vendor} name="vendor">
                <option value="">Any vendor</option>
                {facets.hardware.vendor.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
            <label>
              <span>Minimum accelerator memory</span>
              <select defaultValue={filters.min_vram_gb} name="min_vram_gb">
                <option value="">Any capacity</option>
                {facets.hardware.vram_gb.map((option) => <option key={option} value={option}>{option} GB</option>)}
              </select>
            </label>
            <label>
              <span>Hardware count</span>
              <select defaultValue={filters.hardware_count} name="hardware_count">
                <option value="">Any count</option>
                {facets.recipes.hardware_count.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
            <label>
              <span>Speed evidence</span>
              <select defaultValue={filters.evidence} name="evidence">
                <option value="">Any</option>
                <option value="true">Evidence attached</option>
                <option value="false">No evidence attached</option>
              </select>
            </label>
            <label>
              <span>Chat capability</span>
              <select defaultValue={filters.chat} name="chat">
                <option value="">Any</option>
                <option value="true">Yes</option><option value="false">No</option><option value="unknown">Unknown</option>
              </select>
            </label>
            <label>
              <span>Tool capability</span>
              <select defaultValue={filters.tools} name="tools">
                <option value="">Any</option>
                <option value="true">Yes</option><option value="false">No</option><option value="unknown">Unknown</option>
              </select>
            </label>
            <label>
              <span>Vision capability</span>
              <select defaultValue={filters.vision} name="vision">
                <option value="">Any</option>
                <option value="true">Yes</option><option value="false">No</option><option value="unknown">Unknown</option>
              </select>
            </label>
          </div>
        </details>
      </form>

      <section className="results" aria-live="polite">
        <div className="results-heading">
          <div>
            <p className="eyebrow">Compatibility units</p>
            <h2>{results.total.toLocaleString()} result{results.total === 1 ? "" : "s"}</h2>
          </div>
          {activeParams.size > 0 && <Link className="quiet-link" href="/">Clear search</Link>}
        </div>

        {results.data.length === 0 ? (
          <div className="empty-state">
            <h3>No recipe matches every selected field.</h3>
            <p>Remove a filter or search one side of the model × hardware resolver.</p>
          </div>
        ) : (
          <div className="result-list">
            {results.data.map((result) => {
              const { hardware, model, model_instance: instance, recipe } = result
              const image = typeof recipe.launch.image === "string" ? recipe.launch.image : null
              const trustLabel = result.launchable
                ? "Validated · launch-safe"
                : recipe.launch.kind === "reference"
                  ? "Reference only · not launch-safe"
                  : "Candidate · not launch-safe"
              return (
                <article className="result-card" key={result.id}>
                  <div className="result-topline">
                    <span className={result.launchable ? "badge validated" : "badge candidate"}>{trustLabel}</span>
                    <code>{result.id}</code>
                  </div>
                  <h3>
                    <Link href={`/models/${model.id}`}>{model.name}</Link>
                    <span aria-hidden="true"> × </span>
                    <Link href={`/hardware/${hardware.id}`}>{hardware.name}</Link>
                  </h3>
                  <div className="result-facts">
                    <span>{instance.weights.precision ?? "Precision unknown"}</span>
                    <span>{hardware.memory.vram_gb} GB</span>
                    <span>{recipe.engine.name}{recipe.engine.version ? ` ${recipe.engine.version}` : ""}</span>
                    <span>{recipe.launch.kind}</span>
                  </div>

                  <div className="artifact-link">
                    <strong>Model instance:</strong>{" "}
                    <Link href={`/model-instances/${instance.id}`}>{instance.repository}</Link>
                    {instance.hugging_face_url ? (
                      <a href={instance.hugging_face_url} rel="noreferrer" target="_blank">Hugging Face ↗</a>
                    ) : instance.artifact_resolution === "non_hugging_face" && instance.url ? (
                      <a href={instance.url} rel="noreferrer" target="_blank">Non-Hugging-Face artifact ↗</a>
                    ) : (
                      <span className="unknown">Canonical Hugging Face URL unresolved</span>
                    )}
                  </div>

                  {image && (
                    <p className="image-line"><strong>Image</strong> <code>{image}</code></p>
                  )}

                  <div className="progressive-details">
                    <details>
                      <summary>Artifact and hardware specifications</summary>
                      <h4>Model instance</h4><DataTree value={instance} />
                      <h4>Hardware</h4><DataTree value={hardware} />
                    </details>
                    <details>
                      <summary>Recipe, engine, and launch contract</summary>
                      <DataTree value={{
                        capabilities: recipe.capabilities,
                        engine: recipe.engine,
                        launch: recipe.launch,
                        serving: recipe.serving,
                        status: recipe.status,
                      }} />
                    </details>
                    <details>
                      <summary>Speed evidence ({recipe.speed_sweeps_ids.length})</summary>
                      {recipe.speed_sweeps_ids.length > 0 ? (
                        <ul className="link-list">
                          {recipe.speed_sweeps_ids.map((id) => (
                            <li key={id}><Link href={`/speed-sweeps/${id}`}>{id}</Link></li>
                          ))}
                        </ul>
                      ) : <p className="unknown">No speed sweep attached.</p>}
                    </details>
                  </div>
                  <Link className="detail-link" href={`/recipes/${result.id}`}>Open complete recipe record →</Link>
                </article>
              )
            })}
          </div>
        )}

        {(offset > 0 || offset + limit < results.total) && (
          <nav className="pagination" aria-label="Results pages">
            {offset > 0 ? <Link href={`/?${previousParams}`}>← Previous</Link> : <span />}
            <span>{offset + 1}–{Math.min(offset + limit, results.total)} of {results.total}</span>
            {offset + limit < results.total ? <Link href={`/?${nextParams}`}>Next →</Link> : <span />}
          </nav>
        )}
      </section>
    </main>
  )
}
