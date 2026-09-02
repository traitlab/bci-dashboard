#!/usr/bin/env python3
"""A dashboard scoped to one Labelbox export, nothing else.

The other two pages answer "how good is the model right now" from the
*cumulative* record: every label collected across every past batch, merged.
That is the right question for the labelling programme and a different question
from "how did this one export do", which merging makes unanswerable from either
page.

This page answers only the second. It reads one NDJSON export directly and
evaluates Pl@ntNet only on the crowns that export labels. It never opens
``gt_dominant_taxon.csv``, the photo corpus, the send-first queues or the
history trend: none of that is "this export".

Read-only against Labelbox data: the export is parsed, never written back,
and the cumulative GT file on disk is never touched (see CLAUDE.md).

    python3 dashboard/build_export_only.py \\
        --export "/path/to/Export  project - 2024_bci - 8_6_2026.ndjson" \\
        [--out PATH]
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core as hc
import figures
import panels as pn
from assets import (
    cap,
    esc,
    filterable_table,
    funnel_list,
    panel,
    pctf,
    status_legend,
    status_tag,
)


def _load_gt_from_export():
    """Import the merge script's ``export_dominants`` without duplicating its
    NDJSON parse.

    Loaded by path, not by package import: labelling/ is not a package on the
    normal path, and this is the one function this page needs from it
    (module-level only; ``main()`` is never called).
    """
    path = os.path.join(hc.REPO, "labelling", "gt_from_export.py")
    spec = importlib.util.spec_from_file_location("_gt_from_export", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def export_only_health(
    export_path: str, *, splits_csv: str, cache_dir: str, wcvp_cache: str
) -> tuple[hc.Health, int]:
    """Load a ``Health`` computed only over this export's own labelled photos.

    Returns ``(health, n_ndjson_rows)``. Writes a throwaway GT CSV to a temp
    file so the existing, already-verified ``load_health`` join/scoring logic
    can be reused unchanged; nothing is written under the repo.
    """
    mod = _load_gt_from_export()
    with open(export_path, encoding="utf-8") as f:
        n_rows = sum(1 for _ in f)
    dominants, _, _ = mod.export_dominants(export_path)  # stem -> species, this export only

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8"
    ) as tf:
        w = csv.writer(tf)
        w.writerow(["global_key", "wcvp_canonical_name"])
        for stem, sp in sorted(dominants.items()):
            w.writerow([hc.GT_KEY_PREFIX + stem, sp])
        tmp_gt = tf.name
    try:
        h = hc.load_health(
            gt_csv=tmp_gt,
            splits_csv=splits_csv,
            cache_dir=cache_dir,
            wcvp_cache=wcvp_cache,
        )
    finally:
        os.unlink(tmp_gt)
    return h, n_rows


def build(h: hc.Health, *, export_name: str, n_rows: int, generated: str) -> str:
    sp_recs, per_species = h.sp_recs, h.per_species
    n, n_sp = len(sp_recs), len(per_species)
    n_labelled = len(h.gt_rows)  # rows export_dominants found a botanist name for
    n_no_cache = len(h.missing_cache)
    n_genus = len(h.genus_recs)  # labelled, cached, but the name stops at the genus
    n_joined = n + n_genus

    c1 = sum(1 for r in sp_recs if r["ranked"][0][0] == r["gt"])
    c5 = sum(1 for r in sp_recs
             if r["gt"] in [b for b, _ in r["ranked"][:figures.N_CANDIDATES]])
    macro1 = (sum(d["top1_accuracy"] for d in per_species) / n_sp) if n_sp else None
    micro1 = (c1 / n) if n else None
    macro5 = (sum(d["top5_accuracy"] for d in per_species) / n_sp) if n_sp else None

    P = [
        "<h1>Pl@ntNet on BCI: this export only</h1>",
        f'<div class="subtitle">built {esc(generated)} &middot; '
        f"<code>{esc(export_name)}</code></div>",
        ('<p class="intro">This page scores one Labelbox export on its own. It asks '
         "how well Pl@ntNet named the trees this batch labelled, and nothing else. "
         "The running total across every past batch is on the model-health page, <code>model_health_dashboard.html</code>.</p>"),
    ]

    # Every row of the export ends in exactly one of these steps, so the counts
    # below sum to n_rows.
    funnel_body = funnel_list(
        [
            (n_rows, "rows in this NDJSON export"),
            (
                n_labelled,
                "of those rows carry a botanist name in the Planta/Taxon field "
                "\u2014 the rest have no annotation in this export",
            ),
            (
                n_joined,
                "of the labelled photos also have a cached Pl@ntNet answer",
            ),
            (
                n,
                "of those name a species rather than stopping at the genus \u2014 every "
                "accuracy figure below is measured on this set",
            ),
            (
                n_genus,
                "stop at the genus, which this page does not score",
            ),
            (
                n_no_cache,
                "labelled photos have no cached prediction, so cannot be scored",
            ),
        ]
    )
    P.append(
        f'<div class="hero">'
        f'<div class="metric first"><div class="v">{pctf(macro1)}</div>'
        f'<div class="l">Right first guess, averaged across species</div>'
        f'<div class="n">this export\u2019s {n_sp} species, each counted once</div></div>'
        f"</div>"
    )
    if n:
        P.append(
            f'<p class="note">Averaged across frames instead of species: '
            f"{pctf(micro1)} right ({c1:,} of {n:,}). The right name is somewhere "
            f"in the {figures.N_CANDIDATES} names Pl@ntNet returned for "
            f"{pctf(macro5)} of species, and {pctf(c5 / n)} of frames. Those "
            f"names were ranked by Pl@ntNet before this export existed. "
            f"They are looked up per photo, so the botanist\u2019s label in this "
            f"export can be checked against them.</p>"
        )
    else:
        P.append(
            '<p class="note">No photo in this export both carries a species label '
            "and has a cached Pl@ntNet prediction, so no accuracy rate can be "
            "computed.</p>"
        )
    P.append(
        panel(
            "Where these numbers come from",
            f"<b>Why {n_rows - n:,} of the {n_rows:,} rows are not in the "
            f"accuracy rate above.</b>",
            funnel_body,
            open_=True,
        )
    )

    if per_species:
        # The same table the model-health page renders, status column included.
        # Without it a row says 40% and nothing says whether that is a species
        # the model gets wrong or one with too few labels to judge, which is the
        # first thing a reader of a single export wants to know.
        rows, attrs = [], []
        for d in per_species:
            st = hc.diagnose(d)
            rows.append([
                f'<span class="sp">{esc(cap(d["species"]))}</span>',
                (f'<span data-sort="{d["n_labelled_crowns"]}">'
                 f'{d["n_labelled_crowns"]:,}</span>'),
                (f'<span data-sort="{d["top1_accuracy"]:.6f}">'
                 f'{pctf(d["top1_accuracy"])}</span>'),
                status_tag(st, pn.STATUS[st][0]),
            ])
            attrs.append(f' data-status="{st}"')
        body = status_legend(
            [(st, pn.STATUS[st][0], pn.STATUS_REASON[st]) for st in pn.STATUS]
        ) + filterable_table(
            [
                ("Species", False),
                ("Labelled frames", True),
                ("First guess right", True),
                ("Status", False),
            ],
            rows,
            options=[(k, v[0]) for k, v in pn.STATUS.items()],
            row_attrs=attrs,
        )
        P.append(panel(
            f"Look up one species: all {len(per_species)} in this export",
            "<b>Find a species you care about and read its status.</b> Click any "
            "heading to sort, type to filter. " + pn.status_precedence_note(),
            body, open_=True))

    return pn.document("Pl@ntNet on BCI - this export only", "\n".join(P))


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--export", required=True, help="Labelbox project export NDJSON")
    ap.add_argument(
        "--splits",
        default=hc.SPLITS_CSV,
        help="splits.csv; used only to resolve a stem to a cache file, "
        "never rendered as a corpus total on this page",
    )
    ap.add_argument("--cache-dir", default=hc.CACHE_DIR)
    ap.add_argument("--wcvp-cache", default=hc.WCVP_CACHE_JSON)
    ap.add_argument(
        "--out",
        default=os.path.join(
            hc.REPO, "build", "export_only_dashboard.html"
        ),
    )
    ap.add_argument(
        "--generated", default=None, help="build date string; defaults to today"
    )
    args = ap.parse_args()

    h, n_rows = export_only_health(
        args.export,
        splits_csv=args.splits,
        cache_dir=args.cache_dir,
        wcvp_cache=args.wcvp_cache,
    )
    page = build(
        h,
        export_name=os.path.basename(args.export),
        n_rows=n_rows,
        generated=args.generated or _dt.date.today().isoformat(),
    )

    print(f"  export rows                 : {n_rows:,}")
    print(f"  labelled (species) rows     : {len(h.gt_rows):,}")
    print(f"  joined to cached prediction : {len(h.sp_recs) + len(h.genus_recs):,}")
    print(f"  species-level, scoreable    : {len(h.sp_recs):,}")
    # No verify list: this page is scoped to one export and has no snapshot to
    # reconcile against, so it passes an empty one.
    pn.write_page(page, [], args.out)


if __name__ == "__main__":
    main()
