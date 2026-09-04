"""Which unlabelled photos to send a botanist next, and in what order.

One decision procedure on top of `core.py`'s shared vocabulary: the four
send-first queues, their order, and how the queue is packed into batches one
sitting can review. `measure.py` and `figures.py` both go through
`send_first_rows`, so the file and the page cannot disagree. They must also go
through `load_novelty` for the same reason: two readings of the ordering file
would put the page and the CSV in a different order, which aborts the build.

Not in `core.py`, which holds "the vocabulary every other module works in",
because this is a decision procedure rather than vocabulary and has its own
reason to change: a botanist saying the queue sends the wrong photos first. The
five thresholds stay in `core` because `run_log.py` and both page builders read
them too. The two column orders came here to sit beside the batcher that
indexes them by position, which is how they last drifted apart.
"""

from __future__ import annotations

import csv
import os
import random
import re
from collections import defaultdict

from core import (
    HARD_MAX_TOP1,
    LOW_CONF,
    RELIABLE_MIN_TOP1,
    WAIT_CONF,
    WELL_SAMPLED_MIN_N,
)


# Queue names, in the order a botanist should work through them.
QUEUE_ORDER = ["long_tail", "low_conf_known", "normal", "can_wait"]

# send_first_queue.csv's columns, in order. `measure.py` writes the header and
# `chunk_send_batches` below reads rows by position, so the order is named once.
SEND_FIRST_COLUMNS = ["queue", "global_key", "split", "predicted_species", "confidence",
                      "species_labelled_crowns", "species_top1_accuracy", "novelty_rank"]
# send_batches.csv's columns, likewise: returned in this order, written as that header.
SEND_BATCH_COLUMNS = ["batch_id", "species_group", "global_key", "queue", "picked_by"]

# No more than this many crowns per Labelbox batch, one botanist session's worth.
BATCH_SIZE = 100

# The share of the first batch drawn at random from the whole unlabelled pool
# instead of from the head of the queue. Nothing here measures whether the queue
# fills gaps faster than sending photos at random, and after the first batch is
# labelled nothing ever can: every later batch is chosen from a pool the queue
# has already reshaped. These frames are the comparison, and they are only a
# comparison if they go out with the first batch.
#
# 15% of a hundred is fifteen frames. Small enough that the botanist hours the
# queue was built to save are still mostly saved, large enough that fifteen
# random draws say something about how the two orders differ.
CONTROL_FRACTION = 0.15
# Fixed, so two runs of measure.py write the same file. Changing it draws a
# different fifteen frames, which is a new comparison, not a correction.
CONTROL_SEED = 20260903
# What a control row carries in `species_group`. Not a species, and it cannot
# collide with one: every species name here is a binomial.
CONTROL_GROUP = "control"

# The place in the order a frame with no vector takes: after every ranked frame
# of its queue, where the frames behind it keep today's confidence order. Bigger
# than any rank the ranker can assign, since the pool is four figures.
NO_NOVELTY = 10 ** 9

# The sidecar `labelling/rank_queue.py` writes beside the ordering file, and the
# `rows=N` it puts on each source line. The ranker runs outside bin/refresh.sh,
# so this file is the only record of when the ordering was last rebuilt and
# against what.
NOVELTY_PROVENANCE_SUFFIX = ".provenance.txt"
_PROVENANCE_ROWS = re.compile(r"\brows=(\d+)\b")


def load_novelty(path: str) -> dict:
    """``global_key`` -> how unlike the labelled frames a photo looks, 1 first.

    Written by ``labelling/rank_queue.py``, which needs numpy and so cannot run
    here. An absent file is the normal state of a fresh clone and of any
    checkout before the embeddings are fetched: it returns ``{}``, every frame
    ties, and the order falls back to what it was before this file existed.
    A row whose rank is not a whole number is dropped rather than guessed at.
    """
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key, rank = row.get("global_key"), row.get("novelty_rank")
            if not key or rank is None:
                continue
            try:
                out[key] = int(rank)
            except ValueError:
                continue
    return out


