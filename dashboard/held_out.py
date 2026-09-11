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
from assets import more

MISSION_RE = re.compile(r"/(\d{8})_([a-z0-9]+)_")

COLUMNS = ("population", "n_frames", "n_correct_top1", "top1_accuracy")
# The draw's own record, beside the CSV health.py reads the held frames from.
HOLDOUT_JSON = os.path.splitext(hc.HOLDOUT_CSV)[0] + ".json"
FLIGHT_CSV = "flight_holdout.csv"
# The graded row and the drawn row. A drawn frame with no cached answer or no
# label row cannot be graded, so the two counts differ and both are written:
# a grade over fewer frames than were held is a fact a reader should see.
FLIGHT_GRADED_ROW = "holdout_held_graded"
FLIGHT_DRAWN_ROW = "holdout_held_drawn"
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


def load_manifest(path: str = HOLDOUT_JSON):
    """The flight holdout's own record: which version, how many flights it
    holds, how many frames it drew, and how many species it cannot grade.

    Every number the note prints about the draw comes from here rather than
    from a constant, because the draw is the thing that decided them. An absent
    file returns None and the page says nothing about a holdout, which is what
    a checkout without a drawn one gets.
    """
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def measure_flight_holdout(sp_recs, manifest) -> dict | None:
    """Top-1 on the frames the flight holdout holds, the same computation
    ``measure`` runs on the test frames.

    The population is every scored frame ``health.load_health`` tagged with
    ``core.HOLDOUT_SPLIT``. Those frames are on flights no train frame is on,
    so this rate leans on no near-copy of a frame the labels already know.
    Returns None when there is no drawn holdout to report.
    """
    if not manifest:
        return None
    stats = manifest.get("stats", {})
    held = [r for r in sp_recs if r["split"] == hc.HOLDOUT_SPLIT]
    return {"version": manifest.get("version", ""),
            "n_flights": int(stats.get("n_held_groups", 0)),
            "n_all_flights": int(stats.get("n_groups", 0)),
            "n_drawn": int(stats.get("n_held", 0)),
            "n_ungradeable": int(stats.get("n_species_ungradeable", 0)),
            "held": _rate(held)}


def flight_rows(flight: dict) -> list[dict]:
    """The rows flight_holdout.csv carries. The drawn row is a count only: the
    frames it counts beyond the graded row have no answer to score."""
    held = flight["held"]
    return [{"population": FLIGHT_GRADED_ROW, "n_frames": held["n"],
             "n_correct_top1": held["correct"],
             "top1_accuracy": hc.fmt(held["top1"])},
            {"population": FLIGHT_DRAWN_ROW, "n_frames": flight["n_drawn"],
             "n_correct_top1": "", "top1_accuracy": ""}]


def write_flight_holdout(out_dir: str, flight: dict | None) -> None:
    """Written whenever a holdout is drawn. Absent, no file: a build reading a
    snapshot without one skips the check rather than failing on it."""
    if flight is None:
        return
    with open(os.path.join(out_dir, FLIGHT_CSV), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(flight_rows(flight))


def write_tables(out_dir: str, sp_recs) -> None:
    """Both tables this module owns, named once so a caller cannot write the
    test one and forget the flight one. The flight table is skipped when no
    holdout is drawn."""
    write_held_out(out_dir, measure(sp_recs, load_flights()))
    write_flight_holdout(out_dir, measure_flight_holdout(sp_recs, load_manifest()))


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


def _flight_sentences(flight: dict) -> str:
    """What the drawn flight holdout adds to the note.

    Names the version, the flights, the frames and the species it cannot
    grade, every one of them read off the draw's own record. Kept apart from
    ``note`` so each sentence stays short enough to read once.
    """
    held, n_f, n_ug = flight["held"], flight["n_flights"], flight["n_ungradeable"]
    n_all = flight["n_all_flights"]
    ver = flight["version"] or "v1"
    if not n_f or not held["n"]:
        return (f'<p class="note">A flight holdout ({ver}) is on record, and no frame '
                f'on it carries an answer to score yet.</p>')
    # Four sentences open, because the guard has to be read where the rate is:
    # these are not the test frames, so the two rates cannot be subtracted. How
    # the holdout was drawn, and which species it cannot grade at all, are read
    # once by someone checking us, so they wait behind a summary line.
    line = (f'<p class="note"><b>A second score, on flights held back whole.</b> '
            f'The first guess is right on {_pct(held["top1"])} of the {held["n"]:,} '
            f'frames on the {n_f:,} held-back flights that carry an answer. These are '
            f'not the test frames, so do not subtract one rate from the other.</p>')
    rest = (f'<p class="note">The {ver} flight holdout holds {n_f:,} of the '
            f'{n_all:,} flights back, whole. ' if n_all else
            f'<p class="note">The {ver} flight holdout holds {n_f:,} whole flights '
            f'back. ')
    rest += ('No train frame sits on any of them, so nothing counted there is a '
             'near-copy of a frame the labels already know. The two sets do not hold '
             'the same species in the same shares, so the two rates grade two '
             'different sets of frames.</p>')
    if n_ug:
        rest += (f'<p class="note">{n_ug:,} species cannot be graded this way, because '
                 f'each one sits on a single flight. Holding that flight would leave '
                 f'the model nothing to learn the species from, so it stays in '
                 f'train.</p>')
    else:
        rest += ('<p class="note">Every species was flown more than once, so none is '
                 'left ungraded.</p>')
    return line + more("How the held-back flights were drawn", rest)


def note(result: dict, flight: dict | None = None) -> str:
    """The one paragraph the species panel prints from this file. Every rate
    names its population and n, and the empty case is said in words.

    ``flight`` is ``measure_flight_holdout``'s result, printed beside the test
    score. None, and the paragraph is the one a checkout without a drawn
    holdout gets.
    """
    t, u = result["test"], result["unseen"]
    unplaced = result["unplaced"]
    line = (f'<p class="note"><b>Were the test frames (the labelled frames set aside for scoring) flown on the same flights as the rest?</b> A flight is one date over one site. The first guess is right on '
            f'{_pct(t["top1"])} of the {t["n"]:,} test frames. ')
    if u["n"]:
        line += (f'On the {u["n"]:,} test frames from flights with no train frame it is '
                 f'right on {_pct(u["top1"])}. Those frames hold different species in '
                 f'different shares from the rest, so the gap between the two rates is '
                 f'not the size of a leak. ')
    else:
        line += ('Every one of them shares its flight with a train frame, so no test '
                 'frame comes from a flight the labels never saw. ')
        line += ('The second score below is on other frames, held back whole by '
                 'flight. ' if flight else
                 'A set held back by whole flights would grade frames that share a '
                 'flight with no train frame. ')
    if unplaced:
        line += (f'{unplaced:,} test frame{"s" if unplaced != 1 else ""} could not be '
                 f'placed on a flight and {"are" if unplaced != 1 else "is"} left out. ')
    else:
        line += 'Every test frame could be placed on a flight. '
    if result["unplaced_train"]:
        line += (f'{result["unplaced_train"]:,} train frames could not be placed either, '
                 f'so their flights read as unseen. ')
    line = line.rstrip() + '</p>'
    if flight is not None:
        line += _flight_sentences(flight)
    return line


def write_held_out(out_dir: str, result: dict) -> None:
    with open(os.path.join(out_dir, "held_out.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(rows(result))
