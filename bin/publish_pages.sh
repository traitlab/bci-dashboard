#!/usr/bin/env bash
# Copy the built dashboards into their two tiers: public into docs/, which
# GitHub Pages serves, and private into build/private/, which is gitignored.
#
# Expert labels stay private until publication. build/ holds the full pages, the
# private tier. build/public/ holds the same pages built with --public: no
# per-frame label, no Labelbox link, no labelling queue. Each tier gets its pages,
# the CSVs they link, and dashboard/build_index.py's index.html and about.html.
# Both the local refresh and the CI refresh (bin/refresh_snapshot.py) call it.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$REPO/build"
DOCS="$REPO/docs"

# The pages each tier publishes, named once: the checks below, the copy, and the
# CSV scan all read them from here. label_queue_team.html is not a page: it is
# the redirect dashboard/build_internal.py writes beside the queue page, left at
# the address the team's own copy used to have so old links still land.
PRIVATE_PAGES="model_health_dashboard.html label_queue_dashboard.html label_queue_team.html"
PUBLIC_PAGES="model_health_dashboard.html"

# publish FROM TO PAGES: copy PAGES, the standalone explorers FROM holds, and
# every CSV they link, then write the index and About page over what TO holds.
publish() {
  local from="$1" to="$2" pages="$3" f
  for f in $pages; do
    [ -s "$from/$f" ] || { echo "publish: $from/$f is missing or empty; run bin/refresh.sh first" >&2; exit 1; }
  done

  # Standalone explorers carry their browser data in the HTML.
  # Raw embedding matrices and intermediate JSON exports are never copied.
  for f in explorer.html embedding-atlas.html crownfirst-atlas.html; do
    if [ -s "$from/$f" ]; then
      pages="$pages $f"
    fi
  done

  mkdir -p "$to"
  # .nojekyll or Pages runs the files through Jekyll, which drops anything whose
  # name starts with an underscore and rewrites nothing else usefully.
  touch "$to/.nojekyll"

  for f in $pages; do
    cp "$from/$f" "$to/$f"
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
  for f in $(cd "$from" && grep -ho 'href="[A-Za-z0-9_]*\.csv"' $pages \
             | sed 's/.*"\(.*\)"/\1/' | sort -u); do
    [ -s "$from/$f" ] || { echo "publish: the pages link $f, absent from $from" >&2; exit 1; }
    cp "$from/$f" "$to/$f"
    echo "  published $f"
  done

  # Keep already-published standalone explorers discoverable when only the
  # operational pages were rebuilt during this refresh.
  python3 "$REPO/dashboard/build_index.py" --build "$to" --out "$to/index.html" --about-out "$to/about.html"
}

echo "publish: private tier, $BUILD/private"
publish "$BUILD" "$BUILD/private" "$PRIVATE_PAGES"
echo "publish: public tier, $DOCS"
publish "$BUILD/public" "$DOCS" "$PUBLIC_PAGES"

echo "publish: docs/ updated. Commit it to put the change on the site."
