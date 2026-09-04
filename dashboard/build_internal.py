#!/usr/bin/env python3
"""What to label next: the labelling team's own page.

Orders the unlabelled pool and says why that order is right. Thin on purpose:
the deliverable is ``send_batches.csv`` beside it, and the page exists so the
order can be argued with first. Accuracy reporting is ``build_external.py``.

    python3 dashboard/build_internal.py [--out PATH]

Every number is recomputed from source, then cross-checked against the snapshot
CSVs; a mismatch aborts the build. It gates on the two send-queue CSVs.

One file that opens from file://.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core as hc
import figures
import page as pg
import queues
from assets import esc, hero
from queues import BATCH_SIZE
from history import fail, verify_snapshot

OUT_NAME = "label_queue_dashboard.html"
TITLE = "BCI labelling: what to label next"


def build(h, *, generated, verify_dir, fallback_tag):
    """The queue page: which photos to label next, and why that order.

    The review queue belongs to the model-health page, so it is not gated here.
    """
    c = figures.prepare(h, verify_dir=verify_dir, fallback_tag=fallback_tag)

    # Before anything is rendered. This page's leading claim is that inside each
    # queue the photo least like everything already labelled comes first, and
    # that ordering is read from a file bin/refresh.sh does not write. Missing,
    # the loader falls back to confidence order without a word and the sentence
    # above becomes false. Refuse the build instead: nobody reads a page for the
    # ordering it quietly stopped using.
    complaint = queues.novelty_complaint(hc.QUEUE_NOVELTY_CSV, c.n_ranked, c.n_unlab)
    if complaint:
        fail(complaint)

    c.checks = verify_snapshot(
        verify_dir, per_species=c.per_species, buckets=c.buckets, bins_all=c.bins_all,
        never_all=c.never_all, unscoreable=c.unscoreable, strict_hits=c.strict1,
        queue_counts=c.queue_counts, n_no_answer=c.n_no_answer,
        queue_keys=c.queue_keys)

    # Two counts and one line: the reasoning lives in the panels that state it.
    send_now = c.queue_counts.get("long_tail", 0) + c.queue_counts.get("low_conf_known", 0)
    # The subtitle used to read "{c.n:,} labelled frames behind the ranking",
    # which was one number standing for two. `c.n` is the species-level
    # evaluation set: it is what every per-species status is measured on, and
    # those statuses are what sorts a frame into a queue. The ranking is the
    # other half, the order inside a queue, and it is anchored on the labelled
    # frames that have an embedding, a smaller and differently-selected set.
    # Both are load-bearing here, so both are named, each against its own work.
    anchors = queues.novelty_provenance(hc.QUEUE_NOVELTY_CSV)["anchors"]
    anchor_words = (f"{anchors:,} labelled frames anchor the ranking"
                    if anchors else "anchor count unrecorded")
    P = ['<h1>What to label next</h1>',
         f'<div class="subtitle">built {esc(generated)} &middot; snapshot '
         f'{esc(c.snap_date)} &middot; Pl@ntNet model <code>{esc(c.tag)}</code> '
         f'&middot; {anchor_words} &middot; {c.n:,} labelled frames behind the '
         f'species statuses that sort the queues</div>',
         # Batch 1 leads, not the pool. The pool is 3,919 and a botanist works
         # through a few hundred a month, so leading with it prices the whole
         # queue as the next task and it is many months of them. The number a
         # reader can act on this week is the one batch that ships.
         # Each card links the file its own number is counted off, so the reader
         # who wants the photos behind a headline takes them from the card. Batch
         # 1 is a batch, so it comes off send_batches.csv; the other two count
         # the pool in queue order, which is send_first_queue.csv.
         hero([("Send next", f"{c.n_batch1:,}", "photos in batch 1",
                "One Labelbox batch, the head of the order. Everything below is "
                "the pool it was drawn from, not this week's work.",
                "send_batches.csv"),
               ("Worth sending first", f"{send_now:,}", "unlabelled photos",
                "They point at a species we barely have or barely get right, or at a "
                "usually-right species the model is unsure of here.",
                "send_first_queue.csv"),
               ("Queued", f"{c.n_unlab:,}", "unlabelled photos",
                "The whole pool this page puts in an order.",
                "send_first_queue.csv")]),
         ('<p class="note"><strong>The prioritised batches are in '
          '<code>build/tables/send_batches.csv</code>.</strong> Send from that file. '
          'This page shows the order and the reason behind each photo\'s place in it. '
          f'The file holds {c.n_batches} batches of at most {BATCH_SIZE} photos, each '
          'species group kept together. One batch there is one Labelbox batch, and '
          '<code>global_key</code> is the column Labelbox is given. To send batch 1: '
          '<code>python labelling/dispatch_round.py --round 1 --csv '
          'build/tables/send_batches.csv --batch 1 --test</code> sends the first five '
          'photos only, then the same command with no <code>--test</code> sends the '
          'rest. How Pl@ntNet scores against the labels is a separate page, '
          '<code>model_health_dashboard.html</code>.</p>'),
         # Cadence, because the obvious guess is a monthly rebuild and that is
         # wrong. Nothing about this order changes until the model does: the
         # queues come from Pl@ntNet's own answers, so re-ranking against an
         # unchanged model reproduces the order it already gave.
         ('<p class="note"><strong>This order is recomputed when the Pl@ntNet model '
          'tag changes, not on a calendar.</strong> Pl@ntNet ships a new model when '
          'its authors have one, roughly every two months. Until the tag above moves, '
          're-running this page returns the same order, so work through the batches '
          'rather than waiting for a refresh.</p>'),
         pg.render(c, pg.INTERNAL_PANELS)]

    return pg.document(TITLE, "\n".join(P)), c.checks


def main() -> None:
    pg.run(__doc__, OUT_NAME, build)


if __name__ == "__main__":
    main()
