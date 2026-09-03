import type { Metadata } from "next"
import Link from "next/link"

import { organisations } from "./data"

export const metadata: Metadata = {
  title: "Local AI organisations · Local AI Registry",
  description: "A source-backed directory of model labs, research institutes, hardware teams, and benchmark publishers shaping local and open AI.",
}

const REGION_ORDER = [
  "Africa",
  "East Asia",
  "Southeast Asia",
  "Middle East",
  "Europe",
  "North America",
] as const


function regionId(region: string): string {
  return `region-${region.toLowerCase().replaceAll(" ", "-")}`
}

function sourceLabel(url: string): string {
  const source = new URL(url)
  const pathname = source.pathname === "/" ? "" : source.pathname.replace(/\/$/, "")

  return `${source.hostname.replace(/^www\./, "")}${pathname}`
}

const regionGroups = REGION_ORDER.map((region) => ({
  region,
  records: organisations.filter((organisation) => organisation.location.endsWith(`· ${region}`)),
}))

export default function OrganisationsPage() {
  return (
    <main className="registry-main directory-page" id="top">
      <nav aria-label="Breadcrumb" className="breadcrumbs">
        <Link href="/">Registry</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">Organisations</span>
      </nav>
      <header className="topic-heading directory-heading">
        <div>
          <span className="mono-label">DIRECTORY / SOURCE-BACKED</span>
          <h1>Organisations</h1>
          <p className="topic-description">
            Model labs, research institutes, hardware teams, and benchmark publishers shaping local and open AI.
          </p>
        </div>
        <span className="topic-total">{organisations.length} organisations</span>
      </header>

      <nav aria-label="Organisation regions" className="topic-tabs directory-region-nav">
        {regionGroups.map(({ region, records }) => (
          <a href={`#${regionId(region)}`} key={region}>
            {region} <span aria-label={`${records.length} organisations`}>({records.length})</span>
          </a>
        ))}
      </nav>

      <div className="directory-regions">
        {regionGroups.map(({ region, records }) => {
          const headingId = `${regionId(region)}-heading`

          return (
            <section aria-labelledby={headingId} className="directory-region" id={regionId(region)} key={region}>
              <header className="section-heading directory-region-heading">
                <div>
                  <span className="mono-label">REGION</span>
                  <h2 id={headingId}>{region}</h2>
                </div>
                <span className="topic-total">
                  {records.length} {records.length === 1 ? "organisation" : "organisations"}
                </span>
              </header>

              <ol className="browser-list directory-list">
                {records.map((organisation) => {
                  const descriptionId = `${organisation.id}-description`
                  const sourcesId = `${organisation.id}-sources`

                  return (
                    <li className="directory-item" key={organisation.id}>
                      <article aria-describedby={descriptionId} className="browser-row directory-card" id={`organisation-${organisation.id}`}>
                        <header className="directory-card-heading">
                          <div>
                            <span className="mono-label">{organisation.entityType}</span>
                            <h3>{organisation.name}</h3>
                          </div>
                          <span className="directory-location">{organisation.location}</span>
                        </header>

                        <p className="directory-description" id={descriptionId}>{organisation.description}</p>

                        <nav aria-label={`${organisation.name} profiles`} className="detail-actions directory-profile-links">
                          <a href={organisation.huggingFaceUrl} rel="noopener noreferrer" target="_blank">
                            Hugging Face
                          </a>
                          <a href={organisation.websiteUrl} rel="noopener noreferrer" target="_blank">
                            Website
                          </a>
                          <a href={organisation.githubUrl} rel="noopener noreferrer" target="_blank">
                            GitHub
                          </a>
                        </nav>

                        <footer className="directory-sources">
                          <h4 className="mono-label" id={sourcesId}>Sources</h4>
                          <ol aria-labelledby={sourcesId} className="directory-source-list">
                            {organisation.sourceUrls.map((url) => (
                              <li key={url}>
                                <a href={url} rel="noopener noreferrer" target="_blank">
                                  {sourceLabel(url)}
                                </a>
                              </li>
                            ))}
                          </ol>
                        </footer>
                      </article>
                    </li>
                  )
                })}
              </ol>
            </section>
          )
        })}
      </div>
    </main>
  )
}
