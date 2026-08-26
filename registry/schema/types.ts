export type RegistryId = string
export type RecipeStatus = "candidate" | "validated"
export type LaunchKind = "reference" | "docker" | "docker-compose" | "controller" | "script" | "native"
export type Capability = boolean | null

export interface Source {
  kind?: string
  url?: string
  repository?: string | null
  commit?: string | null
  paths?: string[] | null
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
}

export interface ModelInstance {
  schema_version: "local-ai-registry/v1"
  id: RegistryId
  model_id: RegistryId
  repository: string
  url?: string | null
  revision: string | null
  served_name: string | null
  weights: { format: string | null; precision: string | null; size_gb: number | null }
  kind: "base" | "quant" | "fine-tune"
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
  launch: { kind: LaunchKind; [key: string]: unknown }
  serving: Record<string, unknown>
  capabilities: { chat: Capability; reasoning: Capability; tools: Capability; vision: Capability }
  speed_sweeps_ids: RegistryId[]
  metadata: Record<string, unknown>
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

export interface SpeedSweep {
  schema_version: "local-ai-registry/v1"
  id: RegistryId
  recipe_id: RegistryId
  measured_at: string | null
  accepted_at: string | null
  source: Source | null
  rows: SpeedRow[]
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
