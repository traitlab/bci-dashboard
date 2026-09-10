"""Top-1 on the test frames from flights the train set never saw.

The split in data/splits.csv is drawn frame by frame, and drone frames from one
flight over one site overlap, so a test frame can be a near-copy of a train
frame. tests/test_split_blocking.py pins that every test frame today shares a
flight with a train frame. This module measures the number that does not lean
on that: top-1 on the test frames whose flight (one date, one site) has no
train frame at all. Today that population is empty and the page says so.

A flight is read out of the Labelbox inventory: each frame URL carries a
mission folder named <yyyymmdd>_<site>_<waypoint>_<aircraft>, the same shape
labelling/draw_field_sample.py reads a site out of. A frame whose URL carries
no such folder cannot be placed on a flight; it is counted, not dropped quietly.
"""

from __future__ import annotations

import csv
import json
import os
import re

import core as hc

MISSION_RE = re.compile(r"/(\d{8})_([a-z0-9]+)_")

COLUMNS = ("population", "n_frames", "n_correct_top1", "top1_accuracy")
# The rows held_out.csv carries, in this order. The unplaced row carries a
# count only: those frames are graded in the overall test rate, never apart.
POPULATIONS = (("test", "test"), ("test_unseen_flight", "unseen"))
UNPLACED_ROW = "test_unplaced"


def flight_of(url: str):
    """(date, site) from a frame URL's mission folder, or None."""
    m = MISSION_RE.search(url or "")
    return (m.group(1), m.group(2)) if m else None


def load_flights(path: str = hc.DATASET_ROWS_COMBINED_JSONL) -> dict:
    """global_key -> (date, site) for every inventory row that has both."""
    flights = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            key, flight = row.get("global_key"), flight_of(row.get("row_data"))
            if key and flight:
                flights[key] = flight
    return flights


def _rate(recs) -> dict:
    correct = sum(1 for r in recs if r["ranked"][0][0] == r["gt"])
    return {"n": len(recs), "correct": correct, "top1": hc.ratio(correct, len(recs))}


def measure(sp_recs, flights: dict) -> dict:
    """Overall test top-1, top-1 on test frames from flights with no train
    frame, and how many frames could not be placed on a flight.

    A train frame with no flight vouches for nothing: the flight it was on
    stays unseen, because nothing says which one that was. Counted apart so a
    page can say so.
    """
    train = [r for r in sp_recs if r["split"] == "train"]
    test = [r for r in sp_recs if r["split"] == "test"]
    seen = {flights[r["global_key"]] for r in train if r["global_key"] in flights}
    placed = [r for r in test if r["global_key"] in flights]
    unseen = [r for r in placed if flights[r["global_key"]] not in seen]
    return {"test": _rate(test), "unseen": _rate(unseen),
            "unplaced": len(test) - len(placed),
            "unplaced_train": sum(1 for r in train if r["global_key"] not in flights)}


def rows(result: dict) -> list[dict]:
    """The rows held_out.csv carries, rates written the way every other table
    writes them so the snapshot check can compare within its tolerance."""
    out = [{"population": name, "n_frames": result[key]["n"],
            "n_correct_top1": result[key]["correct"],
            "top1_accuracy": hc.fmt(result[key]["top1"])}
           for name, key in POPULATIONS]
    out.append({"population": UNPLACED_ROW, "n_frames": result["unplaced"],
                "n_correct_top1": "", "top1_accuracy": ""})
    return out


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def note(result: dict) -> str:
    """The one paragraph the species panel prints from this file. Every rate
    names its population and n, and the empty case is said in words."""
    t, u = result["test"], result["unseen"]
    line = (f'<p class="note"><b>Scored on frames from flights the labels never saw.</b> '
            f'The first guess is right on {_pct(t["top1"])} of the {t["n"]:,} test frames. ')
    if u["n"]:
        line += (f'On the {u["n"]:,} test frames from flights with no train frame it is '
                 f'right on {_pct(u["top1"])}. ')
    else:
        line += ('A flight is one date over one site. Every test frame shares its flight '
                 'with a train frame, so no test frame comes from a flight the labels '
                 'never saw. ')
    line += (f'{result["unplaced"]:,} test frame{"s" if result["unplaced"] != 1 else ""} '
             f'could not be placed on a flight and {"are" if result["unplaced"] != 1 else "is"} '
             f'left out of that comparison. ')
    if result["unplaced_train"]:
        line += (f'{result["unplaced_train"]:,} train frames could not be placed either, '
                 f'so their flights read as unseen. ')
    return line + ('A large gap between the two rates would mean the test score leans '
                   'on near-copies of train frames. The rate on new flights would then '
                   'be closer to the lower one.</p>')


def write_held_out(out_dir: str, result: dict) -> None:
    with open(os.path.join(out_dir, "held_out.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(rows(result))
