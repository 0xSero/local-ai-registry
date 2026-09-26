import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import RecipeCard, { ENGINE } from "@/components/RecipeCard";
import { cards, card, picks, more, model, format, engineKind, ctxLabel, status, VENDOR, short, setupName, Setup } from "@/lib/registry";

type P = { params: Promise<{ card: string }> };
export const generateStaticParams = () => cards.map((c) => ({ card: c.id }));

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const c = card((await params).card);
  if (!c) return {};
  const top = picks(c)[0];
  const name = short(c.name);
  return {
    title: `${name} ${c.vram_gb} GB`,
    description: top ? `Run ${model(top).name} on the ${name}: ${Math.round(top.proof[0].tps ?? 0)} tok/s, tested on the card. The top ${picks(c).length} recipes${c.setups.length > 1 ? ` for one card, more for ${c.setups.slice(1).map((s) => setupName(name, s.cards, s.machines)).join(", ")}` : ""}, and the exact commands.` : undefined,
  };
}

export default async function Gpu({ params }: P) {
  const c = card((await params).card);
  if (!c) notFound();
  const many = c.setups.length > 1;
  return (
    <main>
      <Link href="/#gpus" className="back">‹ all GPUs</Link>
      <h1 className="title">{short(c.name)}</h1>
      <div className="dim">{VENDOR[c.vendor]} · {c.vram_gb} GB{c.bandwidth_gb_s ? ` · ${c.bandwidth_gb_s} GB/s` : ""}</div>
      {many && (
        <nav className="dim" style={{ marginTop: 14 }}>
          {c.setups.map((s, i) => <span key={i}>{i ? " · " : ""}<a href={`#${anchor(s)}`}>{setupName(short(c.name), s.cards, s.machines)}</a></span>)}
        </nav>
      )}
      {c.setups.map((s) => <SetupSection key={anchor(s)} s={s} name={short(c.name)} many={many} />)}
    </main>
  );
}

const anchor = (s: Setup) => (s.machines > 1 ? `${s.machines}-machines` : `${s.cards}-cards`);

/** One way to run the card: its top picks, then every other recipe for it. */
function SetupSection({ s, name, many }: { s: Setup; name: string; many: boolean }) {
  const ps = picks(s), ms = more(s);
  const top = ps.length === 1 ? "The recipe" : `Top ${ps.length} recipes`;
  return (
    <div id={anchor(s)}>
      {many && <h2 className="setup">{setupName(name, s.cards, s.machines)} <span className="dim">· {s.vram_gb} GB</span></h2>}
      <section>
        <span className="label">{top}</span>
        <div className={`grid ${ps.length >= 3 ? "cols-3" : ps.length === 2 ? "cols-2" : ""}`} style={ps.length === 1 ? { maxWidth: 480 } : {}}>
          {ps.map((r) => <RecipeCard key={r.key} r={r} all={ps} />)}
        </div>
      </section>
      {ms.length > 0 && (
        <section>
          <span className="label">More recipes ({ms.length})</span>
          <div style={{ overflowX: "auto" }}><table className="t">
            <thead><tr><th>Model</th><th>Format</th><th>Engine</th><th>Context</th><th>Decode</th><th>Status</th></tr></thead>
            <tbody>
              {ms.map((r) => (
                <tr key={r.key}>
                  <td><Link href={`/gpu/${r.card}/${r.slug}`}>{model(r).name} ›</Link></td>
                  <td>{format(r) || "–"}</td><td>{ENGINE[engineKind(r)] ?? engineKind(r)}</td><td>{ctxLabel(r.launch.ctx)}</td>
                  <td>{r.proof[0].tps ? `${Math.round(r.proof[0].tps)} tok/s` : "–"}</td>
                  <td className="dim">{status(r).label}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </section>
      )}
    </div>
  );
}
