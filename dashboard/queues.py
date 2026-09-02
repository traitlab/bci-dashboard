"""Which unlabelled photos to send a botanist next, and in what order.

`core.py` holds the vocabulary every module shares. This holds one decision
procedure written on top of it: the four send-first queues, the order a
botanist works through them, and how the queue is packed into batches one
sitting can review. `measure.py` writes it to CSV and `figures.py` counts the
page from it, both through `send_first_rows`, so the file and the page cannot
disagree.

The two column lists are here rather than in `measure.py` because
`chunk_send_batches` reads queue rows by position: the order is a fact the
writer and the batcher share, so it is named once and both read it.
"""

from __future__ import annotations

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

# send_first_queue.csv's columns, in order. `measure.py` writes this as the
# header and `chunk_send_batches` below reads rows by position, so the order is
# a fact two modules share. Named here, indexed from here, written from here.
SEND_FIRST_COLUMNS = ["queue", "global_key", "split", "predicted_species", "confidence",
                      "species_labelled_crowns", "species_top1_accuracy"]
# send_batches.csv's columns, likewise: `chunk_send_batches` returns rows in
# this order and `measure.py` writes the header.
SEND_BATCH_COLUMNS = ["batch_id", "species_group", "global_key", "queue"]

# Labelbox send batches: no more than this many crowns per batch, so a single
# send stays inside what one botanist session can review.
BATCH_SIZE = 100


def chunk_send_batches(queue_rows: list, batch_size: int = BATCH_SIZE) -> list:
    """Species-grouped, priority-first batches over an already-ordered
    ``queue_rows`` (send_first_queue.csv order). Each species is visited
    once, at its highest-priority row; its rows travel together, packed
    whole until the next would overflow ``batch_size``, then split.
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

    # One group per species, split first so an oversized species cannot
    # straddle a batch boundary; the trailing part packs like any other group.
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

    ``support``: labelled-crown count per species. ``top1``: measured
    accuracy per species. Absent from both means never labelled. First
    rule wins, so a weak guess on a rare species stays in the long tail.
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


def send_first_rows(predictions, joined_stems, canon, support, top1) -> tuple:
    """Every unlabelled frame's queue, in the order send_first_queue.csv writes.

    Returns ``([(queue, stem, species, confidence), ...], n_no_answer)``.
    ``measure.py`` writes the CSV from this and ``figures.py`` counts the page
    from it: both used to walk the cache themselves, and `verify_snapshot` then
    compared the two lists row for row to catch the drift. One walk means there
    is no drift to catch.

    Order is queue first, then least confident inside a queue, then the stem:
    the most uncertain frame of a group is the one most worth an expert look.
    A frame the model answered nothing for is counted, not queued.
    """
    rows, n_no_answer = [], 0
    for stem in sorted(predictions):
        if stem in joined_stems:
            continue
        ranked = [(canon(name), score) for name, score in predictions[stem]]
        if not ranked:
            n_no_answer += 1
            continue
        pred, conf = ranked[0]
        rows.append((queue_of_prediction(pred, conf, support, top1), stem, pred, conf))
    rows.sort(key=lambda r: (QUEUE_ORDER.index(r[0]), r[3], r[1]))
    return rows, n_no_answer
