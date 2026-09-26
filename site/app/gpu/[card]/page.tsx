import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import RecipeCard from "@/components/RecipeCard";
import { cards, card, picks, model, VENDOR, short } from "@/lib/registry";

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
    </main>
  );
}
