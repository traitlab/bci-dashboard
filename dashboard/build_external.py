#!/usr/bin/env python3
"""How Pl@ntNet does against the labels: the page that leaves the lab.

The external half of the 2026-08-27 split. It answers one question, for people
outside the labelling team: how well does Pl@ntNet name BCI drone close-ups, per
species, and what are the ceilings on that number. The queue panels moved to
``build_internal.py``, which is the labelling team's own tool.

    python3 dashboard/build_external.py [--out PATH]

Numbers are recomputed here from source rather than read from the CSVs, then
cross-checked against the CSVs measure.py wrote into the snapshot; a mismatch
aborts the build, so the page cannot disagree with the measurement. This page
gates on the measurement CSVs it actually reports and not on the send-queue
ones, which belong to the other page. The page reports the latest snapshot only,
no trend over the sibling folders.

No network, no API key, no third-party package: the page opens from a file://
URL with every style, script and chart inlined.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core as hc  # noqa: E402
import panels as pn  # noqa: E402
from assets import esc, info_tip  # noqa: E402
from history import latest_snapshot_dir, verify_snapshot  # noqa: E402

OUT_NAME = "model_health_dashboard.html"
TITLE = "How well does Pl@ntNet name BCI trees?"


def build(h, *, generated, verify_dir, fallback_tag):
    c = pn.prepare(h, verify_dir=verify_dir, fallback_tag=fallback_tag)

    # This page reports no send queue, so it does not gate on one. It still
    # gates on every CSV behind a number it does print, including the review
    # queue, which moved here with the panel that renders it.
    c.checks = verify_snapshot(
        verify_dir, per_species=c.per_species, buckets=c.buckets, bins_all=c.bins_all,
        never_all=c.never_all, unscoreable=c.unscoreable, strict_hits=c.strict1,
        review_counts=c.review_counts)

    # The head is two numbers and one line saying which to quote. Everything that
    # qualifies them is a panel below: the glossary, the caveats the design requires,
    # and the four corpus-wide rates with the region mismatch they inherit.
    delta = (f'Asking Pl@ntNet about each outlined crown, then combining the answers into '
             f'one name for the frame, is worth {100 * c.cf["crown_minus_photo"]:+.1f} '
             f'points over sending the fixed centre square. Measured on frames set aside '
             f'before either number existed, and a gap that size almost never happens by '
             f'chance.')
    P = ['<h1>How well does Pl@ntNet name BCI trees?</h1>',
         f'<div class="subtitle">built {esc(generated)} &middot; snapshot '
         f'{esc(c.snap_date)} &middot; Pl@ntNet model <code>{esc(c.tag)}</code> '
         f'&middot; {c.n:,} labelled frames &middot; {c.n_sp} species</div>',
         f'<p class="intro">This page says how well Pl@ntNet names the trees a botanist '
         f'labelled. The two numbers at the top come from {int(c.cf["n_frames"])} frames '
         f'set aside in advance, and they show what difference it makes to outline the '
         f'trees before asking. Everything below them covers all {c.n:,} labelled frames, '
         f'one Pl@ntNet guess per frame, so we can say species by species how often the '
         f'guess is right. What to label next is a separate page.</p>',
         # The headline first, on the frozen sample, because it is the only number here
         # whose unit of prediction is the unit the label describes. The corpus-wide
         # grid follows it, inside a panel, not the other way round.
         pn.confirmatory_hero(c.cf),
         f'<p class="note"><strong>Quote the top number, and carry the two warnings '
         f'below it.</strong> {info_tip(delta)}</p>']
    P.append(pn.render(c, pn.EXTERNAL_PANELS))

    return pn.document(TITLE, "\n".join(P)), c.checks


def main() -> None:
    args = pn.parse_args(__doc__, OUT_NAME)
    h = hc.load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                       wcvp_cache=args.wcvp_cache)
    page, checks = build(h, generated=args.generated or _dt.date.today().isoformat(),
                         verify_dir=args.verify_against or latest_snapshot_dir(),
                         fallback_tag=args.model_tag)
    pn.write_page(page, checks, args.out)


if __name__ == "__main__":
    main()
