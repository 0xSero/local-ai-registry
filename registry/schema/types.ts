export type RegistryId = string
export type RecipeStatus = "candidate" | "validated"
export type LaunchKind = "reference" | "docker" | "docker-compose" | "controller" | "script" | "native"
export type Capability = boolean | null
export type FactState = "known" | "unknown" | "unavailable" | "not_applicable"
export type ContainerState = "digest-pinned" | "mutable" | "indirect" | "none"
export type ComputePrecision = "fp32" | "tf32" | "fp16" | "bf16" | "fp8" | "fp4" | "int8" | "int4"
export type ComputeSparsity = "dense" | "structured_2_4" | "unstructured" | "unknown"

export interface Source {
  kind?: string
  url?: string
  repository?: string | null
  commit?: string | null
  paths?: string[] | null
  captured_at?: string
  publisher?: string
  retrieved_from?: string
}

export interface Provenance {
  sources: Source[]
  captured_at: string
}

export interface Fact<T = unknown> {
  value?: T
  state: FactState
  reason?: string | { code: string; detail: string }
  note?: string
  scope?: string
  unit?: string
  as_of?: string
  provenance: Provenance
}

export interface HuggingFaceIdentity {
  repository: string | null
  url: string
  status: "known" | "unknown" | "unavailable"
  link_type: "repository" | "search"
  reason: string | { code: string; detail: string }
  provenance: Provenance
}

export interface ContainerProvenance {
  state: ContainerState
  runtime: "docker" | "docker-compose" | null
  image: string | null
  digest: string | null
  compose_file: string | null
  source: Source[]
  captured_at: string
  reason: string
}

export interface Hardware {
  schema_version: "local-ai-registry/v1"
  id: RegistryId
  vendor: "nvidia" | "amd" | "intel" | "apple"
  name: string
  family: string | null
  kind: "discrete" | "integrated" | "unified"
  accelerator_backend: "nvidia" | "amd-rocm" | "intel-xpu" | "metal"
  memory: {
    vram_gb: number
    cpu_memory_gb: number | null
    vram_type: string | null
    bandwidth_gb_per_s: number | { min: number; max: number } | null
  }
  aliases: string[]
  products: string[]
  sources: Source[]
  commercial?: { availability: Fact; prices: Array<{ amount: number; currency: string; unit: string; region?: string | null; source: Source; captured_at: string }> }
  accelerator?: Record<string, unknown>
  compute?: {
    stats: Partial<Record<ComputePrecision, Partial<Record<ComputeSparsity, { value?: number | null; state: FactState; reason?: string | { code: string; detail: string }; provenance: Provenance; unit: string }>>>>
    [key: string]: unknown
  }
  captured_at?: string
  provenance?: Provenance
  facts?: Record<string, Fact>
}

export interface Model {
  schema_version: "local-ai-registry/v1"
  id: RegistryId
  family: string
  name: string
  params: number | null
  active_params: number | null
  architecture: string | null
  url: string | null
  huggingface: HuggingFaceIdentity
  provenance: Provenance
  facts: Record<string, Fact>
}

export interface ModelInstance {
  schema_version: "local-ai-registry/v1"
  id: RegistryId
  model_id: RegistryId
  repository: string
  url?: string | null
  revision: string | null
  served_name: string | null
  weights: {
    format: string | null
    precision: string | null
    size_gb: number | null
    artifact?: string
    source?: string
    publication_id?: string
  }
  kind: "base" | "quant" | "fine-tune"
  huggingface: HuggingFaceIdentity
  provenance: Provenance
  facts: Record<string, Fact>
}

export interface Recipe {
  schema_version: "local-ai-registry/v1"
  id: RegistryId
  recipe_source: string
  status: RecipeStatus
  description?: string | null
  model_instance_id: RegistryId
  hardware_id: RegistryId
  hardware_count: number
  engine: { name: string; version: string | null; graph_mode: string | null; [key: string]: unknown }
  launch: { kind: LaunchKind; container: ContainerProvenance; [key: string]: unknown }
  serving: Record<string, unknown>
  capabilities: { chat: Capability; reasoning: Capability; tools: Capability; vision: Capability }
  speed_sweeps_ids: RegistryId[]
  metadata: Record<string, unknown>
  provenance: Provenance
  facts: Record<string, Fact>
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

export interface SpeedSweep {
  schema_version: "local-ai-registry/v1"
  id: RegistryId
  recipe_id: RegistryId
  measured_at: string | null
  accepted_at: string | null
  source: Source | null
  metrics?: SpeedMetrics
  rows: SpeedRow[]
  provenance?: Provenance
  facts?: Record<string, Fact>
}

export interface PriceObservation {
  retailer: string
  title: string
  condition: "new" | "refurbished" | "used"
  amount: number
  currency: string
  in_stock: boolean | null
  quantity: number | null
  url: string
  observed_at: string
}

export interface PriceRecord {
  schema_version: "local-ai-registry/v1"
  id: RegistryId
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
  hardware: Array<{
    id: RegistryId
    match_scope: "exact" | "family"
  }>
  observed_at: string
  summary: {
    listing_count: number
    retailer_count: number
    in_stock_count: number
    lowest_new: number | null
    lowest_refurbished: number | null
    lowest_used: number | null
  }
  observations: PriceObservation[]
  verification: {
    state: "candidate"
    method: string
    rejected_observations: number
  }
  provenance: {
    scanner: string
    snapshot_generated_at: string
    source_error_count: number
  }
}

export interface RegistryIndex {
  schema_version: "local-ai-registry/v1"
  resolver_rule: string
  collections: Record<string, RegistryId[]>
  counts: Record<string, number>
  recipes: Array<Pick<Recipe, "id" | "recipe_source" | "status" | "model_instance_id" | "hardware_id" | "hardware_count" | "capabilities"> & {
    engine: string
    launch_kind: LaunchKind
    has_evidence: boolean
  }>
}
