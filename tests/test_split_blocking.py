"""Is `data/splits.csv` blocked by site, and does the page say the right thing.

The wait-rule panel publishes a wrong-guess share measured on the `test` frames
and calls it a floor, because the split is drawn frame by frame. Drone frames
from one flight over one site overlap, so a held-out frame can be a near-copy of
a frame the rule learned from.

This file is the caveat's expiry date. When the split is redrawn by whole sites
the first test fails, and the failure message says what to write in its place.
"""

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SPLITS = REPO / "data" / "splits.csv"
INVENTORY = REPO / "data" / "dataset_rows_combined.jsonl"

# Mission folders are named <yyyymmdd>_<site>_<waypoint>_<aircraft>, the same
# shape `labelling/draw_field_sample.py` reads a site out of.
MISSION_RE = re.compile(r"/(\d{8})_([a-z0-9]+)_")

CAVEAT = "Why the wrong-guess share is a floor, not an estimate"


def _split_by_site():
    if not SPLITS.exists() or not INVENTORY.exists():
        pytest.skip("data/splits.csv or the inventory not present (fresh clone, "
                    "data/ is gitignored)")
    site = {}
    with open(INVENTORY, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            gk, m = row.get("global_key"), MISSION_RE.search(line)
            if gk and m:
                site[gk] = m.group(2)
    counts = defaultdict(Counter)
    with open(SPLITS, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            s = site.get(r["global_key"])
            if s and r["split"]:
                counts[s][r["split"]] += 1
    return counts


def test_the_split_is_not_blocked_by_site_so_the_caveat_still_applies():
    """Fails the day someone redraws the split by whole sites. That is good
    news, and the fix is to rewrite the caveat, not to relax this test."""
    counts = _split_by_site()
    shared = sorted(s for s, c in counts.items() if c["train"] and c["test"])
    assert shared, (
        "No site has frames in both train and test any more. The split looks "
        "blocked by site now, so rewrite the floor caveat in "
        "dashboard/queue_why_panels.py: a site-blocked score is still not "
        "unbiased, and it now answers a different question.")


def test_every_held_out_frame_sits_at_a_site_the_rule_also_learned_from():
    """What the caveat asserts on the page, in one number."""
    counts = _split_by_site()
    shared = {s for s, c in counts.items() if c["train"] and c["test"]}
    leaked = sum(counts[s]["test"] for s in shared)
    total = sum(c["test"] for c in counts.values())
    assert total and leaked == total, (
        f"{leaked} of {total} test frames sit at a site that is also in train. "
        f"The panel says every one does. Reword it to match.")


def test_the_queue_page_carries_the_caveat_or_the_regrade(internal_page):
    """The floor caveat stands until the rule is graded on flights held back
    whole; then the page prints that grade in its place."""
    html = internal_page[0]
    assert CAVEAT in html or "The same rule on flights held back whole" in html
