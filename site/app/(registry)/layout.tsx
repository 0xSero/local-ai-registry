import Link from "next/link";

export default function RegistryLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="wrap">
      <header className="top">
        <Link href="/" className="brand"><b>LOCAL AI</b><span>registry</span></Link>
        <nav className="nav">
          <Link href="/hardware/#gpus">Hardware</Link>
          <Link href="/models/">Models</Link>
          <Link href="/docs/">How it works</Link>
          <Link href="/docs/#api">API</Link>
          <a href="https://github.com/sybil-solutions/local-ai-registry">GitHub</a>
        </nav>
      </header>
      {children}
      <footer className="foot">
        <span>Tested recipes passed six checks on the hardware. Community results are marked as reported.</span>
        <span><a href="https://github.com/sybil-solutions/local-ai-registry">github.com/sybil-solutions/local-ai-registry</a> · <a href="https://github.com/sybil-solutions/omarchy-local-ai">Omarchy Local AI</a></span>
      </footer>
    </div>
  );
}
