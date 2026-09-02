"""How a page is put together: which panels it carries, and the plumbing.

``PANELS`` names every panel on either page and ``EXTERNAL_PANELS`` /
``INTERNAL_PANELS`` say which page carries which, so a panel names its audience
here once instead of each builder keeping a list. ``render`` groups the chosen
panels into sections; ``run`` is the whole of both builders' ``main()``.

The panels themselves are elsewhere: the model-health ones in ``panels.py``,
the queue page's in ``queue_panels.py``. This module knows what a page is made
of, never what a panel says.
"""

from __future__ import annotations

import datetime as _dt
import os

import core as hc
from assets import section, strip_comments
from style import CSS, JS
from history import latest_snapshot_dir
from panels import (
    p_candidates, p_caveats, p_ceiling, p_confirmatory, p_counts, p_method,
    p_review, p_species, p_terms, p_weighting)
from queue_panels import p_conf, p_rules, p_send, p_todo, p_wait


SECTIONS = {
    # The headline band has no heading of its own: it sits directly under the cards
    # and belongs to them. render() emits its panels bare when the title is None.
    "headline": (None, None),
    "label-first": (
        "What to label first",
        "Which frames to send, which can wait, and the evidence behind the wait rule."),
    "model-health": (
        "How Pl@ntNet is doing against the labels",
        # No live figure in a lede: SECTIONS is a constant, so a number written
        # here would not move with the snapshot and nothing would catch it.
        "Which species it handles well, and which labels look worth a second look. "
        "Also why two fair ways of averaging the same frames disagree."),
    "limits": (
        "What this cannot tell you",
        # The method panel sits here too, and it is provenance rather than a
        # ceiling, so the lede says both instead of describing two-thirds of
        # what the reader is about to open.
        "The ceilings on every number above, and where the numbers came from."),
}

# panel id -> (section key, builder). A panel belongs to the goal it serves, so
# the confidence evidence sits with the queue rule it justifies and the species
# lookup sits with the scores it reports.
PANELS = {
    "confirmatory": ("headline", p_confirmatory),
    "caveats": ("headline", p_caveats),
    "terms": ("headline", p_terms),
    "counts": ("headline", p_counts),
    "todo": ("label-first", p_todo),
    "send": ("label-first", p_send),
    "wait": ("label-first", p_wait),
    "rules": ("label-first", p_rules),
    "conf": ("label-first", p_conf),
    "weighting": ("model-health", p_weighting),
    "species": ("model-health", p_species),
    "review": ("model-health", p_review),
    "candidates": ("limits", p_candidates),
    "ceiling": ("limits", p_ceiling),
    "method": ("limits", p_method),
}

# The 2026-08-27 split. Internal is the labelling team's tool and stays thin;
# its real deliverable is send_batches.csv. External is what leaves the lab, and
# the confident disagreements go with it so they can be worked in Labelbox.
INTERNAL_PANELS = ("todo", "send", "wait", "rules", "conf")
# Order inside a section is the order these ids are listed in. A reader arrives to
# look up a species, so the lookup comes before the averaging argument.
# "terms" leads: frame, crown, label and centre crop are load-bearing from the
# first card down, and a reader who met them third had already been through two
# sections that used them.
EXTERNAL_PANELS = ("terms", "counts", "confirmatory", "caveats", "species", "review",
                   "weighting", "candidates", "ceiling", "method")

if set(INTERNAL_PANELS) | set(EXTERNAL_PANELS) != set(PANELS):
    raise SystemExit(f"every panel belongs to a page: "
                     f"{sorted(set(PANELS) - set(INTERNAL_PANELS) - set(EXTERNAL_PANELS))} "
                     f"belongs to neither")


def render(c, ids) -> str:
    """The chosen panels, grouped into their sections, in SECTIONS order.

    A section with no chosen panel is not emitted at all, so a page never shows
    a heading and a jump list over nothing.
    """
    unknown = [i for i in ids if i not in PANELS]
    if unknown:
        raise SystemExit(f"no such panel: {unknown}. Known: {sorted(PANELS)}")
    out = []
    for key, (title, lede) in SECTIONS.items():
        chosen = [PANELS[i][1](c) for i in ids if PANELS[i][0] == key]
        if not chosen:
            continue
        body = "\n".join(chosen)
        # A titleless section is the headline band: its panels belong to the cards
        # above them, so wrapping them in a heading would announce a second subject.
        out.append(body if title is None else section(title, lede, body))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The bits of a page that are not a panel: the command line, the document
# wrapper, and writing the file. Both pages do these identically, and a second
# copy is a second place for the verify flags to drift.
# ---------------------------------------------------------------------------

def parse_args(doc: str, default_out: str):
    """The builder command line. Same flags on both pages, different --out."""
    import argparse

    ap = argparse.ArgumentParser(description=hc.summarise(doc))
    hc.add_input_flags(ap)
    ap.add_argument("--verify-against", default=None,
                    help="directory holding the committed measurement CSVs to cross-check; "
                         "defaults to the newest model-health-<date>/ folder")
    ap.add_argument("--model-tag", default="unknown",
                    help="Pl@ntNet model iteration to record for a snapshot whose "
                         "run_log.txt does not name one")
    ap.add_argument("--out", default=os.path.join(hc.REPO, "build", default_out),
                    help=f"write the page here (default: build/{default_out})")
    ap.add_argument("--generated", default=None,
                    help="build date string; defaults to today (pass a fixed value for "
                         "byte-reproducible output)")
    return ap.parse_args()


def document(title: str, body: str) -> str:
    """One self-contained file: every style and script inlined, nothing fetched.

    No footer: the subtitle already carries the build date, the snapshot and the
    model tag, and a second copy at the foot said nothing new.
    """
    return ("<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title}</title>"
            f"<style>{strip_comments(CSS)}</style></head><body>" + body
            + f"<script>{strip_comments(JS)}</script></body></html>")


def write_page(page: str, checks, out: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    # Encoded here so the reported size is the size on disk: accented species names
    # cost more than a byte each, and len(page) undercounts by ten.
    blob = page.encode("utf-8")
    with open(out, "wb") as f:
        f.write(blob)
    for c in checks:
        print(f"  verified  {c}")
    print(f"  wrote     {out}  ({len(blob):,} bytes)")


def run(doc: str, out_name: str, build) -> None:
    """Load the data, build the page, write it. The whole of both builders'
    ``main()``, which were identical apart from the two module constants."""
    args = parse_args(doc, out_name)
    h = hc.load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                       wcvp_cache=args.wcvp_cache)
    page, checks = build(h, generated=args.generated or _dt.date.today().isoformat(),
                         verify_dir=args.verify_against or latest_snapshot_dir(),
                         fallback_tag=args.model_tag)
    write_page(page, checks, args.out)
