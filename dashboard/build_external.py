#!/usr/bin/env python3
"""How Pl@ntNet does against the labels: the page that leaves the lab.

For people outside the labelling team: how well Pl@ntNet names BCI drone
close-ups, per species, and what the ceilings on that number are. What to label
next is ``build_internal.py``.

    python3 dashboard/build_external.py [--out PATH]

Every number is recomputed from source, then cross-checked against the CSVs
``measure.py`` wrote into the snapshot; a mismatch aborts the build. It gates
only on the CSVs behind a number it prints, so not on the send queue. Latest
snapshot only, no trend.

No network, no key, no third-party package: one file that opens from file://.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import confirmatory_panels as cp
import figures
import page as pg
from assets import esc
from history import verify_snapshot

OUT_NAME = "model_health_dashboard.html"
TITLE = "How well does Pl@ntNet name BCI trees?"


def build(h, *, generated, verify_dir, fallback_tag):
    """The model-health page: how well Pl@ntNet names the trees, and what that
    number does not cover.

    Every figure is recomputed here and checked against the snapshot CSVs before
    a single line of HTML is written, so a page that builds is a page whose
    numbers still match what was committed.
    """
    c = figures.prepare(h, verify_dir=verify_dir, fallback_tag=fallback_tag)

    # This page reports no send queue, so it does not gate on one. It still gates
    # on every CSV behind a number it does print, including the review queue.
    c.checks = verify_snapshot(
        verify_dir, per_species=c.per_species, buckets=c.buckets, bins_all=c.bins_all,
        never_all=c.never_all, unscoreable=c.unscoreable, strict_hits=c.strict1,
        review_counts=c.review_counts)

    # The head is two numbers and one line saying which to quote. Everything that
    # qualifies them is a panel below: the glossary, the caveats the design requires,
    # and the four corpus-wide rates with the region mismatch they inherit.
    # The heading is the tab title. They were the same sentence typed twice.
    P = [f'<h1>{esc(TITLE)}</h1>',
         f'<div class="subtitle">built {esc(generated)} &middot; snapshot '
         f'{esc(c.snap_date)} &middot; Pl@ntNet model <code>{esc(c.tag)}</code> '
         f'&middot; {c.n:,} labelled frames &middot; {c.n_sp} species</div>',
         # The set-aside sample is not named here. Both cards below say "on the
         # {n} set-aside frames" in their own sublabel, and the note under them
         # says the gap was measured before either number existed, so a reader
         # met it three times in the first hundred words. The intro's job is
         # what the two numbers compare.
         f'<p class="intro">This page says how well Pl@ntNet names the trees a botanist '
         f'labelled. The two numbers at the top show what difference it makes to outline '
         f'the trees before asking.</p>'
         f'<p class="intro">Everything below them covers all {c.n:,} labelled frames, one '
         f'Pl@ntNet guess per frame. That is what lets the page say, species by species, '
         f'how often the guess is right. What to label next is a separate page, <code>label_queue_dashboard.html</code>.</p>',
         # The headline first, on the frozen sample, because it is the only number here
         # whose unit of prediction is the unit the label describes. The corpus-wide
         # grid follows it, inside a panel, not the other way round.
         cp.confirmatory_hero(c.cf),
         # The gap is the finding, so it is prose rather than a hover tooltip nothing
         # on a phone would see.
         # The two warnings are the fourth panel down, not the first: "terms"
         # and "counts" lead, for the reasons above EXTERNAL_PANELS. So the
         # instruction links rather than pointing, and the script's openHash
         # expands the panel on arrival.
         (f'<p class="note"><strong>Quote the top number, and carry the '
          f'<a href="#two-warnings">two warnings</a> that go with it.</strong> '
          f'Outlining the trees first is worth '
          f'{100 * c.cf["crown_minus_photo"]:+.1f} points over sending the fixed centre '
          f'square. That gap was measured on frames set aside before either number '
          f'existed.</p>'),
         ]
    P.append(pg.render(c, pg.EXTERNAL_PANELS))

    return pg.document(TITLE, "\n".join(P)), c.checks


def main() -> None:
    pg.run(__doc__, OUT_NAME, build)


if __name__ == "__main__":
    main()
