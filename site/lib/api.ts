import { cards, picks, card, type Card } from "./registry";

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body, null, 2), { status, headers: { "content-type": "application/json", "access-control-allow-origin": "*", "cache-control": "public, max-age=300" } });

export const gpu = (c: Card) => ({ id: c.id, name: c.name, vendor: c.vendor, backend: c.backend, vram_gb: c.vram_gb, recipes: picks(c) });

const norm = (s: string) => s.toLowerCase().replace(/geforce|nvidia|amd|radeon|intel|graphics|[^a-z0-9]/g, "");
/** The card a detected GPU name (and its memory) is: the longest name that matches, the right memory size. */
export function detect(name: string, vram?: number) {
  const n = norm(name);
  const hits = cards.filter((c) => n.includes(norm(c.name)) && (!vram || Math.abs(c.vram_gb - vram) <= 2));
  return hits.sort((a, b) => norm(b.name).length - norm(a.name).length)[0] ?? (card(name) ?? null);
}
