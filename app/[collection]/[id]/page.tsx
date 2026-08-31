import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"

import { CollectionNav } from "@/app/components/collection-nav"
import { RecordBody } from "@/app/components/record-body"
import {
  collectionHref,
  collectionLabel,
  collectionTopic,
  isCollection,
} from "@/app/lib/catalog"
import { huggingFaceIdentity, recordTitle } from "@/app/lib/record-view"
import { getEntityDetail } from "@/lib/registry"

export const dynamic = "force-dynamic"

type DetailProps = {
  params: Promise<{ collection: string; id: string }>
}

export async function generateMetadata({ params }: DetailProps): Promise<Metadata> {
  const { collection, id } = await params
  if (!isCollection(collection)) return { title: "Record not found" }
  const detail = getEntityDetail(collection, id)
  if (!detail) return { title: "Record not found" }
  return { title: `${recordTitle(detail, id)} · Local AI Registry` }
}

export default async function DetailPage({ params }: DetailProps) {
  const { collection, id } = await params
  const label = collectionLabel(collection)
  if (!label || !isCollection(collection)) notFound()
  const detail = getEntityDetail(collection, id)
  if (!detail) notFound()
  if (collection === "model-instances" && !huggingFaceIdentity(detail)?.url) {
    throw new Error(`Model instance '${id}' lacks its authoritative Hugging Face identity`)
  }

  const title = recordTitle(detail, id)
  const topic = collectionTopic(collection)
  const collectionBrowse = collectionHref(collection)
  const recipeSearch = collection === "recipes" || collection === "hardware" || collection === "models" || collection === "model-instances"

  return (
    <main className="detail-page">
      <CollectionNav current={topic} />
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Registry</Link>
        <span>/</span>
        <Link href={collectionBrowse}>{label}</Link>
        <span>/</span>
        <span>{title}</span>
      </nav>
      <header className="detail-header">
        <p className="eyebrow">{label}</p>
        <h1>{title}</h1>
        <code>{id}</code>
        <div className="detail-actions">
          <a href={`/api/v1/${collection}/${id}`}>JSON API</a>
          {recipeSearch ? (
            <Link href={`/?topic=recipes&q=${encodeURIComponent(title)}`}>Find compatible recipes</Link>
          ) : (
            <Link href={`${collectionBrowse}&q=${encodeURIComponent(title)}`}>Back to {label.toLowerCase()} search</Link>
          )}
        </div>
      </header>
      <RecordBody collection={collection} record={detail} variant="page" />
    </main>
  )
}
