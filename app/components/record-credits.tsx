type Credit = { name: string; role: string; url: string }

export function RecordCredits({ record }: { record: Record<string, unknown> }) {
  const metadata = record.metadata as Record<string, unknown> | undefined
  const credits = Array.isArray(metadata?.credits) ? metadata.credits.filter((value): value is Credit => {
    if (!value || typeof value !== "object") return false
    return typeof value.name === "string" && typeof value.role === "string" &&
      typeof value.url === "string" && /^https:\/\//.test(value.url)
  }) : []
  if (credits.length === 0) return null
  return (
    <section aria-label="Credits" className="record-evidence">
      <p className="eyebrow">Credits</p>
      <ul>
        {credits.map((credit) => (
          <li key={`${credit.name}:${credit.url}`}>
            <a href={credit.url} target="_blank" rel="noreferrer">{credit.name}</a>
            {" — "}{credit.role}
          </li>
        ))}
      </ul>
    </section>
  )
}
