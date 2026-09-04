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

# The two pages this script publishes, named once: the checks below, the copy,
# and the CSV scan all read them from here.
PAGES="model_health_dashboard.html label_queue_dashboard.html"

for f in $PAGES; do
  [ -s "$BUILD/$f" ] || { echo "publish: $BUILD/$f is missing or empty; run bin/refresh.sh first" >&2; exit 1; }
done

mkdir -p "$DOCS"
# .nojekyll or Pages runs the files through Jekyll, which drops anything whose
# name starts with an underscore and rewrites nothing else usefully.
touch "$DOCS/.nojekyll"

for f in $PAGES; do
  cp "$BUILD/$f" "$DOCS/$f"
  echo "  published $f"
done

# The pages link their CSVs relatively, so the CSVs travel with them or the
# links 404 on the published copy while working locally. The list is read out of
# the built pages, not kept here: a list written here drifts the moment a panel
# adds a link, and it drifts into a 404 on the public site rather than into an
# error anybody sees. dashboard/page.py reads the same links for build/, for the
# same reason. A linked file missing from build/ stops the publish: the builder
# already refused to write a page whose CSV was absent, so by here it means
# build/ was changed underneath us.
for f in $(cd "$BUILD" && grep -ho 'href="[A-Za-z0-9_]*\.csv"' $PAGES \
           | sed 's/.*"\(.*\)"/\1/' | sort -u); do
  [ -s "$BUILD/$f" ] || { echo "publish: the pages link $f, absent from $BUILD" >&2; exit 1; }
  cp "$BUILD/$f" "$DOCS/$f"
  echo "  published $f"
done

python3 "$REPO/dashboard/build_index.py" --build "$BUILD" --out "$DOCS/index.html"

echo "publish: docs/ updated. Commit it to put the change on the site."
