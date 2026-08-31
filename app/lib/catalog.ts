export type Topic = "recipes" | "hardware" | "models" | "prices" | "benchmark"

export type TopicSpec = {
  countKey: string | null
  description: string
  key: Topic
  label: string
}

export const TOPICS: TopicSpec[] = [
  { key: "recipes", label: "Recipes", countKey: "recipe", description: "One artifact × hardware × engine unit. Validated rows are launch-safe; measured speed sweeps attach to each recipe as evidence." },
  { key: "hardware", label: "Hardware", countKey: "hardware", description: "Accelerator specifications connected to compatible models, recipes, and regional prices." },
  { key: "models", label: "Models", countKey: "model", description: "Canonical models connected to artifacts, supported hardware, and recipes." },
  { key: "prices", label: "Prices", countKey: "price", description: "Fresh regional listing observations in native currency. Candidate matches remain inspectable." },
  { key: "benchmark", label: "Leaderboards", countKey: "benchmark", description: "Scraped public quality scores from GitHub Pages leaderboards such as Terminal-Bench 2.1. These are not local speed measurements." },
]

const COLLECTION_LABELS: Record<string, string> = {
  hardware: "Hardware",
  "model-instances": "Model instance",
  models: "Model",
  prices: "Regional market price",
  recipes: "Recipe",
  benchmark: "Leaderboard",
  "speed-sweep": "Speed sweep",
}

const COLLECTION_TOPICS: Record<string, Topic> = {
  hardware: "hardware",
  "model-instances": "recipes",
  models: "models",
  prices: "prices",
  recipes: "recipes",
  benchmark: "benchmark",
  "speed-sweep": "recipes",
}

export const TOPIC_FILTERS: Record<Topic, string[]> = {
  hardware: ["vendor", "backend", "min_vram_gb", "priced_only", "has_recipes"],
  models: ["family", "architecture"],
  prices: ["region", "category", "condition", "retailer", "in_stock"],
  recipes: ["by", "hardware_id", "model_id", "validation", "engine", "runtime", "evidence"],
  benchmark: ["category"],
}

export function isTopic(value: string): value is Topic {
  return TOPICS.some((topic) => topic.key === value)
}

export function topicSpec(value: string): TopicSpec | undefined {
  return TOPICS.find((topic) => topic.key === value)
}

export function isCollection(value: string): boolean {
  return value in COLLECTION_LABELS
}

export function collectionLabel(collection: string): string | undefined {
  return COLLECTION_LABELS[collection]
}

export function collectionTopic(collection: string): Topic | undefined {
  return COLLECTION_TOPICS[collection]
}

export function topicHref(key: Topic, query = ""): string {
  const selected = new URLSearchParams()
  selected.set("topic", key)
  if (query) selected.set("q", query)
  return `/?${selected.toString()}`
}

export function collectionHref(collection: string): string {
  const topic = collectionTopic(collection)
  return topic ? topicHref(topic) : "/"
}

export function recordHref(collection: string, id: string): string {
  return `/${collection}/${id}`
}

export function hrefWithRecord(state: URLSearchParams, id: string): string {
  const selected = new URLSearchParams(state)
  selected.set("record", id)
  return `/?${selected.toString()}`
}

export function hrefWithFilter(state: URLSearchParams, name: string, value: string): string {
  const selected = new URLSearchParams(state)
  selected.delete("record")
  selected.delete("offset")
  selected.set(name, value)
  return `/?${selected.toString()}`
}

export function stateHref(state: URLSearchParams): string {
  const query = state.toString()
  return query ? `/?${query}` : "/"
}
