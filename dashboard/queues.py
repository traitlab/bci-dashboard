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
SEND_BATCH_COLUMNS = ["batch_id", "species_group", "global_key", "queue"]

# No more than this many crowns per Labelbox batch, one botanist session's worth.
BATCH_SIZE = 100

# The place in the order a frame with no vector takes: after every ranked frame
# of its queue, where the frames behind it keep today's confidence order. Bigger
# than any rank the ranker can assign, since the pool is four figures.
NO_NOVELTY = 10 ** 9


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


def chunk_send_batches(queue_rows: list, batch_size: int = BATCH_SIZE) -> list:
    """Species-grouped, priority-first batches over an already-ordered
    ``queue_rows`` (send_first_queue.csv order). Each species is visited once,
    at its highest-priority row; its rows travel together, packed whole until
    the next would overflow ``batch_size``, then split.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")
    order: list[str] = []
    seen: set[str] = set()
    by_species: dict[str, list] = defaultdict(list)
    queue_at = SEND_FIRST_COLUMNS.index("queue")
    key_at = SEND_FIRST_COLUMNS.index("global_key")
    species_at = SEND_FIRST_COLUMNS.index("predicted_species")
    for row in queue_rows:
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
    held = batch_size  # rows already in the open batch; forces the first one open
    for sp, rows in groups:
        if held + len(rows) > batch_size:
            batch_id += 1
            held = 0
        held += len(rows)
        for row in rows:
            batches.append([batch_id, sp, row[key_at], row[queue_at]])
    return batches


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
