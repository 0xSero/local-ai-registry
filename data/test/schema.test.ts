import assert from "node:assert/strict"
import { execFileSync } from "node:child_process"
import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import test from "node:test"

import Ajv2020 from "ajv/dist/2020"
import addFormats from "ajv-formats"

const ROOT = join(import.meta.dirname, "..", "registry")
const SCHEMA_DIR = join(ROOT, "schema")

const COLLECTION_SCHEMAS: Record<string, string> = {
  hardware: "hardware.schema.json",
  model: "model.schema.json",
  "model-instance": "model-instance.schema.json",
  recipe: "recipe.schema.json",
  "speed-sweep": "speed-sweep.schema.json",
  benchmark: "benchmark.schema.json",
  asset: "asset.schema.json",
}

const ajv = new Ajv2020({ allErrors: true, strict: false })
addFormats(ajv)
for (const file of readdirSync(SCHEMA_DIR)) {
  if (!file.endsWith(".schema.json")) continue
  ajv.addSchema(JSON.parse(readFileSync(join(SCHEMA_DIR, file), "utf8")))
}

function schemaId(file: string): string {
  return `https://local-ai-registry.dev/schema/${file}`
}

function formatErrors(path: string, errors: unknown): string {
  return `${path}\n${JSON.stringify(errors, null, 2)}`
}

for (const [collection, schemaFile] of Object.entries(COLLECTION_SCHEMAS)) {
  test(`every ${collection} record validates against ${schemaFile}`, () => {
    const validate = ajv.getSchema(schemaId(schemaFile))
    assert.ok(validate, `schema ${schemaFile} is registered`)
    const dir = join(ROOT, collection)
    const files = readdirSync(dir).filter((f) => f.endsWith(".json"))
    assert.ok(files.length > 0, `${collection} has records`)
    const failures: string[] = []
    for (const file of files) {
      const record = JSON.parse(readFileSync(join(dir, file), "utf8"))
      if (!validate(record)) failures.push(formatErrors(`${collection}/${file}`, validate.errors))
    }
    assert.deepEqual(failures, [], `${failures.length} invalid ${collection} record(s):\n${failures.slice(0, 5).join("\n")}`)
  })
}

test("cloning a device-bearing recipe retains a valid draft contract", () => {
  const cloned = JSON.parse(execFileSync("python3", ["-c", `
import io, json, sys, tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, "scripts")
import clone_candidate as clone
original = clone.REG
source = "lfm25-26b-qad-q4-0-rtx4060-laptop-llamacpp-tp1"
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / "recipe").mkdir()
    with patch.object(clone, "REG", root), \\
         patch.object(clone, "read", side_effect=lambda kind, identifier: json.loads((original / kind / (identifier + ".json")).read_text())), \\
         patch.object(sys, "argv", ["clone_candidate.py", source, "rtx-4060-laptop-8gb", "--id", "schema-clone"]), \\
         redirect_stdout(io.StringIO()):
        clone.main()
    print((root / "recipe/schema-clone.json").read_text())
`], { cwd: join(ROOT, ".."), encoding: "utf8" }))
  assert.deepEqual(cloned.draft_launch.devices, ["/dev/nvidia-uvm"])
  assert.equal(cloned.status, "candidate")
  const validate = ajv.getSchema(schemaId("recipe.schema.json"))
  assert.ok(validate)
  assert.ok(validate(cloned), formatErrors("cloned recipe", validate.errors))
})

test("every price record validates against price.schema.json", () => {
  const validate = ajv.getSchema(schemaId("price.schema.json"))
  assert.ok(validate, "price schema is registered")
  const priceRoot = join(ROOT, "price")
  const failures: string[] = []
  let count = 0
  for (const product of readdirSync(priceRoot, { withFileTypes: true })) {
    if (!product.isDirectory()) continue
    for (const file of readdirSync(join(priceRoot, product.name))) {
      if (!file.endsWith(".json")) continue
      count += 1
      const path = join(priceRoot, product.name, file)
      const record = JSON.parse(readFileSync(path, "utf8"))
      if (!validate(record)) failures.push(formatErrors(`price/${product.name}/${file}`, validate.errors))
    }
  }
  assert.ok(count > 0, "price collection has records")
  assert.deepEqual(failures, [], `${failures.length} invalid price record(s):\n${failures.slice(0, 5).join("\n")}`)
})

test("index shards are well-formed", () => {
  const validate = ajv.getSchema(schemaId("index.schema.json"))
  assert.ok(validate, "index schema is registered")
  const collections = JSON.parse(readFileSync(join(ROOT, "index", "collections.json"), "utf8"))
  assert.ok(validate(collections), formatErrors("index/collections.json", validate.errors))
  const validateRecipes = ajv.getSchema(schemaId("index-recipes.schema.json"))
  assert.ok(validateRecipes, "index-recipes schema is registered")
  const recipeRows = JSON.parse(readFileSync(join(ROOT, "index", "recipes.json"), "utf8"))
  assert.ok(validateRecipes(recipeRows), formatErrors("index/recipes.json", validateRecipes.errors))
  for (const shard of ["recipes.json", "recipes-by-hardware.json", "instances-by-model.json", "benchmarks-by-model.json", "prices-by-hardware.json"]) {
    const doc = JSON.parse(readFileSync(join(ROOT, "index", shard), "utf8"))
    assert.equal(doc.schema_version, "local-ai-registry/v1", `${shard} schema_version`)
  }
})
