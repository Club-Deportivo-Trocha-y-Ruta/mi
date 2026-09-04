#!/usr/bin/env bash
# check-chart-chunk.sh — build gate for specs/040-growth-module-redesign (SC-005).
#
# Verifies that recharts and the WHO growth-reference data are NOT reachable
# from the first paint (the entry route). Fails when:
#
#   1. dist/index.html <link rel="modulepreload"> references the chunk that
#      contains the string "recharts-wrapper" (the chunk Vite hoists recharts
#      into), or
#   2. the entry chunk (dist/assets/index-*.js) has a static import of that
#      same chunk — pattern `from"./<chunk>"` or `import"./<chunk>"`, or
#   3. the entry chunk contains the string "WHO 2007 Growth Reference".
#
# Expected to FAIL until Phase 7 of specs/040-growth-module-redesign/tasks.md
# lazy-loads the growth tab (React.lazy + Suspense) and moves the WHO JSON
# behind a dynamic import() inside the chart module.
#
# Usage: npm run check:chunks   (run from anywhere inside the frontend/ tree)

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DIST_DIR="dist"
ASSETS_DIR="$DIST_DIR/assets"
INDEX_HTML="$DIST_DIR/index.html"

if [ ! -d "$DIST_DIR" ]; then
  echo "check-chart-chunk: $DIST_DIR not found — running npm run build first" >&2
  npm run build
fi

if [ ! -f "$INDEX_HTML" ]; then
  echo "check-chart-chunk: $INDEX_HTML not found after build" >&2
  exit 1
fi

ENTRY_FILE=$(find "$ASSETS_DIR" -maxdepth 1 -type f -name 'index-*.js' | head -n 1)
if [ -z "$ENTRY_FILE" ]; then
  echo "check-chart-chunk: could not find entry chunk $ASSETS_DIR/index-*.js" >&2
  exit 1
fi
ENTRY_BASENAME=$(basename "$ENTRY_FILE")

# Locate the chunk that bundles recharts. Vite names it unpredictably
# (currently useAthleteInsights-*.js), so detect it by content, not by name.
RECHARTS_FILE=""
for f in "$ASSETS_DIR"/*.js; do
  if grep -q "recharts-wrapper" "$f" 2>/dev/null; then
    RECHARTS_FILE="$f"
    break
  fi
done

FAILED=0

if [ -n "$RECHARTS_FILE" ]; then
  RECHARTS_BASENAME=$(basename "$RECHARTS_FILE")
  echo "check-chart-chunk: recharts chunk is $RECHARTS_BASENAME"

  if grep -oE '<link[^>]*href="[^"]*'"$RECHARTS_BASENAME"'"[^>]*>' "$INDEX_HTML" 2>/dev/null | grep -q 'modulepreload'; then
    echo "FAIL: $INDEX_HTML module-preloads $RECHARTS_BASENAME" >&2
    FAILED=1
  fi

  if grep -qE '(from|import)"\./'"$RECHARTS_BASENAME"'"' "$ENTRY_FILE"; then
    echo "FAIL: entry chunk $ENTRY_BASENAME statically imports $RECHARTS_BASENAME" >&2
    FAILED=1
  fi
else
  echo "check-chart-chunk: no chunk containing \"recharts-wrapper\" was found in $ASSETS_DIR (recharts may already be fully lazy)"
fi

if grep -q "WHO 2007 Growth Reference" "$ENTRY_FILE"; then
  echo "FAIL: entry chunk $ENTRY_BASENAME contains \"WHO 2007 Growth Reference\"" >&2
  FAILED=1
fi

if [ "$FAILED" -ne 0 ]; then
  echo "check-chart-chunk: FAILED — recharts and/or the WHO growth reference are still reachable from first paint." >&2
  exit 1
fi

echo "check-chart-chunk: OK — recharts chunk and WHO growth reference are not on the entry path."
