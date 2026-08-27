import assert from "node:assert/strict"
import test from "node:test"

import {
  collectionCounts,
  getEntityDetail,
  getFacets,
  isLaunchable,
  listHardware,
  listModelInstances,
  listModels,
  listPrices,
  listSpeedSweeps,
  queryCompatibility,
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
  assert.ok(detail)
  assert.equal(detail.launchable, true)
  const recipe = detail.recipe
  assert.ok(recipe && typeof recipe === "object" && "status" in recipe && "launch" in recipe)
  assert.equal(recipe.status, "validated")
  const launch = recipe.launch
  assert.ok(launch && typeof launch === "object" && "kind" in launch)
  assert.equal(launch.kind, "docker")

  const instance = detail.model_instance
  assert.ok(
    instance &&
    typeof instance === "object" &&
    "hugging_face_url" in instance &&
    "huggingface" in instance,
  )
  const huggingface = instance.huggingface
  assert.ok(huggingface && typeof huggingface === "object" && "url" in huggingface)
  assert.equal(instance.hugging_face_url, huggingface.url)

  const sweeps = detail.speed_sweeps
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

test("virtual Prices topic exposes every real price observation", () => {
  const prices = listPrices({}, { limit: 200, offset: 0 })
  const facets = getFacets()

  assert.equal(prices.total, 123)
  assert.equal(prices.data.length, 123)
  assert.equal(new Set(prices.data.map((result) => result.hardware_id)).size, 85)
  assert.ok(prices.data.every(({ price }) => price.currency === "USD" && price.unit === "one_time"))
  assert.equal(Math.min(...prices.data.map(({ price }) => price.amount)), 299)
  assert.equal(Math.max(...prices.data.map(({ price }) => price.amount)), 6999)
  assert.deepEqual(facets.prices.vendor, ["amd", "apple", "intel", "nvidia"])
  assert.deepEqual(facets.prices.kind, ["current_street", "CURRENT_SYSTEM_PRICE", "MSRP"])
  assert.deepEqual(facets.prices.scope, [
    "current_system_price",
    "manufacturer_launch_price",
    "representative_product_starting_price",
  ])
})

test("price filters compose across vendor taxonomy and maximum amount", () => {
  const sample = listPrices({}, { limit: 1, offset: 0 }).data[0]
  assert.ok(sample)

  const filtered = listPrices(
    {
      kind: sample.price.kind,
      max_price: String(sample.price.amount),
      scope: sample.price.scope,
      vendor: sample.hardware.vendor,
    },
    { limit: 200, offset: 0 },
  )
  assert.ok(filtered.total > 0)
  for (const result of filtered.data) {
    assert.equal(result.hardware.vendor, sample.hardware.vendor)
    assert.equal(result.price.kind, sample.price.kind)
    assert.equal(result.price.scope, sample.price.scope)
    assert.ok(result.price.amount <= sample.price.amount)
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
    assert.ok((hardware.commercial?.prices.length ?? 0) > 0)
  }
})

test("model topic filters family and architecture together", () => {
  const models = listModels({}, { limit: 200, offset: 0 })
  const sample = models.data.find((model) => model.architecture !== null)
  assert.ok(sample)

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
