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
  recipes: "Recipe",
  "speed-sweeps": "Speed evidence",
}

type DetailProps = {
  params: Promise<{ collection: string; id: string }>
}

export async function generateMetadata({ params }: DetailProps): Promise<Metadata> {
  const { collection, id } = await params
  if (!COLLECTION_LABELS[collection]) return { title: "Record not found" }
  const detail = getEntityDetail(collection, id)
  if (!detail) return { title: "Record not found" }
  const title = String(detail.name ?? detail.repository ?? detail.id ?? id)
  return { title: `${title} · Local AI Registry` }
}

export default async function DetailPage({ params }: DetailProps) {
  const { collection, id } = await params
  const collectionLabel = COLLECTION_LABELS[collection]
  if (!collectionLabel) notFound()
  const detail = getEntityDetail(collection, id)
  if (!detail) notFound()

  const title = String(detail.name ?? detail.repository ?? detail.id ?? id)
  const instance = collection === "model-instances" ? detail : null
  const huggingFaceUrl = instance && typeof instance.hugging_face_url === "string"
    ? instance.hugging_face_url
    : null
  const artifactUrl = instance && typeof instance.url === "string" ? instance.url : null
  const artifactResolution = instance ? String(instance.artifact_resolution) : null

  return (
    <main className="detail-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Search</Link><span>/</span><span>{collectionLabel}</span>
      </nav>
      <header className="detail-header">
        <p className="eyebrow">{collectionLabel}</p>
        <h1>{title}</h1>
        <code>{id}</code>
        <div className="detail-actions">
          <a href={`/api/v1/${collection}/${id}`}>JSON API</a>
          <Link href={`/?${collection === "hardware" ? "hardware" : "model"}=${encodeURIComponent(title)}`}>
            Find compatibility
          </Link>
        </div>
      </header>

      {instance && (
        <section className="artifact-resolution" aria-label="Artifact resolution">
          <p className="eyebrow">Canonical artifact link from this model-instance body</p>
          {huggingFaceUrl ? (
            <a href={huggingFaceUrl} rel="noreferrer" target="_blank">{huggingFaceUrl} ↗</a>
          ) : artifactResolution === "non_hugging_face" && artifactUrl ? (
            <p>Non-Hugging-Face artifact: <a href={artifactUrl}>{artifactUrl}</a></p>
          ) : (
            <p className="unknown">No canonical Hugging Face URL is resolved for this artifact.</p>
          )}
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
