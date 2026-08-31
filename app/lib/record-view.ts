export type HuggingFaceIdentity = {
  link_type?: string
  reason?: string | { code: string; detail: string }
  repository?: string | null
  status?: string
  url?: string
}

export type RelatedLink = {
  href: string
  id: string
  label: string
}

export type RelatedGroup = {
  key: string
  label: string
  links: RelatedLink[]
  moreHref: string | null
  total: number
}

const RELATED_CAP = 8

const RELATION_LABELS: Record<string, string> = {
  hardware: "Hardware",
  model: "Model",
  model_instance: "Artifact",
  model_instances: "Artifacts",
  prices: "Prices",
  recipe: "Recipe",
  recipes: "Recipes",
  speed_sweep: "Speed sweeps",
}

const TREE_OMIT = new Set([
  "launch",
  "huggingface",
  "relationships",
  "description",
  "registry",
])

export type RecordFact = {
  href?: string
  label: string
  value: string
}

export type CopyItem = {
  label: string
  value: string
}

function nestedName(record: Record<string, unknown>, key: string): string | null {
  const value = record[key]
  if (value && typeof value === "object" && "name" in value && typeof value.name === "string") return value.name
  return null
}

export function recordTitle(detail: Record<string, unknown>, fallback: string): string {
  if (typeof detail.name === "string" && detail.name) return detail.name
  if (typeof detail.repository === "string" && detail.repository) return detail.repository
  return nestedName(detail, "product") ?? nestedName(detail, "model") ?? (typeof detail.id === "string" ? detail.id : fallback)
}

export function huggingFaceIdentity(record: Record<string, unknown>): HuggingFaceIdentity | null {
  const value = record.huggingface
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  return value as HuggingFaceIdentity
}

export function displayRecord(detail: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(detail).filter(([key]) => !TREE_OMIT.has(key)))
}

export function recipeIsLaunchable(record: Record<string, unknown>): boolean {
  const registry = record.registry
  return record.status === "validated"
    && !!registry
    && typeof registry === "object"
    && "launchable" in registry
    && registry.launchable === true
}

function isRecordLink(value: unknown): value is { href: string; id: string; name?: string } {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false
  const link = value as { href?: unknown; id?: unknown }
  return typeof link.href === "string" && typeof link.id === "string"
}

function moreHrefFor(key: string, record: Record<string, unknown>): string | null {
  const id = typeof record.id === "string" ? record.id : ""
  if (key === "recipes" && id) {
    if (typeof record.vendor === "string" || typeof record.memory === "object") return `/?topic=recipes&hardware_id=${encodeURIComponent(id)}`
    if (typeof record.family === "string") return `/?topic=recipes&model_id=${encodeURIComponent(id)}`
  }
  return null
}

export function relatedGroups(record: Record<string, unknown>): RelatedGroup[] {
  const relationships = record.relationships
  if (!relationships || typeof relationships !== "object" || Array.isArray(relationships)) return []
  const groups: RelatedGroup[] = []
  for (const [key, value] of Object.entries(relationships as Record<string, unknown>)) {
    const items = (Array.isArray(value) ? value : [value]).filter(isRecordLink)
    if (items.length === 0) continue
    groups.push({
      key,
      label: RELATION_LABELS[key] ?? key.replaceAll("_", " "),
      links: items.slice(0, RELATED_CAP).map((item) => ({
        href: item.href,
        id: item.id,
        label: item.name || item.id,
      })),
      moreHref: items.length > RELATED_CAP ? moreHrefFor(key, record) : null,
      total: items.length,
    })
  }
  return groups
}

function asObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function fact(label: string, value: unknown, href?: string): RecordFact | null {
  if (value === null || value === undefined || value === "") return null
  if (typeof value === "number" && Number.isFinite(value)) return { label, value: value.toLocaleString(), href }
  if (typeof value === "boolean") return { label, value: value ? "yes" : "no", href }
  if (typeof value === "string") return { label, value, href }
  return null
}

function capabilityFacts(record: Record<string, unknown>): RecordFact[] {
  const capabilities = asObject(record.capabilities)
  if (!capabilities) return []
  return ["chat", "reasoning", "tools", "vision"].flatMap((key) => {
    const value = capabilities[key]
    if (value === true) return [{ label: key, value: "yes" }]
    if (value === false) return [{ label: key, value: "no" }]
    return [{ label: key, value: "unknown" }]
  })
}

