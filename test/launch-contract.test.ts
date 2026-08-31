import assert from "node:assert/strict"
import { readFileSync, readdirSync, existsSync } from "node:fs"
import { join } from "node:path"
import test from "node:test"

// The Omarchy local-ai plugin (basecamp/omarchy PR #8836) launches every
// validated docker recipe through a safety gate. This test runs the same
// contract here, so a registry change that would brick or silently shrink
// the plugin's catalog fails CI instead of shipping.

const ROOT = join(__dirname, "..", "registry")
const readJson = (p: string) => JSON.parse(readFileSync(p, "utf8"))

const index = readJson(join(ROOT, "index", "recipes.json"))
const launchable = index.recipes.filter(
  (r: any) => r.status === "validated" && r.launch_kind === "docker",
)

// Placeholders the plugin owns and interpolates; anything else is refused client-side.
const OWNED = new Set(["${MODEL_ROOT}", "${CACHE_ROOT}"])
const strings = (v: unknown): string[] =>
  typeof v === "string" ? [v]
  : Array.isArray(v) ? v.flatMap(strings)
  : v && typeof v === "object" ? Object.values(v).flatMap(strings)
  : []

test("the sharded discovery index exposes launchable docker recipes", () => {
  assert.equal(index.schema_version, "local-ai-registry/v1")
  assert.ok(launchable.length > 0, "no validated docker recipes in index/recipes.json")
})

test("every validated docker recipe passes the Omarchy launch gate", () => {
  for (const row of launchable) {
    const recipe = readJson(join(ROOT, "recipe", `${row.id}.json`))
    const instance = readJson(join(ROOT, "model-instance", `${recipe.model_instance_id}.json`))
    const launch = recipe.launch
    const args: string[] = launch.arguments ?? []

    assert.match(String(launch.image ?? ""), /@sha256:[0-9a-f]{64}$/, `${row.id}: image is not digest-pinned`)
    assert.match(String(instance.revision ?? ""), /^[0-9a-f]{40,64}$/, `${row.id}: model revision is not pinned`)
    assert.equal(typeof launch.container_port, "number", `${row.id}: container_port must be a number`)
    assert.ok(
      !args.some((a) => /enforce.eager|disable.?cuda.?graph/i.test(a)),
      `${row.id}: disallowed launch argument`,
    )
    assert.ok(
      typeof instance.weights?.size_gb === "number" && instance.weights.size_gb > 0,
      `${row.id}: instance ${recipe.model_instance_id} needs weights.size_gb (the plugin's download-completeness check depends on it)`,
    )

    for (const mount of launch.mounts ?? []) {
      const src = String(mount.source ?? "")
      assert.ok(!src.includes(".."), `${row.id}: mount traverses upward: ${src}`)
      const allowed =
        src.startsWith("~/.cache/") ||
        src.startsWith("${MODEL_ROOT}/") ||
        src.startsWith("${CACHE_ROOT}/") ||
        src === "/dev/dri/by-path" ||
        (!src.startsWith("/") && !src.includes("${") && existsSync(join(ROOT, src)))
      assert.ok(allowed, `${row.id}: mount source outside the plugin allowlist: ${src}`)
    }

    // Multi-node recipes are legitimately blocked client-side; single-node ones
    // must not smuggle placeholders the plugin does not own.
    if (!args.includes("--nnodes")) {
      for (const s of strings(launch)) {
        for (const m of s.matchAll(/\$\{[^}]+\}/g)) {
          assert.ok(OWNED.has(m[0]), `${row.id}: unsupported placeholder ${m[0]} in a single-node recipe`)
        }
      }
    }
  }
})

test("model-instance files referenced by launchable recipes exist", () => {
  const files = new Set(readdirSync(join(ROOT, "model-instance")))
  for (const row of launchable) {
    const recipe = readJson(join(ROOT, "recipe", `${row.id}.json`))
    assert.ok(files.has(`${recipe.model_instance_id}.json`), `${row.id}: missing model-instance ${recipe.model_instance_id}`)
  }
})
