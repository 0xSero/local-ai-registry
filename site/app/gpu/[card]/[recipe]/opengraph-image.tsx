import { og, size } from "@/lib/og";
import { recipes, recipe, model, format, ctxLabel, cardName, status } from "@/lib/registry";
export { size };
export const contentType = "image/png";
export const generateStaticParams = () => recipes.map((r) => ({ card: r.card, recipe: r.slug }));
export default async function Image({ params }: { params: Promise<{ card: string; recipe: string }> }) {
  const { card: c, recipe: s } = await params;
  const r = recipe(c, s)!;
  const m = model(r);
  return og({ kicker: cardName(c), title: m.name, sub: `${format(r)} · ${ctxLabel(r.launch.ctx)} context · ${status(r).label.toLowerCase()}`, logo: m.family === "qwen",
    stats: [[`${Math.round(r.proof[0].tps ?? 0)}`, "tok/s decode"], [r.proof[0].prefill ? `${Math.round(r.proof[0].prefill).toLocaleString("en-US")}` : "–", "tok/s prefill"], [ctxLabel(r.launch.ctx), "context"]] });
}
