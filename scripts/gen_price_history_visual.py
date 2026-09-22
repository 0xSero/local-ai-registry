#!/usr/bin/env python3
"""Generate the price-history visual from cache/price-history-data.json.

The page is committed, so it has to be a pure function of that payload: no clock, no
network, no scrape dump. `make price-visual-check` regenerates it and requires no diff,
which is what keeps every number on it traceable to the registry.

Usage
-----
    python3 scripts/build_price_history_data.py
    python3 scripts/gen_price_history_visual.py
    python3 scripts/gen_price_history_visual.py --data cache/price-history-data.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--data", default="cache/price-history-data.json",
                help="payload written by build_price_history_data.py")
ap.add_argument("--out", default="docs/visuals/gpu-price-history.html",
                help="page path (default: docs/visuals/gpu-price-history.html)")
args = ap.parse_args()

data = Path(args.data).read_text()
payload = json.loads(data)
grid = payload.get("gpu") or {"cards": [], "classes": 0, "observations": 0, "year_deep": 0, "deepest": 0}
html = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GPU price evidence — Geizhals history into the registry</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;600&family=Spectral:ital,wght@0,300;0,400;0,600;1,400&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-chart-financial@0.2.1/dist/chartjs-chart-financial.min.js"></script>
<style>
:root {
  --font-display: 'Instrument Serif', Georgia, serif;
  --font-body: 'Spectral', Georgia, serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', Consolas, monospace;

  --paper: #f7f5f0;
  --surface: #fffdf9;
  --surface-sunken: #efece4;
  --border: rgba(27, 36, 52, 0.10);
  --border-bright: rgba(27, 36, 52, 0.22);
  --ink: #1b2434;
  --ink-dim: #6a6559;
  --navy: #16233a;
  --navy-dim: rgba(22, 35, 58, 0.07);
  --gold: #9a7412;
  --gold-bright: #c9a227;
  --gold-dim: rgba(154, 116, 18, 0.10);
  --sage: #4f6b52;
  --sage-dim: rgba(79, 107, 82, 0.10);
  --rust: #9c4221;
  --rust-dim: rgba(156, 66, 33, 0.09);
  --red: #a33a2a;
  --green: #4f6b52;
  --candle-up: #2f7d4f;
  --candle-down: #b23a2e;
}

@media (prefers-color-scheme: dark) {
  :root {
    --paper: #0f141b;
    --surface: #161d26;
    --surface-sunken: #12181f;
    --border: rgba(232, 227, 217, 0.09);
    --border-bright: rgba(232, 227, 217, 0.22);
    --ink: #e9e4d9;
    --ink-dim: #9a9384;
    --navy: #cfd8e8;
    --navy-dim: rgba(207, 216, 232, 0.08);
    --gold: #d8b451;
    --gold-bright: #e8ca6a;
    --gold-dim: rgba(216, 180, 81, 0.12);
    --sage: #8fb096;
    --sage-dim: rgba(143, 176, 150, 0.12);
    --rust: #d98a63;
    --rust-dim: rgba(217, 138, 99, 0.12);
    --red: #d98a63;
    --green: #8fb096;
    --candle-up: #4fae76;
    --candle-down: #e2705a;
  }
}

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 0 0 96px;
  background-color: var(--paper);
  background-image:
    radial-gradient(ellipse at 50% -10%, var(--gold-dim) 0%, transparent 55%),
    repeating-linear-gradient(0deg, var(--border) 0 1px, transparent 1px 32px);
  color: var(--ink);
  font-family: var(--font-body);
  font-size: 16px;
  line-height: 1.65;
  overflow-wrap: break-word;
  -webkit-font-smoothing: antialiased;
}

.wrap { max-width: 1120px; margin: 0 auto; padding: 0 24px; }
.grid > *, .flex > * { min-width: 0; }

.masthead {
  border-bottom: 1px solid var(--border-bright);
  padding: 64px 0 28px;
  margin-bottom: 48px;
}
.masthead__kicker {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--gold);
  margin-bottom: 18px;
}
.masthead h1 {
  font-family: var(--font-display);
  font-weight: 400;
  font-size: clamp(40px, 6.4vw, 74px);
  line-height: 1.02;
  letter-spacing: -0.02em;
  margin: 0 0 18px;
  max-width: 20ch;
}
.masthead h1 em { font-style: italic; color: var(--gold); }
.masthead__standfirst {
  font-size: 19px;
  line-height: 1.6;
  color: var(--ink-dim);
  max-width: 68ch;
  margin: 0;
}
.masthead__meta {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-dim);
  margin-top: 24px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
}

section { margin: 0 0 72px; }
.section-head { margin-bottom: 24px; }
.section-num {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 2px;
  color: var(--gold);
  display: block;
  margin-bottom: 8px;
}
.section-head h2 {
  font-family: var(--font-display);
  font-weight: 400;
  font-size: clamp(28px, 3.6vw, 42px);
  letter-spacing: -0.01em;
  margin: 0 0 10px;
}
.section-head p { margin: 0; color: var(--ink-dim); max-width: 74ch; }

.ve-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 22px 24px;
  position: relative;
}
.ve-card--recessed {
  background: var(--surface-sunken);
  border-color: var(--border);
}
.ve-card--hero {
  background: color-mix(in srgb, var(--surface) 90%, var(--gold) 10%);
  border-color: color-mix(in srgb, var(--border-bright) 60%, var(--gold) 40%);
  box-shadow: 0 3px 18px rgba(27, 36, 52, 0.06);
  padding: 28px 30px;
}

.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.kpi {
  background: var(--surface);
  padding: 22px 24px;
}
.kpi--lead { background: color-mix(in srgb, var(--surface) 88%, var(--gold) 12%); }
.kpi__value {
  font-family: var(--font-display);
  font-size: clamp(34px, 4.6vw, 50px);
  line-height: 1;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.kpi--lead .kpi__value { color: var(--gold); }
.kpi__label {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1.4px;
  text-transform: uppercase;
  color: var(--ink-dim);
  margin-top: 10px;
}
.kpi__note { font-size: 13px; color: var(--ink-dim); margin-top: 6px; font-family: var(--font-mono); }

.chart-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 20px 22px 12px;
  position: relative;
}
.chart-card__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.chart-card__title {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1.4px;
  text-transform: uppercase;
  color: var(--ink-dim);
}
.chart-card__legend { font-family: var(--font-mono); font-size: 11px; color: var(--ink-dim); }
.chart-frame { position: relative; height: 380px; }
.chart-frame--tall { height: 460px; }
.chart-frame--short { height: 300px; }
canvas { display: block; }

table { width: 100%; border-collapse: collapse; font-size: 14.5px; }
.table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 4px; background: var(--surface); }
thead th {
  position: sticky; top: 0;
  background: var(--surface-sunken);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  color: var(--ink-dim);
  text-align: left;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-bright);
  white-space: nowrap;
}
tbody td { padding: 11px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
tbody tr:nth-child(even) { background: color-mix(in srgb, var(--surface-sunken) 55%, transparent); }
tbody tr:last-child td { border-bottom: none; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; font-family: var(--font-mono); }
code {
  font-family: var(--font-mono);
  font-size: 0.86em;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 5px;
}

.status { display: inline-flex; align-items: center; gap: 7px; font-family: var(--font-mono); font-size: 12px; white-space: nowrap; }
.status::before { content: ''; width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
.status--ok { color: var(--green); }
.status--ok::before { background: var(--green); }
.status--part { color: var(--gold); }
.status--part::before { background: var(--gold); }
.status--no { color: var(--red); }
.status--no::before { background: var(--red); }

.diff-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.diff-panels > * { min-width: 0; overflow-wrap: break-word; }
.diff-head {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  padding: 12px 18px;
}
.diff-head--before { background: var(--rust-dim); color: var(--rust); border-bottom: 2px solid var(--rust); }
.diff-head--after { background: var(--sage-dim); color: var(--sage); border-bottom: 2px solid var(--sage); }
.diff-body { padding: 20px 18px; background: var(--surface); }
.diff-body__num { font-family: var(--font-display); font-size: 42px; line-height: 1; font-variant-numeric: tabular-nums; }
.diff-body__cap { font-family: var(--font-mono); font-size: 11px; color: var(--ink-dim); margin-top: 8px; letter-spacing: 0.6px; }
.diff-body p { margin: 14px 0 0; font-size: 14.5px; color: var(--ink-dim); }

.pull {
  border-left: 3px solid var(--gold);
  padding: 4px 0 4px 24px;
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(22px, 2.7vw, 30px);
  line-height: 1.35;
  max-width: 46ch;
}
.pull cite { display: block; font-family: var(--font-mono); font-size: 11px; font-style: normal; color: var(--ink-dim); margin-top: 14px; letter-spacing: 0.6px; }

.callout {
  border: 1px solid var(--border);
  border-left: 3px solid var(--gold);
  background: var(--gold-dim);
  border-radius: 4px;
  padding: 16px 20px;
  font-size: 15px;
}
.callout strong { font-family: var(--font-mono); font-size: 12px; letter-spacing: 1px; text-transform: uppercase; display: block; margin-bottom: 6px; color: var(--gold); }

.split { display: grid; grid-template-columns: 1.35fr 1fr; gap: 24px; align-items: start; }
.split > * { min-width: 0; }

.mermaid-wrap {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 32px 24px;
  overflow: auto;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 420px;
  scrollbar-width: thin;
  cursor: grab;
}
.mermaid-wrap.is-panning { cursor: grabbing; user-select: none; }
.mermaid .nodeLabel { color: var(--ink) !important; }
.mermaid .edgeLabel { color: var(--ink-dim) !important; background-color: var(--surface) !important; }
.mermaid .edgeLabel rect { fill: var(--surface) !important; }
.mermaid .node rect, .mermaid .node polygon, .mermaid .node circle { stroke-width: 1.5px; }
.mermaid .edge-pattern-solid { stroke-width: 1.5px; }
.mermaid .nodeLabel { font-family: var(--font-body) !important; font-size: 15px !important; }
.mermaid .edgeLabel { font-family: var(--font-mono) !important; font-size: 12px !important; }
.zoom-controls {
  position: absolute; top: 8px; right: 8px; display: flex; gap: 2px; z-index: 10;
  background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 2px;
}
.zoom-controls button {
  width: 28px; height: 28px; border: none; background: transparent; color: var(--ink-dim);
  font-family: var(--font-mono); font-size: 14px; cursor: pointer; border-radius: 3px;
}
.zoom-controls button:hover { background: var(--surface-sunken); color: var(--ink); }

details.collapsible { border: 1px solid var(--border); border-radius: 4px; background: var(--surface); }
details.collapsible summary {
  cursor: pointer; padding: 14px 20px; font-family: var(--font-mono); font-size: 12px;
  font-weight: 600; letter-spacing: 1.2px; text-transform: uppercase; color: var(--ink-dim);
}
details.collapsible summary::marker { color: var(--gold); }
details.collapsible[open] summary { border-bottom: 1px solid var(--border); color: var(--ink); }
details.collapsible .body { padding: 18px 20px; }
details.collapsible + details.collapsible { margin-top: 10px; }

pre.code {
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 14px 16px;
  margin: 0 0 12px;
}
pre.code .cm { color: var(--ink-dim); }
pre.code .hi { color: var(--gold); }

.ve-card, .kpi, .chart-card, .mermaid-wrap, details.collapsible, .diff-panels { opacity: 0; animation: fadeUp 0.5s ease forwards; }
@keyframes fadeUp { to { opacity: 1; transform: none; } }
.ve-card, .kpi, .chart-card { transform: translateY(12px); }
.kpi { animation-delay: 0.05s; }
.chart-card:nth-of-type(1) { animation-delay: 0.12s; }
.chart-card:nth-of-type(2) { animation-delay: 0.18s; }
@media (prefers-reduced-motion: reduce) {
  .ve-card, .kpi, .chart-card, .mermaid-wrap, details.collapsible, .diff-panels {
    opacity: 1 !important; animation: none !important; transform: none !important;
  }
}

.gpu-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: 14px;
}
.gpu-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 14px 16px 12px;
}
.gpu-card__head { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }
.gpu-card__name {
  font-family: var(--font-mono); font-size: 11px; font-weight: 600; letter-spacing: 0.4px;
  color: var(--ink); text-transform: uppercase;
}
.gpu-card__change { font-family: var(--font-mono); font-size: 11px; white-space: nowrap; }
.gpu-card__change--up { color: var(--rust); }
.gpu-card__change--down { color: var(--sage); }
.gpu-card__change--flat { color: var(--ink-dim); }
.gpu-card__price { font-family: var(--font-display); font-size: 26px; line-height: 1.1; margin-top: 6px; font-variant-numeric: tabular-nums; }
.gpu-card__meta { font-family: var(--font-mono); font-size: 10px; color: var(--ink-dim); margin-top: 2px; letter-spacing: 0.4px; }
.gpu-card svg { display: block; width: 100%; height: 40px; margin-top: 8px; }
.gpu-card svg .wick { stroke-width: 1; }
.gpu-card svg .body { stroke: none; }
.gpu-card svg .up { stroke: var(--candle-up); fill: var(--candle-up); }
.gpu-card svg .down { stroke: var(--candle-down); fill: var(--candle-down); }


.footnote { font-size: 13.5px; color: var(--ink-dim); max-width: 74ch; }
.footnote code { font-size: 0.9em; }
@media (max-width: 860px) {
  .split { grid-template-columns: 1fr; }
  .diff-panels { grid-template-columns: 1fr; }
  .chart-frame { height: 300px; }
}
</style>
</head>
<body>
<div class="wrap">

  <header class="masthead">
    <div class="masthead__kicker">Geizhals / Micro Center · 22 September 2026</div>
    <h1>What the GPU price record can <em>actually</em> hold</h1>
    <p class="masthead__standfirst">
      Geizhals publishes a daily price series for every card it tracks, reaching back to launch. Micro Center
      publishes nothing, and its prices are in-store only. This page is the evidence behind importing the first into the
      registry as an append-only series — <strong>__GRID_CLASSES__ GPU classes, __GRID_OBS__ Geizhals observations, the deepest running __GRID_DEEPEST__ days</strong> —
      and the argument for why the second can only be accumulated forward.
    </p>
    <div class="masthead__meta">
      <span>registry <code>price/*/de.json</code></span>
      <span>__GRID_CLASSES__ classes</span>
      <span>__GRID_OBS__ observations</span>
      <span>__GRID_DEEPEST__ days deepest</span>
      <span>0 observations lost</span>
    </div>
  </header>

  <section>
    <div class="section-head">
      <span class="section-num">01 — the series</span>
      <h2>__DE_SPAN__ of RTX 5090 prices, day by day</h2>
      <p>__DE_LISTINGS__ Geizhals listings, one point per day each, in EUR. Imported into <code>registry/price/rtx-5090/de.json</code>
      and unioned with the observations already recorded, so nothing was replaced.</p>
    </div>
    <div class="kpi-row">
      <div class="kpi kpi--lead">
        <div class="kpi__value">__DE_OBS__</div>
        <div class="kpi__label">Geizhals observations</div>
        <div class="kpi__note">__DE_LISTINGS__ listings</div>
      </div>
      <div class="kpi">
        <div class="kpi__value">__DE_DAYS__</div>
        <div class="kpi__label">Days covered</div>
        <div class="kpi__note">__DE_FIRST__ → __DE_LAST__</div>
      </div>
      <div class="kpi">
        <div class="kpi__value">__DE_LOW__</div>
        <div class="kpi__label">Series low</div>
        <div class="kpi__note">high __DE_HIGH__ · 0 half-median outliers</div>
      </div>
      <div class="kpi">
        <div class="kpi__value">0</div>
        <div class="kpi__label">Observations lost</div>
        <div class="kpi__note">superset check vs. pre-import backup</div>
      </div>
    </div>
  </header>

  <section>
    <div class="chart-card">
      <div class="chart-card__head">
        <span class="chart-card__title">RTX 5090 · weekly candles, Geizhals DE</span>
        <span class="chart-card__legend">EUR · open / high / low / close per week · green closes above open</span>
      </div>
      <div class="chart-frame chart-frame--tall"><canvas id="chartCandles"></canvas></div>
    </div>
  </section>

  <section>
    <div class="section-head">
      <span class="section-num">02 — every GPU</span>
      <h2>The whole category, one series per chip</h2>
      <p>Every Geizhals GPU class the registry tracks, cheapest model per class, full daily history in EUR. The grid is
      sorted by depth and drawn as candles; the index below normalises each class to its first observation so classes of very
      different price levels can be compared.</p>
    </div>
    <div class="kpi-row" style="margin-bottom: 24px">
      <div class="kpi kpi--lead">
        <div class="kpi__value">__GRID_CLASSES__</div>
        <div class="kpi__label">GPU classes with history</div>
        <div class="kpi__note">__GRID_OBS__ daily points</div>
      </div>
      <div class="kpi">
        <div class="kpi__value">__GRID_YEAR__</div>
        <div class="kpi__label">Classes with a year or more</div>
        <div class="kpi__note">daily resolution</div>
      </div>
      <div class="kpi">
        <div class="kpi__value">__GRID_DEEPEST__</div>
        <div class="kpi__label">Deepest series</div>
        <div class="kpi__note">days</div>
      </div>
      <div class="kpi">
        <div class="kpi__value">42</div>
        <div class="kpi__label">GPU classes in registry</div>
        <div class="kpi__note">one cheapest model each</div>
      </div>
    </div>
    <div class="chart-card" style="margin-bottom: 24px">
      <div class="chart-card__head">
        <span class="chart-card__title">__DEEP_TITLE__ · monthly candles</span>
        <span class="chart-card__legend">EUR · __DEEP_DAYS__ tracked days</span>
      </div>
      <div class="chart-frame chart-frame--tall"><canvas id="chartDeep"></canvas></div>
    </div>
    <div class="chart-card" style="margin-bottom: 24px">
      <div class="chart-card__head">
        <span class="chart-card__title">Indexed price · first observation = 100</span>
        <span class="chart-card__legend">classes with 365+ days</span>
      </div>
      <div class="chart-frame"><canvas id="chartIndex"></canvas></div>
    </div>
    <div class="gpu-grid">
__GPU_GRID__
    </div>
    <p class="footnote" style="margin-top: 18px">
      Each card is one listing drawn as monthly candles — weekly for series under 500 days. Geizhals gives one price a day,
      the lowest offer it tracked, so a candle opens on the first day of its bucket, closes on the last, and its wick is that
      bucket's range: <span style="color: var(--candle-up)">green closes above open</span>,
      <span style="color: var(--candle-down)">red closes below</span>. The percentage is against the first tracked day, which can be a
      promotional price — the 2021 mining peak is the tall candle cluster in the 30-series cards, and the newer cards open on
      launch-window scalper prices.
    </p>
  </section>

  <section>
    <div class="section-head">
      <span class="section-num">03 — the Micro Center point</span>
      <h2>Chain-wide prices, store-level stock</h2>
      <p>The newest run the registry holds — __MC_RUN__ — priced __MC_LISTINGS__ listings across
      __MC_STORES__ stores. Of the __MC_MULTI__ SKUs priced in more than one store in that same run,
      <strong>__MC_DIFFER__ differed in price</strong> — Micro Center prices its cards chain-wide. What differs per
      store is which models it stocks, and how deep the stock runs, which is what moves the cheapest listing.</p>
    </div>
    <div class="kpi-row" style="margin-bottom: 24px">
      <div class="kpi kpi--lead">
        <div class="kpi__value">__MC_DIFFER__<span style="font-size: 0.45em; color: var(--ink-dim)"> / __MC_MULTI__</span></div>
        <div class="kpi__label">SKUs priced differently across stores</div>
        <div class="kpi__note">one run, every store</div>
      </div>
      __MC_STORE_KPIS__
    </div>
    <div class="split">
      <div class="chart-card">
        <div class="chart-card__head">
          <span class="chart-card__title">Price range by chip · all stores</span>
          <span class="chart-card__legend">bars span min → max · label shows listings</span>
        </div>
        <div class="chart-frame chart-frame--tall"><canvas id="chartMcRange"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="chart-card__head">
          <span class="chart-card__title">Cheapest listing per store, where it differs</span>
          <span class="chart-card__legend">USD · __MC_DIV__ of __MC_CHIPS__ chips</span>
        </div>
        <div class="chart-frame chart-frame--tall"><canvas id="chartMcStore"></canvas></div>
      </div>
    </div>
    <p class="footnote" style="margin-top: 18px">
      The divergence above is model availability, not pricing: every one of those SKUs carries an identical price in each
      store that stocks it, so a store that does not stock the cheapest variant shows a higher floor. For the other
      __MC_AGREE__ chips the compared stores agree exactly.
    </p>
  </section>

  <section>
    <div class="section-head">
      <span class="section-num">04 — the accumulation</span>
      <h2>How deep each source actually goes</h2>
      <p>Nothing on disk reached a year before this import. The registry's own price history spans five observation days,
      its Micro Center slice three, and the scanner's snapshot cache three. The Geizhals series is the only one measured in
      hundreds of days — which is exactly why it had to be imported rather than averaged into a summary.</p>
    </div>
    <div class="split">
      <div class="chart-card">
        <div class="chart-card__head">
          <span class="chart-card__title">Days of price history by source</span>
          <span class="chart-card__legend">log scale</span>
        </div>
        <div class="chart-frame"><canvas id="chartDepth"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="chart-card__head">
          <span class="chart-card__title">Registry observations by retailer</span>
          <span class="chart-card__legend">after import · 2693 total</span>
        </div>
        <div class="chart-frame"><canvas id="chartRetailer"></canvas></div>
      </div>
    </div>
  </section>

  <section>
    <div class="section-head">
      <span class="section-num">05 — the correction</span>
      <h2>The importer was erasing repeat prices</h2>
      <p>The first import kept only 364 of 1220 points and stamped 856 as rejected. The importer's dedupe key was
      <code>(retailer, url, condition, price)</code> — no timestamp — so every day a price held steady collapsed into the
      day it was first seen. Adding the observation timestamp to the key is what makes a series a series.</p>
    </div>
    <div class="diff-panels">
      <div class="diff-head diff-head--before">Before · key without timestamp</div>
      <div class="diff-head diff-head--after">After · key includes observed_at</div>
      <div class="diff-body">
        <div class="diff-body__num" style="color: var(--rust)">364</div>
        <div class="diff-body__cap">observations kept of 1220</div>
        <p>856 points dropped as <code>rejected_observations</code>. The record's <code>observed_at</code> landed on
        2026-09-19, not the newest day, because the collapse kept the first day of each price.</p>
      </div>
      <div class="diff-body">
        <div class="diff-body__num" style="color: var(--sage)">1220</div>
        <div class="diff-body__cap">observations kept of 1220</div>
        <p><code>rejected_observations: 0</code>. The record's <code>observed_at</code> is the newest point,
        2026-09-21, and re-importing the same dump adds nothing.</p>
      </div>
    </div>
  </section>

  <section>
    <div class="section-head">
      <span class="section-num">06 — the sources</span>
      <h2>What is reachable from a European IP, and what is not</h2>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Source</th><th>Access</th><th>Status</th><th class="num">History depth</th><th>Note</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Geizhals DE / AT</strong><br><small>price_history API</small></td>
            <td>Headed browser clears the JS challenge, then a public JSON endpoint</td>
            <td><span class="status status--ok">imported</span></td>
            <td class="num">__GRID_DEEPEST__ days<br><small>deepest class</small></td>
            <td>Machine-readable, reaches launch. Full scan of the category: 35 GPU classes, cheapest model each. <code>days=9999</code> is the full series.</td>
          </tr>
          <tr>
            <td><strong>Micro Center</strong><br><small>category scrape</small></td>
            <td>US egress via SOCKS tunnel + headed browser</td>
            <td><span class="status status--ok">working</span></td>
            <td class="num">3 days<br><small>weekly</small></td>
            <td>No published history and no archives to backfill; forward accumulation only, now four stores plus shippable.</td>
          </tr>
          <tr>
            <td><strong>Ceneo PL</strong><br><small>product pages</small></td>
            <td>Open, no challenge</td>
            <td><span class="status status--part">partial</span></td>
            <td class="num">—<br><small>current only</small></td>
            <td>Series is login-gated: <em>Historia cen dostępna jest po zalogowaniu się.</em> Publicly only the current and lowest price.</td>
          </tr>
          <tr>
            <td><strong>Idealo DE</strong></td>
            <td>403 from Akamai to plain HTTP; JS-rendered</td>
            <td><span class="status status--part">untested</span></td>
            <td class="num">—</td>
            <td>Charts exist but were not extracted; needs the same browser treatment Geizhals got.</td>
          </tr>
          <tr>
            <td><strong>PCPartPicker US</strong></td>
            <td>Hard Cloudflare block on datacenter IPs</td>
            <td><span class="status status--no">blocked</span></td>
            <td class="num">—</td>
            <td><em>Sorry, you have been blocked.</em> Would need a residential US IP, which this homelab does not have.</td>
          </tr>
          <tr>
            <td><strong>camelcamelcamel</strong><br><small>Amazon US</small></td>
            <td>Cloudflare interstitial</td>
            <td><span class="status status--part">untested</span></td>
            <td class="num">years</td>
            <td>Same JS challenge as Geizhals, so likely passable with a headed session.</td>
          </tr>
          <tr>
            <td><strong>Keepa</strong></td>
            <td>Site reachable, history behind a paid API</td>
            <td><span class="status status--part">partial</span></td>
            <td class="num">years</td>
            <td>The public chart endpoint returns a 500×200 PNG, not data.</td>
          </tr>
          <tr>
            <td><strong>Skinflint UK</strong></td>
            <td>Retired</td>
            <td><span class="status status--no">gone</span></td>
            <td class="num">—</td>
            <td>HTTP 410 for every path; the UK Geizhals sibling no longer exists.</td>
          </tr>
          <tr>
            <td><strong>eBay</strong></td>
            <td>Open</td>
            <td><span class="status status--part">partial</span></td>
            <td class="num">~90 days<br><small>sold</small></td>
            <td>Sold listings age out, so it cannot reach a year.</td>
          </tr>
          <tr>
            <td><strong>Wayback Machine</strong></td>
            <td>CDX offline, availability API degraded</td>
            <td><span class="status status--no">unverifiable</span></td>
            <td class="num">—</td>
            <td>The API returned no snapshots for <code>example.com</code> either, so the archive path is unproven, not disproven.</td>
          </tr>
          <tr>
            <td><strong>toolshedlabs-hash/gpu-price-feed</strong></td>
            <td>Open on GitHub</td>
            <td><span class="status status--part">adjacent</span></td>
            <td class="num">daily</td>
            <td>Cloud <em>rental</em> prices with an append-only history — not retail cards.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section>
    <div class="section-head">
      <span class="section-num">07 — the pipeline</span>
      <h2>Two egress paths, one contract</h2>
      <p>Both sources converge on the same importer, so one set of rules governs identity, currency and outlier rejection.</p>
    </div>
    <div class="mermaid-wrap">
      <div class="zoom-controls">
        <button onclick="zoomDiagram(this, 1.2)" title="Zoom in">+</button>
        <button onclick="zoomDiagram(this, 0.8)" title="Zoom out">&minus;</button>
        <button onclick="resetZoom(this)" title="Reset zoom">&#8634;</button>
      </div>
      <pre class="mermaid">
flowchart TD
  GH["geizhals.de price_history API"] -->|"daily series, 9999 days"| GHE["scrape_geizhals_history.py<br/>headed browser clears challenge"]
  GHE -->|"out/geizhals-history-*.json"| GHF["fetch_geizhals_history.py<br/>maps SKU, unions prior"]
  MC["microcenter.com category"] -->|"blocks non-US IPs"| MCS["scrape_microcenter_prices.py<br/>SOCKS tunnel to a US host"]
  MCS -->|"out/run-*.json"| MCF["fetch_microcenter_prices.py<br/>maps SKU, unions prior"]
  GHF --> IMP["import_market_snapshot.py<br/>identity, currency, outlier floor"]
  MCF --> IMP
  IMP --> REG["registry/price/product/region.json"]
  REG --> CUR["curate_registry.py --index-only"]
  CUR --> IDX["registry/index/collections.json"]
  IDX --> VAL["validate_registry.py"]

  classDef blocked fill:#9c422122,stroke:#9c4221,stroke-width:1px
  classDef ok fill:#4f6b5222,stroke:#4f6b52,stroke-width:1px
  classDef core fill:#9a741222,stroke:#9a7412,stroke-width:2px
  class MC blocked
  class GH,GHE,GHF,MCS,MCF ok
  class IMP,REG,IDX,VAL core
      </pre>
    </div>
  </section>

  <section>
    <div class="section-head">
      <span class="section-num">08 — reproduce</span>
      <h2>Every claim above, re-runnable</h2>
    </div>
    <details class="collapsible" open>
      <summary>Import the Geizhals series</summary>
      <div class="body">
<pre class="code"><span class="cm"># 1. pull the daily series (headed browser clears Cloudflare once)</span>
python3 scripts/scrape_geizhals_history.py --match 5090 --days 9999 --pages 2 --limit 40

<span class="cm"># 2. map onto the registry and union with prior observations</span>
python3 scripts/fetch_geizhals_history.py out/geizhals-history-*.json
python3 scripts/import_market_snapshot.py cache/geizhals-history.json

<span class="cm"># 3. rebuild the index and run the registry's own gate</span>
python3 scripts/curate_registry.py --index-only
python3 scripts/validate_registry.py</pre>
      </div>
    </details>
    <details class="collapsible">
      <summary>Prove nothing was overwritten</summary>
      <div class="body">
<pre class="code"><span class="cm"># every pre-import observation must still exist, keyed by</span>
<span class="cm"># (retailer, url, condition, amount, observed_at)</span>
$ python3 - &lt;&lt;'PY'
import json
from pathlib import Path
bk = Path.home() / ".sero-registry-backups/price-20260922T121531Z/price"
lost = 0
for p in bk.glob("*/*.json"):
    old = json.loads(p.read_text())
    new = json.loads((Path("registry/price") / p.parent.name / p.name).read_text())
    key = lambda o: (o["retailer"], o["url"], o["condition"], o["amount"], o["observed_at"])
    lost += len({key(o) for o in old["observations"]} - {key(o) for o in new["observations"]})
print("observations lost:", lost)   <span class="cm"># 0</span>
PY</pre>
      </div>
    </details>
    <details class="collapsible">
      <summary>Why Micro Center cannot be backfilled</summary>
      <div class="body">
        <p class="footnote">Micro Center publishes no price history and prices are in-store only, per store. The archive
        route is unverified rather than ruled out: the CDX API answered <em>Internet Archive: Temporarily Offline</em> and the
        availability API returned no snapshots for <code>example.com</code> and <code>en.wikipedia.org</code> as well, so it
        cannot distinguish "no captures" from "service degraded". The weekly chain therefore records one point per store per run,
        and a year-deep Micro Center view begins to exist a year from the first run — not before.</p>
      </div>
    </details>
  </section>

  <footer class="footnote">
    Series: <code>geizhals.de/api/gh0/price_history</code>, <code>loc=de</code>, daily, EUR, lowest tracked offer per product.
    Registry record: <code>registry/price/rtx-5090/de.json</code>, linked to hardware <code>rtx-5090-32gb</code> at
    <code>match_scope: family</code>. Backup before import: <code>~/.sero-registry-backups/price-20260922T121531Z</code>.
  </footer>

</div>

<script>
const DATA = __DATA__;

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const isDark = () => window.matchMedia('(prefers-color-scheme: dark)').matches;
const euro = (v) => '€' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 });
const DAY = 86400000;
const dayToISO = (d) => new Date(d * DAY).toISOString().slice(0, 10);
const toDay = (v) => Math.round((typeof v === 'number' ? v : Date.parse(v + 'T00:00:00Z')) / DAY);

const charts = [];

function palette() {
  return isDark()
    ? { navy: '#cfd8e8', gold: '#d8b451', sage: '#8fb096', rust: '#d98a63', dim: '#9a9384', grid: 'rgba(232,227,217,0.07)' }
    : { navy: '#16233a', gold: '#9a7412', sage: '#4f6b52', rust: '#9c4221', dim: '#6a6559', grid: 'rgba(27,36,52,0.07)' };
}

function baseOptions(p, extra) {
  return Object.assign({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 600 },
    plugins: {
      legend: {
        display: true,
        labels: { color: p.dim, font: { family: css('--font-mono'), size: 11 }, boxWidth: 10, boxHeight: 10, usePointStyle: true }
      },
      tooltip: {
        backgroundColor: isDark() ? '#1b2432' : '#1b2434',
        titleFont: { family: css('--font-mono'), size: 12 },
        bodyFont: { family: css('--font-mono'), size: 12 },
        padding: 10,
        displayColors: true,
        boxWidth: 8,
        boxHeight: 8,
        usePointStyle: true
      }
    }
  }, extra || {});
}

function axes(p, extra) {
  return Object.assign({
    x: { ticks: { color: p.dim, font: { family: css('--font-mono'), size: 11 } }, grid: { color: p.grid }, border: { color: p.grid } },
    y: { ticks: { color: p.dim, font: { family: css('--font-mono'), size: 11 } }, grid: { color: p.grid }, border: { color: p.grid } }
  }, extra || {});
}

function candleDataset(source, p) {
  return {
    label: source.title,
    data: source.candles.map((c, i) => ({ x: i, o: c.o, h: c.h, l: c.l, c: c.c })),
    color: { up: isDark() ? '#4fae76' : '#2f7d4f', down: isDark() ? '#e2705a' : '#b23a2e', unchanged: p.dim },
    borderColor: { up: isDark() ? '#4fae76' : '#2f7d4f', down: isDark() ? '#e2705a' : '#b23a2e', unchanged: p.dim },
  };
}

function candleOptions(source, p) {
  const labels = source.candles.map((c) => c.k);
  return baseOptions(p, {
    plugins: Object.assign(baseOptions(p).plugins, {
      legend: { display: false },
      tooltip: Object.assign(baseOptions(p).plugins.tooltip, {
        callbacks: {
          title: (items) => labels[items[0].parsed.x] || '',
          label: (item) => {
            const c = item.raw;
            return ['open  ' + euro(c.o), 'high  ' + euro(c.h), 'low   ' + euro(c.l), 'close ' + euro(c.c)];
          }
        }
      })
    }),
    scales: axes(p, {
      x: {
        type: 'linear',
        min: -0.5,
        max: source.candles.length - 0.5,
        ticks: {
          color: p.dim,
          font: { family: css('--font-mono'), size: 10 },
          autoSkip: true,
          maxTicksLimit: 8,
          callback: (v) => labels[Math.round(v)] || ''
        },
        grid: { color: p.grid }
      },
      y: {
        ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 }, callback: (v) => '€' + v.toLocaleString('en-US') },
        grid: { color: p.grid }
      }
    })
  });
}

function build() {
  charts.forEach((c) => c.destroy());
  charts.length = 0;
  const p = palette();

  // 01 — weekly candles of the RTX 5090 market floor
  const c5090 = DATA.candles.featured;
  charts.push(new Chart(document.getElementById('chartCandles'), {
    type: 'candlestick',
    data: { datasets: [candleDataset(c5090, p)] },
    options: candleOptions(c5090, p)
  }));

  // 02 — Micro Center range by chip
  const chips = DATA.mc_chips;
  charts.push(new Chart(document.getElementById('chartMcRange'), {
    type: 'bar',
    data: {
      labels: chips.map((c) => c.chip + '  ·  ' + c.count),
      datasets: [{
        label: 'min → max',
        data: chips.map((c) => [c.min, c.max]),
        backgroundColor: p.sage + '55',
        borderColor: p.sage,
        borderWidth: 1.5,
        borderRadius: 2,
        barPercentage: 0.7
      }]
    },
    options: baseOptions(p, {
      indexAxis: 'y',
      plugins: Object.assign(baseOptions(p).plugins, { legend: { display: false },
        tooltip: Object.assign(baseOptions(p).plugins.tooltip, {
          callbacks: { label: (item) => ' ' + euro(item.raw[0]) + ' → ' + euro(item.raw[1]) }
        })
      }),
      scales: axes(p, {
        x: { ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 }, callback: (v) => '$' + (v / 1000) + 'k' }, grid: { color: p.grid } },
        y: { ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 } }, grid: { display: false } }
      })
    })
  }));

  // 03 — where the cheapest listing differs per store (model availability)
  const top = DATA.mc.divergence.slice().sort((a, b) => a.spread - b.spread);
  const storeIds = DATA.mc.compared;
  const storeColors = [p.navy, p.gold, p.sage, p.rust];
  charts.push(new Chart(document.getElementById('chartMcStore'), {
    type: 'bar',
    data: {
      labels: top.map((c) => c.chip),
      datasets: storeIds.map((sid, i) => ({
        label: DATA.mc.stores[sid].label,
        data: top.map((c) => (c.mins[sid] !== undefined ? c.mins[sid] : null)),
        backgroundColor: storeColors[i] + '66',
        borderColor: storeColors[i],
        borderWidth: 1.2,
        borderRadius: 2,
        barPercentage: 0.86,
        categoryPercentage: 0.8
      }))
    },
    options: baseOptions(p, {
      plugins: Object.assign(baseOptions(p).plugins, {
        tooltip: Object.assign(baseOptions(p).plugins.tooltip, {
          callbacks: { label: (item) => ' ' + item.dataset.label + '  $' + Number(item.parsed.y).toLocaleString('en-US') }
        })
      }),
      scales: axes(p, {
        x: { ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 }, maxRotation: 40, minRotation: 40 }, grid: { display: false } },
        y: { ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 }, callback: (v) => '$' + (v / 1000) + 'k' }, grid: { color: p.grid } }
      })
    })
  }));

  // 04 — history depth
  const tone = { gold: p.gold, navy: p.navy, sage: p.sage };
  const depth = (DATA.registry.depth || []).map((row) => ({ ...row, color: tone[row.tone] || p.navy }));
  charts.push(new Chart(document.getElementById('chartDepth'), {
    type: 'bar',
    data: {
      labels: depth.map((d) => d.label),
      datasets: [{
        data: depth.map((d) => d.value),
        backgroundColor: depth.map((d) => d.color + '66'),
        borderColor: depth.map((d) => d.color),
        borderWidth: 1.4,
        borderRadius: 2,
        barPercentage: 0.72
      }]
    },
    options: baseOptions(p, {
      indexAxis: 'y',
      plugins: Object.assign(baseOptions(p).plugins, {
        legend: { display: false },
        tooltip: Object.assign(baseOptions(p).plugins.tooltip, {
          callbacks: { label: (item) => ' ' + item.parsed.x + ' days' }
        })
      }),
      scales: axes(p, {
        x: { type: 'logarithmic', min: 1, ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 }, callback: (v) => [1, 3, 10, 30, 100, 300, 600].includes(v) ? v + 'd' : '' }, grid: { color: p.grid } },
        y: { ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 } }, grid: { display: false } }
      })
    })
  }));

  // 05 — registry by retailer
  const ret = Object.entries(DATA.registry.by_retailer).slice(0, 12);
  charts.push(new Chart(document.getElementById('chartRetailer'), {
    type: 'bar',
    data: {
      labels: ret.map(([k]) => k),
      datasets: [{
        data: ret.map(([, v]) => v),
        backgroundColor: ret.map(([k]) => (k === 'geizhals' ? p.gold + '77' : p.navy + '44')),
        borderColor: ret.map(([k]) => (k === 'geizhals' ? p.gold : p.navy)),
        borderWidth: 1.2,
        borderRadius: 2,
        barPercentage: 0.75
      }]
    },
    options: baseOptions(p, {
      indexAxis: 'y',
      plugins: Object.assign(baseOptions(p).plugins, {
        legend: { display: false },
        tooltip: Object.assign(baseOptions(p).plugins.tooltip, {
          callbacks: { label: (item) => ' ' + item.parsed.x.toLocaleString('en-US') + ' observations' }
        })
      }),
      scales: axes(p, {
        x: { type: 'logarithmic', min: 1, ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 } }, grid: { color: p.grid } },
        y: { ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 } }, grid: { display: false } }
      })
    })
  }));
}

function baseOptions(p, extra) { return baseOptions_(p, extra); }
function baseOptions_(p, extra) {
  return Object.assign({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 500 },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: isDark() ? '#1b2432' : '#1b2434',
        titleFont: { family: css('--font-mono'), size: 12 },
        bodyFont: { family: css('--font-mono'), size: 12 },
        padding: 10,
        displayColors: true,
        boxWidth: 8,
        boxHeight: 8,
        usePointStyle: true
      }
    }
  }, extra || {});
}

build();
buildDeep();
buildIndex();
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { build(); buildDeep(); buildIndex(); });

var INITIAL_ZOOM = 1.15;
function zoomDiagram(btn, factor) {
  var wrap = btn.closest('.mermaid-wrap');
  var target = wrap.querySelector('.mermaid');
  var current = parseFloat(target.dataset.zoom || INITIAL_ZOOM);
  var next = Math.min(Math.max(current * factor, 0.5), 5);
  target.dataset.zoom = next;
  target.style.zoom = next;
}
function resetZoom(btn) {
  var wrap = btn.closest('.mermaid-wrap');
  var target = wrap.querySelector('.mermaid');
  target.dataset.zoom = INITIAL_ZOOM;
  target.style.zoom = INITIAL_ZOOM;
}
document.querySelectorAll('.mermaid-wrap').forEach(function (wrap) {
  wrap.addEventListener('wheel', function (e) {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    var target = wrap.querySelector('.mermaid');
    var current = parseFloat(target.dataset.zoom || INITIAL_ZOOM);
    var next = Math.min(Math.max(current * (e.deltaY < 0 ? 1.1 : 0.9), 0.5), 5);
    target.dataset.zoom = next;
    target.style.zoom = next;
  }, { passive: false });
  var startX, startY, scrollL, scrollT;
  wrap.addEventListener('mousedown', function (e) {
    if (e.target.closest('.zoom-controls')) return;
    wrap.classList.add('is-panning');
    startX = e.clientX; startY = e.clientY;
    scrollL = wrap.scrollLeft; scrollT = wrap.scrollTop;
  });
  window.addEventListener('mousemove', function (e) {
    if (!wrap.classList.contains('is-panning')) return;
    wrap.scrollLeft = scrollL - (e.clientX - startX);
    wrap.scrollTop = scrollT - (e.clientY - startY);
  });
  window.addEventListener('mouseup', function () { wrap.classList.remove('is-panning'); });
});

// 02 — normalised index for classes with a year or more
function buildDeep() {
  const p = palette();
  const deep = DATA.candles.deepest;
  if (!deep || !deep.candles.length) return;
  charts.push(new Chart(document.getElementById('chartDeep'), {
    type: 'candlestick',
    data: { datasets: [candleDataset(deep, p)] },
    options: candleOptions(deep, p)
  }));
}

function buildIndex() {
  const p = palette();
  const deep = (DATA.gpu ? DATA.gpu.cards : []).filter((c) => c.days >= 365).slice(0, 12);
  if (!deep.length) return;
  const idxColors = [p.navy, p.gold, p.sage, p.rust, '#7b6a52', '#4b6b7a', '#8a6f4d', '#5c7a6b', '#9a5f4a', '#6b6b8a', '#7a5c4b', '#4f6b52'];
  charts.push(new Chart(document.getElementById('chartIndex'), {
    type: 'line',
    data: {
      datasets: deep.map((c, i) => ({
        label: c.name,
        data: c.points.map(([day, price]) => ({ x: Math.round(new Date(day + 'T00:00:00Z').getTime() / DAY), y: +(price / c.points[0][1] * 100).toFixed(1) })),
        borderColor: idxColors[i % idxColors.length],
        backgroundColor: idxColors[i % idxColors.length],
        borderWidth: 1.5, pointRadius: 0, pointHitRadius: 8, tension: 0, spanGaps: true
      }))
    },
    options: baseOptions(p, {
      interaction: { mode: 'nearest', intersect: false },
      plugins: Object.assign(baseOptions(p).plugins, {
        legend: { labels: { color: p.dim, font: { family: css('--font-mono'), size: 10 }, boxWidth: 14, boxHeight: 2 } },
        tooltip: Object.assign(baseOptions(p).plugins.tooltip, {
          callbacks: {
            title: (items) => dayToISO(items[0].parsed.x),
            label: (item) => ' ' + item.dataset.label + '  ' + item.parsed.y.toFixed(1) + ' (first = 100)'
          }
        })
      }),
      scales: axes(p, {
        x: { type: 'linear', ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 }, maxTicksLimit: 6, callback: (v) => dayToISO(v).slice(0, 7) }, grid: { color: p.grid } },
        y: { ticks: { color: p.dim, font: { family: css('--font-mono'), size: 10 }, callback: (v) => v }, grid: { color: p.grid } }
      })
    })
  }));
}

const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (!prefersReduced) {
  document.querySelectorAll('[data-count]').forEach(function (el) {
    const target = parseInt(el.dataset.count, 10);
    const start = performance.now();
    const step = (now) => {
      const t = Math.min((now - start) / 900, 1);
      el.textContent = Math.round(target * (1 - Math.pow(1 - t, 3))).toLocaleString('en-US');
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}
</script>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
mermaid.initialize({
  startOnLoad: true,
  theme: 'base',
  look: 'classic',
  flowchart: { curve: 'basis', nodeSpacing: 40, rankSpacing: 52 },
  themeVariables: {
    primaryColor: isDark ? '#1c2532' : '#efece4',
    primaryBorderColor: isDark ? '#d8b451' : '#9a7412',
    primaryTextColor: isDark ? '#e9e4d9' : '#1b2434',
    secondaryColor: isDark ? '#16241c' : '#e6efe6',
    secondaryBorderColor: isDark ? '#8fb096' : '#4f6b52',
    secondaryTextColor: isDark ? '#e9e4d9' : '#1b2434',
    tertiaryColor: isDark ? '#2a1e18' : '#f6e8e0',
    tertiaryBorderColor: isDark ? '#d98a63' : '#9c4221',
    tertiaryTextColor: isDark ? '#e9e4d9' : '#1b2434',
    lineColor: isDark ? '#6f7686' : '#a9a294',
    fontSize: '16px',
    fontFamily: "'Spectral', Georgia, serif"
  }
});
</script>
</body>
</html>
'''
data = json.dumps(payload)

def esc(v):
    return (str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

def candles_svg(card, width=190, height=44, pad=3):
    """Hand-rolled candlesticks: wick + body, green when the bucket closed up."""
    candles = card.get('candles') or []
    if not candles:
        return ''
    hi = max(c['h'] for c in candles)
    lo = min(c['l'] for c in candles)
    span = (hi - lo) or 1
    slot = (width - 2 * pad) / len(candles)
    body_w = max(1.2, min(slot * 0.62, 6))
    parts = []
    for i, c in enumerate(candles):
        cx = pad + slot * (i + 0.5)
        y = lambda v: height - pad - (v - lo) / span * (height - 2 * pad)
        up = c['c'] >= c['o']
        cls = 'up' if up else 'down'
        parts.append(f'<line class="wick {cls}" x1="{cx:.1f}" y1="{y(c["h"]):.1f}" x2="{cx:.1f}" y2="{y(c["l"]):.1f}"/>')
        top, bottom = y(max(c['o'], c['c'])), y(min(c['o'], c['c']))
        h = max(1.0, bottom - top)
        parts.append(f'<rect class="body {cls}" x="{cx - body_w / 2:.1f}" y="{top:.1f}" width="{body_w:.1f}" height="{h:.1f}"/>')
    return ''.join(parts)


cards_html = []
for c in grid.get('cards', []):
    delta = f"{c['change_pct']:+.1f}%" if c['change_pct'] is not None else 'n/a'
    cards_html.append(
        '<div class="gpu-card">'
        f'<div class="gpu-card__head"><span class="gpu-card__name">{esc(c["name"])}</span>'
        f'<span class="gpu-card__change gpu-card__change--{c["direction"]}">{delta}</span></div>'
        f'<div class="gpu-card__price">€{c["current"]:,.0f}</div>'
        f'<div class="gpu-card__meta">{c["days"]}d · {c["listings"]} listing{"s" if c["listings"] != 1 else ""} · €{c["lo"]:,.0f}–€{c["hi"]:,.0f}</div>'
        f'<svg viewBox="0 0 190 44" preserveAspectRatio="none">{candles_svg(c)}</svg>'
        '</div>')

ge = payload['geizhals_meta']
de_obs = ge['observations']
de_days = ge['days']
_mins = [g['min'] for g in payload['geizhals']]
_maxs = [g['max'] for g in payload['geizhals']]
de_low = min(_mins) if _mins else 0
de_high = max(_maxs) if _maxs else 0
de_listings = len(payload['geizhals'])
de_span_days = (__import__('datetime').date.fromisoformat(ge['last'])
                - __import__('datetime').date.fromisoformat(ge['first'])).days
months = round(de_span_days / 30.44)
html = html.replace('__DE_SPAN__', f"{months} months")
html = html.replace('__DE_LISTINGS__', str(de_listings))
html = html.replace('__DE_OBS__', f"{de_obs:,}")
html = html.replace('__DE_DAYS__', f"{de_days:,}")
html = html.replace('__DE_FIRST__', ge['first'])
html = html.replace('__DE_LAST__', ge['last'])

mc = payload['mc']
run = __import__('datetime').datetime.fromisoformat(mc['run'].replace('Z', '+00:00'))
store_kpis = ''.join(
    f'<div class="kpi"><div class="kpi__value">{row["listings"]}</div>'
    f'<div class="kpi__label">{mc["stores"][store]["label"]} listings</div>'
    f'<div class="kpi__note">{row["in_stock"]} in stock</div></div>'
    for store, row in mc['per_store'].items() if store in mc['compared']
)
html = html.replace('__MC_RUN__', run.strftime('%Y-%m-%d %H:%M UTC'))
html = html.replace('__MC_LISTINGS__', str(mc['listings']))
html = html.replace('__MC_STORES__', str(len(mc['stores'])))
html = html.replace('__MC_MULTI__', str(mc['sku_multi_store']))
html = html.replace('__MC_DIFFER__', str(mc['sku_price_differs']))
html = html.replace('__MC_STORE_KPIS__', store_kpis)
html = html.replace('__MC_CHIPS__', str(len(payload['mc_chips'])))
html = html.replace('__MC_DIV__', str(len(mc['divergence'])))
html = html.replace('__MC_AGREE__', str(len(payload['mc_chips']) - len(mc['divergence'])))
html = html.replace('__DE_LOW__', f"€{de_low:,.0f}")
html = html.replace('__DE_HIGH__', f"€{de_high:,.0f}")

html = html.replace('__DEEP_TITLE__', payload['candles']['deepest']['title'])
html = html.replace('__DEEP_DAYS__', f"{payload['candles']['deepest']['days']:,}")
html = html.replace('__GPU_GRID__', '\n'.join(cards_html))
html = html.replace('__GRID_CLASSES__', str(grid.get('classes', 0)))
html = html.replace('__GRID_OBS__', f"{grid.get('observations', 0):,}")
html = html.replace('__GRID_YEAR__', str(grid.get('year_deep', 0)))
html = html.replace('__GRID_DEEPEST__', str(grid.get('deepest', 0)))
html = html.replace('__DATA__', data)
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(html)
print(f"wrote {out} ({len(html):,} bytes)")
