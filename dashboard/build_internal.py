#!/usr/bin/env python3
"""What to label next: the labelling team's own page.

Orders the unlabelled pool and says why that order is right. Deliberately thin,
because the deliverable is ``send_batches.csv`` beside it, which the labelling
script reads; the page exists so the order can be argued with first. Accuracy
reporting is ``build_external.py``.

    python3 dashboard/build_internal.py [--out PATH]

Every number is recomputed from source, then cross-checked against the CSVs
``measure.py`` wrote into the snapshot; a mismatch aborts the build. It gates on
the two send-queue CSVs, which the external page does not report.

No network, no key, no third-party package: one file that opens from file://.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import figures
import panels as pn
from assets import esc, hero
from history import verify_snapshot

OUT_NAME = "label_queue_dashboard.html"
TITLE = "BCI labelling: what to label next"


def build(h, *, generated, verify_dir, fallback_tag):
    c = figures.prepare(h, verify_dir=verify_dir, fallback_tag=fallback_tag)

    # The send queue is this page's whole subject, so it gates on both queue
    # CSVs. The review queue belongs to the external page and is checked there.
    c.checks = verify_snapshot(
        verify_dir, per_species=c.per_species, buckets=c.buckets, bins_all=c.bins_all,
        never_all=c.never_all, unscoreable=c.unscoreable, strict_hits=c.strict1,
        queue_counts=c.queue_counts, n_no_answer=c.n_no_answer,
        queue_keys=c.queue_keys)

    # Two counts and one line. The page is a check on the order, so the reasoning
    # behind the order lives in the panels that state it, not above them.
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
          '<code>send_batches.csv</code> in the snapshot folder.</strong> '
          'It carries the same order in batches of at most 100, with each species '
          'group kept together. Read this page to check the order and the rule behind '
          'it, then work the CSV. How Pl@ntNet scores against the labels is a separate '
          'page, <code>model_health_dashboard.html</code>.</p>'),
         pn.render(c, pn.INTERNAL_PANELS)]

    return pn.document(TITLE, "\n".join(P)), c.checks


def main() -> None:
    pn.run(__doc__, OUT_NAME, build)


if __name__ == "__main__":
    main()
