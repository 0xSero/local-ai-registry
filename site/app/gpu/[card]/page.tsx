import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import RecipeCard, { ENGINE } from "@/components/RecipeCard";
import { cards, card, picks, more, model, format, engineKind, ctxLabel, status, VENDOR, short } from "@/lib/registry";

type P = { params: Promise<{ card: string }> };
export const generateStaticParams = () => cards.map((c) => ({ card: c.id }));

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const c = card((await params).card);
  if (!c) return {};
  const top = picks(c)[0];
  const name = short(c.name);
  return {
    title: `${name} ${c.vram_gb} GB`,
    description: top ? `Run ${model(top).name} on the ${name}: ${Math.round(top.proof[0].tps ?? 0)} tok/s, tested on the card. The top ${picks(c).length} recipes and the exact commands.` : undefined,
  };
}

export default async function Gpu({ params }: P) {
  const c = card((await params).card);
  if (!c) notFound();
  const ps = picks(c);
  return (
    <main>
      <Link href="/#gpus" className="back">‹ all GPUs</Link>
      <h1 className="title">{short(c.name)}</h1>
      <div className="dim">{VENDOR[c.vendor]} · {c.vram_gb} GB{c.bandwidth_gb_s ? ` · ${c.bandwidth_gb_s} GB/s` : ""}</div>
      <section>
        <span className="label">{ps.length === 1 ? "The recipe" : `Top ${ps.length} recipes`}</span>
        <div className={`grid ${ps.length >= 3 ? "cols-3" : ps.length === 2 ? "cols-2" : ""}`} style={ps.length === 1 ? { maxWidth: 480 } : {}}>
          {ps.map((r) => <RecipeCard key={r.key} r={r} all={ps} />)}
        </div>
      </section>
      {more(c).length > 0 && (
        <section>
          <span className="label">More recipes ({more(c).length})</span>
          <div style={{ overflowX: "auto" }}><table className="t">
            <thead><tr><th>Model</th><th>Format</th><th>Engine</th><th>Context</th><th>Machines</th><th>Decode</th><th>Status</th></tr></thead>
            <tbody>
              {more(c).map((r) => (
                <tr key={r.key}>
                  <td><Link href={`/gpu/${r.card}/${r.slug}`}>{model(r).name} ›</Link></td>
                  <td>{format(r) || "–"}</td><td>{ENGINE[engineKind(r)] ?? engineKind(r)}</td><td>{ctxLabel(r.launch.ctx)}</td>
                  <td>{r.launch.machines ?? 1}</td><td>{r.proof[0].tps ? `${Math.round(r.proof[0].tps)} tok/s` : "–"}</td>
                  <td className="dim">{status(r).label}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </section>
      )}
    </main>
  );
}
