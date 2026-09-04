#!/usr/bin/env python3
"""How Pl@ntNet does against the labels: the page that leaves the lab.

For people outside the labelling team: how well Pl@ntNet names BCI drone
close-ups, per species, and what the ceilings on that number are. What to label
next is ``build_internal.py``.

    python3 dashboard/build_external.py [--out PATH]

Every number is recomputed from source, then cross-checked against the snapshot
CSVs; a mismatch aborts the build. It gates only on the CSVs behind a number it
prints, so not on the send queue.

One file that opens from file://.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import confirmatory_panels as cp
import figures
import panels
import page as pg
from assets import esc
from history import verify_snapshot

OUT_NAME = "model_health_dashboard.html"
TITLE = "How well does Pl@ntNet name BCI trees?"


def build(h, *, generated, verify_dir, fallback_tag):
    """The model-health page: how well Pl@ntNet names the trees, and what that
    number does not cover.

    Every figure is checked against the snapshot CSVs before any HTML is written.
    """
    c = figures.prepare(h, verify_dir=verify_dir, fallback_tag=fallback_tag)

    # No send queue printed here, so none gated on. The review queue is.
    c.checks = verify_snapshot(
        verify_dir, per_species=c.per_species, buckets=c.buckets, bins_all=c.bins_all,
        never_all=c.never_all, unscoreable=c.unscoreable, strict_hits=c.strict1,
        review_counts=c.review_counts)

    # The head is two numbers and one line saying which to quote. Everything
    # that qualifies them is a panel below.
    P = [f'<h1>{esc(TITLE)}</h1>',
         f'<div class="subtitle">built {esc(generated)} &middot; snapshot '
         f'{esc(c.snap_date)} &middot; Pl@ntNet model <code>{esc(c.tag)}</code> '
         f'&middot; {c.n:,} labelled frames &middot; {c.n_sp} species</div>',
         # One paragraph, not three. Etienne on 2026-09-03: "there's a lot of
         # text there ... people don't read stuff, because they'll read if they
         # need to." It has one job, to say what population every number below
         # is measured on, because a rate without its denominator is the thing
         # this repo refuses to publish. The averaging argument moved to the
         # explanations section, next to the chart that makes it.
         f'<p class="intro">Pl@ntNet is asked to name the tree in each frame a botanist '
         f'labelled. Every number below is measured on the same {c.n:,} labelled frames '
         f'across {c.n_sp} species, one guess per frame. What to label next is a separate '
         f'page, <code>label_queue_dashboard.html</code>.</p>',
         # The corpus rates lead: they are what this page measures every session
         # and the only rates the deployable path can produce.
         panels.headline_hero(c),
         # They are measured against a label for a region they do not cover, so
         # the correction travels with them rather than sitting in a panel. The
         # script's openHash expands the panel behind the link on arrival.
         cp.floor_note(cp.require(c.cf)),
         ]
    P.append(pg.render(c, pg.EXTERNAL_PANELS))

    return pg.document(TITLE, "\n".join(P)), c.checks


def main() -> None:
    pg.run(__doc__, OUT_NAME, build)


if __name__ == "__main__":
    main()
