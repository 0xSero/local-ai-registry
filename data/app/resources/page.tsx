import type { Metadata } from "next"
import Link from "next/link"

import { RESOURCE_CATEGORIES, resources, type ResourceCategory } from "./data"

export const metadata: Metadata = {
  title: "Local AI resources · Local AI Registry",
  description: "A source-backed directory of tools, runtimes, benchmarks, learning material, and communities for running AI locally.",
}

type CategoryDetails = Readonly<{
  label: string
  description: string
}>

const CATEGORY_DETAILS: Record<ResourceCategory, CategoryDetails> = {
  "desktop-app": {
    label: "Desktop apps",
    description: "Installable applications for downloading models, chatting locally, and exposing local endpoints.",
  },
  "deployment-runtime": {
    label: "Deployment runtimes",
    description: "Inference engines, model servers, and portable runtimes for CPUs, GPUs, browsers, and edge devices.",
  },
  "interface-tool": {
    label: "Interfaces & tools",
    description: "Self-hosted workspaces and web interfaces for using local models, documents, agents, and tools.",
  },
  orchestration: {
    label: "Orchestration",
    description: "Control planes, proxies, and distributed-serving systems for operating one or many model servers.",
  },
  "training-quantization": {
    label: "Training & quantization",
    description: "Libraries for adapting models, reducing memory use, and preparing efficient local artifacts.",
  },
  benchmark: {
    label: "Benchmarking",
    description: "Reproducible harnesses and public leaderboards for measuring inference performance and model or agent quality.",
  },
  "model-hub": {
    label: "Models & hubs",
    description: "Primary collections and platforms for finding, versioning, and distributing models and datasets.",
  },
  education: {
    label: "Education",
    description: "Open learning material for understanding, adapting, and deploying language models.",
  },
  community: {
    label: "Community",
    description: "Community-maintained maps of the local-AI ecosystem and places to discover related projects.",
  },
}

function sourceLabel(sourceUrl: string): string {
  const source = new URL(sourceUrl)
  const path = source.pathname === "/" ? "" : source.pathname.replace(/\/$/, "")
  return `${source.hostname.replace(/^www\./, "")}${path}`
}

export default function ResourcesPage() {
  return (
    <main className="detail-page directory-page" id="top">
      <nav aria-label="Breadcrumb" className="breadcrumbs">
        <Link href="/">Registry</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">Resources</span>
      </nav>

      <header className="topic-heading directory-heading">
        <div>
          <span className="mono-label">DIRECTORY / SOURCE-BACKED</span>
          <h1>Local AI resources</h1>
          <p className="topic-description">
            A curated field guide to running, adapting, measuring, and learning about AI on hardware you control.
            Every entry links to its canonical home, code repository, and primary sources.
          </p>
        </div>
        <span className="topic-total">{resources.length.toLocaleString("en-US")} resources</span>
      </header>

      <nav aria-label="Resource categories" className="directory-category-nav">
        {RESOURCE_CATEGORIES.map((category) => {
          const details = CATEGORY_DETAILS[category]
          const count = resources.filter((resource) => resource.category === category).length
          return (
            <a href={`#${category}`} key={category}>
              <span>{details.label}</span>
              <span aria-label={`${count} resources`}>{count}</span>
            </a>
          )
        })}
      </nav>

      <div className="directory-groups">
        {RESOURCE_CATEGORIES.map((category) => {
          const details = CATEGORY_DETAILS[category]
          const categoryResources = resources.filter((resource) => resource.category === category)

          return (
            <section aria-labelledby={`${category}-heading`} className="directory-group" id={category} key={category}>
              <header className="section-heading directory-group-heading">
                <div>
                  <span className="mono-label">{categoryResources.length.toString().padStart(2, "0")} ENTRIES</span>
                  <h2 id={`${category}-heading`}>{details.label}</h2>
                  <p>{details.description}</p>
                </div>
                <a href="#top" aria-label="Back to the top of the resources directory">Back to top</a>
              </header>

              <div className="directory-list">
                {categoryResources.map((resource) => (
                  <article aria-labelledby={`${resource.id}-name`} className="directory-card" id={resource.id} key={resource.id}>
                    <div className="directory-card-main">
                      <header>
                        <span className="mono-label">{resource.owner}</span>
                        <h3 id={`${resource.id}-name`}>
                          <a href={resource.url} rel="noopener noreferrer" target="_blank">{resource.name}</a>
                        </h3>
                      </header>
                      <p>{resource.description}</p>
                      <dl className="directory-facts">
                        <div>
                          <dt>Access</dt>
                          <dd>{resource.access}</dd>
                        </div>
                        <div>
                          <dt>Maintainer</dt>
                          <dd>{resource.owner}</dd>
                        </div>
                      </dl>
                      <div aria-label={`${resource.name} links`} className="directory-actions">
                        <a href={resource.url} rel="noopener noreferrer" target="_blank">Project site <span aria-hidden="true">↗</span></a>
                        <a href={resource.repositoryUrl} rel="noopener noreferrer" target="_blank">Repository <span aria-hidden="true">↗</span></a>
                      </div>
                    </div>

                    <aside aria-label={`Sources for ${resource.name}`} className="directory-sources">
                      <span className="mono-label">PRIMARY SOURCES</span>
                      <ol>
                        {resource.sourceUrls.map((sourceUrl, index) => (
                          <li key={sourceUrl}>
                            <a href={sourceUrl} rel="noopener noreferrer" target="_blank">
                              <span aria-hidden="true">[{index + 1}]</span> {sourceLabel(sourceUrl)}
                            </a>
                          </li>
                        ))}
                      </ol>
                    </aside>
                  </article>
                ))}
              </div>
            </section>
          )
        })}
      </div>
    </main>
  )
}
