#!/usr/bin/env bash
# Copy the built dashboards into docs/, which GitHub Pages serves.
#
# The build reads data/ and snapshots/, both gitignored, so CI cannot rebuild
# the pages. What gets published is therefore whatever was built locally and
# committed here, and that is the reason this is a copy step rather than a
# workflow: the page and the commit that carries it are the same act.
#
# Run after bin/refresh.sh, then commit docs/.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$REPO/build"
DOCS="$REPO/docs"

for f in model_health_dashboard.html label_queue_dashboard.html; do
  [ -s "$BUILD/$f" ] || { echo "publish: $BUILD/$f is missing or empty; run bin/refresh.sh first" >&2; exit 1; }
done

mkdir -p "$DOCS"
# .nojekyll or Pages runs the files through Jekyll, which drops anything whose
# name starts with an underscore and rewrites nothing else usefully.
touch "$DOCS/.nojekyll"

# The pages link their CSVs relatively, so the CSVs travel with them or the
# download buttons 404 on the published copy while working locally.
for f in model_health_dashboard.html label_queue_dashboard.html \
         per_species_health.csv label_review_queue.csv \
         send_batches.csv send_first_queue.csv; do
  if [ -s "$BUILD/$f" ]; then
    cp "$BUILD/$f" "$DOCS/$f"
    echo "  published $f"
  else
    echo "  SKIPPED  $f (not in build/)" >&2
  fi
done

python3 "$REPO/dashboard/build_index.py" --build "$BUILD" --out "$DOCS/index.html"

echo "publish: docs/ updated. Commit it to put the change on the site."
