import { ConfigurationCard, configurationFromRecipe } from "@/app/components/configuration-card"
import { DataTree } from "@/app/components/data-tree"
import { HuggingFaceCard } from "@/app/components/huggingface-card"
import { RelatedRecords } from "@/app/components/related-records"
import { displayRecord, huggingFaceIdentity, relatedGroups, recipeIsLaunchable } from "@/app/lib/record-view"

export function RecordBody({
  collection,
  record,
  variant = "page",
}: {
  collection: string
  record: Record<string, unknown>
  variant?: "overlay" | "page"
}) {
  const recipe = collection === "recipes"
  const config = recipe ? configurationFromRecipe(record) : null
  const groups = relatedGroups(record)
  const tree = displayRecord(record)
  return (
    <>
      <HuggingFaceCard identity={huggingFaceIdentity(record)} />
      {config && (
        <>
          <p className="trust-note">
            {recipeIsLaunchable(record)
              ? "Validated: pinned artifact, pinned runtime, and accepted evidence. This is a launch contract."
              : "Candidate: useful compatibility or speed evidence. The registry does not offer Run until promotion requirements are met."}
          </p>
          <ConfigurationCard config={config} />
        </>
      )}
      <RelatedRecords groups={groups} />
      {variant === "page" ? (
        <section className="record-sheet">
          <div className="record-sheet-heading">
            <h2>Complete normalized record</h2>
            <p>Launch contracts, Hub identity, and related records are shown above. Remaining fields stay in page flow.</p>
          </div>
          <DataTree value={tree} />
        </section>
      ) : (
        <DataTree value={tree} />
      )}
    </>
  )
}
