type HuggingFaceFields = {
  link_type?: string
  reason?: string | { code: string; detail: string }
  repository?: string | null
  status?: string
  url?: string
}

function reasonText(reason: HuggingFaceFields["reason"]): string {
  if (!reason) return "Identity recorded by the registry."
  if (typeof reason === "string") return reason.replaceAll("-", " ")
  return `${reason.code.replaceAll("-", " ")}: ${reason.detail}`
}

export function HuggingFaceCard({ identity, title = "Hugging Face model card" }: { identity?: HuggingFaceFields | null; title?: string }) {
  if (!identity?.url) return null
  const known = identity.status === "known" && identity.link_type === "repository"
  return (
    <section aria-label={title} className="hf-card">
      <p className="eyebrow">{title}</p>
      <h3>Identity</h3>
      <a href={identity.url} rel="noreferrer" target="_blank">{identity.url}</a>
      <dl>
        <div><dt>Repository</dt><dd>{identity.repository ?? "Not an exact repository"}</dd></div>
        <div><dt>Status</dt><dd>{identity.status ?? "unknown"}</dd></div>
        <div><dt>Link type</dt><dd>{identity.link_type === "repository" ? "Exact Hub repository" : "Hub search fallback"}</dd></div>
      </dl>
      <p className="hf-card-note">
        {known
          ? "Public Hugging Face repository confirmed by the Hub API."
          : reasonText(identity.reason)}
      </p>
    </section>
  )
}
