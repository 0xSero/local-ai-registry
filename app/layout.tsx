import type { Metadata } from "next"
import Link from "next/link"
import type { ReactNode } from "react"

import "./globals.css"

export const metadata: Metadata = {
  title: "Local AI Registry",
  description: "Search local model artifacts, hardware compatibility, launch recipes, and measured speed.",
}

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <Link className="wordmark" href="/">
            <span className="wordmark-mark" aria-hidden="true">LAI</span>
            <span>Local AI Registry</span>
          </Link>
          <nav aria-label="Primary navigation">
            <Link href="/api/v1">API</Link>
            <a href="https://github.com/0xSero/local-ai-registry#read-only-api">Docs</a>
          </nav>
        </header>
        {children}
        <footer>
          <p>Registry records are shown as written. Unknown stays unknown.</p>
          <a href="/api/v1/index">Normalized registry index</a>
        </footer>
      </body>
    </html>
  )
}
