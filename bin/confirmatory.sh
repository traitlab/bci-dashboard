#!/usr/bin/env bash
# Carry the confirmatory tiles arm to completion across the days the quota
# needs, then score it once. Safe to re-run and safe to run daily:
#
# - frames already in the cache are skipped, so nothing is paid for twice
# - predict/tiles.py stops itself the moment the quadrat quota is exhausted
#   and says so, rather than burning the rest of the list on failures
# - the scorer refuses to print a confirmatory read until both region-aligned
#   arms hold all 300, so an early run can only produce a labelled EXPLORATORY
#   report, never a result
#
# 300 frames at 140 quadrat credits is 42,000 against 20,000/day, so this takes
# three calendar days from a standing start. The point of the script is that
# nobody has to remember which day it is.
#
#     bin/confirmatory.sh            # fetch what today's quota allows, then score
#
set -euo pipefail
cd "$(dirname "$0")/.."

FROZEN=input/confirmatory_frames_2026-08.csv
PY=.venv/bin/python
LOG=data/confirmatory_fetch.log

# --limit is the daily ceiling, not a target: 20000/140 = 142 frames. Passing it
# means a run cannot overshoot the quota even if the balance is misread.
"$PY" predict/tiles.py --frames "$FROZEN" --limit 142 --workers 3 2>&1 | tee -a "$LOG"

frozen=$(( $(wc -l < "$FROZEN") - 1 ))
cached=$("$PY" - "$FROZEN" <<'PYEOF'
import csv, pathlib, sys
cache = pathlib.Path("data/tiles/cache")
with open(sys.argv[1], newline="", encoding="utf-8") as fh:
    print(sum((cache / f"{r['base_image']}.json").exists() for r in csv.DictReader(fh)))
PYEOF
)

echo "tiles arm: ${cached}/${frozen} frames" | tee -a "$LOG"
if [ "$cached" -lt "$frozen" ]; then
    echo "not complete; re-run tomorrow when the quadrat quota resets" | tee -a "$LOG"
    exit 0
fi

echo "both arms complete: scoring once, per the stopping rule" | tee -a "$LOG"
"$PY" dashboard/score_confirmatory.py --adjudication docs/adjudication.csv 2>&1 | tee -a "$LOG"
