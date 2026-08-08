#!/usr/bin/env bash
# Daily model-health refresh: export labels, fold into the ground truth,
# snapshot, rebuild both dashboard pages. Safe to re-run:
#
# - a snapshot folder for today already exists  -> stop (a same-day GT change
#   is a human event; handle it by hand)
# - the export adds no new labels               -> rebuild the pages against
#   the newest snapshot, no new folder
# - otherwise                                   -> new model-health-<date>/
#   folder, both pages rebuilt and verified against it
#
# Labelbox access is the read-only export in 15a0; nothing here writes to
# Labelbox. Intended to be run by launchd (org.bci.dashboard-refresh.plist)
# or by hand.
set -euo pipefail

REPO="$REPO"
DOCS="$(dirname "$REPO")/bci_workshop_labelbox_plantnet-docs"
GT="$REPO/output/15_active_selection/gt_dominant_taxon.csv"
TODAY="$(date +%F)"
SNAP="$DOCS/model-health-$TODAY"
EXPORT="$REPO/data/exports/project_2024_bci_$TODAY.ndjson"

cd "$REPO"

if [ -d "$SNAP" ]; then
  echo "refresh: $SNAP already exists; nothing to do"
  exit 0
fi

if [ ! -s "$EXPORT" ]; then
  .venv/bin/python scripts/15_active_selection/15a0_export_project_labels.py \
    --project 2024_bci --out "$EXPORT"
fi

# Fold the export into the GT. Back up first; drop the backup when the merge
# changed nothing (the common case on a day with no new labels).
BAK="${GT%.csv}_$TODAY.csv"
cp "$GT" "$BAK"
BEFORE="$(md5 -q "$GT")"
python3 scripts/15_active_selection/15a2_gt_from_labelbox_export.py \
  --export "$EXPORT" \
  --note "Ground truth: Labelbox project 2024_bci export of $TODAY, not yet reviewed."
AFTER="$(md5 -q "$GT")"

if [ "$BEFORE" = "$AFTER" ]; then
  rm "$BAK"
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
