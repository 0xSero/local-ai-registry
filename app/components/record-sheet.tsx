import Link from "next/link"

import type { ReactNode } from "react"

type Row = { label: string; value: unknown }

const QUIET_KEYS = new Set(["provenance", "facts", "metadata", "source", "sources", "state", "reason", "unit", "prices"])

function label(value: string): string {
  return value.replaceAll("_", " ")
}

function displayUrl(value: string): string {
  try {
    const url = new URL(value)
    return `${url.hostname}${url.pathname === "/" ? "" : url.pathname}`
  } catch {
    return value
  }
}

function isScalar(value: unknown): boolean {
  return value === null || typeof value !== "object"
}

function Scalar({ value }: { value: unknown }): ReactNode {
  if (value === null || value === undefined || value === "") return <span className="unknown">Unknown</span>
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>
  if (typeof value === "number") return <span>{value.toLocaleString("en-US")}</span>
  const text = String(value)
  if (/^https?:\/\//.test(text)) {
    return (
      <a className="data-link" href={text} rel="noreferrer" target="_blank" title={text}>
        {displayUrl(text)} ↗
      </a>
    )
  }
  if (/^\/(?!\/)/.test(text)) return <Link className="data-link" href={text}>{text}</Link>
  return <span>{text}</span>
}

function keyedTableRows(value: Record<string, unknown>): Record<string, unknown>[] | null {
  const entries = Object.entries(value)
  if (entries.length < 3) return null
  if (!entries.every(([, item]) => item === null || (typeof item === "object" && !Array.isArray(item)))) return null
  const keyCounts = new Map<string, number>()
  let populated = 0
  for (const [, item] of entries) {
    if (item === null) continue
    populated += 1
    for (const key of Object.keys(unwrap(item as Record<string, unknown>))) keyCounts.set(key, (keyCounts.get(key) ?? 0) + 1)
  }
  if (populated < 2) return null
  const shared = [...keyCounts.values()].filter((count) => count >= populated / 2).length
  if (shared === 0) return null
  return entries.flatMap(([key, item]) => explode(key, (item ?? {}) as Record<string, unknown>))
}

function explode(name: string, value: Record<string, unknown>): Record<string, unknown>[] {
  const entries = Object.entries(value)
  const allObjects = entries.length > 0 && entries.every(([, item]) => item !== null && typeof item === "object" && !Array.isArray(item))
  if (allObjects) {
    return entries
      .filter(([, item]) => {
        const state = (item as Record<string, unknown>).state
        return state === undefined || state === "known"
      })
      .map(([variant, item]) => ({ "": name, variant, ...(item as Record<string, unknown>) }))
  }
  return [{ "": name, ...value }]
}

function unwrap(value: Record<string, unknown>): Record<string, unknown> {
  const entries = Object.entries(value)
  if (entries.length === 1 && entries[0][1] !== null && typeof entries[0][1] === "object" && !Array.isArray(entries[0][1])) {
    return { variant: entries[0][0], ...(entries[0][1] as Record<string, unknown>) }
  }
  return value
}

function flatten(value: Record<string, unknown>, prefix = ""): { rows: Row[]; tables: Array<{ label: string; rows: Record<string, unknown>[] }>; quiet: Row[] } {
  const rows: Row[] = []
  const tables: Array<{ label: string; rows: Record<string, unknown>[] }> = []
  const quiet: Row[] = []
  for (const [key, item] of Object.entries(value)) {
    const path = prefix ? `${prefix} · ${label(key)}` : label(key)
    if (QUIET_KEYS.has(key)) {
      quiet.push({ label: path, value: item })
      continue
    }
    if (isScalar(item)) {
      if (item !== null && item !== "") rows.push({ label: path, value: item })
    } else if (Array.isArray(item)) {
      if (item.length === 0) {
        continue
      } else if (item.every(isScalar)) {
        rows.push({ label: path, value: item.map((entry) => String(entry)).join(", ") })
      } else {
        tables.push({ label: path, rows: item.filter((entry): entry is Record<string, unknown> => entry !== null && typeof entry === "object") })
      }
    } else {
      const keyed = keyedTableRows(item as Record<string, unknown>)
      if (keyed) {
        tables.push({ label: path, rows: keyed })
        continue
      }
      const nested = flatten(item as Record<string, unknown>, path)
      rows.push(...nested.rows)
      tables.push(...nested.tables)
      quiet.push(...nested.quiet)
    }
  }
  return { rows, tables, quiet }
}

function columnsOf(rows: Record<string, unknown>[]): string[] {
  const seen = new Set<string>()
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!QUIET_KEYS.has(key)) seen.add(key)
    }
  }
  const priority = ["", "variant", "value", "amount", "unit", "currency", "state", "reason"]
  return [...seen]
    .sort((left, right) => {
      const a = priority.indexOf(left)
      const b = priority.indexOf(right)
      return (a === -1 ? priority.length : a) - (b === -1 ? priority.length : b)
    })
    .slice(0, 8)
}

