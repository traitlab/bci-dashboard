"""The species pairs the model swaps most: the rows behind confused_pairs.csv.

measure.py writes them, the model-health builder recomputes them and aborts on
a mismatch (``history.check_confused``), and ``manifest.entry`` keeps them on
each refresh line, so ``history_panels.p_confused`` can set a pair's count
beside the one an earlier export gave. Standard library only, like everything
under dashboard/.
"""

from __future__ import annotations

import csv
import os
from collections import Counter

NAME = "confused_pairs.csv"
COLUMNS = ("label", "first_guess", "n_frames", "n_label_frames")
SHOWN = 15


def pairs(sp_recs, support) -> list[tuple]:
    """The label-and-first-guess pairs that occur most among wrong first guesses,
    as (label, guess, frames, labelled frames of the label species). Every scored
    frame counts, not only the confident ones the review list holds."""
    counts = Counter((r["gt"], r["ranked"][0][0]) for r in sp_recs
                     if r["ranked"][0][0] != r["gt"])
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(gt, guess, n, support[gt]) for (gt, guess), n in ordered[:SHOWN]]


def write(out_dir: str, rows: list[tuple]) -> None:
    with open(os.path.join(out_dir, NAME), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)


def read(directory: str) -> list[list] | None:
    """[label, guess, frames] per row, the manifest's form, or None for a
    table directory older than the file."""
    path = os.path.join(directory, NAME)
    if not os.path.exists(path):
        return None
    with open(path, newline="", encoding="utf-8") as f:
        return [[r["label"], r["first_guess"], int(r["n_frames"])] for r in csv.DictReader(f)]


def earlier(changes) -> tuple[str, dict] | None:
    """(export, {(label, guess): frames}) off the manifest line before the
    newest, the one "Since the last update" compares with. None when there is
    no such line, it predates the pair counts, or it was scored against other
    reference labels, where a moved count would be the labels' change."""
    d = (changes or {}).get("diff")
    if d is None or d["crossed"] or d["prev"].get("confused_pairs") is None:
        return None
    return d["prev"]["export"], {(gt, guess): n for gt, guess, n in d["prev"]["confused_pairs"]}
