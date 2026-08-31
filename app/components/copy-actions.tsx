"use client"

import { useState } from "react"

import type { CopyItem } from "@/app/lib/record-view"

export function CopyActions({ items }: { items: CopyItem[] }) {
  const [copied, setCopied] = useState<string | null>(null)
  if (items.length === 0) return null

  async function copy(item: CopyItem) {
    await navigator.clipboard.writeText(item.value)
    setCopied(item.label)
    window.setTimeout(() => setCopied((current) => current === item.label ? null : current), 1600)
  }

  return (
    <div className="copy-actions" aria-label="Copy record fields">
      {items.map((item) => (
        <button key={item.label} onClick={() => copy(item)} type="button">
          Copy {item.label.toLowerCase()}
        </button>
      ))}
      <span className="copy-status" aria-live="polite">{copied ? `Copied ${copied.toLowerCase()}` : ""}</span>
    </div>
  )
}
