/**
 * GENERATED FILE — do not edit by hand.
 * Source of truth: registry/schema/*.schema.json
 * Regenerate with: npm run gen:types
 */

export type Fact = {
  value?: unknown
  state: "known" | "unknown" | "unavailable" | "not_applicable"
  reason?:
    | string
    | {
        code: string
        detail: string
      }
  note?: string
  scope?: string
  unit?: string
  as_of?: string
  provenance: Provenance
}
export type HuggingfaceIdentity = {
  repository: string | null
  url: string
  status: "known" | "unknown" | "unavailable"
  link_type: "repository" | "search"
  reason:
    | string
    | {
        code: string
        detail: string
      }
  provenance: Provenance
}
export type Recipe = {
  schema_version: "local-ai-registry/v1"
  id: string
  recipe_source: string
  status: "candidate" | "validated"
  description?: string | null
  model_instance_id: string
  hardware_id: string
  hardware_count: number
  engine: {
    name: string
    version: string | null
    graph_mode: string | null
    [k: string]: unknown
  }
  launch: {
    kind: "reference" | "docker" | "docker-compose" | "controller" | "script" | "native"
    container?: Container
    [k: string]: unknown
  }
  serving: {}
  capabilities: {
    chat: boolean | null
    reasoning: boolean | null
    tools: boolean | null
    vision: boolean | null
  }
  metadata: {}
  provenance: Provenance
  facts: Facts
  speed_sweep_ids: string[]
}
export type Container = {
  state: "digest-pinned" | "mutable" | "indirect" | "none"
  runtime: "docker" | "docker-compose" | null
  image: string | null
  digest: string | null
  compose_file: string | null
  /**
   * @minItems 1
   */
  source: [Source, ...Source[]]
  captured_at: string
  reason: string
}

export interface RegistryBundle {
  hardware?: Hardware
  model?: Model
  model_instance?: ModelInstance
  recipe?: Recipe
  speed_sweep?: SpeedSweep
  benchmark?: Benchmark
  price?: PriceRecord
  asset?: Asset
  index?: RegistryIndex
}
export interface Hardware {
  schema_version: "local-ai-registry/v1"
  id: string
  vendor: "nvidia" | "amd" | "intel" | "apple"
  name: string
  family?: string | null
  kind: "discrete" | "integrated" | "unified"
  accelerator_backend: "nvidia" | "amd-rocm" | "intel-xpu" | "metal"
  memory: {
    vram_gb: number
    vram_type: string | null
    cpu_memory_gb: number | null
    bandwidth_gb_per_s:
      | number
      | null
      | {
          min: number
          max: number
        }
    [k: string]: unknown
  }
  aliases?: string[]
  products?: string[]
  sources: {
    kind: string
    url: string
    [k: string]: unknown
  }[]
  commercial?: {
    availability: Fact
    prices: {
      amount: number
      currency: string
      unit: string
      region?: string | null
      kind?: string
      scope?: string
      configuration?: string
      as_of?: string
      source: Source
      captured_at: string
    }[]
  }
  compute?: {
    stats: {
      [k: string]: unknown
    }
    [k: string]: unknown
  }
  provenance?: Provenance
  facts?: Facts
  [k: string]: unknown
}
export interface Provenance {
  /**
   * @minItems 1
   */
  sources: [Source, ...Source[]]
  captured_at: string
}
export interface Source {
  kind: string
  url: string
  repository?: string | null
  commit?: string | null
  paths?: string[] | null
  captured_at?: string
  publisher?: string
  retrieved_from?: string
}
export interface Facts {
  [k: string]: Fact
}
export interface Model {
  schema_version: "local-ai-registry/v1"
  id: string
  family: string
  name: string
  params: number
  active_params: number | null
  architecture: string | null
  url: string | null
  huggingface: HuggingfaceIdentity
  provenance: Provenance
  facts: Facts
}
export interface ModelInstance {
  schema_version: "local-ai-registry/v1"
  id: string
  model_id: string
  repository: string
  url?: string | null
  revision: string | null
  served_name: string | null
  weights: {
    format: string | null
    precision: string | null
    size_gb: number | null
    [k: string]: unknown
  }
  kind: "base" | "quant" | "fine-tune"
  huggingface: HuggingfaceIdentity
  provenance: Provenance
  facts: Facts
}
export interface SpeedSweep {
  schema_version: "local-ai-registry/v1"
  id: string
  recipe_id: string
  measured_at: string | null
  accepted_at: string | null
  source: {} | null
  metrics: SpeedMetrics
  provenance?: Provenance
  facts?: Facts
  /**
   * @minItems 1
   */
  rows: [SpeedRow, ...SpeedRow[]]
}
export interface SpeedMetrics {
  inference_engine_version?: string | null
  concurrency?: number | null
  decode_mode?: string | null
  point_count?: number | null
  max_prompt_tokens?: number | null
  max_context_tokens?: number | null
  peak_generation_tps?: number | null
  peak_prompt_tps?: number | null
  peak_memory_bytes?: string | null
  base_memory_bytes?: string | null
  base_memory_context_tokens?: number | null
  decode8k_tps?: number | null
  decode8k_context_tokens?: number | null
  decode32k_tps?: number | null
  decode32k_context_tokens?: number | null
  decode_max_context_tps?: number | null
  decode_max_context_tokens?: number | null
  ttft32k_seconds?: number | null
  ttft32k_context_tokens?: number | null
  ttft32k_cached_prompt_tokens?: number | null
  memory8k_bytes?: string | null
  memory8k_context_tokens?: number | null
  memory_max_context_bytes?: string | null
  memory_max_context_tokens?: number | null
  latest_point_at?: string | null
}
export interface SpeedRow {
  concurrency: number | null
  context_tokens: number | null
  output_tokens: number | null
  prefill_tok_s: number | null
  decode_tok_s: number | null
  decode_tok_s_per_stream?: number | null
  ttft_ms_p50: number | null
  peak_vram_gb: number | null
  samples: number | null
  status: string
  [k: string]: unknown
}
export interface Benchmark {
  schema_version: "local-ai-registry/v1"
  id: string
  name: string
  category: string | null
  source: {
    kind?: string
    url?: string | null
    paths?: string[]
  }
  rows: BenchmarkScoreRow[]
}
export interface BenchmarkScoreRow {
  rank: number
  variant: string | null
  root: string | null
  org: string | null
  score: number | null
  conf?: string | null
  context?: string | null
  [k: string]: unknown
}
/**
 * Regional market price record: retailer observations for one product in one region.
 */
