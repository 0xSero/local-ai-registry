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
  speed_sweeps: "Speed sweeps",
}

const TREE_OMIT = new Set(["launch", "huggingface", "relationships"])

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
