import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"

import { DataTree } from "@/app/components/data-tree"
import { getEntityDetail } from "@/lib/registry"

export const dynamic = "force-dynamic"

const COLLECTION_LABELS: Record<string, string> = {
  hardware: "Hardware",
  "model-instances": "Model instance",
  models: "Model",
  prices: "Regional market price",
  recipes: "Recipe",
  benchmarks: "Leaderboard",
  "speed-sweeps": "Speed sweep",
}

const COLLECTION_TOPICS: Record<string, string> = {
  hardware: "hardware",
  "model-instances": "recipes",
  models: "models",
  prices: "prices",
  recipes: "recipes",
  benchmarks: "benchmarks",
  "speed-sweeps": "speed-sweeps",
}

type DetailProps = {
  params: Promise<{ collection: string; id: string }>
}

type HuggingFaceDisplay = {
  linkType: "repository" | "search"
  status: "known" | "unknown" | "unavailable"
  url: string
}

function readHuggingFace(record: Record<string, unknown>): HuggingFaceDisplay | null {
  const value = record.huggingface
  if (!value || typeof value !== "object") return null
  if (!("url" in value) || !("status" in value) || !("link_type" in value)) return null
  const { link_type: linkType, status, url } = value
  if (typeof url !== "string" || url.length === 0) return null
  if (status !== "known" && status !== "unknown" && status !== "unavailable") return null
  if (linkType !== "repository" && linkType !== "search") return null
  return { linkType, status, url }
}

export async function generateMetadata({ params }: DetailProps): Promise<Metadata> {
  const { collection, id } = await params
  if (!COLLECTION_LABELS[collection]) return { title: "Record not found" }
  const detail = getEntityDetail(collection, id)
  if (!detail) return { title: "Record not found" }
  const product = detail.product && typeof detail.product === "object" && "name" in detail.product ? detail.product.name : null
  const title = String(detail.name ?? detail.repository ?? product ?? detail.id ?? id)
  return { title: `${title} · Local AI Registry` }
}

export default async function DetailPage({ params }: DetailProps) {
  const { collection, id } = await params
  const collectionLabel = COLLECTION_LABELS[collection]
  if (!collectionLabel) notFound()
  const detail = getEntityDetail(collection, id)
  if (!detail) notFound()

  const product = detail.product && typeof detail.product === "object" && "name" in detail.product ? detail.product.name : null
  const title = String(detail.name ?? detail.repository ?? product ?? detail.id ?? id)
  const instance = collection === "model-instances" ? detail : null
  const huggingFace = instance ? readHuggingFace(instance) : null
  if (instance && !huggingFace) {
    throw new Error(`Model instance '${id}' lacks its authoritative Hugging Face identity`)
  }

  const topic = COLLECTION_TOPICS[collection]
  const collectionHref = `/?topic=${encodeURIComponent(topic)}`
  const recipeSearchHref = `/?topic=recipes&q=${encodeURIComponent(title)}`
  const collectionSearchHref = `${collectionHref}&q=${encodeURIComponent(title)}`
  const showRecipeSearch = collection === "recipes" || collection === "hardware" || collection === "models" || collection === "model-instances"

  return (
    <main className="detail-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Registry</Link>
        <span>/</span>
        <Link href={collectionHref}>{collectionLabel}</Link>
        <span>/</span>
        <span>{title}</span>
      </nav>
      <header className="detail-header">
        <p className="eyebrow">{collectionLabel}</p>
        <h1>{title}</h1>
        <code>{id}</code>
        <div className="detail-actions">
          <a href={`/api/v1/${collection}/${id}`}>JSON API</a>
          {showRecipeSearch ? (
            <Link href={recipeSearchHref}>Find compatible recipes</Link>
          ) : (
            <Link href={collectionSearchHref}>Back to {collectionLabel.toLowerCase()} search</Link>
          )}
        </div>
      </header>

      {huggingFace && (
        <section className="artifact-resolution" aria-label="Hugging Face identity">
          <p className="eyebrow">Authoritative Hugging Face link from this model-instance body</p>
          <a href={huggingFace.url} rel="noreferrer" target="_blank">{huggingFace.url} ↗</a>
          <dl className="artifact-fields">
            <div><dt>Status</dt><dd>{huggingFace.status}</dd></div>
            <div><dt>Link type</dt><dd>{huggingFace.linkType}</dd></div>
          </dl>
          <p className="link-explanation">
            {huggingFace.linkType === "repository"
              ? "Exact Hugging Face repository link."
              : "Hugging Face search fallback; not an exact repository link."}
          </p>
        </section>
      )}

      <section className="record-sheet">
        <div className="record-sheet-heading">
          <h2>Complete normalized record</h2>
          <p>Null values are explicit unknowns. Nested enrichment is shown whenever it is present.</p>
        </div>
        <DataTree value={detail} />
      </section>
    </main>
  )
}
