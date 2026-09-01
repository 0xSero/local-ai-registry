import { readFileSync } from "node:fs"
import nodePath from "node:path"

import { NextRequest, NextResponse } from "next/server"

import {
  collectionCounts,
  getEntityDetail,
  getFacets,
  getRegistryIndex,
  listHardware,
  listModelInstances,
  listModels,
  listPrices,
  listBenchmarks,
  listSpeedSweeps,
  queryCompatibility,
  type CompatibilityFilters,
  type Pagination,
} from "@/lib/registry"

export const dynamic = "force-dynamic"

const PUBLIC_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
}

type RouteContext = {
  params: Promise<{ path: string[] }>
}

function response(body: unknown, status = 200): NextResponse {
  return NextResponse.json(body, { status, headers: PUBLIC_HEADERS })
}

function pagination(searchParams: URLSearchParams): Pagination {
  const requestedLimit = Number(searchParams.get("limit") ?? 25)
  const requestedOffset = Number(searchParams.get("offset") ?? 0)
  return {
    limit: Number.isFinite(requestedLimit) ? Math.min(100, Math.max(1, Math.trunc(requestedLimit))) : 25,
    offset: Number.isFinite(requestedOffset) ? Math.max(0, Math.trunc(requestedOffset)) : 0,
  }
}

function filters(searchParams: URLSearchParams): Record<string, string> {
  return Object.fromEntries(
    [...searchParams.entries()].filter(([key]) => key !== "limit" && key !== "offset"),
  )
}

function listResponse(
  request: NextRequest,
  result: { data: unknown[]; total: number },
  page: Pagination,
): NextResponse {
  const url = new URL(request.url)
  const links: Record<string, string | null> = { next: null, previous: null }
  if (page.offset + page.limit < result.total) {
    url.searchParams.set("offset", String(page.offset + page.limit))
    url.searchParams.set("limit", String(page.limit))
    links.next = url.toString()
  }
  if (page.offset > 0) {
    url.searchParams.set("offset", String(Math.max(0, page.offset - page.limit)))
    url.searchParams.set("limit", String(page.limit))
    links.previous = url.toString()
  }

  return response({
    data: result.data,
    meta: {
      limit: page.limit,
      offset: page.offset,
      returned: result.data.length,
      source: "registry",
      total: result.total,
    },
    links,
  })
}


function assetBlob(id: string): NextResponse {
  if (!/^[a-z0-9][a-z0-9.-]*$/.test(id)) {
    return response({ error: { code: "not_found", message: "asset not found" } }, 404)
  }
  const base = nodePath.join(process.cwd(), "registry", "asset")
  let manifest: { file: string; media_type?: string; sha256?: string }
  try {
    manifest = JSON.parse(readFileSync(nodePath.join(base, `${id}.json`), "utf8"))
  } catch {
    return response({ error: { code: "not_found", message: "asset not found" } }, 404)
  }
  const blobPath = nodePath.join(base, nodePath.basename(manifest.file))
  const body = readFileSync(blobPath)
  return new NextResponse(new Uint8Array(body), {
    headers: {
      "content-type": manifest.media_type ?? "application/octet-stream",
      "x-content-sha256": manifest.sha256 ?? "",
      "cache-control": "public, max-age=3600",
    },
  })
}

export async function GET(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params
  const [resource, id, extra] = path
  if (resource === "asset" && id && extra === "file") {
    return assetBlob(id)
  }
  if (!resource || extra) {
    return response({ error: { code: "not_found", message: "API route not found" } }, 404)
  }

  const collection = resource === "benchmarks" ? "benchmark" : resource
  if (id) {
    const detail = getEntityDetail(collection, id)
    if (!detail) {
      return response(
        { error: { code: "not_found", message: `${resource} record '${id}' was not found` } },
        404,
      )
    }
    return response({ data: detail, meta: { source: "registry" } })
  }

  if (resource === "index") {
    return response({ data: getRegistryIndex(), meta: { source: "registry" } })
  }
  if (resource === "facets") {
    return response({ data: getFacets(), meta: { counts: collectionCounts(), source: "registry" } })
  }

  const page = pagination(request.nextUrl.searchParams)
  const selectedFilters = filters(request.nextUrl.searchParams)

  if (resource === "models") {
    return listResponse(request, listModels(selectedFilters, page), page)
  }
  if (resource === "model-instances") {
    return listResponse(request, listModelInstances(selectedFilters, page), page)
  }
  if (resource === "hardware") {
    return listResponse(request, listHardware(selectedFilters, page), page)
  }
  if (resource === "prices") {
    return listResponse(request, listPrices(selectedFilters, page), page)
  }
  if (resource === "recipes" || resource === "compatibility") {
    return listResponse(
      request,
      queryCompatibility(selectedFilters as CompatibilityFilters, page),
      page,
    )
  }
  if (resource === "benchmarks") {
    return listResponse(request, listBenchmarks(selectedFilters, page), page)
  }
  if (resource === "speed-sweep") {
    return listResponse(request, listSpeedSweeps(selectedFilters, page), page)
  }

  return response({ error: { code: "not_found", message: "API route not found" } }, 404)
}
