import { og, size } from "@/lib/og";
import { cards, card, picks, lead, model, format, ctxLabel, short, setupTag } from "@/lib/registry";
export { size };
export const contentType = "image/png";
export const dynamic = "force-static";
export const generateStaticParams = () => cards.map((c) => ({ card: c.id }));
export default async function Image({ params }: { params: Promise<{ card: string }> }) {
  const c = card((await params).card)!;
  const s = lead(c);
  const top = picks(s)[0];
  const m = model(top);
  const others = c.setups.filter((x) => x.picks !== s.picks);
  return og({ kicker: `${c.picks.length ? `${c.vram_gb} GB` : `${c.setups[0].label} · ${c.setups[0].vram_gb} GB`}${others.length ? ` · also ${others.map(setupTag).join(", ")}` : ""}`, title: short(c.name), sub: `Runs ${m.name} · ${format(top)} · ${ctxLabel(top.launch.ctx)} context`, logo: m.family === "qwen",
    stats: [[`${Math.round(top.proof[0].tps ?? 0)}`, "tok/s decode"], [top.proof[0].prefill ? `${Math.round(top.proof[0].prefill).toLocaleString("en-US")}` : "–", "tok/s prefill"], [`${picks(s).length}`, picks(s).length === 1 ? "recipe" : "recipes"]] });
}
