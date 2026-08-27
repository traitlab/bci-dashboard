#!/usr/bin/env python3
"""What to label next: the labelling team's own page.

The internal half of the 2026-08-27 split. Its job is to order the unlabelled
pool and say why that order is the right one; the accuracy reporting moved to
``build_external.py``, which is the page that leaves the lab.

Deliberately thin, because the deliverable is not this page. It is
``send_batches.csv`` in the snapshot folder, which the labelling script reads
directly. The page exists so the order can be checked by eye and argued with
before a batch goes out.

    python3 dashboard/build_internal.py [--out PATH]

Numbers are recomputed here from source rather than read from the CSVs, then
cross-checked against the CSVs measure.py wrote into the snapshot; a mismatch
aborts the build. This page gates on the two send-queue CSVs, which the external
page does not report and does not check.

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
from assets import esc  # noqa: E402
from history import latest_snapshot_dir, verify_snapshot  # noqa: E402

OUT_NAME = "label_queue_dashboard.html"
TITLE = "BCI labelling: what to label next"


def build(h, *, generated, verify_dir, fallback_tag):
    c = pn.prepare(h, verify_dir=verify_dir, fallback_tag=fallback_tag)

    # The send queue is this page's whole subject, so it gates on both queue
    # CSVs. The review queue belongs to the external page and is checked there.
    c.checks = verify_snapshot(
        verify_dir, per_species=c.per_species, buckets=c.buckets, bins_all=c.bins_all,
        never_all=c.never_all, unscoreable=c.unscoreable, strict_hits=c.strict1,
        queue_counts=c.queue_counts, n_no_answer=c.n_no_answer)

    P = ['<h1>What to label next</h1>',
         f'<div class="subtitle">built {esc(generated)} &middot; snapshot '
         f'{esc(c.snap_date)} &middot; Pl@ntNet model <code>{esc(c.tag)}</code> '
         f'&middot; {c.n_unlab:,} unlabelled photos queued &middot; '
         f'{c.n:,} labelled frames behind the ranking</div>',
         '<p class="intro">This page says where botanist time is worth spending. Every '
         'unlabelled photo already has a Pl@ntNet guess, and every species already has a '
         'measured record, so the two together put the pool in an order: the frames that '
         'buy the most per label first.</p>',
         '<p class="intro"><strong>The page is not the deliverable.</strong> '
         '<code>send_batches.csv</code> in the snapshot folder is, and it carries the same '
         'order in batches of at most 100 with each species group kept together. Read this '
         'page to check the order and the rule behind it, then work the CSV. How Pl@ntNet '
         'scores against the labels is a separate page.</p>',
         pn.render(c, pn.INTERNAL_PANELS)]

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
