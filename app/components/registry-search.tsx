"use client"

import { useRef, useTransition, type FormEvent } from "react"
import { useRouter } from "next/navigation"

type RegistrySearchProps = {
  engines: Array<string | number>
  evidence: string
  memory: string
  query: string
  recipeFilters: boolean
  selectedEngine: string
  topic: string
  validation: string
  vramOptions: Array<string | number>
}

const SEARCH_LABELS: Record<string, string> = {
  hardware: "Search hardware",
  models: "Search models",
  recipes: "Find a model or machine",
  "speed-sweeps": "Search measured speed sweeps",
}

export function RegistrySearch({
  engines,
  evidence,
  memory,
  query,
  recipeFilters,
  selectedEngine,
  topic,
  validation,
  vramOptions,
}: RegistrySearchProps) {
  const formRef = useRef<HTMLFormElement>(null)
  const debounceRef = useRef<NodeJS.Timeout | undefined>(undefined)
  const router = useRouter()
  const [pending, startTransition] = useTransition()

  function apply() {
    const form = formRef.current
    if (!form) return
    const params = new URLSearchParams()
    for (const [key, value] of new FormData(form).entries()) {
      if (typeof value === "string" && value.trim()) params.set(key, value.trim())
    }
    startTransition(() => router.replace(`/?${params.toString()}`, { scroll: false }))
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    clearTimeout(debounceRef.current)
    apply()
  }

  function searchSoon() {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(apply, 240)
  }

  const searchTopic = topic || "recipes"
  const searchLabel = SEARCH_LABELS[searchTopic] ?? "Search registry"

  return (
    <form
      action="/"
      aria-busy={pending}
      aria-label={searchLabel}
      className="registry-search"
      method="get"
      onSubmit={submit}
      ref={formRef}
      role="search"
    >
      <input name="topic" type="hidden" value={searchTopic} />
      <label className="search-field">
        <span className="sr-only">{searchLabel}</span>
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle cx="11" cy="11" r="6.5" />
          <path d="m16 16 4 4" />
        </svg>
        <input
          autoComplete="off"
          defaultValue={query}
          name="q"
          onInput={searchSoon}
          placeholder={searchLabel}
          type="search"
        />
        <kbd>⌘ K</kbd>
      </label>

      {recipeFilters && (
        <div className="compact-filters" aria-label="Recipe filters">
          <label>
            <span>Status</span>
            <select defaultValue={validation} name="validation" onChange={apply}>
              <option value="">All statuses</option>
              <option value="validated">Validated · launch-safe</option>
              <option value="candidate">Candidate or reference</option>
            </select>
          </label>
          <label>
            <span>Engine</span>
            <select defaultValue={selectedEngine} name="engine" onChange={apply}>
              <option value="">Any engine</option>
              {engines.map((engine) => <option key={engine} value={engine}>{engine}</option>)}
            </select>
          </label>
          <label>
            <span>Memory</span>
            <select defaultValue={memory} name="min_vram_gb" onChange={apply}>
              <option value="">Any memory</option>
              {vramOptions.map((amount) => <option key={amount} value={amount}>At least {amount} GB</option>)}
            </select>
          </label>
          <label>
            <span>Evidence</span>
            <select defaultValue={evidence} name="evidence" onChange={apply}>
              <option value="">Any evidence</option>
              <option value="true">Measured speed attached</option>
              <option value="false">No measured speed</option>
            </select>
          </label>
        </div>
      )}
      <noscript><button type="submit">Search</button></noscript>
    </form>
  )
}
