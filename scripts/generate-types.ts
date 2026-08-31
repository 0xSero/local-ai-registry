// Regenerates registry/schema/types.ts from the JSON Schemas.
// The schemas are the contract; the TypeScript interfaces are derived output.
// Run: npm run gen:types

import { writeFileSync } from "node:fs"
import { join } from "node:path"

import { compile } from "json-schema-to-typescript"

const SCHEMA_DIR = join(import.meta.dirname, "..", "registry", "schema")
const OUT = join(SCHEMA_DIR, "types.ts")

const bundle = {
  $id: "https://local-ai-registry.dev/schema/bundle.json",
  title: "Registry bundle",
  type: "object",
  additionalProperties: false,
  properties: {
    hardware: { $ref: "hardware.schema.json" },
    model: { $ref: "model.schema.json" },
    model_instance: { $ref: "model-instance.schema.json" },
    recipe: { $ref: "recipe.schema.json" },
    speed_sweep: { $ref: "speed-sweep.schema.json" },
    benchmark: { $ref: "benchmark.schema.json" },
    price: { $ref: "price.schema.json" },
    index: { $ref: "index.schema.json" },
  },
} as const

const banner = `/**
 * GENERATED FILE — do not edit by hand.
 * Source of truth: registry/schema/*.schema.json
 * Regenerate with: npm run gen:types
 */`

async function main() {
  const ts = await compile(bundle as never, "RegistryBundle", {
    cwd: SCHEMA_DIR,
    bannerComment: banner,
    additionalProperties: false,
    style: { semi: false, printWidth: 110 },
  })

  const aliases = `
// Stable aliases kept for existing imports.
export type RegistryId = string
`

  writeFileSync(OUT, ts + aliases)
  console.log(`wrote ${OUT}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
