import assert from "node:assert/strict"
import test from "node:test"

import { collectionHref, collectionLabel, collectionTopic, isCollection, isTopic, recordHref, topicHref } from "../app/lib/catalog"
import { copyItems, displayRecord, recordFacts, recordTitle, relatedGroups, recipeIsLaunchable } from "../app/lib/record-view"
import { getEntityDetail } from "../lib/registry"

test("collection catalog maps path segments onto browse topics", () => {
  assert.equal(isTopic("recipes"), true)
  assert.equal(isTopic("model-instances"), false)
  assert.equal(isCollection("model-instances"), true)
  assert.equal(collectionLabel("recipes"), "Recipe")
  assert.equal(collectionTopic("model-instances"), "recipes")
  assert.equal(topicHref("hardware", "rtx"), "/?topic=hardware&q=rtx")
  assert.equal(collectionHref("prices"), "/?topic=prices")
  assert.equal(recordHref("recipes", "gemma-4-12b-it-nvfp4-rtxpro6000-sglang-tp1"), "/recipes/gemma-4-12b-it-nvfp4-rtxpro6000-sglang-tp1")
})

test("record title and display tree hide contract fields already shown as cards", () => {
  const recipe = getEntityDetail("recipes", "gemma-4-12b-it-nvfp4-rtxpro6000-sglang-tp1") as Record<string, unknown>
  assert.equal(recordTitle(recipe, "fallback"), recipe.id)
  const tree = displayRecord(recipe)
  assert.ok(!("launch" in tree))
  assert.ok(!("huggingface" in tree))
  assert.ok(!("relationships" in tree))
  assert.equal(recipeIsLaunchable(recipe), true)
})

test("related records expose permanent hrefs instead of burying them in the tree", () => {
  const recipe = getEntityDetail("recipes", "acereason-nemotron-1-1-7b-q4-k-m-rtx-3060-ti-8gb-llama-cpp-tp1") as Record<string, unknown>
  const groups = relatedGroups(recipe)
  const hardware = groups.find((group) => group.key === "hardware")
  const model = groups.find((group) => group.key === "model")
  assert.ok(hardware)
  assert.equal(hardware.links[0]?.href, "/hardware/rtx-3060-ti-8gb")
  assert.ok(model)
  assert.match(model.links[0]?.href ?? "", /^\/models\//)
  assert.equal(recipeIsLaunchable(recipe), false)
})

test("long relationship lists cap and offer a collection search", () => {
  const model = getEntityDetail("models", "gemma-4-12b-it") as Record<string, unknown>
  const groups = relatedGroups(model)
  const recipes = groups.find((group) => group.key === "recipes")
  assert.ok(recipes)
  assert.ok(recipes.total >= recipes.links.length)
  if (recipes.total > 8) {
    assert.equal(recipes.links.length, 8)
    assert.equal(recipes.moreHref, "/?topic=recipes&model_id=gemma-4-12b-it")
  }
})

test("detail facts and copy items come from the record, not a shell dump", () => {
  const recipe = getEntityDetail("recipes", "gemma-4-12b-it-nvfp4-rtxpro6000-sglang-tp1") as Record<string, unknown>
  const facts = recordFacts("recipes", recipe)
  assert.ok(facts.some((item) => item.label === "Status" && item.value === "validated"))
  assert.ok(facts.some((item) => item.label === "Engine" && item.value === "sglang"))
  const copies = copyItems("recipes", recipe)
  assert.ok(copies.some((item) => item.label === "Launch arguments" && item.value.includes("-lc")))
  const candidate = getEntityDetail("recipes", "acereason-nemotron-1-1-7b-q4-k-m-rtx-3060-ti-8gb-llama-cpp-tp1") as Record<string, unknown>
  assert.equal(copyItems("recipes", candidate).some((item) => item.label === "Launch arguments"), false)
})
