"""Which labels a number is scored against, and the break in the series when that changed.

Until ``core.REFERENCE_SWITCHED_ON`` every headline was scored on the Labelbox
labels. From then on it is scored on the frames whose label is the reviewed
publication name, and the frames Labelbox labelled but no review covered are
reported beside it with their own counts, never pooled into it.

measure.py writes ``reference.json`` next to its tables, so every snapshot
records the reference it was scored against. A snapshot from before the switch
has no such file and is read as Labelbox. Anything that compares two snapshots
asks ``read`` for both and refuses to report a change across the break as if it
were the model's.

Read with the standard library only, like everything under dashboard/.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

import core as hc

REFERENCE_JSON = "reference.json"
# What a table with no reference.json was scored against: every snapshot up to
# the switch, and a GT without a label_source column.
LABELBOX = "labelbox"
# Both label_source populations pooled, which no page publishes.
POOLED = "pooled"

WORDS = {
    LABELBOX: "the Labelbox labels",
    hc.LABEL_SOURCE_REVIEWED: "the reviewed publication labels",
    hc.LABEL_SOURCE_UNREVIEWED: "the Labelbox labels no review has covered",
    POOLED: "reviewed and unreviewed labels pooled",
}


def reference_of(gt_rows_all: list, label_source: str | None) -> str:
    """The reference a run scores against, from the whole GT file and the
    population asked for."""
    if label_source and label_source != hc.LABEL_SOURCE_ALL:
        return label_source
    if gt_rows_all and hc.LABEL_SOURCE_COLUMN in gt_rows_all[0]:
        return POOLED
    return LABELBOX


def read(directory: str) -> str:
    """The reference a table directory or snapshot was scored against."""
    path = os.path.join(directory, REFERENCE_JSON)
    if not os.path.exists(path):
        return LABELBOX
    with open(path, encoding="utf-8") as f:
        return json.load(f)["reference"]


def break_sentence(then: str, now: str) -> str:
    """What every place that crosses the break prints, word for word."""
    return (
        f"The reference labels changed on {hc.REFERENCE_SWITCHED_ON}. Numbers "
        f"before then are scored against {WORDS.get(then, then)}. Numbers after are "
        f"scored against {WORDS.get(now, now)}. A change across that date is a "
        f"change of reference, not of the model."
    )


def population_stats(h) -> list[dict]:
    """The headline rates once per label_source population, headline first.

    Each carries its own frame and species counts, gated and ungated, so an
    unreviewed rate is never read off the reviewed n. Species rates are pooled
    within a species, then averaged across species. Empty for a GT without the
    column: then there is one population and the headline already is it.
    """
    rows = []
    for source, recs in h.by_source.items():
        by_species = defaultdict(list)
        for r in recs:
            by_species[r["gt"]].append(r)

        gate = hc.coverage_gate_stats(recs)
        rows.append(
            {
                "label_source": source,
                "headline": source == h.reference,
                "n_frames": len(recs),
                "n_species": len(by_species),
                "n_correct_top1": sum(_hit(r, 1) for r in recs),
                "n_correct_top5": sum(_hit(r, hc.N_CANDIDATES) for r in recs),
                "macro_top1": _macro(by_species, 1),
                "macro_top5": _macro(by_species, hc.N_CANDIDATES),
                "gated_n_frames": gate["n_admitted"],
                "gated_n_correct_top1": gate["n_correct_top1"],
                "gated_macro_top1": gate["macro_top1"],
                "gated_n_species": gate["n_species"],
            }
        )
    rows.sort(key=lambda r: (not r["headline"], r["label_source"]))
    return rows


def _macro(by_species: dict, k: int):
    """Top-k pooled within a species, then averaged across species."""
    return hc.ratio(
        sum(
            hc.ratio(sum(_hit(r, k) for r in rs), len(rs)) for rs in by_species.values()
        ),
        len(by_species),
    )


def _hit(r, k) -> bool:
    return any(name == r["gt"] for name, _ in r["ranked"][:k])


def write(out_dir: str, h, gt_csv: str, label_source: str | None) -> None:
    """``reference.json``: what this run was scored against, and each
    population's counts, so a snapshot says for itself which side of the
    break it is on."""
    doc = {
        "reference": h.reference,
        "label_source": label_source or hc.LABEL_SOURCE_ALL,
        "gt_csv": os.path.basename(gt_csv),
        "gt_provenance": hc.gt_provenance(gt_csv),
        "populations": population_stats(h),
    }
    with open(os.path.join(out_dir, REFERENCE_JSON), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
        f.write("\n")


def check(directory: str, reference: str, populations: list[dict]) -> str:
    """Abort when the tables were scored against another reference, or when a
    population the page prints beside the headline disagrees with them."""
    on_disk = read(directory)
    if on_disk != reference:
        raise SystemExit(
            f"VERIFY FAIL: this page is scored against {WORDS.get(reference, reference)}, "
            f"{directory} against {WORDS.get(on_disk, on_disk)}. "
            f"{break_sentence(on_disk, reference)} Re-run dashboard/measure.py."
        )
    path = os.path.join(directory, REFERENCE_JSON)
    if not os.path.exists(path):
        return f"{REFERENCE_JSON}: absent, read as {LABELBOX} (older than the file)"
    with open(path, encoding="utf-8") as f:
        want = json.load(f)["populations"]
    if [_counts(p) for p in want] != [_counts(p) for p in populations]:
        raise SystemExit(
            f"VERIFY FAIL: the label_source populations here differ from "
            f"{path}. Re-run dashboard/measure.py."
        )
    return (
        f"{REFERENCE_JSON}: scored against {reference}, "
        f"{len(populations)} label_source populations match"
    )


def _counts(p: dict) -> tuple:
    return tuple(
        p[k]
        for k in (
            "label_source",
            "n_frames",
            "n_species",
            "n_correct_top1",
            "n_correct_top5",
            "gated_n_frames",
            "gated_n_correct_top1",
        )
    )
