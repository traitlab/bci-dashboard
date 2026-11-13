#!/usr/bin/env python3
"""Say whether the weekly refresh should open or close the stale-feed issue.

Reads the same files the build reads (graded frames, the 2026 catalog pool, the
label-date sidecar) and prints ``open`` when the newest photo or label is older
than snapshot_delta.STALE_DAYS, else ``close``. With ``--body-file`` it also
writes the issue body. The workflow does the gh calls.

    python bin/freshness_issue.py --body-file body.md
"""

from __future__ import annotations

import argparse
import csv
import importlib
import os
import sys
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "dashboard"))
hc = importlib.import_module("core")
snapshot_delta = importlib.import_module("snapshot_delta")

TITLE = "Data feed stale"
LABEL = "data-feed"


def _keys(path: str) -> list[str]:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return [r["global_key"] for r in csv.DictReader(f)]
    except OSError:
        return []


def decide(rows: list[dict], graded: int, catalog: int, built: str) -> tuple[str, str]:
    """``("open", body)`` when any feed is stale, else ``("close", "")``."""
    if not any(r["stale"] for r in rows):
        return "close", ""
    lines = [f"The weekly refresh on {built} found a feed older than {snapshot_delta.STALE_DAYS} days, or with no date at all.", ""]
    for r in rows:
        age = "unknown" if r["age"] is None else f"{r['age']} days"
        lines.append(f"- Newest {r['what']}: {r['newest'] or 'not found'} (age {age}){' **stale**' if r['stale'] else ''}")
    lines += ["", f"Threshold: {snapshot_delta.STALE_DAYS} days.",
              f"Population: {graded} graded frames and {catalog} frames in the 2026 catalog pool.",
              "", "This issue closes itself when both feeds are fresh."]
    return "open", "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--body-file", help="write the issue body here when the action is open")
    ap.add_argument("--date", default=date.today().isoformat(), help="the build date (default today)")
    args = ap.parse_args(argv)
    graded, catalog = _keys(hc.SPLITS_CSV), _keys(hc.CATALOG_INPUT_CSV)
    rows = snapshot_delta.freshness(graded + catalog, hc.GT_LABEL_DATES_CSV, args.date)
    action, body = decide(rows, len(graded), len(catalog), args.date)
    if args.body_file and body:
        with open(args.body_file, "w", encoding="utf-8") as f:
            f.write(body)
    print(action)
    return 0


if __name__ == "__main__":
    sys.exit(main())
