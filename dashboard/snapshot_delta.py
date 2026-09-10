"""Then and now: did the last labelling round move the numbers.

Every page reports the latest state, and the snapshot store keeps one dated
folder per merge. Nothing compared two of them, so "did that round help" was
answered by opening two CSVs by hand. This finds the newest snapshot dated
before the build date and reports two things then and now: the species with at
least the shared floor of labelled frames, and the overall test top-1 when the
older snapshot recorded one (held_out.csv is newer than most snapshots).

Read with the standard library only, like everything under dashboard/.
"""

from __future__ import annotations

import glob
import os
import re

import core as hc
from history import SNAPSHOT_DIR, SNAPSHOT_GLOB

# The build date is free text on the command line ("2026-08-25-test" in the
# test suite), so only a leading date is read out of it.
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
# Snapshots up to 2026-08-27 call the labelled-frame column by its old name.
FRAME_COLUMNS = ("n_labelled_frames", "n_labelled_crowns")


def previous_snapshot(snapshots_dir: str, generated: str):
    """Path of the newest model-health-<date>/ folder dated strictly before
    the build date, or None when there is none or the build date is not one."""
    m = DATE_RE.match(generated or "")
    if not m:
        return None
    dated = []
    for d in glob.glob(os.path.join(snapshots_dir, SNAPSHOT_GLOB)):
        s = SNAPSHOT_DIR.search(d)
        if s and s.group(1) < m.group(1):
            dated.append((s.group(1), d))
    return max(dated)[1] if dated else None


def species_at_floor(per_species_csv: str, floor: int) -> int:
    rows = hc.read_csv_rows(per_species_csv)
    if not rows:
        return 0
    col = next((c for c in FRAME_COLUMNS if c in rows[0]), None)
    if col is None:
        raise SystemExit(f"{per_species_csv} has none of {FRAME_COLUMNS}")
    return sum(1 for r in rows if int(r[col]) >= floor)


def test_top1_of(snap_dir: str):
    """(n, top1) from the snapshot's held_out.csv, or None when it has none."""
    path = os.path.join(snap_dir, "held_out.csv")
    if not os.path.exists(path):
        return None
    row = next(r for r in hc.read_csv_rows(path) if r["population"] == "test")
    return int(row["n_frames"]), float(row["top1_accuracy"]) if row["top1_accuracy"] else None


def compute(now: dict, snapshots_dir: str, generated: str, *, floor: int) -> dict:
    """``now`` carries n_species_floor, test_n and test_top1 for this build."""
    prev = previous_snapshot(snapshots_dir, generated)
    out = {"generated": generated, "previous": None, "now": dict(now),
           "then": None, "date_readable": bool(DATE_RE.match(generated or ""))}
    if prev is None:
        return out
    top1 = test_top1_of(prev)
    out["previous"] = SNAPSHOT_DIR.search(prev).group(1)
    out["then"] = {
        "n_species_floor": species_at_floor(
            os.path.join(prev, "per_species_health.csv"), floor),
        "test_n": top1[0] if top1 else None,
        "test_top1": top1[1] if top1 else None}
    return out


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def note(d: dict, *, floor: int) -> str:
    """One paragraph for the frame-counts panel."""
    now = d["now"]
    head = ('<p class="note"><b>Since the last snapshot:</b> ')
    if d["then"] is None:
        why = ("the build date is not a date, so no earlier snapshot was looked for"
               if not d["date_readable"] else "this is the first snapshot")
        return (head + f'{why}. Today {now["n_species_floor"]} species carry at least '
                f'{floor} labelled frames, and the first guess is right on '
                f'{_pct(now["test_top1"])} of the {now["test_n"]:,} test frames.</p>')
    then = d["then"]
    line = (head + f'on {d["previous"]} {then["n_species_floor"]} species carried at least '
            f'{floor} labelled frames, now {now["n_species_floor"]} species do. ')
    if then["test_top1"] is None:
        line += (f'The overall test top-1 was not recorded then. Now the first guess is '
                 f'right on {_pct(now["test_top1"])} of the {now["test_n"]:,} test frames.')
    else:
        line += (f'The first guess was right on {_pct(then["test_top1"])} of the test '
                 f'frames then (n = {then["test_n"]:,}). Now it is right on '
                 f'{_pct(now["test_top1"])} (n = {now["test_n"]:,}).')
    return line + "</p>"
