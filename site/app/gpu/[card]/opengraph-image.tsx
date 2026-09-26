import { og, size } from "@/lib/og";
import { cards, card, picks, model, format, ctxLabel, short } from "@/lib/registry";
export { size };
export const contentType = "image/png";
export const generateStaticParams = () => cards.map((c) => ({ card: c.id }));
export default async function Image({ params }: { params: Promise<{ card: string }> }) {
  const c = card((await params).card)!;
  const top = picks(c)[0];
  const m = model(top);
  return og({ kicker: `${c.vram_gb} GB`, title: short(c.name), sub: `Runs ${m.name} · ${format(top)} · ${ctxLabel(top.launch.ctx)} context`, logo: m.family === "qwen",
    stats: [[`${Math.round(top.proof[0].tps ?? 0)}`, "tok/s decode"], [top.proof[0].prefill ? `${Math.round(top.proof[0].prefill).toLocaleString("en-US")}` : "–", "tok/s prefill"], [`${picks(c).length}`, picks(c).length === 1 ? "recipe" : "recipes"]] });
}
