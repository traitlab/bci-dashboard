#!/usr/bin/env python3
"""What to label next: the labelling team's own page.

Orders the unlabelled pool and says why that order is right. Thin on purpose:
the deliverable is ``send_batches.csv`` beside it, and the page exists so the
order can be argued with first. Accuracy reporting is ``build_external.py``.

    python3 dashboard/build_internal.py [--out PATH]

Every number is recomputed from source, then cross-checked against the snapshot
CSVs; a mismatch aborts the build. It gates on the two send-queue CSVs.

No network, no key, no third-party package: one file that opens from file://.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import figures
import page as pg
from assets import esc, hero
from queues import BATCH_SIZE
from history import verify_snapshot

OUT_NAME = "label_queue_dashboard.html"
TITLE = "BCI labelling: what to label next"


def build(h, *, generated, verify_dir, fallback_tag):
    """The queue page: which photos to label next, and why that order.

    The review queue belongs to the model-health page, so it is not gated here.
    """
    c = figures.prepare(h, verify_dir=verify_dir, fallback_tag=fallback_tag)

    c.checks = verify_snapshot(
        verify_dir, per_species=c.per_species, buckets=c.buckets, bins_all=c.bins_all,
        never_all=c.never_all, unscoreable=c.unscoreable, strict_hits=c.strict1,
        queue_counts=c.queue_counts, n_no_answer=c.n_no_answer,
        queue_keys=c.queue_keys)

    # Two counts and one line: the reasoning lives in the panels that state it.
    send_now = c.queue_counts.get("long_tail", 0) + c.queue_counts.get("low_conf_known", 0)
    P = ['<h1>What to label next</h1>',
         f'<div class="subtitle">built {esc(generated)} &middot; snapshot '
         f'{esc(c.snap_date)} &middot; Pl@ntNet model <code>{esc(c.tag)}</code> '
         f'&middot; {c.n:,} labelled frames behind the ranking</div>',
         hero([("Worth sending first", f"{send_now:,}", "unlabelled photos",
                "They point at a species we barely have or barely get right, or at a "
                "usually-right species the model is unsure of here."),
               ("Queued", f"{c.n_unlab:,}", "unlabelled photos",
                "The whole pool this page puts in an order.")]),
         ('<p class="note"><strong>The page is not the deliverable. Work '
          '<code>build/tables/send_batches.csv</code>.</strong> '
          f'It carries the same order in batches of at most {BATCH_SIZE}, with each species '
          'group kept together. Read this page to check the order and the rule behind '
          'it, then work the CSV. How Pl@ntNet scores against the labels is a separate '
          'page, <code>model_health_dashboard.html</code>.</p>'),
         pg.render(c, pg.INTERNAL_PANELS)]

    return pg.document(TITLE, "\n".join(P)), c.checks


def main() -> None:
    pg.run(__doc__, OUT_NAME, build)


if __name__ == "__main__":
    main()
