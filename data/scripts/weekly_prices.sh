#!/bin/bash
# Weekly GPU price accumulation.
#
# Micro Center publishes no price history, so the only way to build a series is to
# record a snapshot on a schedule. This runs the whole chain from one place:
#
#   scrape (US SOCKS tunnel) -> verify -> map to the registry contract ->
#   merge observations -> Geizhals refresh -> enrich -> index -> validate ->
#   rebuild the price-history visual
#
# The registry keeps every observation in registry/price/<product>/<region>.json, so
# each run appends one weekly point to the series instead of replacing it.
# Committing and pushing the registry is deliberately left to review.
#
# Install (weekly, Sundays 09:00) once a manual run looks right:
#   ln -sf "$PWD/scripts/weekly_prices.sh" ~/bin/local-ai-weekly-prices
#   cat > ~/Library/LaunchAgents/com.sero.local-ai-weekly-prices.plist <<PLIST
#   ... see scripts/README.md ...
# PLIST
#   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sero.local-ai-weekly-prices.plist
#
# Usage: scripts/weekly_prices.sh [--dry-run]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STORES="${MC_STORES:-all}"
LOG="${MC_LOG:-$ROOT/cache/weekly-prices.log}"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DRY_RUN=0

[ "${1:-}" = "--dry-run" ] && DRY_RUN=1
mkdir -p "$(dirname "$LOG")"

log() { printf '%s %s\n' "$STAMP" "$*" | tee -a "$LOG"; }

log "starting weekly price accumulation (stores=$STORES)"

if [ "$DRY_RUN" = 1 ]; then
  log "dry run: would scrape $STORES, verify, map, import, refresh Geizhals, enrich, index, validate, rebuild the visual"
  exit 0
fi

# 1. Scrape every configured store through the US tunnel. The scraper raises its
#    own ssh -D tunnel to the US host and tears it down afterwards.
log "scraping…"
python3 scripts/scrape_microcenter_prices.py --stores "$STORES" --out out --delay 4 --max-pages 12 >>"$LOG" 2>&1
log "scrape done: $(ls -1 out/run-*.json 2>/dev/null | wc -l | tr -d ' ') runs on disk"

# 2. Internal consistency of the new run (missing prices, duplicate SKUs, coverage).
python3 scripts/verify_microcenter_scrape.py out/latest.json >>"$LOG" 2>&1

# 3. Map the scrape onto the registry contract and merge the observations, so the
#    new weekly point joins the existing series instead of replacing it.
python3 scripts/fetch_microcenter_prices.py out/latest.json >>"$LOG" 2>&1
python3 scripts/import_market_snapshot.py cache/microcenter-prices.json >>"$LOG" 2>&1
python3 scripts/enrich_hardware_prices.py >>"$LOG" 2>&1

# 4. Refresh the Geizhals DE price history, the only year-deep GPU series this
#    registry can reach. Best effort: Cloudflare can refuse the browser session, and
#    that must not cost the Micro Center point, because the importer keeps every
#    observation already recorded either way.
log "refreshing Geizhals DE price history…"
if python3 scripts/scrape_geizhals_history.py --days 365 --pages 2 --limit 60 >>"$LOG" 2>&1; then
  DUMP=$(ls -t out/geizhals-history-*.json | head -1)
  python3 scripts/fetch_geizhals_history.py "$DUMP" >>"$LOG" 2>&1
  python3 scripts/import_market_snapshot.py cache/geizhals-history.json >>"$LOG" 2>&1
else
  log "geizhals refresh failed (Cloudflare?); keeping the observations already recorded"
fi

# 5. Rebuild the index over both sources and run the registry's own gate, which
#    must pass before either point is trusted.
python3 scripts/curate_registry.py --index-only >>"$LOG" 2>&1
python3 scripts/validate_registry.py | tee -a "$LOG"

# 6. Rebuild the price-history visual from the records that just changed.
python3 scripts/build_price_history_data.py >>"$LOG" 2>&1
python3 scripts/gen_price_history_visual.py >>"$LOG" 2>&1

log "done; review the registry diff and the visual, then commit/push to extend the series"
