"use client";
// Type your GPU, pick it, land on its recipes.
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { track } from "./PostHog";

type Option = { id: string; name: string; vendor: string; vram: number };
const norm = (s: string) => s.toLowerCase().replace(/geforce|nvidia|amd|radeon|intel|[^a-z0-9]/g, "");

export default function Picker({ options }: { options: Option[] }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);
  const router = useRouter();
  const hits = useMemo(() => (q ? options.filter((o) => norm(o.name + o.vram).includes(norm(q))) : options).slice(0, 12), [q, options]);
  const go = (o: Option) => { track("gpu_selected", { gpu: o.id, query: q }); router.push(`/gpu/${o.id}`); };
  return (
    <div className="picker">
      <input
        placeholder="Your GPU: RTX 3090, 4060 Ti 16GB, Arc B70, RX 7600 XT..."
        value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); setI(0); }}
        onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { setI(Math.min(i + 1, hits.length - 1)); e.preventDefault(); }
          if (e.key === "ArrowUp") { setI(Math.max(i - 1, 0)); e.preventDefault(); }
          if (e.key === "Enter" && hits[i]) go(hits[i]);
        }}
        aria-label="Find your GPU"
      />
      {open && hits.length > 0 && (
        <ul>
          {hits.map((o, n) => (
            <li key={o.id}><a href={`/gpu/${o.id}`} aria-selected={n === i} onMouseDown={(e) => { e.preventDefault(); go(o); }}>
              <span>{o.name}</span><span className="dim">{o.vram} GB</span></a></li>
          ))}
        </ul>
      )}
    </div>
  );
}
