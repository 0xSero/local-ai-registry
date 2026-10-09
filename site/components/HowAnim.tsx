import s from "./HowAnim.module.css";

// One small looping picture per "How it works" step, drawn in CSS only. Each loop is 8 s; with reduced motion
// every picture shows its last frame and stands still.

function Hardware() {
  const rows: [string, string][] = [["GPU 0", "RTX 3090 · 24 GB"], ["GPU 1", "Arc Pro B70 · 32 GB"], ["CPU", "AVX2 · 48 threads"], ["RAM", "512 GB"], ["DISK", "NVMe · 3.5 TB free"]];
  return (
    <div className={`${s.box} ${s.hw}`}>
      <span className={s.scan} />
      {rows.map(([k, v], i) => (
        <div key={k} className={s.row} style={{ ["--i" as string]: i }}><span className={s.key}>{k}</span><span>{v}</span></div>
      ))}
    </div>
  );
}

function Checks() {
  const gates = ["loads", "answers", "thinks", "calls a tool", "recalls at 128k", "≥ 15 tok/s"];
  return (
    <div className={s.box}>
      {gates.map((g, i) => (
        <div key={g} className={s.row} style={{ ["--i" as string]: i }}>
          <span className={s.tick}>✓</span><span>{g}</span><span className={s.dots} />
        </div>
      ))}
    </div>
  );
}

function Weights() {
  const files = ["config.json", "model-00001.safetensors", "model-00002.safetensors", "model-00003.safetensors"];
  return (
    <div className={s.box}>
      {files.map((f, i) => (
        <div key={f} className={s.file} style={{ ["--i" as string]: i }}>
          <span className={s.name}>{f}</span><span className={s.bar}><span /></span><span className={s.ok}>sha256 ✓</span>
        </div>
      ))}
    </div>
  );
}

function Serve() {
  return (
    <div className={`${s.box} ${s.serve}`}>
      <div className={s.node}>engine<small>image@sha256</small></div>
      <div className={s.wire}><span /><span /><span /></div>
      <div className={s.node}>gateway<small>127.0.0.1 · key</small></div>
      <div className={s.apis}><span>OpenAI</span><span>Anthropic</span><span>Responses</span></div>
    </div>
  );
}

function Agent() {
  return (
    <div className={`${s.box} ${s.term}`}>
      <div className={s.bar2}><i /><i /><i /><span>claude · local</span></div>
      <div className={s.typed}><span className={s.p}>›</span> fix the failing test</div>
      <div className={s.stream}>Reading test/view-test.sh… the snapshot fixture is stale. Updating it.</div>
      <div className={s.meta2}>model on this machine · 0 bytes sent out</div>
    </div>
  );
}

function Tiers() {
  const tiers: [string, string, number][] = [["VRAM", "24 GB", 4], ["RAM", "55 GB", 7], ["NVMe", "117 GB", 12]];
  return (
    <div className={`${s.box} ${s.tiers}`}>
      {tiers.map(([k, v, n], t) => (
        <div key={k} className={s.tier}>
          <span className={s.key}>{k}</span>
          <span className={s.cells}>{Array.from({ length: n }, (_, i) => <i key={i} style={{ ["--d" as string]: `${((i * 7 + t * 3) % 11) * 0.55}s` }} />)}</span>
          <span className={s.size}>{v}</span>
        </div>
      ))}
      <div className={s.meta2}>hot experts move up, cold ones wait below</div>
    </div>
  );
}

const PICTURES = [Hardware, Checks, Weights, Serve, Agent, Tiers];

export default function HowAnim({ step }: { step: number }) {
  const P = PICTURES[step];
  return P ? <div className={s.wrap} aria-hidden="true"><P /></div> : null;
}
