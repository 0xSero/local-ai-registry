import { og, size } from "@/lib/og";
import { stats } from "@/lib/registry";
export { size };
export const contentType = "image/png";
export const dynamic = "force-static";
export const alt = "Local AI: the model to run on your GPU";
export default () => og({ kicker: "local.sybilsolutions.ai", title: "The model to run on your GPU.", sub: "Tested recipes, the speed, and the exact command.", stats: [[`${stats.gpus}`, "GPUs"], [`${stats.recipes}`, "recipes"], [`${stats.tested}`, "tested on the card"], ["6", "checks each"]] });
