import assert from "node:assert/strict"
import test from "node:test"

import {
  collectionCounts,
  getBenchmark,
  getEntityDetail,
  getFacets,
  isLaunchable,
  listBenchmarks,
  listHardware,
  marketPriceCount,
  listModelInstances,
  listModels,
  listPrices,
  listSpeedSweeps,
  queryCompatibility,
  recipeCountForHardware,
} from "../lib/registry"

test("model and hardware searches intersect on compatible recipes", () => {
  const result = queryCompatibility(
    {
      hardware: "RTX PRO 6000 Blackwell",
      launchable: "true",
      model: "Gemma-4-12B-it",
      precision: "NVFP4",
    },
    { limit: 100, offset: 0 },
  )

  assert.ok(result.total > 0)
  for (const item of result.data) {
    assert.equal(item.launchable, true)
    assert.match(item.model.name, /gemma-4-12b-it/i)
    assert.match(item.hardware.name, /rtx pro 6000 blackwell/i)
    assert.equal(item.model_instance.hugging_face_url, item.model_instance.huggingface.url)
    assert.match(item.model_instance.hugging_face_url, /^https:\/\/huggingface\.co\//)
  }
})

test("candidate and reference recipes are never launchable", () => {
  assert.equal(isLaunchable({ status: "candidate", launch_kind: "docker" }), false)
  assert.equal(isLaunchable({ status: "validated", launch_kind: "reference" }), false)

  const result = queryCompatibility(
    { launch_kind: "reference", launchable: "true" },
    { limit: 100, offset: 0 },
  )
  assert.equal(result.total, 0)
})

test("GLM-5.3 selective EXL3 distinguishes measured TP4 and PP3 from blocked TP3 and TP2", () => {
  const fourGpu = getEntityDetail("recipes", "glm53-flash-exl3-q4-rtxpro6000-sglang-tp4")
  const threeGpuPp = getEntityDetail("recipes", "glm53-flash-exl3-q4-rtxpro6000-sglang-pp3")
  const threeGpu = getEntityDetail("recipes", "glm53-flash-exl3-q4-rtxpro6000-sglang-tp3")
  const twoGpu = getEntityDetail("recipes", "glm53-flash-exl3-q4-rtxpro6000-sglang-tp2")
  const fourGpuSweep = getEntityDetail(
    "speed-sweeps",
    "glm53-flash-exl3-q4-rtxpro6000-sglang-tp4-sweep",
  )
  const threeGpuPpSweep = getEntityDetail(
    "speed-sweeps",
    "glm53-flash-exl3-q4-rtxpro6000-sglang-pp3-sweep",
  )
  const twoGpuSweep = getEntityDetail(
    "speed-sweeps",
    "glm53-flash-exl3-q4-rtxpro6000-sglang-tp2-sweep",
  )
  const threeGpuSweep = getEntityDetail(
    "speed-sweeps",
    "glm53-flash-exl3-q4-rtxpro6000-sglang-tp3-sweep",
  )

  assert.ok(fourGpu && typeof fourGpu === "object")
  assert.ok(threeGpuPp && typeof threeGpuPp === "object")
  assert.ok(threeGpu && typeof threeGpu === "object")
  assert.ok(twoGpu && typeof twoGpu === "object")
  assert.ok(fourGpuSweep && typeof fourGpuSweep === "object")
  assert.ok(threeGpuPpSweep && typeof threeGpuPpSweep === "object")
  assert.ok(threeGpuSweep && typeof threeGpuSweep === "object")
  assert.ok(twoGpuSweep && typeof twoGpuSweep === "object")

  const four = fourGpu as {
    hardware_count: number
    launch: { kind: string }
    serving: { tensor_parallel: number }
    status: string
  }
  const two = twoGpu as {
    hardware_count: number
    launch: { kind: string }
    metadata: { compatibility_state: string }
    status: string
  }
  const threePp = threeGpuPp as {
    hardware_count: number
    launch: { kind: string }
    metadata: { acceptance: { generated_completion: boolean } }
    serving: { pipeline_parallel: number; tensor_parallel: number }
    status: string
  }
  const three = threeGpu as {
    hardware_count: number
    launch: { kind: string }
    metadata: { compatibility_state: string }
    status: string
  }
  const fourSweep = fourGpuSweep as { rows: Array<{ status?: string; decode_tok_s?: number }> }
  const threePpSweep = threeGpuPpSweep as { rows: Array<{ status?: string; decode_tok_s?: number }> }
  const threeSweep = threeGpuSweep as { rows: Array<{ decode_tok_s?: number | null }> }
  const twoSweep = twoGpuSweep as { rows: Array<{ decode_tok_s?: number | null }> }

  assert.equal(four.hardware_count, 4)
  assert.equal(four.status, "candidate")
  assert.equal(four.launch.kind, "docker")
  assert.equal(four.serving.tensor_parallel, 4)
  assert.ok(fourSweep.rows.some((row) =>
    row.status === "accepted-matched-screen" && row.decode_tok_s === 73.4979))

  assert.equal(threePp.hardware_count, 3)
  assert.equal(threePp.status, "candidate")
  assert.equal(threePp.launch.kind, "docker")
  assert.equal(threePp.serving.tensor_parallel, 1)
  assert.equal(threePp.serving.pipeline_parallel, 3)
  assert.equal(threePp.metadata.acceptance.generated_completion, true)
  assert.ok(threePpSweep.rows.some((row) =>
    row.status === "accepted-cold-unique-prefix-throughput" && row.decode_tok_s === 176.824))

  assert.equal(three.hardware_count, 3)
  assert.equal(three.status, "candidate")
  assert.equal(three.launch.kind, "reference")
  assert.equal(three.metadata.compatibility_state, "blocked")
  assert.ok(threeSweep.rows.every((row) => row.decode_tok_s == null))

  assert.equal(two.hardware_count, 2)
  assert.equal(two.status, "candidate")
  assert.equal(two.launch.kind, "reference")
  assert.equal(two.metadata.compatibility_state, "blocked")
  assert.ok(twoSweep.rows.every((row) => row.decode_tok_s === null))

  for (const record of [fourGpu, threeGpuPp, twoGpu, fourGpuSweep, threeGpuPpSweep, twoGpuSweep]) {
    const serialized = JSON.stringify(record)
    assert.doesNotMatch(serialized, /\/home\//)
    assert.doesNotMatch(serialized, /tailadb/i)
    assert.doesNotMatch(serialized, /GPU-[0-9a-f-]{20,}/i)
  }
})

test("validated recipes for the Omarchy GPUs use Docker", () => {
  for (const hardware_id of ["rtx-3090-24gb", "intel-arc-pro-b70-32gb"]) {
    const result = queryCompatibility({ hardware_id, status: "validated" }, { limit: 100, offset: 0 })
    assert.ok(result.total > 0)
    assert.ok(result.data.every((item) => item.recipe.launch.kind === "docker" && item.launchable))
  }
  const detail = getEntityDetail("recipes", "qwen38-q4km-arcb70-llamacpp-tp1")
  assert.ok(detail && typeof detail === "object" && "capabilities" in detail)
  const capabilities = detail.capabilities
  assert.ok(capabilities && typeof capabilities === "object" && "tools" in capabilities)
  assert.equal(capabilities.tools, true)
})

test("repository link results expose the authoritative body identity", () => {
  const result = listModelInstances(
    { huggingface_link_type: "repository", q: "unsloth/gemma-4-12b-it-NVFP4" },
    { limit: 10, offset: 0 },
  )
  const exact = result.data.find((item) => item.id === "unsloth-gemma-4-12b-it-nvfp4--nvfp4")

  assert.ok(exact)
  assert.equal(exact.huggingface.link_type, "repository")
  assert.equal(exact.huggingface.status, "known")
  assert.equal(exact.huggingface.repository, "unsloth/gemma-4-12b-it-NVFP4")
  assert.equal(exact.hugging_face_url, exact.huggingface.url)
  assert.equal(exact.hugging_face_url, "https://huggingface.co/unsloth/gemma-4-12b-it-NVFP4")
  assert.equal(exact.credits.artifact.publisher, "unsloth")
  assert.equal(exact.credits.artifact.repository, "unsloth/gemma-4-12b-it-NVFP4")
  assert.equal(exact.credits.artifact.status, "known")
  assert.equal(exact.credits.base_model?.publisher, "google")
  assert.equal(exact.credits.base_model?.repository, "google/gemma-4-12B-it")
  assert.ok(exact.credits.provenance.sources.length > 0)
})

test("search fallback results stay distinct from repository links", () => {
  const result = listModelInstances(
    { huggingface_link_type: "search", q: "agents-a1-q4km" },
    { limit: 10, offset: 0 },
  )

  assert.equal(result.total, 1)
  const fallback = result.data[0]
  assert.equal(fallback.repository, "agents-a1-q4km")
  assert.equal(fallback.url, null)
  assert.equal(fallback.huggingface.repository, null)
  assert.equal(fallback.huggingface.link_type, "search")
  assert.equal(fallback.huggingface.status, "unavailable")
  assert.equal(fallback.hugging_face_url, fallback.huggingface.url)
  assert.equal(fallback.hugging_face_url, "https://huggingface.co/models?search=agents-a1-q4km")
  assert.equal(fallback.credits.artifact.publisher, null)
  assert.equal(fallback.credits.artifact.repository, null)
  assert.equal(fallback.credits.artifact.status, "unavailable")
})

test("hardware filters use normalized vendor and memory fields", () => {
  const result = listHardware(
    { min_vram_gb: "96", vendor: "nvidia" },
    { limit: 100, offset: 0 },
  )
  assert.ok(result.total > 0)
  for (const hardware of result.data) {
    assert.equal(hardware.vendor, "nvidia")
    assert.ok(hardware.memory.vram_gb >= 96)
  }
})

test("recipe detail progressively resolves related records and speed evidence", () => {
  const detail = getEntityDetail(
    "recipes",
    "gemma-4-12b-it-nvfp4-rtxpro6000-sglang-tp1",
  )
  if (!detail) throw new Error("recipe detail not found")
  assert.equal(detail.status, "validated")
  const launch = detail.launch
  assert.ok(launch && typeof launch === "object" && "kind" in launch)
  assert.equal((launch as { kind: string }).kind, "docker")

  const registry = detail.registry
  assert.ok(registry && typeof registry === "object" && "launchable" in registry)
  assert.equal((registry as { launchable: boolean }).launchable, true)

  const relationships = detail.relationships
  assert.ok(
    relationships &&
    typeof relationships === "object" &&
    "model_instance" in relationships &&
    "speed_sweeps" in relationships,
  )
  const instance = (relationships as { model_instance: unknown }).model_instance
  assert.ok(instance && typeof instance === "object" && "href" in instance)
  assert.equal((instance as { href: string }).href, "/model-instances/unsloth-gemma-4-12b-it-nvfp4--nvfp4")

  const sweeps = (relationships as { speed_sweeps: unknown }).speed_sweeps
  assert.ok(Array.isArray(sweeps))
  assert.equal(sweeps.length, 1)
})

test("combined search matches model and hardware fields in one query", () => {
  const result = queryCompatibility(
    { evidence: "true", q: "gemma rtx 3090" },
    { limit: 100, offset: 0 },
  )

  assert.ok(result.total > 0)
  for (const item of result.data) {
    assert.match(item.model.name, /gemma/i)
    assert.match(item.hardware.name, /rtx.*3090/i)
    assert.equal(item.speed_evidence.available, true)
    assert.ok(item.speed_evidence.count > 0)
  }
})

test("recipe browsing sorts by hardware or model before pagination", () => {
  const byHardware = queryCompatibility({ sort_by: "hardware" }, { limit: 100, offset: 0 }).data
  const byModel = queryCompatibility({ sort_by: "model" }, { limit: 100, offset: 0 }).data

  const ordered = (items: typeof byHardware, primary: "hardware" | "model") => items.every((item, index) => {
    if (index === 0) return true
    const previous = items[index - 1]
    const first = primary === "hardware" ? [previous.hardware.name, item.hardware.name] : [previous.model.name, item.model.name]
    const second = primary === "hardware" ? [previous.model.name, item.model.name] : [previous.hardware.name, item.hardware.name]
    const order = first[0].localeCompare(first[1], undefined, { numeric: true })
    return order < 0 || (order === 0 && second[0].localeCompare(second[1], undefined, { numeric: true }) <= 0)
  })

  assert.equal(ordered(byHardware, "hardware"), true)
  assert.equal(ordered(byModel, "model"), true)
})

test("navigable topic collections expose real registry records", () => {
  const counts = collectionCounts()
  const models = listModels({}, { limit: 5, offset: 0 })
  const hardware = listHardware({}, { limit: 5, offset: 0 })
  const sweeps = listSpeedSweeps({}, { limit: 5, offset: 0 })
  const recipes = queryCompatibility({}, { limit: 5, offset: 0 })

  assert.equal(models.total, counts.model)
  assert.equal(hardware.total, counts.hardware)
  assert.equal(sweeps.total, counts.speed_sweeps)
  assert.equal(recipes.total, counts.recipe)
  assert.ok(models.data.length > 0)
  assert.ok(hardware.data.length > 0)
  assert.ok(sweeps.data.length > 0)
  assert.ok(recipes.data.length > 0)
})

test("scraped benchmark leaderboards expose quality scores separate from speed sweeps", () => {
  const counts = collectionCounts()
  const benchmarks = listBenchmarks({}, { limit: 200, offset: 0 })
  const sweeps = listSpeedSweeps({}, { limit: 5, offset: 0 })

  assert.equal(benchmarks.total, counts.benchmarks)
  assert.ok(benchmarks.total >= 90)
  assert.ok(benchmarks.data.every((benchmark) => benchmark.rows.length > 0))
  assert.ok(sweeps.total > 0)
  assert.ok(sweeps.data.every((sweep) => !("rows" in sweep && Array.isArray(sweep.rows) && sweep.rows.some((row) => "variant" in row))))

  const mmlu = getBenchmark("mmlu")
  assert.ok(mmlu)
  assert.equal(mmlu.name, "MMLU")
  assert.ok(mmlu.rows.length > 0)
  assert.ok(mmlu.rows.every((row) => row.score === null || (row.score >= 0 && row.score <= 100)))
  assert.ok(mmlu.rows.every((row) => typeof row.root === "string" && row.root.length > 0))

  const terminalBench = getBenchmark("terminal-bench-2.1")
  assert.ok(terminalBench)
  assert.equal(terminalBench.name, "Terminal-Bench 2.1")
  assert.equal(terminalBench.category, "agentic-coding")
  assert.equal(terminalBench.rows.length, 17)
  assert.equal(terminalBench.source.kind, "leaderboard-scrape")
  assert.ok(terminalBench.source.paths?.includes("benchmarks/terminal-bench-2.1.html"))

  const detail = getEntityDetail("benchmarks", "terminal-bench-2.1")
  assert.ok(detail && typeof detail === "object")
  assert.equal((detail as { id: string }).id, "terminal-bench-2.1")
  assert.equal(getEntityDetail("benchmark", "terminal-bench-2.1"), undefined)
  assert.equal(getEntityDetail("speed-sweeps", "terminal-bench-2.1"), undefined)

  const agentic = listBenchmarks({ category: "agentic-coding" }, { limit: 50, offset: 0 })
  assert.ok(agentic.data.some((benchmark) => benchmark.id === "terminal-bench-2.1"))
  assert.ok(agentic.data.every((benchmark) => benchmark.category === "agentic-coding"))

  const query = listBenchmarks({ q: "terminal-bench-2.1" }, { limit: 10, offset: 0 })
  assert.ok(query.data.some((benchmark) => benchmark.id === "terminal-bench-2.1"))
  const sweepQuery = listSpeedSweeps({ q: "terminal-bench-2.1" }, { limit: 10, offset: 0 })
  assert.equal(sweepQuery.total, 0)
})

test("Prices topic exposes regional market records without flattening currencies", () => {
  const prices = listPrices({}, { limit: 500, offset: 0 })
  const facets = getFacets()

  assert.ok(prices.total >= 100)
  assert.equal(prices.data.length, prices.total)
  assert.ok(new Set(prices.data.map((record) => record.product.id)).size >= 45)
  assert.ok(prices.data.reduce((count, record) => count + record.observations.length, 0) >= 1000)
  assert.ok(prices.data.every((record) => record.observations.every((observation) => observation.currency === record.region.currency)))
  assert.deepEqual(facets.prices.region, ["DE", "GB", "JP", "PL", "US"])
  assert.deepEqual(facets.prices.currency, ["EUR", "GBP", "JPY", "PLN", "USD"])
  assert.deepEqual(facets.prices.condition, ["new", "refurbished", "used"])
  assert.ok(prices.data.some((record) => record.product.id === "rtx-5060"))
  assert.ok(prices.data.some((record) => record.product.id === "intel-arc-pro-b70"))
  assert.ok(prices.data.some((record) => record.product.id === "rx-9070-xt"))
  assert.ok(prices.data.some((record) => record.product.id === "rtx-pro-4000-blackwell"))
})

test("market filters compose across region, category, condition, and retailer", () => {
  const sample = listPrices({}, { limit: 200, offset: 0 }).data.find((record) => record.observations.some((observation) => observation.in_stock === true))
  if (!sample) throw new Error("no in-stock price sample found")
  const observation = sample.observations.find((candidate) => candidate.in_stock === true)
  if (!observation) throw new Error("no in-stock observation found")

  const filtered = listPrices(
    {
      category: sample.product.category,
      condition: observation.condition,
      in_stock: "true",
      region: sample.region.code,
      retailer: observation.retailer,
    },
    { limit: 200, offset: 0 },
  )
  assert.ok(filtered.total > 0)
  for (const record of filtered.data) {
    assert.equal(record.product.category, sample.product.category)
    assert.equal(record.region.code, sample.region.code)
    assert.ok(record.observations.some((candidate) => candidate.condition === observation.condition))
    assert.ok(record.observations.some((candidate) => candidate.retailer === observation.retailer))
    assert.ok(record.observations.some((candidate) => candidate.in_stock === true))
  }
})

test("hardware topic filters vendor backend memory and priced state", () => {
  const filtered = listHardware(
    { backend: "nvidia", min_vram_gb: "24", priced_only: "true", vendor: "nvidia" },
    { limit: 200, offset: 0 },
  )
  assert.ok(filtered.total > 0)
  for (const hardware of filtered.data) {
    assert.equal(hardware.vendor, "nvidia")
    assert.equal(hardware.accelerator_backend, "nvidia")
    assert.ok(hardware.memory.vram_gb >= 24)
    assert.ok(marketPriceCount(hardware.id) > 0)
  }
})

test("model topic filters family and architecture together", () => {
  const models = listModels({}, { limit: 200, offset: 0 })
  const sample = models.data.find((model) => model.architecture !== null)
  if (!sample) throw new Error("no architecture sample found")

  const filtered = listModels(
    { architecture: sample.architecture ?? "", family: sample.family },
    { limit: 200, offset: 0 },
  )
  assert.ok(filtered.total > 0)
  for (const model of filtered.data) {
    assert.equal(model.family, sample.family)
    assert.equal(model.architecture, sample.architecture)
  }

  const unknown = listModels({ architecture: "unknown" }, { limit: 200, offset: 0 })
  assert.ok(unknown.total > 0)
  assert.ok(unknown.data.every((model) => model.architecture === null))
})

test("runtime and engine filters distinguish docker from evidence-only recipes", () => {
  const docker = queryCompatibility({ runtime: "docker" }, { limit: 50, offset: 0 })
  const evidence = queryCompatibility({ runtime: "reference" }, { limit: 50, offset: 0 })
  const llama = queryCompatibility({ engine: "llama.cpp" }, { limit: 50, offset: 0 })

  assert.ok(docker.total > 0)
  assert.ok(evidence.total > 0)
  assert.ok(docker.data.every((item) => item.recipe.launch.kind === "docker" || item.recipe.launch.kind === "docker-compose"))
  assert.ok(evidence.data.every((item) => item.recipe.launch.kind === "reference" && item.launchable === false))
  assert.ok(llama.total > 0)
  assert.ok(llama.data.every((item) => item.recipe.engine.name === "llama.cpp"))
})

test("hardware has_recipes filter and previously empty SKUs stay exact", () => {
  const filled = listHardware({ has_recipes: "true" }, { limit: 200, offset: 0 })
  const empty = listHardware({ has_recipes: "false" }, { limit: 200, offset: 0 })
  const ti = listHardware({ q: "3060 ti" }, { limit: 20, offset: 0 })
  const spark = listHardware({ q: "dgx spark" }, { limit: 20, offset: 0 })

  assert.ok(filled.total > 0)
  assert.ok(empty.total > 0)
  assert.ok(filled.data.every((hardware) => recipeCountForHardware(hardware.id) > 0))
  assert.ok(empty.data.every((hardware) => recipeCountForHardware(hardware.id) === 0))
  assert.ok(ti.data.some((hardware) => hardware.id === "rtx-3060-ti-8gb" && recipeCountForHardware(hardware.id) > 0))
  assert.ok(spark.data.some((hardware) => hardware.id === "dgx-spark-gb10-128gb" && recipeCountForHardware(hardware.id) > 0))
})

test("recipe detail exposes Hugging Face identity and a visual configuration, never a local-ai launch", () => {
  const detail = getEntityDetail("recipes", "gemma-4-12b-it-nvfp4-rtxpro6000-sglang-tp1")
  assert.ok(detail && typeof detail === "object")
  const record = detail as {
    huggingface?: { status?: string; url?: string }
    launch?: { kind?: string }
    registry?: { launchable?: boolean }
  }
  assert.equal(record.huggingface?.status, "known")
  assert.match(String(record.huggingface?.url), /^https:\/\/huggingface\.co\//)
  assert.equal(record.launch?.kind, "docker")
  assert.equal(record.registry?.launchable, true)
  assert.doesNotMatch(JSON.stringify(record.launch), /local-ai launch/i)
})

test("mlx.fast official Gemma 4 score is a candidate on M5 Max attached to the canonical model", () => {
  const detail = getEntityDetail("recipes", "gemma-4-26b-a4b-it-qat-4bit-apple-m5-max-128gb-mlxfast-tp1")
  assert.ok(detail && typeof detail === "object")
  const record = detail as {
    hardware_id: string
    launch: { kind: string }
    recipe_source: string
    registry: { launchable: boolean }
    relationships: { model: { id: string } }
    status: string
  }
  assert.equal(record.recipe_source, "mlxfast")
  assert.equal(record.status, "candidate")
  assert.equal(record.launch.kind, "native")
  assert.equal(record.hardware_id, "apple-m5-max-128gb")
  assert.equal(record.registry.launchable, false)
  assert.equal(record.relationships.model.id, "gemma-4-26b-a4b-it")

  const instance = getEntityDetail("model-instances", "mlx-community-gemma-4-26b-a4b-it-qat-4bit--4bit") as {
    huggingface: { repository: string; status: string }
    model_id: string
    revision: string
  }
  assert.equal(instance.model_id, "gemma-4-26b-a4b-it")
  assert.equal(instance.revision, "0e3cbab38ce568cf6e23543010d08d03b731910c")
  assert.equal(instance.huggingface.status, "known")
  assert.equal(instance.huggingface.repository, "mlx-community/gemma-4-26B-A4B-it-qat-4bit")
})

test("observed LocalMaxxing and Postgres recipes stay reference-only candidates", () => {
  const lmx = queryCompatibility({ q: "localmaxxing" }, { limit: 20, offset: 0 })
  const recipes = queryCompatibility({ hardware_id: "rtx-3060-ti-8gb" }, { limit: 50, offset: 0 })
  assert.ok(recipes.total > 0)
  for (const item of recipes.data) {
    if (item.recipe.recipe_source === "localmaxxing" || item.recipe.recipe_source === "exo-postgres") {
      assert.equal(item.recipe.status, "candidate")
      assert.equal(item.recipe.launch.kind, "reference")
      assert.equal(item.launchable, false)
    }
    assert.notEqual(item.recipe.recipe_source, "omlx")
  }
  assert.equal(getEntityDetail("recipes", "gemma-4-26b-a4b-it-4bit-apple-m5-max-128gb-omlx-tp1"), undefined)
  assert.ok(lmx.total >= 0)
})
