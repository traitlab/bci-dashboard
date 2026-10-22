"""The per-run manifest: one JSON line per Labelbox export the weekly refresh saw.

Snapshots are dated folders that CI throws away, so nothing compared one update
with the next. This keeps the few numbers a change log needs: how many frames
were labelled, which species, how many frames each, the test top-1 with its
frame count, and the model version. ``refresh_snapshot.py build`` appends a line;
``snapshot_delta.py`` reads the last two.

Idempotent on the export: a rerun on an export already recorded appends nothing.
Standard library only, like everything under dashboard/.
"""

from __future__ import annotations

import json
import os

import core as hc
import reference

FRAME_COLUMNS = ("n_labelled_frames", "n_labelled_crowns")


def entry(tables_dir: str, *, run_date: str, export: str, frames: int) -> dict:
    """One manifest line off a measure.py table directory.

    ``frames`` is every frame a botanist has labelled at all; ``labelled`` is the
    subset labelled to a species and scored, the population the rates are over.
    """
    rows = hc.read_csv_rows(os.path.join(tables_dir, "per_species_health.csv"))
    if not rows:
        raise ValueError(f"{tables_dir}/per_species_health.csv has no species")
    col = next((c for c in FRAME_COLUMNS if c in rows[0]), None)
    if col is None:
        raise ValueError(f"per_species_health.csv has none of {FRAME_COLUMNS}")
    counts = {r["species"]: int(r[col]) for r in rows}
    test = next((r for r in hc.read_csv_rows(os.path.join(tables_dir, "held_out.csv"))
                 if r["population"] == "test"), None)
    if test is None:
        raise ValueError(f"{tables_dir}/held_out.csv has no test row")
    return {
        "run_date": run_date,
        "export": export,
        "frames": frames,
        "labelled": sum(counts.values()),
        "species": len(counts),
        "test_n": int(test["n_frames"]),
        "test_correct": int(test["n_correct_top1"]) if test["n_correct_top1"] else None,
        "test_top1": float(test["top1_accuracy"]) if test["top1_accuracy"] else None,
        "model_version": hc.PLANTNET_MODEL_VERSION,
        "reference": reference.read(tables_dir),
        "species_counts": dict(sorted(counts.items())),
    }


def read(path: str) -> list[dict]:
    """Every line, oldest first. A missing file is no history, not an error."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append(path: str, new: dict) -> bool:
    """Write ``new`` unless its export is already recorded. True when written."""
    if any(e["export"] == new["export"] for e in read(path)):
        return False
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(new, sort_keys=True) + "\n")
    return True