def novelty_provenance(path: str) -> dict:
    """What the ordering file was built from: written date, anchors, pool.

    ``labelling/rank_queue.py`` writes the sidecar beside the CSV because the
    ranker runs outside ``bin/refresh.sh``, in its own virtualenv, and nothing
    else on disk records when it last ran. Every value is ``None`` when the
    sidecar is absent or does not carry that line: a missing number is reported
    as missing, never guessed at from the CSV, because the two counts a reader
    wants (how many labelled frames anchored the ranking, how many photos were
    ranked against them) are properties of the embedding files and not of this
    CSV's row count.
    """
    out: dict = {"written": None, "anchors": None, "pool": None}
    sidecar = os.path.splitext(path)[0] + NOVELTY_PROVENANCE_SUFFIX
    if not os.path.exists(sidecar):
        return out
    with open(sidecar, encoding="utf-8") as f:
        for line in f:
            role, sep, rest = line.partition(":")
            if not sep:
                continue
            role = role.strip()
            if role == "written":
                out["written"] = rest.strip() or None
            elif role in ("anchors", "pool"):
                found = _PROVENANCE_ROWS.search(rest)
                if found:
                    out[role] = int(found.group(1))
    return out


def novelty_complaint(path: str, n_ranked: int, n_unlab: int) -> str:
    """Why a page must not be built off this ordering file, or ``""``.

    ``queues.load_novelty`` is deliberately forgiving: an absent file is the
    normal state of a fresh clone, and it returns ``{}`` so the queue still
    comes out in confidence order. That forgiveness is the hazard. The ranker
    is not in ``bin/refresh.sh``, so the file can go missing between two builds
    without anything else changing, and the page goes on saying the photo least
    like everything already labelled comes first while the order behind that
    sentence has silently reverted to the one it replaced.

    So the loader keeps falling back and the *builder* refuses instead. A page
    that describes an ordering it is not using is worse than a page that will
    not build: the first is read and believed, the second is fixed.
    """
    if not os.path.exists(path):
        return (f"{path} is missing, so every frame ties on novelty and the queue "
                f"has silently fallen back to confidence order, which is not the "
                f"order this page describes. Re-run labelling/rank_queue.py, or "
                f"take the ordering claim off the page.")
    if n_unlab and not n_ranked:
        return (f"{path} is present but ranks none of the {n_unlab:,} queued frames, "
                f"so the queue is in confidence order while the page describes an "
                f"embedding order. The file is stale against this pool: re-run "
                f"labelling/rank_queue.py.")
    return ""


def control_size(batch_size: int = BATCH_SIZE,
                 fraction: float = CONTROL_FRACTION) -> int:
    """How many of a batch are the comparison rather than queue work.

    The page quotes this and the batcher reserves room for it, so it is worked
    out once. Never the whole batch: the first batch has queue work to do too.
    """
    if not 0 <= fraction < 1:
        raise ValueError(f"control fraction must be in [0, 1), got {fraction}")
    n = round(batch_size * fraction)
    return 0 if n < 1 else min(n, batch_size - 1)


def draw_control_slice(queue_rows: list, batch_size: int = BATCH_SIZE,
                       fraction: float = CONTROL_FRACTION,
                       seed: int = CONTROL_SEED) -> list:
    """The row indices of the frames the first batch carries as a comparison.

    A uniform draw from the whole pool, the head of the queue included. A frame
    that the queue would have sent anyway is a legitimate outcome of a random
    draw, and dropping it to avoid the overlap is what would bias the sample.

    ``fraction`` of ``batch_size``, not of the pool: the slice rides in the
    first batch, so its size is set by what one batch holds. A fraction of 0
    draws nothing, which is how this is turned off.
    """
    n = min(control_size(batch_size, fraction), len(queue_rows))
    if n < 1:
        return []
    return sorted(random.Random(seed).sample(range(len(queue_rows)), n))


