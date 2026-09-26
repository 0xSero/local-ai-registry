// Cloudflare Pages Function: GET /api/v2/pick?gpu=<name the driver reports>&vram=<GB> -> the recommended recipe.
import catalog from "../../../../dist/catalog.json";

type Card = { name: string; vram_gb: number; picks: string[] };
const cards = (catalog as any).cards as Record<string, Card>;
const recipes = (catalog as any).recipes as Record<string, unknown>;
const norm = (s: string) => s.toLowerCase().replace(/geforce|nvidia|amd|radeon|intel|graphics|[^a-z0-9]/g, "");
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body, null, 2), { status, headers: { "content-type": "application/json", "access-control-allow-origin": "*", "cache-control": "public, max-age=300" } });

export const onRequestGet = ({ request }: { request: Request }) => {
  const q = new URL(request.url).searchParams;
  const gpu = norm(q.get("gpu") ?? ""), vram = Number(q.get("vram")) || 0;
  const hit = Object.entries(cards)
    .filter(([id, c]) => (gpu.includes(norm(c.name)) || norm(id) === gpu) && (!vram || Math.abs(c.vram_gb - vram) <= 2))
    .sort(([, a], [, b]) => norm(b.name).length - norm(a.name).length)[0];
  if (!hit) return json({ error: "no recipe for that GPU", gpu: q.get("gpu") }, 404);
  const [id, c] = hit;
  return json({ gpu: { id, name: c.name, vram_gb: c.vram_gb }, recipe: recipes[c.picks[0]], alternatives: c.picks.slice(1).map((k) => recipes[k]) });
};
