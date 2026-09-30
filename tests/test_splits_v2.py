"""`input/splits_v2.csv` adds to `data/splits.csv` and never moves a row of it.

The legacy split is what the Pl@ntNet runs were graded on, so a frame it names
keeps its split, and a frame it sent with no split is treated as seen. The
promises the extension makes are checked on the committed file itself: every
legacy row is carried over unchanged, no `clean_test` frame stands within the
buffer of a seen frame, and no flight has frames on both sides. The rules are
also checked on a hand-built inventory that needs no data directory.

    .venv/bin/pytest tests/test_splits_v2.py
"""

from __future__ import annotations

import collections
import csv
import json
import math
import subprocess
import sys

import pytest
from conftest import REPO, load

LEGACY = REPO / "data" / "splits.csv"
OUT = REPO / "input" / "splits_v2.csv"
META = REPO / "input" / "splits_v2.json"
SCRIPT = REPO / "labelling" / "extend_splits.py"


@pytest.fixture(scope="session")
def es():
    return load("extend_splits", SCRIPT)


@pytest.fixture(scope="session")
def rows():
    if not OUT.exists():
        pytest.skip("input/splits_v2.csv not written yet")
    with open(OUT, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _inventory(*frames):
    """frame -> row, from (frame, flight, x_m, y_m) tuples."""
    return {f: {"global_key": f, "flight": fl, "xy": (x, y)} for f, fl, x, y in frames}


def test_a_legacy_frame_keeps_its_split_and_a_blank_one_is_seen(es):
    inv = _inventory(("a.jpg", "20250101/site", 0, 0), ("b.jpg", "20250101/site", 500, 0))
    got = {r["frame"]: (r["split"], r["source"]) for r in es.assign(inv, {"a.jpg": "test", "b.jpg": ""})}
    assert got == {"a.jpg": ("test", "legacy"), "b.jpg": ("train", "sent_blank")}


def test_a_new_frame_near_a_seen_one_is_buffered_and_a_far_one_is_clean(es):
    inv = _inventory(("seen.jpg", "20250101/site", 0, 0),
                     ("near.jpg", "20260101/site", 20, 0),
                     ("far.jpg", "20260101/site", 200, 0))
    got = {r["frame"]: (r["split"], r["source"]) for r in es.assign(inv, {"seen.jpg": "train"})}
    assert got["near.jpg"] == ("buffered", "near")
    assert got["far.jpg"] == ("clean_test", "flight")


def test_a_late_frame_on_a_legacy_flight_joins_its_neighbours_or_stays_out(es):
    inv = _inventory(("t.jpg", "20250101/site", 0, 0), ("v.jpg", "20250101/site", 1000, 0),
                     ("agree.jpg", "20250101/site", 10, 0),
                     ("alone.jpg", "20250101/site", 500, 0),
                     ("torn.jpg", "20250101/site", 1000, 0),
                     ("t2.jpg", "20250101/site", 1010, 0))
    legacy = {"t.jpg": "train", "v.jpg": "valid", "t2.jpg": "train"}
    got = {r["frame"]: (r["split"], r["source"]) for r in es.assign(inv, legacy)}
    assert got["agree.jpg"] == ("train", "near")
    assert got["alone.jpg"] == ("buffered", "flight")
    assert got["torn.jpg"] == ("buffered", "conflict")


def test_a_frame_without_a_flight_or_a_position_is_kept_out_by_name(es):
    inv = {"x.jpg": {"global_key": "x.jpg", "flight": "", "xy": (0, 0)},
           "y.jpg": {"global_key": "y.jpg", "flight": "20260101/site", "xy": None}}
    got = {r["frame"]: (r["split"], r["source"]) for r in es.assign(inv, {})}
    assert got == {"x.jpg": ("buffered", "unplaced"), "y.jpg": ("buffered", "unplaced")}


def test_the_frame_id_is_the_file_name_under_every_key_shape(es):
    for key in ("comb_A.JPG", "migrated/A.JPG", "DJI_2026_flight-m3e/A.JPG", "A.JPG"):
        assert es.frame_of(key) == "A.JPG"


def test_every_legacy_row_is_carried_over_unchanged(es, rows):
    if not LEGACY.exists():
        pytest.skip("data/splits.csv not present (data/ is gitignored)")
    got = {r["frame"]: r for r in rows}
    with open(LEGACY, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            frame = es.frame_of(r["global_key"])
            if frame not in got:
                continue
            if r["split"]:
                assert (got[frame]["split"], got[frame]["source"]) == (r["split"], "legacy"), frame
            else:
                assert (got[frame]["split"], got[frame]["source"]) == ("train", "sent_blank"), frame


def test_no_flight_has_frames_on_both_sides(rows):
    sides = collections.defaultdict(set)
    for r in rows:
        if r["split"] != "buffered":
            sides[r["flight"]].add(r["split"] == "clean_test")
    torn = sorted(f for f, s in sides.items() if len(s) > 1)
    assert not torn, f"flights with both a legacy split and clean_test: {torn}"


def test_no_clean_frame_stands_within_the_buffer_of_a_seen_one(es, rows):
    inv = es.load_inventory() if all(p.exists() for p in es.INVENTORIES) else None
    if inv is None:
        pytest.skip("inventories not present (data/ is gitignored)")
    buffer = json.loads(META.read_text(encoding="utf-8"))["buffer_m"]
    seen = [inv[r["frame"]]["xy"] for r in rows if r["split"] in es.LEGACY_SPLITS and inv[r["frame"]]["xy"]]
    clean = [inv[r["frame"]]["xy"] for r in rows if r["split"] == "clean_test"]
    assert clean
    for cx, cy in clean:
        assert all(math.hypot(cx - sx, cy - sy) > buffer for sx, sy in seen)


def test_the_committed_file_reproduces(rows):
    if not LEGACY.exists():
        pytest.skip("data/splits.csv not present (data/ is gitignored)")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--verify"], capture_output=True,
                          text=True, check=False)
    assert proc.returncode == 0, proc.stderr
