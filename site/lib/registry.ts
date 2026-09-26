// Everything the site shows comes from ../dist/catalog.json, built by lab/catalog.py.
import catalog from "../../dist/catalog.json";

export type Proof = {
  at: string; on: string; gpu?: string | null; gates: string; tps: number | null; prefill?: number | null;
  proxy?: string; legacy?: boolean; log?: string;
};
export type Launch = {
  image: string; entrypoint: string | null; args: string[]; env: Record<string, string>; port: number; shm: string | null;
  weights: { repo: string; revision: string; at: string; layout?: string } | { repo: string; revision: string; at: string; layout?: string }[];
  config: { at: string; text: string } | null; ctx: number; seqs: number; vision: boolean; cards?: number; backend?: string | null;
};
export type Recipe = { key: string; slug: string; model: string; weights: string; engine: string; card: string; proof: Proof[]; launch: Launch };
export type Model = { family: string; name: string; released: string; reasoning: boolean; vision: boolean; about?: string; good_for?: string; logo?: string; hf?: string };
export type Card = { id: string; name: string; vendor: string; backend: string; vram_gb: number; bandwidth_gb_s: number | null; picks: string[] };

type Raw = { models: Record<string, Model>; builds: Record<string, { format: string; size_gb: number }>; cards: Record<string, Omit<Card, "id">>; recipes: Record<string, Omit<Recipe, "key" | "slug">> };
const raw = catalog as unknown as Raw;

export const models = raw.models;
export const builds = raw.builds ?? {};
export const cards: Card[] = Object.entries(raw.cards)
  .map(([id, c]) => ({ id, ...c }))
  .sort((a, b) => vendorRank(a.vendor) - vendorRank(b.vendor) || b.vram_gb - a.vram_gb || a.name.localeCompare(b.name));
export const recipes: Recipe[] = Object.entries(raw.recipes).map(([key, r]) => ({ key, slug: key.split("/").pop()!, ...r }));

function vendorRank(v: string) { return ["nvidia", "amd", "intel"].indexOf(v); }

export const VENDOR: Record<string, string> = { nvidia: "NVIDIA", amd: "AMD", intel: "Intel" };
export const card = (id: string) => cards.find((c) => c.id === id);
export const recipe = (cardId: string, slug: string) => recipes.find((r) => r.card === cardId && r.slug === slug);
export const picks = (c: Card) => c.picks.map((k) => recipes.find((r) => r.key === k)!).filter(Boolean);
export const model = (r: Recipe): Model => models[r.model] ?? { family: "", name: r.model, released: "", reasoning: false, vision: false };
export const engineKind = (r: Recipe) => r.slug.slice(r.model.length + 1, r.slug.lastIndexOf("."));
export const weightsList = (l: Launch) => (Array.isArray(l.weights) ? l.weights : [l.weights]).filter((w) => w && w.repo);

/** What a recipe proved, in plain words. */
export function status(r: Recipe) {
  const p = r.proof[0];
  if (p.legacy) return { label: "Earlier check", tone: "dim", detail: "Passed the older check (loads and chats); a full six-check run is pending." };
  if (p.proxy) return { label: "Tested on a sibling", tone: "warm", detail: `No ${cardName(r.card)} is rentable; this ran on the ${cardName(p.proxy)}, the same chip family.` };
  return { label: "Tested on this card", tone: "ok", detail: `Passed all six checks on a real ${p.gpu ?? cardName(r.card)} on ${fmtDate(p.at)}.` };
}
export const gates = (r: Recipe) => new Set(r.proof[0].gates.split(" "));
export const short = (name: string) => name.replace(/^(NVIDIA|AMD|Intel)\s+/i, "").replace(/^GeForce\s+/i, "").replace(/\s+(Generation|GPU)\b/gi, "").replace(/Laptop$/, "Laptop").trim();
export const cardName = (id: string) => (card(id) ? short(card(id)!.name) : id);
export const ctxLabel = (n: number) => (n >= 1024 ? `${Math.round(n / 1024)}K` : `${n}`);
export const fmtDate = (d: string) => (d ? new Date(d + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }) : "");

