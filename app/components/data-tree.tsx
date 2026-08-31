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

const COLLAPSED_KEYS = new Set(["facts", "provenance", "sources", "source", "metadata"])
const MAX_OPEN_DEPTH = 3

function Branch({ value, open, depth }: { value: unknown[] | Record<string, unknown>; open: boolean; depth: number }) {
  return (
    <details className="data-branch" open={open}>
      <summary>{branchSummary(value)}</summary>
      <div className="data-branch-body"><DataTree depth={open ? depth + 1 : MAX_OPEN_DEPTH} nested value={value} /></div>
    </details>
  )
}

function branchOpen(key: string | null, depth: number): boolean {
  if (key !== null && COLLAPSED_KEYS.has(key)) return false
  return depth < MAX_OPEN_DEPTH
}

export function DataTree({ nested = false, value, depth = 0 }: { nested?: boolean; value: unknown; depth?: number }): ReactNode {
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
              ? <Branch depth={depth} open={branchOpen(null, depth)} value={item as unknown[] | Record<string, unknown>} />
              : <DataTree depth={depth + 1} nested value={item} />}
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
              ? <Branch depth={depth} open={branchOpen(key, depth)} value={item as unknown[] | Record<string, unknown>} />
              : <DataTree depth={depth + 1} nested value={item} />}
          </dd>
        </div>
      ))}
    </dl>
  )
}
