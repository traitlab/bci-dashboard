#!/usr/bin/env bash
# Daily model-health refresh: fold the newest Labelbox export into the ground
# truth, snapshot, rebuild every dashboard page. Safe to re-run:
#
# - a snapshot folder for today already exists  -> stop (a same-day GT change
#   is a human event; handle it by hand)
# - no new export since the last merge          -> nothing to do
# - the export adds no new labels               -> rebuild the pages against
#   the newest snapshot, no new folder
# - otherwise                                   -> new model-health-<date>/
#   folder, every page rebuilt and verified against it
#
# Exports come from the Labelbox UI (the account here has no API export
# permission): download the project NDJSON, it lands in ~/Downloads, and this
# script finds it. An explicit path also works: refresh.sh path/to/export.ndjson
# Intended to be run by launchd (org.bci.dashboard-refresh.plist) or by hand.
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

if [ "$BEFORE" = "$AFTER" ]; then
  rm "$BAK"
  [ -f "$BAK.provenance.txt" ] && mv "$BAK.provenance.txt" "$SIDECAR"
  SNAP="$(ls -d "$DOCS"/model-health-* | sort | tail -1)"
  echo "refresh: no new labels; rebuilding pages against $SNAP"
else
  echo "refresh: GT moved ($BAK kept); new snapshot $SNAP"
  mkdir -p "$SNAP"
  python3 dashboard/measure.py --out-dir "$SNAP" > /dev/null
fi

python3 dashboard/build_external.py --verify-against "$SNAP" \
  --out "$REPO/build/model_health_dashboard.html" --generated "$TODAY"
python3 dashboard/build_internal.py --verify-against "$SNAP" \
  --out "$REPO/build/label_queue_dashboard.html" --generated "$TODAY"
python3 dashboard/build_simple.py \
  --out "$REPO/build/simple_dashboard.html" --generated "$TODAY"
cp "$REPO/build/model_health_dashboard.html" "$SNAP/"
cp "$REPO/build/label_queue_dashboard.html" "$SNAP/"
cp "$REPO/build/simple_dashboard.html" "$SNAP/"
echo "refresh: done; snapshot $SNAP"
