export type LaunchConfiguration = {
  arguments: string[]
  composeFile: string | null
  digest: string | null
  endpoint: string | null
  engine: string
  environment: Record<string, string>
  hasContainer: boolean
  image: string | null
  kind: string
  launchable: boolean
  mounts: Array<{ source?: string; target?: string; read_only?: boolean }>
  notes: string[]
  ports: string | null
  servedModelName: string | null
  sourceUrl: string | null
  status: string
  steps: string[][]
  title: string
}

function value(record: Record<string, unknown>, key: string): unknown {
  return record[key]
}

function stringMap(record: unknown): Record<string, string> {
  if (!record || typeof record !== "object" || Array.isArray(record)) return {}
  return Object.fromEntries(
    Object.entries(record as Record<string, unknown>).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  )
}

function stringList(record: unknown): string[] {
  return Array.isArray(record) ? record.map(String) : []
}

function argvList(record: unknown): string[][] {
  if (!Array.isArray(record)) return []
  return record.filter((step): step is unknown[] => Array.isArray(step)).map((step) => step.map(String))
}

export function flagRows(tokens: string[]): Array<[string, string | null]> {
  const rows: Array<[string, string | null]> = []
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index]
    if (!token.startsWith("-") || token === "-") continue
    const equals = token.indexOf("=")
    if (equals > 0) {
      rows.push([token.slice(0, equals), token.slice(equals + 1)])
      continue
    }
    const next = tokens[index + 1]
    if (next && !next.startsWith("-")) {
      rows.push([token, next])
      index += 1
    } else {
      rows.push([token, null])
    }
  }
  return rows
}

export function configurationFromRecipe(recipe: Record<string, unknown>, engineName?: string): LaunchConfiguration {
  const launch = (value(recipe, "launch") as Record<string, unknown> | undefined) ?? {}
  const container = (launch.container as Record<string, unknown> | undefined) ?? {}
  const kind = typeof launch.kind === "string" ? launch.kind : "reference"
  const hasContainer = kind === "docker" || kind === "docker-compose"
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
  const status = typeof value(recipe, "status") === "string" ? String(value(recipe, "status")) : "candidate"
  const registryMeta = (value(recipe, "registry") as Record<string, unknown> | undefined) ?? {}
  const launchable = registryMeta.launchable === true && status === "validated" && kind !== "reference"
  const mounts = Array.isArray(launch.mounts)
    ? launch.mounts.filter((item): item is LaunchConfiguration["mounts"][number] => !!item && typeof item === "object")
    : []
  return {
    arguments: stringList(launch.arguments),
    composeFile: typeof (launch.compose as { file?: string } | undefined)?.file === "string"
      ? (launch.compose as { file: string }).file
      : typeof container.compose_file === "string" ? container.compose_file : null,
    digest: typeof container.digest === "string" ? container.digest : null,
    endpoint: typeof launch.endpoint === "string" ? launch.endpoint : null,
    engine: engineName || (typeof (value(recipe, "engine") as { name?: string } | undefined)?.name === "string" ? (value(recipe, "engine") as { name: string }).name : "unknown"),
    environment: stringMap(launch.environment),
    hasContainer,
    image,
    kind,
    launchable,
    mounts,
    notes: stringList(launch.notes),
    ports: hostPort == null ? null : String(hostPort),
    servedModelName: typeof launch.served_model_name === "string" ? launch.served_model_name : null,
    sourceUrl,
    status,
    steps: argvList(launch.steps),
    title: titles[kind] ?? "Configuration",
  }
}

function Argv({ tokens }: { tokens: string[] }) {
  if (tokens.length === 0) return null
  return (
    <ol className="argv">
      {tokens.map((token, index) => (
        <li key={`${index}:${token}`}><code>{token}</code></li>
      ))}
    </ol>
  )
}

function FlagTable({ tokens }: { tokens: string[] }) {
  const rows = flagRows(tokens)
  if (rows.length < 2) return null
  return (
    <table className="flag-table">
      <thead>
        <tr><th>Flag</th><th>Value</th></tr>
      </thead>
      <tbody>
        {rows.map(([flag, item], index) => (
          <tr key={`${index}:${flag}`}>
            <th scope="row"><code>{flag}</code></th>
            <td>{item ? <code>{item}</code> : "set"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function ConfigurationCard({ config }: { config: LaunchConfiguration }) {
  const runtime = config.hasContainer ? "Container" : config.kind === "reference" ? "Evidence only" : "No container"
  const trust = config.launchable ? "Validated launch contract" : "Candidate evidence — not a Run contract"
  const argv = config.steps.length > 0 ? null : config.arguments
  const empty = !config.image && !config.arguments.length && !config.steps.length && !config.endpoint && !Object.keys(config.environment).length && !config.notes.length
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
        {config.endpoint && <div><dt>Endpoint</dt><dd><code>{config.endpoint}</code></dd></div>}
        {config.servedModelName && <div><dt>Served model</dt><dd><code>{config.servedModelName}</code></dd></div>}
        {config.sourceUrl && <div><dt>Source</dt><dd><a href={config.sourceUrl} rel="noreferrer" target="_blank">{config.sourceUrl}</a></dd></div>}
      </dl>
      {config.steps.length > 0 && (
        <div className="config-block">
          <h4>Setup steps</h4>
          {!config.launchable && <p>Tokenized source fields. The registry does not offer Run for this recipe.</p>}
          <ol className="config-steps">
            {config.steps.map((step, index) => (
              <li key={index}><Argv tokens={step} /></li>
            ))}
          </ol>
        </div>
      )}
      {argv && argv.length > 0 && (
        <div className="config-block">
          <h4>{config.launchable ? "Launch arguments" : "Documented arguments"}</h4>
          {!config.launchable && <p>Tokenized source fields. The registry does not offer Run for this recipe.</p>}
          <Argv tokens={argv} />
          <FlagTable tokens={argv} />
        </div>
      )}
      {config.steps.length > 0 && flagRows(config.arguments).length >= 2 && (
        <div className="config-block">
          <FlagTable tokens={config.arguments} />
        </div>
      )}
      {Object.keys(config.environment).length > 0 && (
        <div className="config-block">
          <h4>Environment</h4>
          <table className="flag-table">
            <thead>
              <tr><th>Variable</th><th>Value</th></tr>
            </thead>
            <tbody>
              {Object.entries(config.environment).map(([key, item]) => (
                <tr key={key}>
                  <th scope="row"><code>{key}</code></th>
                  <td><code>{item}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {config.mounts.length > 0 && (
        <div className="config-block">
          <h4>Mounts</h4>
          <table className="flag-table">
            <thead>
              <tr><th>Source</th><th>Target</th></tr>
            </thead>
            <tbody>
              {config.mounts.map((mount, index) => (
                <tr key={`${mount.source ?? index}`}>
                  <td><code>{mount.source}</code></td>
                  <td><code>{mount.target}</code>{mount.read_only ? " (read-only)" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {config.notes.length > 0 && (
        <div className="config-block">
          <h4>Source notes</h4>
          {config.notes.map((note, index) => <p key={index}>{note}</p>)}
        </div>
      )}
      {empty && (
        <p className="config-empty">No tokenized launch fields. This is measured or documented compatibility, not a Docker launch.</p>
      )}
    </section>
  )
}
