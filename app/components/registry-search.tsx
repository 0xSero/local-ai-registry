"use client"

import { useRef, useTransition, type FormEvent } from "react"
import { useRouter } from "next/navigation"

export type SearchFilter = {
  label: string
  name: string
  options: Array<{ label: string; value: string }>
  value: string
}

type RegistrySearchProps = {
  filters: SearchFilter[]
  query: string
  topic: string
}

const SEARCH_LABELS: Record<string, string> = {
  hardware: "Search hardware",
  models: "Search models",
  prices: "Search price observations",
  recipes: "Find a model or machine",
  "speed-sweeps": "Search measured speed sweeps",
}

export function RegistrySearch({ filters, query, topic }: RegistrySearchProps) {
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
          key={`${searchTopic}:${query}`}
          defaultValue={query}
          name="q"
          onInput={searchSoon}
          placeholder={searchLabel}
          type="search"
        />
      </label>

      {filters.length > 0 && (
        <div className="compact-filters" aria-label={`${searchTopic} filters`}>
          {filters.map((filter) => (
            <label key={filter.name}>
              <span>{filter.label}</span>
              <select name={filter.name} onChange={apply} value={filter.value}>
                {filter.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
          ))}
        </div>
      )}
      <noscript><button type="submit">Search</button></noscript>
    </form>
  )
}
