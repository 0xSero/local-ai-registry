// Cloudflare Pages Function: GET /api/v2/pick?gpu=<name the driver reports>&vram=<GB> -> the recommended recipe and the others.
import catalog from "../../../../dist/catalog.json";
import { detect } from "../../../../sdk/js/index.js";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body, null, 2), { status, headers: { "content-type": "application/json", "access-control-allow-origin": "*", "cache-control": "public, max-age=300" } });

export const onRequestGet = ({ request }: { request: Request }) => {
  const q = new URL(request.url).searchParams;
  const cat = catalog as any;
  const id = detect(cat, q.get("gpu") ?? "", Number(q.get("vram")) || undefined);
  if (!id) return json({ error: "no recipe for that GPU", gpu: q.get("gpu") }, 404);
  const c = cat.cards[id];
  const [first, ...rest] = c.picks.map((k: string) => ({ key: k, ...cat.recipes[k] }));
  return json({ gpu: { id, name: c.name, vram_gb: c.vram_gb }, recipe: first, alternatives: rest });
};
