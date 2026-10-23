"""The per-run manifest: one JSON line per Labelbox export the weekly refresh saw.

Snapshots are dated folders that CI throws away, so nothing compared one update
with the next. This keeps the few numbers a change log needs: how many frames
were labelled, which species, how many frames each, the test top-1 with its
frame count, and the model version. ``refresh_snapshot.py build`` appends a line;
``snapshot_delta.py`` reads the last two.

Idempotent on the export: a rerun with the same content changes nothing, and
a rerun whose numbers moved replaces the newest line.
Standard library only, like everything under dashboard/.
"""

from __future__ import annotations

import json
import os

import core as hc
import reference

FRAME_COLUMNS = ("n_labelled_frames", "n_labelled_crowns")
REQUIRED = {"run_date", "export", "frames", "labelled", "species", "test_n", "test_correct",
            "test_top1", "model_version", "species_counts"}


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
    """Every usable line, oldest first. A missing file is no history, not an error.

    A truncated line or one missing a key is skipped with a warning: one bad
    line in a kept artifact must not block every later refresh.
    """
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                if not isinstance(e, dict) or REQUIRED - e.keys():
                    raise ValueError("missing key")
            except ValueError:
                print(f"::warning::{path} line {n} is unreadable and was skipped", flush=True)
                continue
            out.append(e)
    return out


def _same(a: dict, b: dict) -> bool:
    return {k: v for k, v in a.items() if k != "run_date"} == {k: v for k, v in b.items() if k != "run_date"}


def append(path: str, new: dict) -> bool:
    """Record ``new``. True when the file changed.

    An export older than the newest recorded one is refused (a run that fetched
    no labels would otherwise run the delta backwards). The same export as the
    newest replaces that line when the numbers or model moved, and changes
    nothing when they did not. Older lines are never rewritten.
    """
    lines = read(path)
    if lines:
        newest = max(range(len(lines)), key=lambda i: lines[i]["export"])
        if new["export"] < lines[newest]["export"]:
            return False
        if new["export"] == lines[newest]["export"]:
            if _same(lines[newest], new):
                return False
            lines[newest] = new
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(json.dumps(e, sort_keys=True) + "\n" for e in lines)
            return True
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(new, sort_keys=True) + "\n")
    return True
