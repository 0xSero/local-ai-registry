import path from "node:path";
/** The site reads ../dist and ../registry at build time. */
export default {
  outputFileTracingRoot: path.join(import.meta.dirname, ".."),
  poweredByHeader: false,
};
