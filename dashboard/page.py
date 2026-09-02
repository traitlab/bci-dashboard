"""How a page is put together: which panels it carries, and the plumbing.

``PANELS`` names every panel and ``EXTERNAL_PANELS`` / ``INTERNAL_PANELS`` say
which page carries which, so a panel names its audience once. ``render`` groups
the chosen panels into sections; ``run`` is both builders' ``main()``.

The panels themselves live in ``panels.py``, ``queue_panels.py`` and
``confirmatory_panels.py``. This module knows what a page is made of, never
what a panel says.
"""

from __future__ import annotations

import datetime as _dt
import os

import core as hc
import health as hl
from assets import css_for, section, strip_comments
from style import CSS, EVERY_PAGE_JS, JS, TABLE_ID
from history import latest_snapshot_dir
from confirmatory_panels import p_caveats, p_confirmatory
from panels import (
    p_candidates, p_ceiling, p_counts, p_method, p_review, p_species, p_terms,
    p_weighting)
from queue_panels import p_conf, p_rules, p_send, p_todo, p_wait


SECTIONS = {
    # The headline band belongs to the cards above it, so no heading of its own:
    # render() emits its panels bare when the title is None.
    "headline": (None, None),
    "label-first": (
        "What to label first",
        "Which frames to send, which can wait, and the evidence behind the wait rule."),
    "model-health": (
        "How Pl@ntNet is doing against the labels",
        # No live figure in a lede: SECTIONS is a constant, so a number here
        # would not move with the snapshot and nothing would catch it.
        "Which species it handles well, and which labels look worth a second look. "
        "Also why two fair ways of averaging the same frames disagree."),
    "limits": (
        "What this cannot tell you",
        # The method panel sits here too and is provenance, not a ceiling.
        "The ceilings on every number above, and where the numbers came from."),
}

# panel id -> (section key, builder). A panel belongs to the goal it serves, so
# the confidence evidence sits with the queue rule it justifies.
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

# Internal is the labelling team's tool and stays thin, its deliverable being
# send_batches.csv. External leaves the lab, carrying the confident
# disagreements so they can be worked in Labelbox.
INTERNAL_PANELS = ("todo", "send", "wait", "rules", "conf")
# Order inside a section is the order these ids are listed in. "terms" leads
# because frame, crown, label and centre crop are load-bearing from the first
# card down; the species lookup comes before the averaging argument.
EXTERNAL_PANELS = ("terms", "counts", "confirmatory", "caveats", "species", "review",
                   "weighting", "candidates", "ceiling", "method")

if set(INTERNAL_PANELS) | set(EXTERNAL_PANELS) != set(PANELS):
    raise SystemExit(f"every panel belongs to a page: "
                     f"{sorted(set(PANELS) - set(INTERNAL_PANELS) - set(EXTERNAL_PANELS))} "
                     f"belongs to neither")


def render(c, ids) -> str:
    """The chosen panels, grouped into their sections, in SECTIONS order.

    A section with no chosen panel is not emitted, so no heading over nothing.
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
        out.append(body if title is None else section(title, lede, body))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The bits of a page that are not a panel: command line, wrapper, file write.
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

    No footer: the subtitle already carries build date, snapshot and model tag.
    """
    return ("<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title}</title>"
            f"<style>{css_for(strip_comments(CSS), body + JS)}</style></head><body>" + body
            + f"<script>{strip_comments(script_for(body))}</script></body></html>")


def script_for(body: str) -> str:
    """The script a page needs, the table half only where there is a table.

    The sort-and-filter half is 2.4KB about the species table; the queue page
    has none, so it gets printing and jump links alone. The CSS is trimmed
    against every class the whole script could write, not just this half.
    """
    return JS if TABLE_ID in body else EVERY_PAGE_JS


def write_page(page: str, checks, out: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    # Encoded here so the reported size is the size on disk: accented species
    # names cost more than a byte each and len(page) undercounts.
    blob = page.encode("utf-8")
    with open(out, "wb") as f:
        f.write(blob)
    for c in checks:
        print(f"  verified  {c}")
    print(f"  wrote     {out}  ({len(blob):,} bytes)")


def run(doc: str, out_name: str, build) -> None:
    """Load the data, build the page, write it: both builders' ``main()``."""
    args = parse_args(doc, out_name)
    h = hl.load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                       wcvp_cache=args.wcvp_cache)
    page, checks = build(h, generated=args.generated or _dt.date.today().isoformat(),
                         verify_dir=args.verify_against or latest_snapshot_dir(),
                         fallback_tag=args.model_tag)
    write_page(page, checks, args.out)
