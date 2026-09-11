#!/usr/bin/env python3
"""What to label next: the labelling team's own page.

Orders the unlabelled pool and says why that order is right. Thin on purpose:
the deliverable is ``send_batches.csv`` beside it, and the page exists so the
order can be argued with first. Accuracy reporting is ``build_external.py``.

    python3 dashboard/build_internal.py [--team] [--out PATH]

Two files come out of this one builder. Without ``--team`` it writes the public
page, which leaves out everything that only works with the repository checked
out. With ``--team`` it writes ``label_queue_team.html``, which carries all of
it. The public page links the team one, so nothing is hidden, only moved.

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
from selection_panels import selection_complaint
from history import fail, verify_snapshot

OUT_NAME = "label_queue_dashboard.html"
TEAM_OUT_NAME = "label_queue_team.html"
TITLE = "BCI labelling: what to label next"

# The one line the public page carries in place of the repository parts. It is
# a link rather than a silence: a reader who wants the commands should be able
# to see that they exist and who they are for.
TEAM_LINK = (f'<p class="note">The same page with the commands that send a batch is '
             f'<a href="{TEAM_OUT_NAME}">{TEAM_OUT_NAME}</a>, for the labelling team, '
             f'needs the repo.</p>')


def build(h, *, generated, verify_dir, fallback_tag, team=False):
    """The queue page: which photos to label next, and why that order.

    The review queue belongs to the model-health page, so it is not gated here.

    ``team`` writes the labelling team's copy. Everything it adds needs the
    repository checked out, so the public page carries a link to it instead.
    """
    c = figures.prepare(h, verify_dir=verify_dir, fallback_tag=fallback_tag)
    # Read by the panels that have a team half and a public half.
    c.team = team

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
         f'{esc(c.snap_date)} &middot; Pl@ntNet model {esc(c.tag)} '
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
         batches_note(c, team),
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
    if not team:
        P.append(TEAM_LINK)
    P.append(pg.footer(c))

    return pg.document(TITLE, "\n".join(P)), c.checks


def batches_note(c, team):
    """Where the batches are, in the words each audience can act on.

    The team copy names the file in the repository and the column Labelbox is
    given, because a reader with the checkout can open both. The public copy
    links the served copy of the same file, which is the one that resolves from
    the site, and says nothing about columns nobody outside the team sends.
    """
    where = ('<code>build/tables/send_batches.csv</code>' if team
             else '<a href="send_batches.csv">send_batches.csv</a>')
    detail = (' One batch there is one Labelbox batch, and <code>global_key</code> is '
              'the column Labelbox is given.' if team else '')
    return (f'<p class="note"><strong>The prioritised batches are in {where}.</strong> '
            f'Send from that file: it holds {c.n_batches} batches of at most '
            f'{BATCH_SIZE} photos, each species group kept together.{detail} This page '
            f'shows the order and the reason behind each photo\u2019s place in it. '
            f'How Pl@ntNet scores against the labels is a separate page, '
            f'<a href="model_health_dashboard.html">model_health_dashboard.html</a>.</p>')


def main() -> None:
    pg.run(__doc__, OUT_NAME, build, team_name=TEAM_OUT_NAME)


if __name__ == "__main__":
    main()
