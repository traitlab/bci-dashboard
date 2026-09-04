#!/usr/bin/env bash
# Daily model-health refresh: fold the newest Labelbox export into the ground
# truth, snapshot, rebuild both cumulative pages. Safe to re-run:
#
# Every run re-measures into build/tables and rebuilds both pages from it. A
# snapshot folder is a record of a day the labels moved, and nothing reads it
# back: the deliverable is build/tables/send_batches.csv.
#
# - a snapshot folder for today already exists  -> stop (a same-day GT change
#   is a human event; handle it by hand)
# - no new export since the last merge          -> nothing to do
# - the export adds no new labels               -> pages rebuilt, no new folder
# - otherwise                                   -> pages rebuilt, and today's
#   tables and pages kept in model-health-<date>/
#
# Exports come from the Labelbox UI (the account here has no API export
# permission): download the project NDJSON, it lands in ~/Downloads, and this
# script finds it. An explicit path also works: refresh.sh path/to/export.ndjson
# Run by hand. Nothing in the repo schedules it; a daily run is a launchd agent
# or a cron line somebody writes on the machine that holds the Labelbox export.
set -euo pipefail

REPO="${BCI_DASHBOARD_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DOCS="${BCI_DASHBOARD_SNAPSHOTS:-$REPO/snapshots}"
GT="$REPO/data/gt_dominant_taxon.csv"
MARKER="$REPO/data/last_merged_export.txt"
TODAY="$(date +%F)"
SNAP="$DOCS/model-health-$TODAY"

cd "$REPO"

if [ -d "$SNAP" ]; then
  echo "refresh: $SNAP already exists; nothing to do"
  exit 0
fi

# Newest NDJSON from the drop folder or Downloads, unless one was passed in.
if [ $# -ge 1 ]; then
  EXPORT="$1"
else
  EXPORT="$(ls -t "$REPO"/data/exports/*.ndjson "$HOME"/Downloads/*.ndjson 2>/dev/null | head -1 || true)"
fi
if [ -z "${EXPORT:-}" ] || [ ! -s "$EXPORT" ]; then
  echo "refresh: no export found; drop the project NDJSON into data/exports/ or Downloads"
  exit 0
fi

HASH="$(md5 -q "$EXPORT")"
if [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$HASH" ]; then
  echo "refresh: newest export already merged ($EXPORT); nothing to do"
  exit 0
fi

# Fold the export into the GT. Back up first (the sidecar too: gt_from_export.py rewrites
# it on every run, and a no-change merge must not restamp the batch's date);
# drop the backups when the merge changed nothing.
BAK="${GT%.csv}_$TODAY.csv"
SIDECAR="${GT%.csv}.provenance.txt"
cp "$GT" "$BAK"
[ -f "$SIDECAR" ] && cp "$SIDECAR" "$BAK.provenance.txt"
BEFORE="$(md5 -q "$GT")"
python3 labelling/gt_from_export.py \
  --export "$EXPORT" \
  --note "Ground truth: Labelbox project 2024_bci export of $TODAY, not yet reviewed."
AFTER="$(md5 -q "$GT")"
echo "$HASH" > "$MARKER"

# Always re-measure. build/tables is what the pages cross-check against, and a
# change to the code that writes a table moves it even when no label did.
python3 dashboard/measure.py --out-dir "$REPO/build/tables" > /dev/null

python3 dashboard/build_external.py \
  --out "$REPO/build/model_health_dashboard.html" --generated "$TODAY"
python3 dashboard/build_internal.py \
  --out "$REPO/build/label_queue_dashboard.html" --generated "$TODAY"

if [ "$BEFORE" = "$AFTER" ]; then
  rm "$BAK"
  [ -f "$BAK.provenance.txt" ] && mv "$BAK.provenance.txt" "$SIDECAR"
  echo "refresh: no new labels; pages rebuilt, no new snapshot"
else
  # The labels moved, so today is a point worth keeping. A snapshot is that
  # record and nothing reads it back: the deliverable is build/tables.
  echo "refresh: GT moved ($BAK kept); new snapshot $SNAP"
  mkdir -p "$SNAP"
  cp "$REPO"/build/tables/* "$SNAP/"
  cp "$REPO/build/model_health_dashboard.html" "$SNAP/"
  cp "$REPO/build/label_queue_dashboard.html" "$SNAP/"
fi

# The published copies. Staged into docs/ rather than pushed, because what goes
# on the public site is a commit somebody made and can point at, not a side
# effect of a local run.
"$REPO/bin/publish_pages.sh"

echo "refresh: done"
