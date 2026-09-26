// Local AI registry, JavaScript. No dependencies; works in Node 18+, Deno, Bun and browsers.
//   const r = await pick({ gpu: "NVIDIA GeForce RTX 4090", vram: 24 });
//   console.log(command(r));
export const URL = "https://local.sybilsolutions.ai/api/v2/catalog.json";

let cached;
/** The whole catalog: cards (with their picks), recipes (with rendered launches), models. */
export async function catalog(url = URL) {
  return (cached ??= fetch(url).then((r) => { if (!r.ok) throw new Error(`catalog: ${r.status}`); return r.json(); }));
}

const norm = (s) => s.toLowerCase().replace(/\((r|tm)\)/g, "").replace(/geforce|nvidia|amd|radeon|intel|graphics|[^a-z0-9]/g, "");
const names = (id, c) => [norm(c.name), norm(id), ...(c.match?.names ?? [])];
/** The card id for a GPU as the driver names it (nvidia-smi, amd-smi, lspci) and its memory in GB. */
export function detect(cat, gpu, vram) {
  const n = norm(gpu);
  const hits = Object.entries(cat.cards).filter(([id, c]) => names(id, c).some((x) => x && n.includes(x)) && (!vram || Math.abs(c.vram_gb - vram) <= 2));
  const best = ([id, c]) => Math.max(...names(id, c).filter((x) => n.includes(x)).map((x) => x.length));
  return hits.sort((a, b) => best(b) - best(a))[0]?.[0] ?? null;
}

/** The recommended recipe for a GPU (or null); `all: true` returns the card's top three. */
export async function pick({ gpu, vram, all = false }, cat) {
  cat ??= await catalog();
  const id = detect(cat, gpu, vram);
  if (!id) return all ? [] : null;
  const rs = cat.cards[id].picks.map((k) => ({ key: k, ...cat.recipes[k] }));
  return all ? rs : rs[0];
}

const GPU = { nvidia: "--gpus all", "amd-rocm": "--device /dev/kfd --device /dev/dri", "intel-xpu": "--device /dev/dri" };
const q = (s) => (/^[\w@%+=:,./-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`);
const weights = (l) => (Array.isArray(l.weights) ? l.weights : [l.weights]).filter((w) => w && w.repo);

/** The steps to run a recipe by hand: download the weights, write the config, start the container. */
export function steps(r) {
  const l = r.launch, name = (r.key ?? r.model).split("/").pop();
  const out = l.setup ? [{ title: "Set up first", code: `# ${l.setup}\n# Full instructions: ${l.source}` }] : [];
  if (l.kind === "host") {
    const env = Object.entries(l.env ?? {}).map(([k, v]) => `${k}=${q(v)}`);
    return [...out, { title: "Install", code: install(l.install) }, { title: "Start the server", code: [...env, ...l.command.map(q)].join(" ") }];
  }
  let image = l.image;
  if (l.build) {  // an image built from the source's Dockerfile at a pinned commit
    image = `local-ai/${name}`;
    const files = (l.build.dockerfile ?? "Dockerfile").split(" + ");
    out.push({ title: "Build the image", code: [install(`https://github.com/${l.build.repo}/tree/${l.build.commit}`), ...files.map((d) => `docker build -t ${image} -f ${d} .`)].join("\n") });
  }
  const mounts = [], dl = [];
  for (const w of weights(l)) {
    const dir = `~/models/${w.repo.split("/")[1]}-${w.revision.slice(0, 8)}`;
    if (w.layout === "hub") { dl.push(`hf download ${w.repo} \\\n  --revision ${w.revision}`); mounts.push("-v ~/.cache/huggingface:/root/.cache/huggingface"); }
    else { dl.push(`hf download ${w.repo} \\\n  --revision ${w.revision} \\\n  --local-dir ${dir}`); mounts.push(`-v ${dir}:${w.at}:ro`); }
  }
  if (dl.length) out.push({ title: "Download the weights", code: dl.join("\n\n") });
  if (l.config) {
    out.push({ title: "Write the server config", code: `cat > ${name}.yml <<'EOF'\n${l.config.text.trimEnd()}\nEOF` });
    mounts.push(`-v $PWD/${name}.yml:${l.config.at}:ro`);
  }
  const ep = Array.isArray(l.entrypoint) ? l.entrypoint : l.entrypoint ? [l.entrypoint] : [];
  const all = [...ep.slice(1), ...l.args], args = [];
  for (let i = 0; i < all.length; i++) {
    const a = all[i], b = all[i + 1];
    if (a.startsWith("-") && b !== undefined && !b.startsWith("-")) { args.push(`${a} ${q(b)}`); i++; } else args.push(q(a));
  }
  const run = ["docker run --rm", GPU[l.backend ?? "nvidia"] ?? GPU.nvidia, `-p 8000:${l.port}`, ...(l.flags ?? []), ...(l.shm ? [`--shm-size ${l.shm}`] : []),
    ...Object.entries(l.env ?? {}).map(([k, v]) => `-e ${k}=${q(v)}`), ...mounts, ...(ep.length ? [`--entrypoint ${q(ep[0])}`] : []), image, ...args];
  out.push({ title: l.machines ? `Start the server on each of the ${l.machines} machines (NODE_RANK 0 to ${l.machines - 1})` : "Start the server", code: run.join(" \\\n  ") });
  return out;
}

/** Getting a source: a pinned GitHub tree becomes a clone at that commit. */
function install(url) {
  const m = url.match(/^https:\/\/github\.com\/([\w.-]+)\/([\w.-]+)\/tree\/([0-9a-f]{40})$/);
  return m ? `git clone https://github.com/${m[1]}/${m[2]} && cd ${m[2]} && git checkout ${m[3]}` : `# ${url}`;
}

/** All the steps as one shell script. */
export const command = (r) => steps(r).map((s) => `# ${s.title}\n${s.code}`).join("\n\n");
