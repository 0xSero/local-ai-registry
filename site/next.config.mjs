import path from "node:path";
/** A static site: every page, preview image and /api/v2 file is built ahead; /api/v2/pick is a Cloudflare Pages Function. */
export default {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  outputFileTracingRoot: path.join(import.meta.dirname, ".."),
};
