import { readFileSync } from "node:fs"
import path from "node:path"

import type {
  Hardware,
  Model,
  ModelInstance,
  PriceRecord,
  Recipe,
  RegistryIndex,
  SpeedSweep,
} from "@/registry/schema/types"

export type HuggingFaceIdentity = {
  link_type: "repository" | "search"
  status: "known" | "unknown" | "unavailable"
  url: string
  [key: string]: unknown
}

type RegistryModelInstance = Omit<ModelInstance, "huggingface"> & {
  huggingface: HuggingFaceIdentity
}

export type ModelInstanceResult = RegistryModelInstance & {
  hugging_face_url: string
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
  sort_by?: string
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

export type PriceResult = PriceRecord

type RegistryRecord = Record<string, unknown>
type CompatibilityRow = RegistryIndex["recipes"][number]

type RecordLink = {
  api: string
  href: string
  id: string
  name?: string
}

type Dataset = {
  hardware: Map<string, Hardware>
  index: RegistryIndex
  instances: Map<string, RegistryModelInstance>
  models: Map<string, Model>
  prices: Map<string, PriceRecord>
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
    instances: loadCollection<RegistryModelInstance>(index, "model-instance"),
    models: loadCollection<Model>(index, "model"),
    prices: new Map(
      (index.collections.price ?? []).map((id) => {
        const separator = id.lastIndexOf("--")
        const productId = id.slice(0, separator)
        const region = id.slice(separator + 2)
        return [id, readJson<PriceRecord>("price", productId, `${region}.json`)]
      }),
    ),
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

export function getModelInstance(id: string): RegistryModelInstance | undefined {
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

export function modelInstanceResult(instance: RegistryModelInstance): ModelInstanceResult {
  if (instance.huggingface.url.length === 0) {
    throw new Error(`Model instance '${instance.id}' has an empty authoritative Hugging Face URL`)
  }

  return {
    ...instance,
    hugging_face_url: instance.huggingface.url,
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
  const data = dataset()
  const primary = filters.sort_by === "model" ? "model" : "hardware"
  const rows = matchingCompatibilityRows(filters).sort((left, right) => {
    const leftInstance = data.instances.get(left.model_instance_id)
    const rightInstance = data.instances.get(right.model_instance_id)
    const leftModel = leftInstance ? data.models.get(leftInstance.model_id)?.name ?? leftInstance.model_id : left.model_instance_id
    const rightModel = rightInstance ? data.models.get(rightInstance.model_id)?.name ?? rightInstance.model_id : right.model_instance_id
    const leftHardware = data.hardware.get(left.hardware_id)?.name ?? left.hardware_id
    const rightHardware = data.hardware.get(right.hardware_id)?.name ?? right.hardware_id
    const leftKeys = primary === "hardware" ? [leftHardware, leftModel] : [leftModel, leftHardware]
    const rightKeys = primary === "hardware" ? [rightHardware, rightModel] : [rightModel, rightHardware]
    return leftKeys[0].localeCompare(rightKeys[0], undefined, { numeric: true })
      || leftKeys[1].localeCompare(rightKeys[1], undefined, { numeric: true })
      || left.engine.localeCompare(right.engine)
      || left.id.localeCompare(right.id)
  })
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
      (filters.architecture === "unknown" ? model.architecture === null : equals(model.architecture, filters.architecture)),
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
        equals(instance.huggingface.status, filters.huggingface_status) &&
        equals(instance.huggingface.link_type, filters.huggingface_link_type),
    )
  return { data: all.slice(pagination.offset, pagination.offset + pagination.limit), total: all.length }
}

export function listHardware(filters: Record<string, string>, pagination: Pagination) {
  const all = [...dataset().hardware.values()].filter((hardware) => {
    const hasPrices = marketPriceCount(hardware.id) > 0
    return (
      contains(hardware, filters.q) &&
      equals(hardware.vendor, filters.vendor) &&
      equals(hardware.accelerator_backend, filters.backend) &&
      equals(hardware.kind, filters.kind) &&
      equals(hardware.family, filters.family) &&
      numericFilter(hardware.memory.vram_gb, filters.min_vram_gb, filters.max_vram_gb) &&
      booleanFilter(hasPrices, filters.priced_only)
    )
  })
  return { data: all.slice(pagination.offset, pagination.offset + pagination.limit), total: all.length }
}

function priceAmount(record: PriceRecord): number | null {
  return record.summary.lowest_new ?? record.summary.lowest_refurbished ?? record.summary.lowest_used
}

function priceResults(): PriceResult[] {
  return [...dataset().prices.values()]
}

export function marketPriceCount(hardwareId: string): number {
  return priceResults().filter((record) => record.hardware.some((hardware) => hardware.id === hardwareId)).length
}

export function listPrices(filters: Record<string, string>, pagination: Pagination) {
  const all = priceResults().filter((record) => {
    const amount = priceAmount(record)
    return (
      contains(record, filters.q) &&
      equals(record.product.category, filters.category) &&
      equals(record.region.code, filters.region) &&
      equals(record.region.currency, filters.currency) &&
      (!filters.condition || record.observations.some((observation) => equals(observation.condition, filters.condition))) &&
      (!filters.retailer || record.observations.some((observation) => equals(observation.retailer, filters.retailer))) &&
      (!filters.in_stock || record.observations.some((observation) => booleanFilter(observation.in_stock, filters.in_stock))) &&
      (amount === null ? !filters.min_price && !filters.max_price : numericFilter(amount, filters.min_price, filters.max_price))
    )
  })
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

function recordLink(collection: string, id: string, name?: string): RecordLink {
  return {
    api: `/api/v1/${collection}/${id}`,
    href: `/${collection}/${id}`,
    id,
    ...(name ? { name } : {}),
  }
}

function recipeLink(row: CompatibilityRow): RecordLink & Pick<CompatibilityRow, "engine" | "hardware_count" | "status"> {
  return {
    ...recordLink("recipes", row.id),
    engine: row.engine,
    hardware_count: row.hardware_count,
    status: row.status,
  }
}

function modelLinksForRows(rows: CompatibilityRow[]): RecordLink[] {
  const links = new Map<string, RecordLink>()
  for (const row of rows) {
    const instance = dataset().instances.get(row.model_instance_id)
    const model = instance ? dataset().models.get(instance.model_id) : undefined
    if (model) links.set(model.id, recordLink("models", model.id, model.name))
  }
  return [...links.values()]
}

function hardwareLinksForRows(rows: CompatibilityRow[]): RecordLink[] {
  const links = new Map<string, RecordLink>()
  for (const row of rows) {
    const hardware = dataset().hardware.get(row.hardware_id)
    if (hardware) links.set(hardware.id, recordLink("hardware", hardware.id, hardware.name))
  }
  return [...links.values()]
}

export function getEntityDetail(collection: string, id: string): RegistryRecord | undefined {
  const data = dataset()

  if (collection === "models") {
    const model = data.models.get(id)
    if (!model) return undefined
    const instances = [...data.instances.values()].filter((instance) => instance.model_id === id)
    const rows = recipeRowsForModel(id)
    return {
      ...model,
      relationships: {
        hardware: hardwareLinksForRows(rows),
        model_instances: instances.map((instance) => recordLink("model-instances", instance.id, instance.repository)),
        recipes: rows.map(recipeLink),
      },
    }
  }

  if (collection === "model-instances") {
    const instance = data.instances.get(id)
    if (!instance) return undefined
    return {
      ...modelInstanceResult(instance),
      relationships: {
        hardware: hardwareLinksForRows(data.index.recipes.filter((row) => row.model_instance_id === id)),
        model: recordLink("models", instance.model_id, data.models.get(instance.model_id)?.name),
        recipes: data.index.recipes.filter((row) => row.model_instance_id === id).map(recipeLink),
      },
    }
  }

  if (collection === "hardware") {
    const hardware = data.hardware.get(id)
    if (!hardware) return undefined
    const rows = data.index.recipes.filter((row) => row.hardware_id === id)
    return {
      ...hardware,
      relationships: {
        models: modelLinksForRows(rows),
        prices: priceResults()
          .filter((record) => record.hardware.some((candidate) => candidate.id === id))
          .map((record) => recordLink("prices", record.id, `${record.product.name} · ${record.region.code}`)),
        recipes: rows.map(recipeLink),
      },
    }
  }

  if (collection === "prices") {
    const price = data.prices.get(id)
    if (!price) return undefined
    return {
      ...price,
      relationships: {
        hardware: price.hardware.map(({ id: hardwareId, match_scope }) => ({
          ...recordLink("hardware", hardwareId, data.hardware.get(hardwareId)?.name),
          match_scope,
        })),
      },
    }
  }

  if (collection === "recipes") {
    const row = data.index.recipes.find((candidate) => candidate.id === id)
    if (!row) return undefined
    const result = compatibilityResult(row)
    if (!result) return undefined
    return {
      ...result.recipe,
      registry: {
        launchable: result.launchable,
        speed_evidence: result.speed_evidence,
      },
      relationships: {
        hardware: recordLink("hardware", result.hardware.id, result.hardware.name),
        model: recordLink("models", result.model.id, result.model.name),
        model_instance: recordLink("model-instances", result.model_instance.id, result.model_instance.repository),
        speed_sweeps: result.recipe.speed_sweeps_ids.map((sweepId) => recordLink("speed-sweeps", sweepId)),
      },
    }
  }

  if (collection === "speed-sweeps") {
    const sweep = getSpeedSweep(id)
    if (!sweep) return undefined
    const recipe = getRecipe(sweep.recipe_id)
    return {
      ...sweep,
      relationships: {
        recipe: recipe ? recordLink("recipes", recipe.id) : null,
      },
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
  const prices = priceResults()
  return {
    models: {
      architecture: unique([...data.models.values()].map((model) => model.architecture ?? "unknown")),
      family: unique([...data.models.values()].map((model) => model.family)),
    },
    model_instances: {
      huggingface_link_type: unique([...data.instances.values()].map((instance) => instance.huggingface.link_type)),
      huggingface_status: unique([...data.instances.values()].map((instance) => instance.huggingface.status)),
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
    prices: {
      amount: unique(prices.map(priceAmount)),
      category: unique(prices.map((price) => price.product.category)),
      condition: unique(prices.flatMap((price) => price.observations.map((observation) => observation.condition))),
      currency: unique(prices.map((price) => price.region.currency)),
      region: unique(prices.map((price) => price.region.code)),
      retailer: unique(prices.flatMap((price) => price.observations.map((observation) => observation.retailer))),
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
