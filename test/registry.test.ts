import assert from "node:assert/strict"
import test from "node:test"

import {
  getEntityDetail,
  isLaunchable,
  listHardware,
  listModelInstances,
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
