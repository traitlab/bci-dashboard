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

import figures
import panels as pn
from assets import esc
from history import verify_snapshot

OUT_NAME = "model_health_dashboard.html"
TITLE = "How well does Pl@ntNet name BCI trees?"


def build(h, *, generated, verify_dir, fallback_tag):
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
    P = ['<h1>How well does Pl@ntNet name BCI trees?</h1>',
         f'<div class="subtitle">built {esc(generated)} &middot; snapshot '
         f'{esc(c.snap_date)} &middot; Pl@ntNet model <code>{esc(c.tag)}</code> '
         f'&middot; {c.n:,} labelled frames &middot; {c.n_sp} species</div>',
         f'<p class="intro">This page says how well Pl@ntNet names the trees a botanist '
         f'labelled. The two numbers at the top come from {int(c.cf["n_frames"])} frames '
         f'set aside in advance. They show what difference it makes to outline the trees '
         f'before asking.</p>'
         f'<p class="intro">Everything below them covers all {c.n:,} labelled frames, one '
         f'Pl@ntNet guess per frame. That is what lets the page say, species by species, '
         f'how often the guess is right. What to label next is a separate page, <code>label_queue_dashboard.html</code>.</p>',
         # The headline first, on the frozen sample, because it is the only number here
         # whose unit of prediction is the unit the label describes. The corpus-wide
         # grid follows it, inside a panel, not the other way round.
         pn.confirmatory_hero(c.cf),
         # The gap is the finding, so it is prose rather than a hover tooltip nothing
         # on a phone would see.
         (f'<p class="note"><strong>Quote the top number, and carry the two warnings '
          f'below it.</strong> Outlining the trees first is worth '
          f'{100 * c.cf["crown_minus_photo"]:+.1f} points over sending the fixed centre '
          f'square. That gap was measured on frames set aside before either number '
          f'existed.</p>'),
         # Three frame counts run through this page and a reader who meets them one
         # at a time cannot tell whether they contradict each other. They do not. Said
         # once, below the headline rather than above it: this is arithmetic a reader
         # needs before the panels, not before the finding.
         f'<p class="note"><strong>Three frame counts appear below, and they fit '
         f'together.</strong> {c.n:,} frames carry a label naming a species, and every '
         f'accuracy rate on this page is measured on those. Add {c.gn:,} frames labelled '
         f'only to a genus and {c.fam_n:,} labelled only to a family and you get the '
         f'{c.n_pred:,} frames that have a cached Pl@ntNet answer.</p>'
         f'<p class="note">{len(h.gt_rows):,} is every frame a botanist has '
         f'labelled at all, the '
         f'{len(h.gt_rows) - c.n_pred} with no cached answer included. Each number below '
         f'says which of the three it is using.</p>']
    P.append(pn.render(c, pn.EXTERNAL_PANELS))

    return pn.document(TITLE, "\n".join(P)), c.checks


def main() -> None:
    pn.run(__doc__, OUT_NAME, build)


if __name__ == "__main__":
    main()
