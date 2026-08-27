import { readFileSync } from "node:fs"
import path from "node:path"

import type {
  Hardware,
  Model,
  ModelInstance,
  Recipe,
  RegistryIndex,
  SpeedSweep,
} from "@/registry/schema/types"

export type ArtifactResolution =
  | "hugging_face"
  | "non_hugging_face"
  | "unresolved"
  | "invalid_url"

export type ModelInstanceResult = ModelInstance & {
  artifact_resolution: ArtifactResolution
  hugging_face_url: string | null
}

export type CompatibilityFilters = {
  backend?: string
  chat?: string
  engine?: string
  evidence?: string
  hardware_id?: string
  hardware?: string
  hardware_count?: string
  instance_kind?: string
  launch_kind?: string
  launchable?: string
  max_vram_gb?: string
  min_vram_gb?: string
  model_id?: string
  model_instance_id?: string
  model?: string
  precision?: string
  q?: string
  reasoning?: string
  status?: string
  tools?: string
  vendor?: string
  vision?: string
}

export type Pagination = {
  limit: number
  offset: number
}

export type CompatibilityResult = {
  hardware: Hardware
  id: string
  launchable: boolean
  links: {
    api: string
    detail: string
    hardware: string
    model: string
    model_instance: string
  }
  model: Model
  model_instance: ModelInstanceResult
  recipe: Recipe
  speed_evidence: {
    available: boolean
    count: number
    detail_urls: string[]
    sweep_ids: string[]
  }
}

type RegistryRecord = Record<string, unknown>
type CompatibilityRow = RegistryIndex["recipes"][number]

type Dataset = {
  hardware: Map<string, Hardware>
  index: RegistryIndex
  instances: Map<string, ModelInstance>
  models: Map<string, Model>
  recipes: Map<string, Recipe>
  sweeps: Map<string, SpeedSweep>
}

let cachedDataset: Dataset | undefined


function readJson<T>(...parts: string[]): T {
  return JSON.parse(
    readFileSync(path.join(process.cwd(), "registry", ...parts), "utf8"),
  ) as T
}

function loadCollection<T>(
  index: RegistryIndex,
  collection: keyof RegistryIndex["collections"],
): Map<string, T> {
  return new Map(
    index.collections[collection].map((id) => [
      id,
      readJson<T>(collection, `${id}.json`),
    ]),
  )
}

function dataset(): Dataset {
  if (cachedDataset) return cachedDataset

  const index = readJson<RegistryIndex>("index.json")
  cachedDataset = {
    hardware: loadCollection<Hardware>(index, "hardware"),
    index,
    instances: loadCollection<ModelInstance>(index, "model-instance"),
    models: loadCollection<Model>(index, "model"),
    recipes: new Map(),
    sweeps: new Map(),
  }
  return cachedDataset
}

function cachedRecord<T>(
  collection: "recipe" | "speed-sweeps",
  id: string,
  cache: Map<string, T>,
): T | undefined {
  const ids = dataset().index.collections[collection]
  if (!ids.includes(id)) return undefined
  const existing = cache.get(id)
  if (existing) return existing
  const record = readJson<T>(collection, `${id}.json`)
  cache.set(id, record)
  return record
}

export function getRegistryIndex(): RegistryIndex {
  return dataset().index
}

export function getModel(id: string): Model | undefined {
  return dataset().models.get(id)
}

export function getModelInstance(id: string): ModelInstance | undefined {
  return dataset().instances.get(id)
}

export function getHardware(id: string): Hardware | undefined {
  return dataset().hardware.get(id)
}

export function getRecipe(id: string): Recipe | undefined {
  return cachedRecord("recipe", id, dataset().recipes)
}

export function getSpeedSweep(id: string): SpeedSweep | undefined {
  return cachedRecord("speed-sweeps", id, dataset().sweeps)
}

export function modelInstanceResult(instance: ModelInstance): ModelInstanceResult {
  const bodyUrl = typeof instance.url === "string" ? instance.url : null
  if (!bodyUrl) {
    return {
      ...instance,
      artifact_resolution: "unresolved",
      hugging_face_url: null,
    }
  }

  try {
    const hostname = new URL(bodyUrl).hostname.toLowerCase()
    const isHuggingFace = hostname === "huggingface.co" || hostname === "www.huggingface.co"
    return {
      ...instance,
      artifact_resolution: isHuggingFace ? "hugging_face" : "non_hugging_face",
      hugging_face_url: isHuggingFace ? bodyUrl : null,
    }
  } catch {
    return {
      ...instance,
      artifact_resolution: "invalid_url",
      hugging_face_url: null,
    }
  }
}

function primitiveText(value: unknown): string[] {
  if (value === null || value === undefined) return []
  if (Array.isArray(value)) return value.flatMap(primitiveText)
  if (typeof value === "object") return Object.values(value).flatMap(primitiveText)
  return [String(value)]
}

function contains(record: unknown, query: string | undefined): boolean {
  if (!query?.trim()) return true
  const terms = query.toLowerCase().trim().split(/\s+/)
  const haystack = primitiveText(record).join(" ").toLowerCase()
  return terms.every((term) => haystack.includes(term))
}

