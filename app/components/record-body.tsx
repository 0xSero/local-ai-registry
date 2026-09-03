import { ConfigurationCard, configurationFromRecipe } from "@/app/components/configuration-card"
import { CopyActions } from "@/app/components/copy-actions"
import { RecordSheet } from "@/app/components/record-sheet"
import { HardwareMarket } from "@/app/components/hardware-market"
import { HuggingFaceCard } from "@/app/components/huggingface-card"
import { LaunchCommand } from "@/app/components/launch-command"
import { ModelScores } from "@/app/components/model-scores"
import { RecordEvidence } from "@/app/components/record-evidence"
import { RecordFacts } from "@/app/components/record-facts"
import { RelatedRecords } from "@/app/components/related-records"
import {
  copyItems,
  displayRecord,
  huggingFaceIdentity,
  recordDescription,
  recordFacts,
  relatedGroups,
  recipeIsLaunchable,
} from "@/app/lib/record-view"

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
  const description = recordDescription(record)
  const facts = recordFacts(collection, record)
  const groups = relatedGroups(record)
  const copies = copyItems(collection, record)
  const tree = displayRecord(record)
  return (
    <>
      {description && <p className="record-lede">{description}</p>}
      <CopyActions items={copies} />
      <RecordFacts facts={facts} />
      <HuggingFaceCard identity={huggingFaceIdentity(record)} />
      {config && (
        <>
          <p className="trust-note">
            {recipeIsLaunchable(record)
              ? "Validated: pinned artifact, pinned runtime, and accepted evidence. This is a launch contract."
              : "Candidate: useful compatibility or speed evidence. The registry does not offer Run until promotion requirements are met."}
          </p>
          <ConfigurationCard config={config} />
          <LaunchCommand recipe={record as never} />
        </>
      )}
      <RecordEvidence collection={collection} record={record} />
      {collection === "hardware" && typeof record.id === "string" && <HardwareMarket hardwareId={record.id} />}
      {collection === "models" && typeof record.id === "string" && <ModelScores modelId={record.id} />}
      <RelatedRecords groups={groups} />
      {variant === "page" ? (
        <section className="record-sheet">
          <div className="record-sheet-heading">
            <h2>Remaining fields</h2>
            <p>Identity, launch, related records, and measured speed are shown above. This is the rest of the normalized record.</p>
          </div>
          <RecordSheet record={tree} />
        </section>
      ) : (
        <RecordSheet record={tree} />
      )}
    </>
  )
}
