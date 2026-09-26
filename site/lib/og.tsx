// Link previews in the panel's look: black, one monospace face, a cream headline, dim labels, a white rule of numbers.
import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const size = { width: 1200, height: 630 };
const font = (w: number) => readFile(path.join(process.cwd(), "assets", `mono-${w}.ttf`));
const qwen = () => readFile(path.join(process.cwd(), "public", "logos", "qwen.svg"), "utf8");

type Stat = [string, string];
export async function og({ kicker, title, sub, stats, logo }: { kicker: string; title: string; sub?: string; stats?: Stat[]; logo?: boolean }) {
  const svg = logo ? `data:image/svg+xml;base64,${Buffer.from(await qwen()).toString("base64")}` : null;
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", background: "#000", color: "#ece8dc", padding: 64, fontFamily: "Mono" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 24, color: "#8d8a80", letterSpacing: 3 }}>
          <span>LOCAL AI · REGISTRY</span><span>{kicker}</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
            {svg && <img src={svg} width={72} height={72} />}
            <div style={{ fontSize: title.length > 26 ? 64 : 80, fontWeight: 500, letterSpacing: -2, lineHeight: 1.05 }}>{title}</div>
          </div>
          {sub && <div style={{ fontSize: 30, color: "#8d8a80" }}>{sub}</div>}
        </div>
        <div style={{ display: "flex", border: "1px solid #262626" }}>
          {(stats ?? []).map(([v, l], i) => (
            <div key={i} style={{ display: "flex", flexDirection: "column", flex: 1, padding: "18px 24px", background: "#0e0e0e", borderLeft: i ? "1px solid #262626" : "none" }}>
              <span style={{ fontSize: 40, fontWeight: 500 }}>{v}</span><span style={{ fontSize: 20, color: "#8d8a80" }}>{l}</span>
            </div>
          ))}
        </div>
      </div>
    ),
    { ...size, fonts: [{ name: "Mono", data: await font(400), weight: 400 }, { name: "Mono", data: await font(500), weight: 500 }] },
  );
}
