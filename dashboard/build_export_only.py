#!/usr/bin/env python3
"""A dashboard scoped to one Labelbox export, nothing else.

The other two pages (16b, 16c) answer "how good is the model, overall,
right now" from the *cumulative* ground truth: every label collected across
every past batch, merged. That is the right question for the labelling
programme, but it is a different question from "how did this one export do",
and merging the two makes the second question unanswerable from either page.

This page answers only the second question. It reads one NDJSON export
directly and evaluates Pl@ntNet only on the crowns that export itself
labels. It never opens ``gt_dominant_taxon.csv`` (the cumulative record), the
photo corpus (``splits.csv`` totals), the send-first queues, or the history
trend -- none of that is "this export", so none of it is on this page.

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

import core as hc  # noqa: E402
from assets import (
    CSS,
    JS,
    cap,
    esc,
    filterable_table,
    funnel_list,
    pctf,
)  # noqa: E402


def _load_gt_from_export():
    """Import the merge script's ``export_dominants`` without duplicating its
    NDJSON parse.

    Loaded by path, not by package import: labelling/ isn't a package on the
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
    n_labelled = len(h.gt_rows)  # rows export_dominants found a species label for
    n_no_cache = len(h.missing_cache)

    c1 = sum(1 for r in sp_recs if r["ranked"][0][0] == r["gt"])
    c5 = sum(1 for r in sp_recs if r["gt"] in [b for b, _ in r["ranked"][:5]])
    macro1 = (sum(d["top1_accuracy"] for d in per_species) / n_sp) if n_sp else None
    micro1 = (c1 / n) if n else None
    macro5 = (sum(d["top5_accuracy"] for d in per_species) / n_sp) if n_sp else None

    P = [
        "<h1>Pl@ntNet on BCI: this export only</h1>",
        f'<div class="subtitle">built {esc(generated)} &middot; '
        f"<code>{esc(export_name)}</code></div>",
    ]

    funnel_body = funnel_list(
        [
            (n_rows, "rows in this NDJSON export"),
            (
                n_labelled,
                "of those rows carry a Planta/Taxon species label \u2014 the rest "
                "have no annotation in this export",
            ),
            (
                n,
                "of the labelled photos also have a cached Pl@ntNet prediction \u2014 every "
                "accuracy figure below is measured on this set",
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
            f'<p class="note">Averaged across crowns instead of species: '
            f"{pctf(micro1)} right ({c1:,} of {n:,}). The right name is in the "
            f"5-guess list for {pctf(macro5)} of species ({pctf(c5 / n)} of "
            f"crowns. The 5-guess list is Pl@ntNet\u2019s own ranked "
            f"prediction for the photo, made before this export existed. "
            f"It is looked up per photo so the "
            f"ground-truth name here can be checked against it.</p>"
        )
    else:
        P.append(
            '<p class="note">No crown in this export both carries a species label '
            "and has a cached Pl@ntNet prediction, so no accuracy rate can be "
            "computed.</p>"
        )
    P.append(
        '<details class="panel" open><summary>Where these numbers come from</summary>'
        f'<div class="pbody"><p class="ask"><b>Why {n_rows - n:,} of the '
        f"{n_rows:,} rows are not in the accuracy rate above.</b></p>"
        f"{funnel_body}</div></details>"
    )

    if per_species:
        rows = [
            [
                f'<span class="sp">{esc(cap(d["species"]))}</span>',
                f'{d["n_labelled_crowns"]:,}',
                pctf(d["top1_accuracy"]),
            ]
            for d in sorted(
                per_species, key=lambda d: (-d["n_labelled_crowns"], d["species"])
            )
        ]
        body = filterable_table(
            [
                ("Species", False),
                ("Labelled crowns", True),
                ("First guess right", True),
            ],
            rows,
            options=[],
        )
        P.append(
            f'<details class="panel" open><summary>Filter Species'
            f'</summary><div class="pbody"><p class="ask"></p>{body}</div></details>'
        )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Pl@ntNet on BCI - this export only</title>"
        f"<style>{CSS}</style></head><body>"
        + "\n".join(P)
        + f"<script>{JS}</script></body></html>"
    )


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

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    blob = page.encode("utf-8")
    with open(args.out, "wb") as f:
        f.write(blob)
    print(f"  export rows                 : {n_rows:,}")
    print(f"  labelled (species) rows     : {len(h.gt_rows):,}")
    print(f"  joined to cached prediction : {len(h.sp_recs) + len(h.genus_recs):,}")
    print(f"  species-level, scoreable    : {len(h.sp_recs):,}")
    print(f"  wrote     {args.out}  ({len(blob):,} bytes)")


if __name__ == "__main__":
    main()