function equals(value: unknown, filter: string | undefined): boolean {
  if (!filter?.trim()) return true
  return String(value ?? "").toLowerCase() === filter.toLowerCase()
}

function numericFilter(value: number, minimum?: string, maximum?: string): boolean {
  const min = minimum ? Number(minimum) : undefined
  const max = maximum ? Number(maximum) : undefined
  if (min !== undefined && Number.isFinite(min) && value < min) return false
  if (max !== undefined && Number.isFinite(max) && value > max) return false
  return true
}

function booleanFilter(value: boolean | null, filter: string | undefined): boolean {
  if (!filter) return true
  if (filter === "unknown") return value === null
  if (filter === "true") return value === true
  if (filter === "false") return value === false
  return true
}

export function isLaunchable(row: Pick<CompatibilityRow, "status" | "launch_kind">): boolean {
  return row.status === "validated" && row.launch_kind !== "reference"
}

function matchingCompatibilityRows(filters: CompatibilityFilters): CompatibilityRow[] {
  const data = dataset()

  return data.index.recipes.filter((row) => {
    const instance = data.instances.get(row.model_instance_id)
    const model = instance ? data.models.get(instance.model_id) : undefined
    const hardware = data.hardware.get(row.hardware_id)
    if (!instance || !model || !hardware) return false

    if (!contains([model, instance], filters.model)) return false
    if (!contains(hardware, filters.hardware)) return false
    if (!contains([row, model, instance, hardware], filters.q)) return false
    if (!equals(model.id, filters.model_id)) return false
    if (!equals(instance.id, filters.model_instance_id)) return false
    if (!equals(hardware.id, filters.hardware_id)) return false
    if (!equals(row.status, filters.status)) return false
    if (!equals(row.engine, filters.engine)) return false
    if (!equals(row.launch_kind, filters.launch_kind)) return false
    if (!equals(instance.weights.precision, filters.precision)) return false
    if (!equals(instance.kind, filters.instance_kind)) return false
    if (!equals(hardware.vendor, filters.vendor)) return false
    if (!equals(hardware.accelerator_backend, filters.backend)) return false
    if (!equals(row.hardware_count, filters.hardware_count)) return false
    if (!numericFilter(hardware.memory.vram_gb, filters.min_vram_gb, filters.max_vram_gb)) return false
    if (!booleanFilter(row.capabilities.chat, filters.chat)) return false
    if (!booleanFilter(row.capabilities.reasoning, filters.reasoning)) return false
    if (!booleanFilter(row.capabilities.tools, filters.tools)) return false
    if (!booleanFilter(row.capabilities.vision, filters.vision)) return false
    if (filters.evidence === "true" && !row.has_evidence) return false
    if (filters.evidence === "false" && row.has_evidence) return false
    if (filters.launchable === "true" && !isLaunchable(row)) return false
    if (filters.launchable === "false" && isLaunchable(row)) return false
    return true
  })
}

function compatibilityResult(row: CompatibilityRow): CompatibilityResult | undefined {
  const data = dataset()
  const instance = data.instances.get(row.model_instance_id)
  const model = instance ? data.models.get(instance.model_id) : undefined
  const hardware = data.hardware.get(row.hardware_id)
  const recipe = getRecipe(row.id)
  if (!instance || !model || !hardware || !recipe) return undefined

  return {
    id: row.id,
    launchable: isLaunchable(row),
    model,
    model_instance: modelInstanceResult(instance),
    hardware,
    recipe,
    speed_evidence: {
      available: row.has_evidence,
      count: recipe.speed_sweeps_ids.length,
      sweep_ids: recipe.speed_sweeps_ids,
      detail_urls: recipe.speed_sweeps_ids.map((id) => `/api/v1/speed-sweeps/${id}`),
    },
    links: {
      api: `/api/v1/recipes/${row.id}`,
      detail: `/recipes/${row.id}`,
      hardware: `/hardware/${hardware.id}`,
      model: `/models/${model.id}`,
      model_instance: `/model-instances/${instance.id}`,
    },
  }
}

export function queryCompatibility(
  filters: CompatibilityFilters,
  pagination: Pagination,
): { data: CompatibilityResult[]; total: number } {
  const rows = matchingCompatibilityRows(filters)
  const selected = rows.slice(pagination.offset, pagination.offset + pagination.limit)
  return {
    data: selected.flatMap((row) => {
      const result = compatibilityResult(row)
      return result ? [result] : []
    }),
    total: rows.length,
  }
}

export function listModels(filters: Record<string, string>, pagination: Pagination) {
  const all = [...dataset().models.values()].filter(
    (model) =>
      contains(model, filters.q) &&
      equals(model.family, filters.family) &&
      equals(model.architecture, filters.architecture),
  )
  return { data: all.slice(pagination.offset, pagination.offset + pagination.limit), total: all.length }
}

