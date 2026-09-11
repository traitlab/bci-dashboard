"""What the label queue must not send, dropped from the pool before ranking.

Two files say a frame is spoken for. ``data/splits.csv`` names the frames the
frame-by-frame grading split holds back. ``input/holdout_v1.csv`` names the
frames the whole-flight holdout holds, drawn by ``labelling/draw_holdout.py``
and kept on record because the pool it came from moves.

Both are dropped for the same reason, and counted apart because they are two
different promises and a reader deserves to know which one moved a number.
Lives here rather than in ``labelling/rank_queue.py`` so that file stays under
the repo's 500-line limit; ``rank_queue`` imports these names and the tests
reach them through it.

Standard library and the array the caller already has. No numpy import, no
speciesfirst import: the only thing done to the vectors is take rows out.
"""

from __future__ import annotations

import csv
from pathlib import Path

# The role ``draw_holdout.py`` writes for a frame the holdout holds. A `train`
# or `buffered` row is not held and keeps whatever splits.csv says about it.
HELD_ROLE = "held"


def load_splits(path: Path) -> dict[str, str]:
    """``global_key -> split`` for every frame that carries one. An absent file
    holds nothing out, which is what a checkout without a split gets."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["global_key"]: r["split"] for r in csv.DictReader(f)
                if r.get("global_key") and r.get("split")}


def load_holdout(path: Path) -> set[str]:
    """The global keys the flight holdout holds, read off its role column.

    An absent file holds nothing, which is what a checkout without a drawn
    holdout gets. Read with the standard library, like everything else that
    reads this file, so no part of the pipeline needs the draw's dependencies
    to know what the draw decided.
    """
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {r["global_key"] for r in csv.DictReader(f)
                if r.get("global_key") and r.get("role") == HELD_ROLE}


def _without(keys: list[str], emb, drop) -> tuple[list[str], object, int]:
    keep = [i for i, k in enumerate(keys) if k not in drop]
    return [keys[i] for i in keep], emb[keep], len(keys) - len(keep)


def drop_split_frames(keys: list[str], emb, splits: dict[str, str]):
    """The pool without the frames the queue would refuse anyway.

    ``dashboard/queues.send_first_rows`` holds out every frame carrying a split,
    so ranking them is not harmless: farthest-first picks the frame furthest
    from everything picked so far, and a held-out frame it picks takes a rank a
    sendable frame never gets, then goes on pushing its neighbours down for
    being near it. Dropped here, not passed as labelled: they are not labelled,
    and a frame that pretends to be would hide the sendable frames beside it.
    """
    return _without(keys, emb, splits)


def drop_holdout_frames(keys: list[str], emb, held: set[str]):
    """The pool without the frames the flight holdout holds.

    Same argument as ``drop_split_frames``, and a separate call because the two
    sets answer different questions. A held frame is on a flight no train frame
    is on, and sending it back for labelling would put a new answer into the one
    set that can say what the model does on a flight it has never seen.
    """
    return _without(keys, emb, held)
