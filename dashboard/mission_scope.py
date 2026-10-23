"""What the data covers, per mission and site: the rows behind scope.csv.

measure.py writes them, the page builders recompute them and abort on a
mismatch (``history.check_scope``), and ``build_index.scope_sentence`` reads
the file for every byline. Standard library only, like everything under
dashboard/.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict

from core import GT_KEY_PREFIX, inventory_origins

NAME = "scope.csv"
COLUMNS = ("mission", "site", "n_frames", "n_labelled")


def rows(h, origins=None) -> list[dict]:
    """One row per (mission, site) over every frame with a cached Pl@ntNet
    answer, labelled or not. ``n_labelled`` counts those with any recorded
    label. A frame the inventory does not place is counted on a row with a
    blank mission and site, never guessed into one."""
    origins = inventory_origins() if origins is None else origins
    counts = defaultdict(lambda: [0, 0])
    for stem in h.predictions:
        n = counts[origins.get(GT_KEY_PREFIX + stem, ("", ""))]
        n[0] += 1
        n[1] += stem in h.labelled_stems
    return [{"mission": m, "site": s, "n_frames": a, "n_labelled": b}
            for (m, s), (a, b) in sorted(counts.items())]


def write(out_dir: str, table: list[dict]) -> None:
    with open(os.path.join(out_dir, NAME), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(table)