export function listModelInstances(filters: Record<string, string>, pagination: Pagination) {
  const all = [...dataset().instances.values()]
    .map(modelInstanceResult)
    .filter(
      (instance) =>
        contains(instance, filters.q) &&
        equals(instance.model_id, filters.model_id) &&
        equals(instance.kind, filters.kind) &&
        equals(instance.weights.precision, filters.precision) &&
        equals(instance.weights.format, filters.format) &&
        equals(instance.artifact_resolution, filters.artifact_resolution),
    )
  return { data: all.slice(pagination.offset, pagination.offset + pagination.limit), total: all.length }
}

export function listHardware(filters: Record<string, string>, pagination: Pagination) {
  const all = [...dataset().hardware.values()].filter(
    (hardware) =>
      contains(hardware, filters.q) &&
      equals(hardware.vendor, filters.vendor) &&
      equals(hardware.accelerator_backend, filters.backend) &&
      equals(hardware.kind, filters.kind) &&
      equals(hardware.family, filters.family) &&
      numericFilter(hardware.memory.vram_gb, filters.min_vram_gb, filters.max_vram_gb),
  )
  return { data: all.slice(pagination.offset, pagination.offset + pagination.limit), total: all.length }
}

export function listSpeedSweeps(filters: Record<string, string>, pagination: Pagination) {
  const ids = dataset().index.collections["speed-sweeps"]
  const all = ids.flatMap((id) => {
    const sweep = getSpeedSweep(id)
    if (!sweep) return []
    if (!contains(sweep, filters.q) || !equals(sweep.recipe_id, filters.recipe_id)) return []
    return [sweep]
  })
  return { data: all.slice(pagination.offset, pagination.offset + pagination.limit), total: all.length }
}

function recipeRowsForModel(modelId: string): CompatibilityRow[] {
  const instanceIds = new Set(
    [...dataset().instances.values()]
      .filter((instance) => instance.model_id === modelId)
      .map((instance) => instance.id),
  )
  return dataset().index.recipes.filter((row) => instanceIds.has(row.model_instance_id))
}

export function getEntityDetail(collection: string, id: string): RegistryRecord | undefined {
  const data = dataset()

  if (collection === "models") {
    const model = data.models.get(id)
    if (!model) return undefined
    const instances = [...data.instances.values()]
      .filter((instance) => instance.model_id === id)
      .map(modelInstanceResult)
    return {
      ...model,
      model_instances: instances,
      recipes: recipeRowsForModel(id),
    }
  }

  if (collection === "model-instances") {
    const instance = data.instances.get(id)
    if (!instance) return undefined
    return {
      ...modelInstanceResult(instance),
      model: data.models.get(instance.model_id) ?? null,
      recipes: data.index.recipes.filter((row) => row.model_instance_id === id),
    }
  }

  if (collection === "hardware") {
    const hardware = data.hardware.get(id)
    if (!hardware) return undefined
    return {
      ...hardware,
      recipes: data.index.recipes.filter((row) => row.hardware_id === id),
    }
  }

  if (collection === "recipes") {
    const row = data.index.recipes.find((candidate) => candidate.id === id)
    if (!row) return undefined
    const result = compatibilityResult(row)
    if (!result) return undefined
    const recipe = result.recipe
    return {
      ...result,
      speed_sweeps: recipe.speed_sweeps_ids.flatMap((sweepId) => {
        const sweep = getSpeedSweep(sweepId)
        return sweep ? [sweep] : []
      }),
    }
  }

  if (collection === "speed-sweeps") {
    const sweep = getSpeedSweep(id)
    if (!sweep) return undefined
    const recipe = getRecipe(sweep.recipe_id)
    return {
      ...sweep,
      recipe: recipe ?? null,
    }
  }

  return undefined
}

function unique(values: Array<string | number | null | undefined>): Array<string | number> {
  return [...new Set(values.filter((value): value is string | number => value !== null && value !== undefined))]
    .sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true }))
}

export function getFacets() {
  const data = dataset()
  return {
    models: {
      architecture: unique([...data.models.values()].map((model) => model.architecture)),
      family: unique([...data.models.values()].map((model) => model.family)),
    },
    model_instances: {
      artifact_resolution: unique([...data.instances.values()].map((instance) => modelInstanceResult(instance).artifact_resolution)),
      format: unique([...data.instances.values()].map((instance) => instance.weights.format)),
      kind: unique([...data.instances.values()].map((instance) => instance.kind)),
      precision: unique([...data.instances.values()].map((instance) => instance.weights.precision)),
    },
    hardware: {
      backend: unique([...data.hardware.values()].map((hardware) => hardware.accelerator_backend)),
      kind: unique([...data.hardware.values()].map((hardware) => hardware.kind)),
      vendor: unique([...data.hardware.values()].map((hardware) => hardware.vendor)),
      vram_gb: unique([...data.hardware.values()].map((hardware) => hardware.memory.vram_gb)),
    },
    recipes: {
      engine: unique(data.index.recipes.map((recipe) => recipe.engine)),
      hardware_count: unique(data.index.recipes.map((recipe) => recipe.hardware_count)),
      launch_kind: unique(data.index.recipes.map((recipe) => recipe.launch_kind)),
      status: unique(data.index.recipes.map((recipe) => recipe.status)),
    },
  }
}

export function collectionCounts(): RegistryIndex["counts"] {
  return dataset().index.counts
}
