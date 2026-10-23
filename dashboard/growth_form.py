"""Growth form per species (input/growth_form.csv): the column on per_species_health.csv
and the send file, and the accuracy panel on the model-health page. Standard library only."""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

from assets import esc, panel, pctf, table
from core import REPO, ratio

PATH = os.path.join(REPO, "input", "growth_form.csv")
NAME = "per_species_health.csv"
UNKNOWN = "unknown"
ORDER = ("tree", "liana", "palm", "shrub", "herb", UNKNOWN)


def load(path=None) -> dict[str, str]:
    with open(path or PATH, newline="", encoding="utf-8") as f:
        return {r["species"]: r["growth_form"] for r in csv.DictReader(f)}


def attach(per_species, forms=None) -> list[str]:
    """Set ``growth_form`` on every species row. A species the file lacks reads
    ``unknown`` and is named on stderr, so a new label does not stop the weekly
    refresh; returns those species."""
    forms = load() if forms is None else forms
    missing = [d["species"] for d in per_species if d["species"] not in forms]
    if missing:
        print(f"growth_form.csv has no row for {len(missing)} species, shown as {UNKNOWN}: "
              f"{', '.join(missing)}. Run bin/build_growth_form.py.", file=sys.stderr)
    for d in per_species:
        d["growth_form"] = forms.get(d["species"], UNKNOWN)
    return missing


def rows(sp_recs, forms: dict[str, str]) -> list[dict]:
    """One row per growth form over the frames labelled to a species, the same
    population as ``mission_scope.rows``: frames, those whose top prediction is the
    label, and the species they cover."""
    n = defaultdict(lambda: [0, 0, set()])
    for r in sp_recs:
        c = n[forms.get(r["gt"], UNKNOWN)]
        c[0] += 1
        c[1] += r["ranked"][0][0] == r["gt"]
        c[2].add(r["gt"])
    return [{"growth_form": g, "n_scored": n[g][0], "n_correct_top1": n[g][1],
             "n_species": len(n[g][2])}
            for g in sorted(n, key=lambda g: (ORDER.index(g) if g in ORDER else len(ORDER), g))]


def p_growth_form(c):
    """Labels and accuracy split by growth form."""
    if not c.growth_forms:
        body = '<p class="note">No frame is labelled to a species.</p>'
    else:
        out = []
        for r in c.growth_forms:
            rate = ratio(r["n_correct_top1"], r["n_scored"])
            out.append([esc(r["growth_form"]), f"{r['n_species']:,}", f"{r['n_scored']:,}",
                        f"{r['n_correct_top1']:,}", f"{pctf(rate)} of {r['n_scored']:,}"])
        body = ('<p class="note">Over the frames labelled to a species, the headline '
                "population; a growth form with few says little. Growth form is from WCVP "
                "(input/growth_form.csv), and unknown where it is mixed or missing.</p>"
                + table([("Growth form", False), ("Species", True), ("Labelled to a species", True),
                         ("Top prediction right", True), ("Rate", True)], out, source=NAME))
    return panel("By growth form",
                 "<b>Which kinds of plant the model gets right.</b> Labelled frames and the "
                 "top-prediction rate for each growth form.",
                 body, anchor="by-growth-form")