export function recordDescription(record: Record<string, unknown>): string | null {
  return typeof record.description === "string" && record.description.trim() ? record.description : null
}

export function recordFacts(collection: string, record: Record<string, unknown>): RecordFact[] {
  const engine = asObject(record.engine)
  const serving = asObject(record.serving)
  const memory = asObject(record.memory)
  const weights = asObject(record.weights)
  const product = asObject(record.product)
  const region = asObject(record.region)
  const summary = asObject(record.summary)
  if (collection === "recipes") {
    return [
      fact("Status", record.status),
      fact("Source", record.recipe_source),
      fact("Engine", engine?.name),
      fact("Engine version", engine?.version),
      fact("Graph", engine?.graph_mode),
      fact("Accelerators", record.hardware_count),
      fact("Tensor parallel", serving?.tensor_parallel),
      fact("Context tokens", serving?.max_context_tokens),
      fact("Max concurrency", serving?.max_concurrency),
      fact("KV cache tokens", serving?.kv_cache_tokens),
      ...capabilityFacts(record),
    ].filter((item): item is RecordFact => item !== null)
  }
  if (collection === "hardware") {
    return [
      fact("Vendor", record.vendor),
      fact("Kind", record.kind),
      fact("Backend", record.accelerator_backend),
      fact("VRAM", memory?.vram_gb === undefined ? null : `${memory.vram_gb} GB`),
      fact("Memory type", memory?.vram_type),
      fact("Bandwidth", (() => {
        const bandwidth = memory?.bandwidth_gb_per_s
        if (bandwidth === undefined || bandwidth === null) return null
        if (typeof bandwidth === "object") {
          const range = bandwidth as { min?: number; max?: number }
          return `${range.min ?? "?"}–${range.max ?? "?"} GB/s`
        }
        return `${bandwidth} GB/s`
      })()),
    ].filter((item): item is RecordFact => item !== null)
  }
  if (collection === "models") {
    const downloads = asObject(record.downloads)
    const monthly = typeof downloads?.last_30d === "number" ? downloads.last_30d.toLocaleString("en-US") : null
    return [
      fact("Family", record.family),
      fact("Architecture", record.architecture),
      fact("Parameters", record.params),
      fact("Active parameters", record.active_params),
      fact("HF downloads / 30d", monthly),
    ].filter((item): item is RecordFact => item !== null)
  }
  if (collection === "model-instances") {
    return [
      fact("Repository", record.repository),
      fact("Revision", record.revision),
      fact("Precision", weights?.precision),
      fact("Format", weights?.format),
    ].filter((item): item is RecordFact => item !== null)
  }
  if (collection === "prices") {
    return [
      fact("Product", product?.name),
      fact("Region", region?.name ?? region?.code),
      fact("Currency", region?.currency),
      fact("Listings", summary?.listing_count),
    ].filter((item): item is RecordFact => item !== null)
  }
  if (collection === "speed-sweep") {
    const rows = Array.isArray(record.rows) ? record.rows.length : null
    return [
      fact("Recipe", record.recipe_id, typeof record.recipe_id === "string" ? `/recipes/${record.recipe_id}` : undefined),
      fact("Measured", record.measured_at),
      fact("Accepted", record.accepted_at),
      fact("Points", rows),
    ].filter((item): item is RecordFact => item !== null)
  }
  if (collection === "benchmark") {
    const rows = Array.isArray(record.rows) ? record.rows.length : null
    return [
      fact("Category", record.category),
      fact("Scored models", rows),
    ].filter((item): item is RecordFact => item !== null)
  }
  return []
}

export function copyItems(collection: string, record: Record<string, unknown>): CopyItem[] {
  const id = typeof record.id === "string" ? record.id : ""
  const items: CopyItem[] = []
  if (id) {
    items.push({ label: "ID", value: id })
    items.push({ label: "JSON API", value: `/api/v1/${collection}/${id}` })
    items.push({ label: "Record URL", value: `/${collection}/${id}` })
  }
  const hub = huggingFaceIdentity(record)
  if (hub?.status === "known" && hub.url) items.push({ label: "Hub repository", value: hub.url })
  if (typeof record.revision === "string" && record.revision) items.push({ label: "Revision", value: record.revision })
  if (recipeIsLaunchable(record)) {
    const launch = asObject(record.launch)
    const args = Array.isArray(launch?.arguments) ? launch.arguments.filter((item): item is string => typeof item === "string") : []
    if (args.length > 0) items.push({ label: "Launch arguments", value: args.join(" ") })
  }
  return items
}
