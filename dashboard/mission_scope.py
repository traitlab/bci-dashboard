"""What the data covers, per mission and site: the rows behind scope.csv.

measure.py writes them, the page builders recompute them and abort on a
mismatch (``history.check_scope``), ``build_index.scope_breakdown`` reads
the file for every byline, and ``p_sites`` lays it out on the model-health
page. Standard library only, like everything under dashboard/.
"""

from __future__ import annotations

import csv
import os
import re
from collections import defaultdict

from assets import esc, more, panel, pctf, table
from core import GT_KEY_PREFIX, inventory_origins, ratio

NAME = "scope.csv"
COLUMNS = ("mission", "site", "n_frames", "n_labelled", "n_scored", "n_correct_top1",
           "n_reviewed", "n_no_answer", "n_above_species", "first_capture", "last_capture")
CHECKED = COLUMNS[:9]  # verified against same-run tables only; capture dates are left out
CAPTURE = re.compile(r"DJI_(\d{8})")


def rows(h, origins=None) -> list[dict]:
    """One row per (mission, site) over every frame with a cached Pl@ntNet
    answer, labelled or not. ``n_labelled`` counts those with any recorded
    label; ``n_scored`` the headline population, frames labelled to a species
    (``h.sp_recs``), and ``n_correct_top1`` those whose top prediction is the
    label. A frame the inventory does not place is counted on a row with a
    blank mission and site, never guessed into one. ``first_capture`` and
    ``last_capture`` are the earliest and latest DJI_YYYYMMDD stamp in the
    frame names, blank where none carries one: a mission folder is not the day
    its photos were taken.

    ``n_reviewed`` counts the labelled frames in the population the headline is
    scored on (``h.records``: a label and a cached answer). Of those,
    ``n_scored`` have a species label and a named answer, ``n_no_answer`` an
    answer with no name, ``n_above_species`` a label that stops at genus or
    family, so n_reviewed = n_scored + n_no_answer + n_above_species. The rest of
    ``n_labelled`` carry a Labelbox label not yet reviewed. A label whose frame
    has no cached answer is no frame here: the GT file holds those rows (3,781 on
    2026-11-03) and ``n_labelled`` does not (3,777)."""
    origins = inventory_origins() if origins is None else origins
    counts = defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0, "", ""])
    for stem in h.predictions:
        n = counts[origins.get(GT_KEY_PREFIX + stem, ("", ""))]
        n[0] += 1
        n[1] += stem in h.labelled_stems
        if found := CAPTURE.search(stem):
            day = found.group(1)
            n[7], n[8] = min(n[7] or day, day), max(n[8], day)
    for r in h.sp_recs:
        n = counts[origins.get(r["global_key"], ("", ""))]
        n[2] += 1
        n[3] += r["ranked"][0][0] == r["gt"]
    for r in h.records:
        n = counts[origins.get(r["global_key"], ("", ""))]
        n[4] += 1
        n[5] += not r["ranked"]
        n[6] += bool(r["ranked"]) and not r["species_level"]
    return [dict(zip(COLUMNS, (m, s, *n))) for (m, s), n in sorted(counts.items())]


def _table(groups: dict, first: str) -> str:
    """One row per group key, its frame counts summed, and the top-prediction rate
    over the scored frames beside the count it is over."""
    out = []
    for key, rs in sorted(groups.items()):
        frames, labelled, scored, hits = (sum(int(r[k]) for r in rs) for k in COLUMNS[2:6])
        rate = ratio(hits, scored)
        out.append([esc(key) or "not placed", f"{frames:,}", f"{labelled:,}", f"{scored:,}",
                    f"{pctf(rate)} of {scored:,}" if rate is not None else "not scored"])
    return table([(first, False), ("Close-ups", True), ("Labelled", True),
                  ("Labelled to a species", True), ("Top prediction right", True)], out,
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
        body = ('<p class="note">Top prediction right is over the frames labelled to a '
                "species, the headline population; a site with few says little.</p>"
                + _table(by_site, "Site")
                + more(f"The same per mission ({len(by_mission)} missions)",
                       '<p class="note">The site is the second part of the mission folder name.</p>'
                       + _table(by_mission, "Mission")))
    return panel("By site and mission",
                 "<b>Where the labels and the errors are.</b> Close-ups, labels and the "
                 "top-prediction rate for each drone site, and per mission below.",
                 body, anchor="by-site-and-mission")


def write(out_dir: str, table: list[dict]) -> None:
    with open(os.path.join(out_dir, NAME), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(table)