/** The format as people say it: "EXL3 3 bpw", "GGUF Q4_K_M", "FP8". */
export function format(r: Recipe) {
  const b = builds[r.weights]?.format;
  if (b) { const m = b.match(/EXL3 · (?:SC )?(\d+(?:\.\d+)?)\s*bpw/); if (m) return `EXL3 ${Number(m[1])} bpw`; }
  const w = weightsList(r.launch)[0];
  const s = `${w?.repo ?? ""} ${w?.at ?? ""} ${r.engine} ${r.slug}`.toLowerCase();
  const bpw = s.match(/(\d(?:\.\d+)?)\s*-?bpw/) ?? s.match(/(\d)bpw/);
  if (s.includes("exl3")) return `EXL3${bpw ? ` ${Number(bpw[1])} bpw` : ""}`;
  if (s.includes("q4-k-m") || s.includes("q4_k_m")) return "GGUF Q4_K_M";
  if (s.includes("ptq1")) return "Ternary";
  if (s.includes("fp8")) return "FP8";
  if (s.includes("nvfp4")) return "NVFP4";
  return "";
}

/** Why a pick is in the top three on its card: the first is recommended, the others say what they are best at. */
export function role(r: Recipe, all: Recipe[]) {
  if (all[0]?.key === r.key) return "Recommended";
  const fastest = [...all].sort((a, b) => (b.proof[0].tps ?? 0) - (a.proof[0].tps ?? 0))[0];
  if (fastest.key === r.key) return "Fastest";
  const longest = [...all].sort((a, b) => b.launch.ctx - a.launch.ctx)[0];
  if (longest.key === r.key) return "Longest context";
  return "Alternative";
}

/** The exact steps to run a recipe by hand: weights, config, container. */
export function steps(r: Recipe) {
  const l = r.launch;
  const out: { title: string; code: string }[] = [];
  const mounts: string[] = [];
  const dl: string[] = [];
  for (const w of weightsList(l)) {
    const dir = `~/models/${w.repo.split("/")[1]}-${w.revision.slice(0, 8)}`;
    if (w.layout === "hub") { dl.push(`hf download ${w.repo} \\\n  --revision ${w.revision}`); mounts.push(`-v ~/.cache/huggingface:/root/.cache/huggingface`); }
    else { dl.push(`hf download ${w.repo} \\\n  --revision ${w.revision} \\\n  --local-dir ${dir}`); mounts.push(`-v ${dir}:${w.at}:ro`); }
  }
  if (dl.length) out.push({ title: "Download the weights", code: dl.join("\n\n") });
  if (l.config) {
    out.push({ title: "Write the server config", code: `cat > ${r.slug}.yml <<'EOF'\n${l.config.text.trimEnd()}\nEOF` });
    mounts.push(`-v $PWD/${r.slug}.yml:${l.config.at}:ro`);
  }
  const args: string[] = [];
  for (let i = 0; i < l.args.length; i++) {
    const a = l.args[i], b = l.args[i + 1];
    if (a.startsWith("-") && b !== undefined && !b.startsWith("-")) { args.push(`${a} ${shq(b)}`); i++; } else args.push(shq(a));
  }
  const run = ["docker run --rm", GPU_FLAGS[l.backend ?? "nvidia"] ?? GPU_FLAGS.nvidia, `-p 8000:${l.port}`, ...(l.shm ? [`--shm-size ${l.shm}`] : []),
    ...Object.entries(l.env).map(([k, v]) => `-e ${k}=${shq(v)}`), ...mounts, ...(l.entrypoint ? [`--entrypoint ${l.entrypoint}`] : []), l.image, ...args];
  out.push({ title: "Start the server", code: run.join(" \\\n  ") });
  return out;
}
const GPU_FLAGS: Record<string, string> = { nvidia: "--gpus all", "amd-rocm": "--device /dev/kfd --device /dev/dri", "intel-xpu": "--device /dev/dri" };
const shq = (s: string) => (/^[\w@%+=:,./-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`);

export const stats = {
  gpus: cards.length,
  recipes: recipes.length,
  tested: recipes.filter((r) => !r.proof[0].legacy && !r.proof[0].proxy).length,
  models: new Set(recipes.map((r) => r.model)).size,
};
