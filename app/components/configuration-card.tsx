export type LaunchConfiguration = {
  arguments: string[]
  composeFile: string | null
  digest: string | null
  engine: string
  environment: Record<string, string>
  hasContainer: boolean
  image: string | null
  kind: string
  launchable: boolean
  mounts: Array<{ source?: string; target?: string; read_only?: boolean }>
  observedCommand: string | null
  ports: string | null
  sourceUrl: string | null
  status: string
  title: string
}

function value(record: Record<string, unknown>, key: string): unknown {
  return record[key]
}

export function configurationFromRecipe(recipe: Record<string, unknown>, engineName?: string): LaunchConfiguration {
  const launch = (value(recipe, "launch") as Record<string, unknown> | undefined) ?? {}
  const container = (launch.container as Record<string, unknown> | undefined) ?? {}
  const metadata = (value(recipe, "metadata") as Record<string, unknown> | undefined) ?? {}
  const localmaxxing = (metadata.localmaxxing as Record<string, unknown> | undefined) ?? {}
  const kind = typeof launch.kind === "string" ? launch.kind : "reference"
  const hasContainer = kind === "docker" || kind === "docker-compose"
  const environment = launch.environment && typeof launch.environment === "object" && !Array.isArray(launch.environment)
    ? Object.fromEntries(Object.entries(launch.environment as Record<string, unknown>).filter((entry): entry is [string, string] => typeof entry[1] === "string"))
    : {}
  const mounts = Array.isArray(launch.mounts) ? launch.mounts.filter((item): item is LaunchConfiguration["mounts"][number] => !!item && typeof item === "object") : []
  const argumentsList = Array.isArray(launch.arguments) ? launch.arguments.map(String) : []
  const hostPort = launch.host_port ?? launch.container_port
  const image = typeof launch.image === "string" ? launch.image : typeof container.image === "string" ? container.image : null
  const source = launch.url ?? launch.source
  const sourceUrl = typeof source === "string" && source.startsWith("http")
    ? source
    : source && typeof source === "object" && typeof (source as { url?: string }).url === "string"
      ? (source as { url: string }).url
      : null
  const titles: Record<string, string> = {
    docker: "Docker configuration",
    "docker-compose": "Compose configuration",
    native: "Native configuration",
    script: "Script configuration",
    controller: "Controller configuration",
    reference: "Observed configuration",
  }
  const mlxfast = (metadata.mlxfast as Record<string, unknown> | undefined) ?? {}
  const status = typeof value(recipe, "status") === "string" ? String(value(recipe, "status")) : "candidate"
  const registryMeta = (value(recipe, "registry") as Record<string, unknown> | undefined) ?? {}
  const launchable = registryMeta.launchable === true && status === "validated" && kind !== "reference"
  const observed = [localmaxxing.observed_command, mlxfast.observed_command]
    .find((item): item is string => typeof item === "string" && item.length > 0) ?? null
  return {
    arguments: argumentsList,
    composeFile: typeof (launch.compose as { file?: string } | undefined)?.file === "string"
      ? (launch.compose as { file: string }).file
      : typeof container.compose_file === "string" ? container.compose_file : null,
    digest: typeof container.digest === "string" ? container.digest : null,
    engine: engineName || (typeof (value(recipe, "engine") as { name?: string } | undefined)?.name === "string" ? (value(recipe, "engine") as { name: string }).name : "unknown"),
    environment,
    hasContainer,
    image,
    kind,
    launchable,
    mounts,
    observedCommand: observed,
    ports: hostPort == null ? null : String(hostPort),
    sourceUrl,
    status,
    title: titles[kind] ?? "Configuration",
  }
}

export function ConfigurationCard({ config }: { config: LaunchConfiguration }) {
  const runtime = config.hasContainer ? "Container" : config.kind === "reference" ? "Evidence only" : "No container"
  const trust = config.launchable ? "Validated launch contract" : "Candidate evidence — not a Run contract"
  return (
    <section aria-label={config.title} className="config-card">
      <header>
        <p className="eyebrow">{config.title}</p>
        <h3>{config.engine}</h3>
        <p className="config-runtime">
          <span data-runtime={config.hasContainer ? "docker" : config.kind}>{runtime}</span>
          {" · "}
          <span data-status={config.status}>{config.status}</span>
          {" · "}
          {config.kind.replace("-", " ")}
        </p>
        <p className="config-trust">{trust}</p>
      </header>
      <dl>
        {config.image && <div><dt>Image</dt><dd><code>{config.image}</code></dd></div>}
        {config.digest && <div><dt>Digest</dt><dd><code>{config.digest}</code></dd></div>}
        {config.composeFile && <div><dt>Compose file</dt><dd><code>{config.composeFile}</code></dd></div>}
        {config.ports && <div><dt>Port</dt><dd>{config.ports}</dd></div>}
        {config.sourceUrl && <div><dt>Source</dt><dd><a href={config.sourceUrl} rel="noreferrer" target="_blank">{config.sourceUrl}</a></dd></div>}
      </dl>
      {config.arguments.length > 0 && (
        <div className="config-block">
          <h4>{config.launchable ? "Launch arguments" : "Documented arguments"}</h4>
          {!config.launchable && <p>Tokenized source fields. The registry does not offer Run for this recipe.</p>}
          <pre>{config.arguments.join(" ")}</pre>
        </div>
      )}
      {config.observedCommand && (
        <div className="config-block">
          <h4>Observed command</h4>
          <p>Recorded on the source run. Kept in metadata, never copied into an executable launch contract.</p>
          <pre>{config.observedCommand}</pre>
        </div>
      )}
      {Object.keys(config.environment).length > 0 && (
        <div className="config-block">
          <h4>Environment</h4>
          <pre>{Object.entries(config.environment).map(([key, item]) => `${key}=${item}`).join("\n")}</pre>
        </div>
      )}
      {config.mounts.length > 0 && (
        <div className="config-block">
          <h4>Mounts</h4>
          <ul>
            {config.mounts.map((mount, index) => (
              <li key={`${mount.source ?? index}`}>{mount.source} → {mount.target}{mount.read_only ? " (read-only)" : ""}</li>
            ))}
          </ul>
        </div>
      )}
      {!config.hasContainer && !config.observedCommand && config.arguments.length === 0 && (
        <p className="config-empty">No container image. This is measured or documented compatibility, not a Docker launch.</p>
      )}
    </section>
  )
}
