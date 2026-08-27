import Link from "next/link"

import type { ReactNode } from "react"

function label(value: string): string {
  return value.replaceAll("_", " ")
}

function branchSummary(value: unknown[] | Record<string, unknown>): string {
  if (Array.isArray(value)) return `${value.length.toLocaleString()} ${value.length === 1 ? "item" : "items"}`
  if (typeof value.name === "string" && value.name.length > 0) return value.name
  if (typeof value.id === "string" && value.id.length > 0) return value.id
  const count = Object.keys(value).length
  return `${count.toLocaleString()} ${count === 1 ? "field" : "fields"}`
}

function displayUrl(value: string): string {
  try {
    const url = new URL(value)
    return `${url.hostname}${url.pathname === "/" ? "" : url.pathname}`
  } catch {
    return value
  }
}

function Scalar({ value }: { value: string | number | boolean | null }): ReactNode {
  if (value === null || value === "") return <span className="unknown">Unknown</span>
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>
  if (typeof value === "number") return <span>{value.toLocaleString()}</span>

  if (/^https?:\/\//.test(value)) {
    return (
      <a className="data-link" href={value} rel="noreferrer" target="_blank" title={value}>
        {displayUrl(value)} ↗
      </a>
    )
  }

  if (/^\/(?!\/)/.test(value)) {
    return <Link className="data-link" href={value}>{value}</Link>
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

function Branch({ value }: { value: unknown[] | Record<string, unknown> }) {
  return (
    <details className="data-branch">
      <summary>{branchSummary(value)}</summary>
      <div className="data-branch-body"><DataTree nested value={value} /></div>
    </details>
  )
}

export function DataTree({ nested = false, value }: { nested?: boolean; value: unknown }): ReactNode {
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
            {item !== null && typeof item === "object"
              ? <Branch value={item as unknown[] | Record<string, unknown>} />
              : <DataTree nested value={item} />}
          </li>
        ))}
      </ol>
    )
  }

  return (
    <dl className={`data-tree ${nested ? "data-tree-nested" : "data-tree-root"}`}>
      {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
        <div className="data-row" key={key}>
          <dt>{label(key)}</dt>
          <dd>
            {item !== null && typeof item === "object"
              ? <Branch value={item as unknown[] | Record<string, unknown>} />
              : <DataTree nested value={item} />}
          </dd>
        </div>
      ))}
    </dl>
  )
}
