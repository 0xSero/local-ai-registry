// Writes the static API into public/api/v2: the catalog, and one file per GPU with its picks rendered.
import { readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
const cat = JSON.parse(readFileSync(new URL("../../dist/catalog.json", import.meta.url)));
const out = new URL("../public/api/v2/", import.meta.url);
rmSync(out, { recursive: true, force: true });
mkdirSync(new URL("gpus/", out), { recursive: true });
writeFileSync(new URL("catalog.json", out), JSON.stringify(cat));
for (const [id, c] of Object.entries(cat.cards)) {
  const { picks, ...card } = c;
  writeFileSync(new URL(`gpus/${id}.json`, out), JSON.stringify({ id, ...card, recipes: picks.map((k) => ({ key: k, ...cat.recipes[k] })) }, null, 2));
}
console.log(`api: catalog + ${Object.keys(cat.cards).length} gpus`);
