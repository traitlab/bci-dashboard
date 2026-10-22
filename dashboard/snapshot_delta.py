"""Then and now: what the last labelling export changed.

Every page reports the latest state. The refresh manifest (``manifest.py``) keeps
one line per Labelbox export, and this compares the last two: new labelled
frames, new species, the species whose count moved, and the test top-1 with the
frame count behind it. It also keeps the last few lines as a short history.

A pair of lines scored against other reference labels is not compared on top-1:
a change across it is the labels', not the model's. ``reference.break_sentence``
names the break.

Read with the standard library only, like everything under dashboard/.
"""

from __future__ import annotations

HISTORY_RUNS = 8


def diff(prev: dict, cur: dict) -> dict:
    """What changed from manifest line ``prev`` to the later line ``cur``."""
    before, after = prev["species_counts"], cur["species_counts"]
    moved = [(sp, before.get(sp, 0), after.get(sp, 0))
             for sp in sorted(set(before) | set(after))
             if before.get(sp, 0) != after.get(sp, 0)]
    # Biggest gain first, then biggest loss, so the rows that matter lead.
    moved.sort(key=lambda m: (-(m[2] - m[1]), m[0]))
    crossed = ((prev.get("reference"), cur.get("reference"))
               if prev.get("reference") != cur.get("reference") else None)
    top1 = (None if crossed or prev["test_top1"] is None or cur["test_top1"] is None
            else cur["test_top1"] - prev["test_top1"])
    return {
        "prev": prev, "cur": cur,
        "new_labelled": cur["labelled"] - prev["labelled"],
        "new_frames": cur["frames"] - prev["frames"],
        "new_species": [(sp, after[sp]) for sp in sorted(set(after) - set(before))],
        "lost_species": sorted(set(before) - set(after)),
        "moved": moved,
        "top1_delta": top1,
        "crossed": crossed,
    }


def compute(lines: list[dict]) -> dict:
    """``lines`` are manifest lines, oldest first. ``diff`` is None until there
    are two, and ``runs`` is the last HISTORY_RUNS, newest first."""
    return {"runs": lines[-HISTORY_RUNS:][::-1],
            "diff": diff(lines[-2], lines[-1]) if len(lines) >= 2 else None}