export interface PriceRecord {
  schema_version: "local-ai-registry/v1"
  id: string
  product: {
    id: string
    name: string
    category: string
  }
  region: {
    code: string
    name: string
    currency: string
  }
  hardware: {
    id: string
    match_scope: "exact" | "family"
  }[]
  observed_at: string
  summary: PriceSummary
  /**
   * @minItems 1
   */
  observations: [PriceObservation, ...PriceObservation[]]
  verification: PriceVerification
  provenance: PriceProvenance
}
export interface PriceSummary {
  listing_count: number
  retailer_count: number
  in_stock_count: number
  lowest_new: number | null
  lowest_refurbished: number | null
  lowest_used: number | null
}
export interface PriceObservation {
  retailer: string
  title: string
  condition: "new" | "refurbished" | "used" | "unknown"
  amount: number
  currency: string
  in_stock: boolean | null
  quantity: number | null
  url: string
  observed_at: string
}
export interface PriceVerification {
  state: "candidate" | "validated"
  method: string
  rejected_observations: number
}
export interface PriceProvenance {
  scanner: string
  snapshot_generated_at: string
  source_error_count: number
}
/**
 * One engine config, patch, or other launch artifact stored beside its manifest in registry/asset/. Recipes reference assets via launch.asset_ids and mount the blob path directly.
 */
export interface Asset {
  schema_version: "local-ai-registry/v1"
  id: string
  /**
   * Blob filename inside registry/asset/.
   */
  file: string
  /**
   * Original basename the launch expects (e.g. config.yml).
   */
  filename: string
  media_type: string
  purpose: string
  sha256: string
  size_bytes: number
}
export interface RegistryIndex {
  schema_version: "local-ai-registry/v1"
  resolver_rule: string
  collections: {
    [k: string]: string[]
  }
  counts: {
    [k: string]: number
  }
  recipes: IndexRecipeRow[]
}
export interface IndexRecipeRow {
  id: string
  model_instance_id: string
  hardware_id: string
  hardware_count: number
  engine: string
  status: "candidate" | "validated"
  recipe_source: string
  launch_kind: "reference" | "docker" | "docker-compose" | "controller" | "script" | "native"
  has_evidence: boolean
  capabilities: {
    chat: boolean | null
    reasoning: boolean | null
    tools: boolean | null
    vision: boolean | null
  }
}

// Stable aliases kept for existing imports.
export type RegistryId = string
