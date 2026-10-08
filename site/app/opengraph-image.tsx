import { og, size } from "@/lib/og";
import { stats } from "@/lib/registry";
import copy from "@/lib/landing/copy.json";
export { size };
export const contentType = "image/png";
export const dynamic = "force-static";
export const alt = `${copy.word}: ${copy.sHead}`;
export default () => og({ kicker: "local.sybilsolutions.ai", title: copy.sHead ?? "", sub: copy.sSub ?? "", stats: [[`${stats.gpus}`, "hardware types"], [`${stats.recipes}`, "recipes"], [`${stats.tested}`, "tested"], ["6", "checks each"]] });
