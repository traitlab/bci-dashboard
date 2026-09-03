"""Whether Pl@ntNet's project vocabulary contains a species, not just our
sample of it.

``predict/fetch_checklist.py`` downloads a Pl@ntNet project's full species
list to ``data/checklist_<project>.json``. This module reads that file back
and turns it into a membership test. It makes no network call and reads no
credential: a missing file is the normal state of a fresh clone, and every
caller degrades to "unknown" rather than aborting, which is what keeps the
page build offline.

``health.load_health`` is the only caller. It passes its own ``canon``
(normalize + WCVP crosswalk) so the checklist's names are put through the
same crosswalk as every botanist label and cached prediction, in one place,
rather than a second copy of it living here.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from core import BASE, EVAL_PROJECT, normalize


def checklist_path(project: str = EVAL_PROJECT) -> str:
    return os.path.join(BASE, f"checklist_{project}.json")


@dataclass
class Checklist:
    project: str
    n_returned: int
    declared_species_count: int | None
    binomials_norm: frozenset  # normalize()'d, no crosswalk applied
    raw_binomials: tuple       # unmodified scientificNameWithoutAuthor values

    def canon_binomials(self, canon) -> frozenset:
        """The checklist's names run through the caller's ``canon``.

        Same crosswalk applied to labels and cached predictions, so a species
        is tested for membership on the vocabulary every other number on the
        page is scored on, not a second, looser one.
        """
        return frozenset(canon(b) for b in self.raw_binomials if b)


def load_checklist(project: str = EVAL_PROJECT, path: str | None = None) -> Checklist | None:
    """Read ``data/checklist_<project>.json``, or ``None`` when it is not there.

    ``None`` is not an error: ``predict/fetch_checklist.py`` is a separate,
    network-touching step, and ``dashboard/`` builds every page offline. A
    caller that cannot answer "is this species out of scope" has to say so,
    not guess.
    """
    p = path or checklist_path(project)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    species = doc.get("species", [])
    n_returned = doc.get("n_returned", len(species))
    declared = doc.get("declared_species_count")
    if declared is not None and declared != n_returned:
        raise SystemExit(
            f"{p} declares {declared} species but only {n_returned} were "
            f"downloaded. That is a short download, not a real checklist: "
            f"re-run predict/fetch_checklist.py before trusting any absence "
            f"read from it.")
    raw = tuple(s.get("scientificNameWithoutAuthor", "") for s in species)
    return Checklist(
        project=doc.get("project", project), n_returned=n_returned,
        declared_species_count=declared,
        binomials_norm=frozenset(normalize(b) for b in raw if b),
        raw_binomials=raw)
