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
      <pre className="launch-command"><code>{command}</code></pre>
      <CopyActions items={[{ label: "Copy docker command", value: command }]} />
    </section>
  )
}
