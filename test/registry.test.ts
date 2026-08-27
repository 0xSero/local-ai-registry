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
    assert.match(String(item.model_instance.hugging_face_url), /^https:\/\/huggingface\.co\//)
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

test("model-instance results derive Hugging Face state only from body URL", () => {
  const unresolved = listModelInstances(
    { q: "agents-a1-q4km" },
    { limit: 10, offset: 0 },
  )
  assert.equal(unresolved.total, 1)
  assert.equal(unresolved.data[0].url, null)
  assert.equal(unresolved.data[0].hugging_face_url, null)
  assert.equal(unresolved.data[0].artifact_resolution, "unresolved")

  const resolved = listModelInstances(
    { q: "unsloth/gemma-4-12b-it-NVFP4" },
    { limit: 10, offset: 0 },
  )
  assert.ok(resolved.total >= 1)
  const exact = resolved.data.find((item) => item.id === "unsloth-gemma-4-12b-it-nvfp4--nvfp4")
  assert.equal(exact?.hugging_face_url, exact?.url)
  assert.equal(exact?.artifact_resolution, "hugging_face")
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
  assert.ok(instance && typeof instance === "object" && "hugging_face_url" in instance)
  assert.match(String(instance.hugging_face_url), /^https:\/\/huggingface\.co\//)

  const sweeps = detail.speed_sweeps
  assert.ok(Array.isArray(sweeps))
  assert.equal(sweeps.length, 1)
})
