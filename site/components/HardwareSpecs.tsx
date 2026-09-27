// A card's spec sheet: memory, compute, throughput per precision, price, and where each came from.
import type { Specs } from "@/lib/registry";

const Rows = ({ rows }: { rows: [string, string][] }) => (
  <table className="t"><tbody>{rows.map(([k, v]) => <tr key={k}><td className="dim" style={{ width: "40%" }}>{k}</td><td>{v}</td></tr>)}</tbody></table>
);
const tf = (v: number | null) => (v == null ? "–" : v.toLocaleString("en-US", { maximumFractionDigits: 1 }));

export default function HardwareSpecs({ h }: { h: Specs }) {
  return (
    <section id="hardware">
      <span className="label">Hardware</span>
      <div className="grid cols-2">
        <div>
          <Rows rows={[...h.memory, ...h.compute, ...(h.products.length ? [["Sold in", h.products.join(", ")] as [string, string]] : [])]} />
        </div>
        <div>
          {h.tflops.length > 0 && (
            <table className="t">
              <thead><tr><th>Precision</th><th>Dense TFLOPS</th><th>2:4 sparse</th></tr></thead>
              <tbody>{h.tflops.map(([p, d, s]) => <tr key={p}><td>{p}</td><td>{tf(d)}</td><td className="dim">{tf(s)}</td></tr>)}</tbody>
            </table>
          )}
          {h.price.length > 0 && <div style={{ marginTop: h.tflops.length ? 24 : 0 }}><Rows rows={h.price} /></div>}
        </div>
      </div>
      {h.listings.length > 0 && (
        <div style={{ overflowX: "auto", marginTop: 24 }}><table className="t">
          <thead><tr><th>Listing</th><th>Price</th><th>Seen</th><th>Where</th></tr></thead>
          <tbody>{h.listings.map((l, i) => (
            <tr key={i}><td>{l.what}</td><td>{l.price}</td><td className="dim">{l.at}</td><td><a href={l.url} rel="nofollow noopener" target="_blank">{l.publisher} ›</a></td></tr>
          ))}</tbody>
        </table></div>
      )}
      {h.sources.length > 0 && (
        <p className="dim" style={{ fontSize: 13, marginTop: 16 }}>
          Sources: {h.sources.map((s, i) => {
            const n = h.sources.slice(0, i).filter((x) => x.publisher === s.publisher).length;
            return <span key={s.url}>{i ? ", " : ""}<a href={s.url} rel="nofollow noopener" target="_blank">{s.publisher}{n ? ` (${n + 1})` : ""}</a></span>;
          })}
        </p>
      )}
    </section>
  );
}
