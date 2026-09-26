import Link from "next/link";
import Logo from "./Logo";
import { Recipe, model, format, ctxLabel, engineKind, claims, status, role, fmtDate } from "@/lib/registry";

export const ENGINE: Record<string, string> = { tabbyapi: "TabbyAPI", sglang: "SGLang", vllm: "vLLM", "llama.cpp": "llama.cpp", exllamav3: "ExLlamaV3", flm: "FastFlowLM" };

export default function RecipeCard({ r, all }: { r: Recipe; all: Recipe[] }) {
  const m = model(r);
  const g = claims(r);
  const s = status(r);
  const p = r.proof[0];
  const which = role(r, all);
  return (
    <article className="rc">
      <span className={`role ${which === "Recommended" ? "" : "alt"}`}>{which}</span>
      <div className="head"><Logo family={m.logo ?? m.family} /><span>{m.name}</span></div>
      <div className="meta"><span>{format(r)}</span><span>{ENGINE[engineKind(r)] ?? engineKind(r)}</span><span>{ctxLabel(r.launch.ctx)} context</span>{r.launch.machines ? <span>{r.launch.machines} machines</span> : null}</div>
      {m.good_for && <p className="about"><span className="faint">Best for </span>{m.good_for}.</p>}
      <div className="numbers">
        <div><b>{p.tps ? `${Math.round(p.tps)} tok/s` : "–"}</b><span>decode</span></div>
        <div><b>{p.prefill ? `${Math.round(p.prefill).toLocaleString("en-US")} tok/s` : "–"}</b><span>prefill</span></div>
        <div><b>{ctxLabel(r.launch.ctx)}</b><span>context</span></div>
      </div>
      <div className="chips">
        {[["reasoning", "Thinks"], ["tools", "Tools"], ...(r.proof[0].reported ? [] : [["context", "Long context"]])].map(([k, l]) => (
          <span key={k} className={`chip ${g.has(k) ? "on" : ""}`}>{g.has(k) ? "✓ " : ""}{l}</span>
        ))}
        {r.launch.vision && <span className="chip on">✓ Vision</span>}
      </div>
      <div className="proof"><span className={`dot ${s.tone}`} /><span>{s.label}{p.at ? ` · ${fmtDate(p.at)}` : ""}</span></div>
      <div className="actions">
        <Link className="btn solid" href={`/gpu/${r.card}/${r.slug}`}>Run it ›</Link>
      </div>
    </article>
  );
}
