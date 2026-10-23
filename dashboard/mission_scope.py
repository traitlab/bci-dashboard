"""What the data covers, per mission and site: the rows behind scope.csv.

measure.py writes them, the page builders recompute them and abort on a
mismatch (``history.check_scope``), ``build_index.scope_sentence`` reads
the file for every byline, and ``p_sites`` lays it out on the model-health
page. Standard library only, like everything under dashboard/.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict

from assets import esc, more, panel, pctf, table
from core import GT_KEY_PREFIX, inventory_origins, ratio

NAME = "scope.csv"
COLUMNS = ("mission", "site", "n_frames", "n_labelled", "n_scored", "n_correct_top1")


def rows(h, origins=None) -> list[dict]:
    """One row per (mission, site) over every frame with a cached Pl@ntNet
    answer, labelled or not. ``n_labelled`` counts those with any recorded
    label; ``n_scored`` the headline population, frames labelled to a species
    (``h.sp_recs``), and ``n_correct_top1`` those whose first guess is the
    label. A frame the inventory does not place is counted on a row with a
    blank mission and site, never guessed into one."""
    origins = inventory_origins() if origins is None else origins
    counts = defaultdict(lambda: [0, 0, 0, 0])
    for stem in h.predictions:
        n = counts[origins.get(GT_KEY_PREFIX + stem, ("", ""))]
        n[0] += 1
        n[1] += stem in h.labelled_stems
    for r in h.sp_recs:
        n = counts[origins.get(r["global_key"], ("", ""))]
        n[2] += 1
        n[3] += r["ranked"][0][0] == r["gt"]
    return [dict(zip(COLUMNS, (m, s, *n))) for (m, s), n in sorted(counts.items())]


def _table(groups: dict, first: str) -> str:
    """One row per group key, its frame counts summed, and the first-guess rate
    over the scored frames beside the count it is over."""
    out = []
    for key, rs in sorted(groups.items()):
        frames, labelled, scored, hits = (sum(int(r[k]) for r in rs) for k in COLUMNS[2:])
        rate = ratio(hits, scored)
        out.append([esc(key) or "not placed", f"{frames:,}", f"{labelled:,}", f"{scored:,}",
                    f"{pctf(rate)} of {scored:,}" if rate is not None else "not scored"])
    return table([(first, False), ("Close-ups", True), ("Labelled", True),
                  ("Labelled to a species", True), ("First guess right", True)], out,
                 source=NAME)


def p_sites(c):
    """Labels and accuracy split by where the photos were taken."""
    by_site, by_mission = defaultdict(list), defaultdict(list)
    for r in c.scope:
        by_site[r["site"]].append(r)
        by_mission[r["mission"]].append(r)
    if not c.scope:
        body = '<p class="note">No close-up has a cached answer.</p>'
    else:
        body = ('<p class="note">First guess right is over the frames labelled to a '
                "species, the headline population; a site with few says little.</p>"
                + _table(by_site, "Site")
                + more(f"The same per mission ({len(by_mission)} missions)",
                       '<p class="note">The site is the second part of the mission folder name.</p>'
                       + _table(by_mission, "Mission")))
    return panel("By site and mission",
                 "<b>Where the labels and the errors are.</b> Close-ups, labels and the "
                 "first-guess rate for each drone site, and per mission below.",
                 body, anchor="by-site-and-mission")


def write(out_dir: str, table: list[dict]) -> None:
    with open(os.path.join(out_dir, NAME), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(table)

