import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import PostHog from "@/components/PostHog";
import { stats } from "@/lib/registry";
import "./globals.css";

const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", weight: ["400", "500"] });
const SITE = "https://local.sybilsolutions.ai";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: "Local AI: the model to run on your GPU", template: "%s · Local AI" },
  description: `Tested recipes for ${stats.gpus} GPUs: which model to run, how fast it goes, and the exact command. Tested recipes passed six checks on the card.`,
  openGraph: { siteName: "Local AI", type: "website" },
  twitter: { card: "summary_large_image" },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={mono.variable}>
      <body>
        <div className="wrap">
          <header className="top">
            <Link href="/" className="brand"><b>LOCAL AI</b><span>registry</span></Link>
            <nav className="nav">
              <Link href="/#gpus">GPUs</Link>
              <Link href="/models">Models</Link>
              <Link href="/docs">How it works</Link>
              <Link href="/docs#api">API</Link>
              <a href="https://github.com/0xSero/local-ai-registry">GitHub</a>
            </nav>
          </header>
          {children}
          <footer className="foot">
            <span>Every recipe here is the output of a run that passed six checks on the card.</span>
            <span><a href="https://github.com/0xSero/local-ai-registry">github.com/0xSero/local-ai-registry</a> · <a href="https://github.com/0xSero/omarchy-local-ai">Omarchy Local AI</a></span>
          </footer>
        </div>
        <PostHog />
        {/* Cloudflare Web Analytics: page views and Core Web Vitals, no cookies */}
        <script defer src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon='{"token": "9e30875864824920804a1f95dd926025"}' />
      </body>
    </html>
  );
}
