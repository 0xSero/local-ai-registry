import { CopyActions } from "@/app/components/copy-actions"
import { dockerCommand } from "@/lib/registry"

import type { Recipe } from "@/registry/schema/types"

export function LaunchCommand({ recipe }: { recipe: Recipe }) {
  const command = dockerCommand(recipe)
  if (!command) return null
  return (
    <section aria-label="Launch command" className="record-evidence">
      <p className="eyebrow">Launch</p>
      <p className="trust-note">
        Exact materialization of this validated launch contract: digest-pinned image, pinned model revision, and the
        audited arguments. Self-contained — required assets are fetched from this registry and verified against their
        recorded sha256 before mounting. Also available as <code>local-ai run {recipe.id}</code>.
      </p>
      <ol className="launch-steps">
        <li>Pulls the exact container image by sha256 digest — the bytes that were validated, not a floating tag.</li>
        <li>Fetches any required engine assets from this registry and verifies each against its recorded sha256; the audited launch script verifies them again inside the container before use.</li>
        <li>Downloads the pinned model revision into your Hugging Face cache on first run (reused afterwards).</li>
        <li>Serves an OpenAI-compatible API on <code>localhost:{String((recipe.launch as Record<string, unknown>).host_port ?? "")}</code> — point any client at it.</li>
      </ol>
      <pre className="launch-command"><code>{command}</code></pre>
      <CopyActions items={[{ label: "Copy docker command", value: command }]} />
    </section>
  )
}
