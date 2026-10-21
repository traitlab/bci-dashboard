#!/usr/bin/env python3
"""What to label next: the labelling team's own page.

Orders the unlabelled pool and says why that order is right. Thin on purpose:
the deliverable is ``send_batches.csv`` beside it, and the page exists so the
order can be argued with first. Accuracy reporting is ``build_external.py``.

    python3 dashboard/build_internal.py [--out PATH]

One page for every reader. What to send comes first and why comes after it,
closed. The commands that need the repository checked out sit in one closed
block for the labelling team, under the photos they send. A small redirect is
written beside the page under the name the team's copy used to have, so a
saved link to it opens that block.

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
import reference
from assets import esc, hero
from queue_panels import TEAM_BLOCK_ID
from queues import BATCH_SIZE
from selection_panels import selection_complaint
from history import fail, verify_snapshot

OUT_NAME = "label_queue_dashboard.html"
TITLE = "BCI labelling: what to label next"

# The labelling team's copy of this page used to be published under this name.
# It is now a redirect to the team block on the one page, so old links land on
# the commands they were saved for.
MOVED_NAME = "label_queue_team.html"


def redirect_stub() -> str:
    """The file left at ``MOVED_NAME``: a meta refresh, and a link for a
    browser that does not follow one."""
    to = f"{OUT_NAME}#{TEAM_BLOCK_ID}"
    return ("<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0; url={to}">'
            f"<title>{TITLE}</title></head><body>"
            f'<p>This page has moved to <a href="{to}">{OUT_NAME}</a>.</p>'
            "</body></html>\n")


def build(h, *, generated, verify_dir, fallback_tag, available_pages=None):
    """The queue page: which photos to label next, and why that order.

    The review queue belongs to the model-health page, so it is not gated here.
    """
    c = figures.prepare(h, verify_dir=verify_dir, fallback_tag=fallback_tag)
    c.available_pages = pg.OPERATIONAL_PAGES | frozenset(available_pages or ())

    # Before anything is rendered. This page's leading claim is that inside each
    # queue the photo least like everything already labelled comes first, and
    # that ordering is read from a file bin/refresh.sh does not write. Missing,
    # the loader falls back to confidence order without a word and the sentence
    # above becomes false. Refuse the build instead: nobody reads a page for the
    # ordering it quietly stopped using.
    complaint = queues.novelty_complaint(hc.QUEUE_NOVELTY_CSV, c.n_ranked, c.n_unlab)
    if complaint:
        fail(complaint)
    # Same refusal for the evidence beside the ordering: an audit or confound
    # file run against a different pool, or different labelled photos, from
    # the ones the ordering file names is stale evidence under a fresh order.
    complaint = selection_complaint(c.selection_audit, c.selection_confound,
                                    queues.novelty_provenance(hc.QUEUE_NOVELTY_CSV))
    if complaint:
        fail(complaint)

    c.checks = verify_snapshot(
        verify_dir, per_species=c.per_species, buckets=c.buckets, bins_all=c.bins_all,
        never_all=c.never_all, unscoreable=c.unscoreable, strict_hits=c.strict1,
        queue_counts=c.queue_counts, n_no_answer=c.n_no_answer,
        queue_keys=c.queue_keys, scored_against=c.reference, populations=c.populations)

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
    anchor_clause = (f"&middot; {anchors:,} labelled frames anchor the ranking "
                     if anchors else "")
    P = ['<h1>What to label next</h1>',
         f'<div class="subtitle">refreshed {esc(generated)} &middot; Labelbox labels merged {esc(c.snap_date)} &middot; '
         f'Pl@ntNet model {esc(c.tag)} '
         f'{anchor_clause}&middot; {c.n:,} frames scored against '
         f'{reference.WORDS[c.reference]} behind the species statuses that sort the '
         f'queues</div>',
         # Batch 1 leads, not the pool. The pool is 3,919 and a botanist works
         # through a few hundred a month, so leading with it prices the whole
         # queue as the next task and it is many months of them. The number a
         # reader can inspect is the first saved batch, regardless of send status.
         # Each card links the file its own number is counted off, so the reader
         # who wants the photos behind a headline takes them from the card. Batch
         # 1 is a batch, so it comes off send_batches.csv; the other two count
         # the pool in queue order, which is send_first_queue.csv.
         hero([("First saved batch", f"{c.n_batch1:,}", "photos in batch 1",
                "The saved first batch from send_batches.csv. The pool below is "
                "broader than this batch.",
                "send_batches.csv"),
               ("Worth sending first", f"{send_now:,}", "unlabelled photos",
                "They point at a species we barely have or barely get right, or at a "
                "usually-right species the model is unsure of here.",
                "send_first_queue.csv"),
               ("Queued", f"{c.n_unlab:,}", "unlabelled photos",
                "The whole pool this page puts in an order.",
                "send_first_queue.csv")], cls="wide"),
         batches_note(c),
         ('<p class="note"><strong>This is a saved queue.</strong> It changes after '
          'labels, predictions or ranking data are refreshed. Work from the published '
          'batch file; reloading this browser page does not refresh the data. '
          'Sending status is not recorded here. Check the batch in Labelbox '
          'before sending it.</p>'),
         pg.render(c, pg.INTERNAL_PANELS),
         pg.footer(c)]

    return pg.document(TITLE, "\n".join(P), current=OUT_NAME,
                       available=c.available_pages), c.checks


def batches_note(c):
    """Where the batches are, in words any reader can act on.

    It links the served copy of the file, which is the one that resolves from
    the site. The path in the repository and the column Labelbox is given are
    in the team block, ``queue_panels.DISPATCH``.
    """
    return (f'<p class="note"><strong>The prioritised batches are in '
            f'<a href="send_batches.csv">send_batches.csv</a>.</strong> '
            f'Send from that file: it holds {c.n_batches} batches of at most '
            f'{BATCH_SIZE} photos, each species group kept together. This page '
            f'shows the order and the reason behind each photo\u2019s place in it. '
            f'How Pl@ntNet scores against the labels is a separate page, '
            f'<a href="model_health_dashboard.html">model_health_dashboard.html</a>.</p>')


def main() -> None:
    out = pg.run(__doc__, OUT_NAME, build)
    stub = os.path.join(os.path.dirname(os.path.abspath(out)), MOVED_NAME)
    with open(stub, "w", encoding="utf-8") as f:
        f.write(redirect_stub())
    print(f"  wrote     {stub}  (redirect to {OUT_NAME}#{TEAM_BLOCK_ID})")


if __name__ == "__main__":
    main()
