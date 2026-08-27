import assert from "node:assert/strict"
import test from "node:test"

import {
  collectionCounts,
  getEntityDetail,
  getFacets,
  isLaunchable,
  listHardware,
  marketPriceCount,
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
  assert.equal(detail.status, "validated")
  const launch = detail.launch
  assert.ok(launch && typeof launch === "object" && "kind" in launch)
  assert.equal(launch.kind, "docker")

  const registry = detail.registry
  assert.ok(registry && typeof registry === "object" && "launchable" in registry)
  assert.equal(registry.launchable, true)

  const relationships = detail.relationships
  assert.ok(
    relationships &&
    typeof relationships === "object" &&
    "model_instance" in relationships &&
    "speed_sweeps" in relationships,
  )
  const instance = relationships.model_instance
  assert.ok(instance && typeof instance === "object" && "href" in instance)
  assert.equal(instance.href, "/model-instances/unsloth-gemma-4-12b-it-nvfp4--nvfp4")

  const sweeps = relationships.speed_sweeps
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

test("Prices topic exposes regional market records without flattening currencies", () => {
  const prices = listPrices({}, { limit: 200, offset: 0 })
  const facets = getFacets()

  assert.equal(prices.total, 84)
  assert.equal(prices.data.length, 84)
  assert.equal(new Set(prices.data.map((record) => record.product.id)).size, 33)
  assert.equal(prices.data.reduce((count, record) => count + record.observations.length, 0), 896)
  assert.ok(prices.data.every((record) => record.observations.every((observation) => observation.currency === record.region.currency)))
  assert.deepEqual(facets.prices.region, ["DE", "GB", "JP", "PL", "US"])
  assert.deepEqual(facets.prices.currency, ["EUR", "GBP", "JPY", "PLN", "USD"])
  assert.deepEqual(facets.prices.condition, ["new", "refurbished", "used"])
})

test("market filters compose across region, category, condition, and retailer", () => {
  const sample = listPrices({}, { limit: 200, offset: 0 }).data.find((record) => record.observations.some((observation) => observation.in_stock === true))
  assert.ok(sample)
  const observation = sample.observations.find((candidate) => candidate.in_stock === true)
  assert.ok(observation)

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