function Cell({ value }: { value: unknown }): ReactNode {
  if (isScalar(value)) return <Scalar value={value} />
  if (Array.isArray(value)) {
    if (value.every(isScalar)) return <span>{value.join(", ")}</span>
    return <span className="unknown">{value.length} entries</span>
  }
  const entry = value as Record<string, unknown>
  if (typeof entry.code === "string") {
    return <span className="unknown" title={typeof entry.detail === "string" ? entry.detail : undefined}>{entry.code}</span>
  }
  const pairs = Object.entries(entry)
  if (pairs.length <= 3 && pairs.every(([, item]) => isScalar(item))) {
    return <span>{pairs.map(([key, item]) => `${label(key)} ${typeof item === "number" ? item.toLocaleString("en-US") : String(item ?? "—")}`).join(" · ")}</span>
  }
  return <span className="unknown">{pairs.length} fields</span>
}

function SheetTable({ caption, rows }: { caption: string; rows: Record<string, unknown>[] }) {
  const columns = columnsOf(rows)
  if (columns.length === 0 || rows.length === 0) return null
  return (
    <div className="sheet-table">
      <p className="sheet-caption">{caption}</p>
      <div className="sheet-table-scroll">
        <table className="flag-table">
          <thead>
            <tr>{columns.map((column) => <th key={column} scope="col">{label(column)}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {columns.map((column) => (
                  <td key={column}>
                    <Cell value={row[column]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function QuietBlock({ items }: { items: Row[] }) {
  if (items.length === 0) return null
  return (
    <details className="sheet-quiet">
      <summary>Provenance &amp; metadata ({items.length})</summary>
      <div className="sheet-quiet-body">
        {items.map((item) => {
          const value = item.value
          if (value !== null && typeof value === "object" && !Array.isArray(value)) {
            const nested = flatten(value as Record<string, unknown>)
            return (
              <div key={item.label}>
                <p className="sheet-caption">{item.label}</p>
                {nested.rows.length > 0 && <SheetGrid rows={nested.rows} />}
                {nested.tables.map((table) => <SheetTable caption={table.label} key={table.label} rows={table.rows} />)}
                {nested.quiet.map((entry) => renderQuietEntry(entry))}
              </div>
            )
          }
          return renderQuietEntry(item)
        })}
      </div>
    </details>
  )
}

function renderQuietEntry(item: Row): ReactNode {
  if (Array.isArray(item.value) && item.value.some((entry) => entry !== null && typeof entry === "object")) {
    return <SheetTable caption={item.label} key={item.label} rows={item.value.filter((entry): entry is Record<string, unknown> => entry !== null && typeof entry === "object")} />
  }
  if (item.value !== null && typeof item.value === "object" && !Array.isArray(item.value)) {
    const nested = flatten(item.value as Record<string, unknown>, item.label)
    return (
      <div key={item.label}>
        {nested.rows.length > 0 && <SheetGrid rows={nested.rows} />}
        {nested.tables.map((table) => <SheetTable caption={table.label} key={table.label} rows={table.rows} />)}
      </div>
    )
  }
  return (
    <div className="sheet-quiet-row" key={item.label}>
      <span className="sheet-caption">{item.label}</span> <Scalar value={Array.isArray(item.value) ? item.value.join(", ") : item.value} />
    </div>
  )
}

function SheetGrid({ rows }: { rows: Row[] }) {
  return (
    <dl className="sheet-grid">
      {rows.map((row) => (
        <div key={row.label}>
          <dt>{row.label}</dt>
          <dd><Scalar value={row.value} /></dd>
        </div>
      ))}
    </dl>
  )
}

export function RecordSheet({ record }: { record: Record<string, unknown> }) {
  const scalarRows: Row[] = []
  const sections: Array<{ key: string; rows: Row[]; tables: Array<{ label: string; rows: Record<string, unknown>[] }>; quiet: Row[] }> = []
  const quietTop: Row[] = []
  for (const [key, value] of Object.entries(record)) {
    if (QUIET_KEYS.has(key)) {
      quietTop.push({ label: label(key), value })
      continue
    }
    if (isScalar(value)) {
      if (value !== null && value !== "") scalarRows.push({ label: label(key), value })
    } else if (Array.isArray(value)) {
      if (value.length === 0) {
        continue
      } else if (value.every(isScalar)) {
        scalarRows.push({ label: label(key), value: value.map((entry) => String(entry)).join(", ") })
      } else {
        sections.push({ key, rows: [], tables: [{ label: label(key), rows: value.filter((entry): entry is Record<string, unknown> => entry !== null && typeof entry === "object") }], quiet: [] })
      }
    } else {
      const nested = flatten(value as Record<string, unknown>)
      sections.push({ key, ...nested })
    }
  }
  return (
    <div className="record-sheet-body">
      {scalarRows.length > 0 && <SheetGrid rows={scalarRows} />}
      {sections.map((section) => (
        <section className="sheet-section" key={section.key}>
          <p className="eyebrow">{label(section.key)}</p>
          {section.rows.length > 0 && <SheetGrid rows={section.rows} />}
          {section.tables.map((table) => <SheetTable caption={table.label === label(section.key) ? "" : table.label} key={table.label} rows={table.rows} />)}
          <QuietBlock items={section.quiet} />
        </section>
      ))}
      <QuietBlock items={quietTop} />
    </div>
  )
}
