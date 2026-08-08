#!/usr/bin/env bash
# Daily model-health refresh: fold the newest Labelbox export into the ground
# truth, snapshot, rebuild both dashboard pages. Safe to re-run:
#
# - a snapshot folder for today already exists  -> stop (a same-day GT change
#   is a human event; handle it by hand)
# - no new export since the last merge          -> nothing to do
# - the export adds no new labels               -> rebuild the pages against
#   the newest snapshot, no new folder
# - otherwise                                   -> new model-health-<date>/
#   folder, both pages rebuilt and verified against it
#
# Exports come from the Labelbox UI (the account here has no API export
# permission): download the project NDJSON, it lands in ~/Downloads, and this
# script finds it. An explicit path also works: refresh.sh path/to/export.ndjson
# Intended to be run by launchd (org.bci.dashboard-refresh.plist) or by hand.
set -euo pipefail

REPO="$REPO"
DOCS="$(dirname "$REPO")/bci_workshop_labelbox_plantnet-docs"
GT="$REPO/output/15_active_selection/gt_dominant_taxon.csv"
MARKER="$REPO/output/15_active_selection/last_merged_export.txt"
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

# Fold the export into the GT. Back up first (the sidecar too: 15a2 rewrites
# it on every run, and a no-change merge must not restamp the batch's date);
# drop the backups when the merge changed nothing.
BAK="${GT%.csv}_$TODAY.csv"
SIDECAR="${GT%.csv}.provenance.txt"
cp "$GT" "$BAK"
[ -f "$SIDECAR" ] && cp "$SIDECAR" "$BAK.provenance.txt"
BEFORE="$(md5 -q "$GT")"
python3 scripts/15_active_selection/15a2_gt_from_labelbox_export.py \
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
  python3 scripts/16_dashboard/16_model_health.py --out-dir "$SNAP" > /dev/null
fi

python3 scripts/16_dashboard/16b_dashboard.py --verify-against "$SNAP" \
  --out "$REPO/output/16_dashboard/model_health_dashboard.html" --generated "$TODAY"
python3 scripts/16_dashboard/16c_simple_dashboard.py \
  --out "$REPO/output/16_dashboard/simple_dashboard.html" --generated "$TODAY"
cp "$REPO/output/16_dashboard/model_health_dashboard.html" "$SNAP/"
cp "$REPO/output/16_dashboard/simple_dashboard.html" "$SNAP/"
echo "refresh: done; snapshot $SNAP"
