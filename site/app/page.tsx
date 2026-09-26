import Link from "next/link";
import Picker from "@/components/Picker";
import Logo from "@/components/Logo";
import { cards, picks, model, format, ctxLabel, stats, VENDOR, short } from "@/lib/registry";

export default function Home() {
  const vendors = ["nvidia", "amd", "intel"];
  return (
    <main>
      <div className="hero">
        <div className="label" style={{ marginBottom: 18 }}>Local AI registry</div>
        <h1>The model to run on your GPU, and exactly how.</h1>
        <p>Pick your card. You get the three best models it can run, how fast each one goes, and the command that starts it. A tested recipe was run on the card and passed six checks: it loads, answers, thinks, calls tools, holds its context window and keeps pace. Below the top three, each card lists every other recipe we know of, including ones published by others, marked as reported until our checks run.</p>
        <Picker options={cards.map((c) => ({ id: c.id, name: short(c.name), vendor: c.vendor, vram: c.vram_gb }))} />
        <div className="facts">
          <span><b>{stats.gpus}</b> GPUs</span><span><b>{stats.recipes}</b> recipes</span>
          <span><b>{stats.tested}</b> tested on the real card</span><span><b>{stats.reported}</b> reported</span>
        </div>
      </div>

      <section id="gpus">
        {vendors.map((v) => (
          <div key={v} style={{ marginTop: v === "nvidia" ? 0 : 40 }}>
            <span className="label" style={{ display: "block", marginBottom: 14 }}>{VENDOR[v]}</span>
            <div className="gpus">
              {cards.filter((c) => c.vendor === v).map((c) => {
                const top = picks(c)[0];
                const m = top && model(top);
                const tps = top?.proof[0].tps ?? 0;
                return (
                  <Link key={c.id} href={`/gpu/${c.id}`} className="row">
                    <span className="gpu-name">{short(c.name)}</span>
                    <span className="gpu-mem dim">{c.vram_gb} GB</span>
                    {top && <span className="gpu-model"><Logo family={m.logo ?? m.family} size={16} />{m.name}<span className="faint">{format(top)}</span></span>}
                    <span className="gpu-speed"><span className="bar"><i style={{ width: `${Math.min(100, tps / 1.8)}%` }} /></span><span>{tps ? Math.round(tps) : "–"}<span className="faint"> tok/s</span></span></span>
                    <span className="dim">›</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </section>
    </main>
  );
}
