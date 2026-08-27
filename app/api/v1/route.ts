import { NextResponse } from "next/server"

import { collectionCounts } from "@/lib/registry"

const routes = {
  compatibility: "/api/v1/compatibility",
  facets: "/api/v1/facets",
  hardware: "/api/v1/hardware",
  index: "/api/v1/index",
  model_instances: "/api/v1/model-instances",
  models: "/api/v1/models",
  recipes: "/api/v1/recipes",
  speed_sweeps: "/api/v1/speed-sweeps",
}

export function GET(): NextResponse {
  return NextResponse.json(
    {
      data: {
        name: "Local AI Registry API",
        read_only: true,
        routes,
        version: "v1",
      },
      meta: { counts: collectionCounts(), source: "registry" },
    },
    {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
      },
    },
  )
}
