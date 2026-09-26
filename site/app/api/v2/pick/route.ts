import { picks } from "@/lib/registry";
import { json, detect } from "@/lib/api";
export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  const c = detect(q.get("gpu") ?? "", Number(q.get("vram")) || undefined);
  if (!c) return json({ error: "no recipe for that GPU", gpu: q.get("gpu") }, 404);
  return json({ gpu: { id: c.id, name: c.name, vram_gb: c.vram_gb }, recipe: picks(c)[0], alternatives: picks(c).slice(1) });
}
