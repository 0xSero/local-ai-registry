import type { ReactNode } from "react"

function Scalar({ value }: { value: string | number | boolean | null }): ReactNode {
  if (value === null || value === "") return <span className="unknown">Unknown</span>
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>
  if (typeof value === "number") return <span>{value.toLocaleString()}</span>

  if (/^https?:\/\//.test(value)) {
    return (
      <a href={value} rel="noreferrer" target="_blank">
        {value}
      </a>
    )
  }

  if (value.length > 180) {
    return (
      <details className="long-value">
        <summary>{value.slice(0, 110)}…</summary>
        <pre>{value}</pre>
      </details>
    )
  }

  return <span>{value}</span>
}

export function DataTree({ value }: { value: unknown }): ReactNode {
  if (value === null || value === undefined) return <Scalar value={null} />
  if (typeof value !== "object") {
    return <Scalar value={value as string | number | boolean} />
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="unknown">None recorded</span>
    return (
      <ol className="data-list">
        {value.map((item, index) => (
          <li key={typeof item === "string" ? item : index}>
            <DataTree value={item} />
          </li>
        ))}
      </ol>
    )
  }

  return (
    <dl className="data-tree">
      {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
        <div className="data-row" key={key}>
          <dt>{key.replaceAll("_", " ")}</dt>
          <dd>
            <DataTree value={item} />
          </dd>
        </div>
      ))}
    </dl>
  )
}