def chunk_send_batches(queue_rows: list, batch_size: int = BATCH_SIZE,
                       control_fraction: float = CONTROL_FRACTION) -> list:
    """Species-grouped, priority-first batches over an already-ordered
    ``queue_rows`` (send_first_queue.csv order). Each species is visited once,
    at its highest-priority row; its rows travel together, packed whole until
    the next would overflow ``batch_size``, then split.

    The first batch gives up ``control_fraction`` of its room to the control
    slice, which rides at the end of it as one block. Every other batch packs as
    before. The result is still a repartition of the queue: the control frames
    are moved forward, never added, and no frame is sent twice.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")
    queue_at = SEND_FIRST_COLUMNS.index("queue")
    key_at = SEND_FIRST_COLUMNS.index("global_key")
    species_at = SEND_FIRST_COLUMNS.index("predicted_species")

    control_at = set(draw_control_slice(queue_rows, batch_size, control_fraction))
    control = [queue_rows[i] for i in sorted(control_at)]
    # Reserved room, so the first batch stays inside batch_size once the slice
    # is appended to it.
    first_cap = batch_size - len(control)

    order: list[str] = []
    seen: set[str] = set()
    by_species: dict[str, list] = defaultdict(list)
    for i, row in enumerate(queue_rows):
        if i in control_at:
            continue
        sp = row[species_at]
        by_species[sp].append(row)
        if sp not in seen:
            seen.add(sp)
            order.append(sp)

    # Split oversized species first, so no group straddles a batch boundary.
    groups = [(sp, by_species[sp][i:i + batch_size])
              for sp in order
              for i in range(0, len(by_species[sp]), batch_size)]

    batches = []
    batch_id = 0
    held = cap = 0  # rows in the open batch, and its room; forces the first open
    pending = list(groups)
    while pending:
        sp, rows = pending.pop(0)
        if held + len(rows) > cap:
            batch_id += 1
            cap = first_cap if batch_id == 1 else batch_size
            held = 0
            if len(rows) > cap:
                # Only reachable on the first batch, whose room is short by the
                # slice. Chop the group to what fits rather than leave the batch
                # nearly empty; the rest is the next group in line. With no
                # slice, `cap` is `batch_size` and the groups are already split
                # to it, so this is unreachable and the packing is unchanged.
                pending.insert(0, (sp, rows[cap:]))
                rows = rows[:cap]
        held += len(rows)
        for row in rows:
            batches.append([batch_id, sp, row[key_at], row[queue_at], "queue"])

    if not control:
        return batches
    # After the first batch's own rows and before the second's, so the block is
    # contiguous and the file still reads in batch order.
    at = next((i for i, b in enumerate(batches) if b[0] > 1), len(batches))
    return (batches[:at]
            + [[1, CONTROL_GROUP, r[key_at], r[queue_at], "control"] for r in control]
            + batches[at:])


def queue_of_prediction(pred: str, conf: float, support: dict, top1: dict) -> str:
    """Which queue an unlabelled crown lands in, from its first guess alone.

    ``support``: labelled-crown count per species. ``top1``: measured accuracy
    per species. Absent from both means never labelled. First rule wins, so a
    weak guess on a rare species stays in the long tail.
    """
    n = support.get(pred, 0)
    a = top1.get(pred)
    if n < WELL_SAMPLED_MIN_N or (a is not None and a < HARD_MAX_TOP1):
        return "long_tail"
    if a is not None and a >= RELIABLE_MIN_TOP1 and conf < LOW_CONF:
        return "low_conf_known"
    if conf >= WAIT_CONF and n >= WELL_SAMPLED_MIN_N:
        return "can_wait"
    return "normal"


def send_first_rows(predictions, joined_stems, canon, support, top1,
                    novelty=None, key_prefix="") -> tuple:
    """Every unlabelled frame's queue, in the order send_first_queue.csv writes.

    Returns ``([(queue, stem, species, confidence, novelty_rank), ...],
    n_no_answer)``. Order is queue first, then least like the frames already
    labelled, then least confident, then the stem. Confidence says nothing about
    a species with almost no labels, and on the long-lens camera it is not
    trustworthy at all, so what a photo looks like leads and confidence breaks
    the tie. A frame the model answered nothing for is counted, not queued.

    ``novelty`` is the map ``load_novelty`` returns, keyed the way the CSV
    writes a photo, hence ``key_prefix``. Empty, or missing a frame, and that
    frame sorts to the back of its queue in confidence order: the behaviour
    before there were any vectors, and the way to undo this ordering.
    """
    novelty = novelty or {}
    rows, n_no_answer = [], 0
    for stem in sorted(predictions):
        if stem in joined_stems:
            continue
        ranked = [(canon(name), score) for name, score in predictions[stem]]
        if not ranked:
            n_no_answer += 1
            continue
        pred, conf = ranked[0]
        rows.append((queue_of_prediction(pred, conf, support, top1), stem, pred, conf,
                     novelty.get(key_prefix + stem, NO_NOVELTY)))
    rows.sort(key=lambda r: (QUEUE_ORDER.index(r[0]), r[4], r[3], r[1]))
    return rows, n_no_answer
