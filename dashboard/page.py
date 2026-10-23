"""How a page is put together: which panels it carries, and the plumbing.

``PANELS`` names every panel and ``EXTERNAL_PANELS`` / ``INTERNAL_PANELS`` say
which page carries which, so a panel names its audience once. ``render`` groups
the chosen panels into sections; ``run`` is both builders' ``main()``.

The panels themselves live in ``panels.py``, ``queue_panels.py``,
``queue_why_panels.py`` and ``confirmatory_panels.py``. This module knows what a page is made of, never
what a panel says.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import shutil

import core as hc
import health as hl
from assets import css_for, esc, section, strip_comments
from style import CSS, EVERY_PAGE_JS, JS, TABLE_ID
from site_navigation import FAVICON, navigation
from confirmatory_panels import p_floor
from history_panels import p_changes, p_confused
from panels import (
    p_calibration, p_ceiling, p_counts, p_coverage, p_method, p_review, p_species,
    p_terms, p_weighting)
from queue_panels import p_send, p_todo
from queue_why_panels import p_evidence, p_look
from selection_panels import audit_footer

OPERATIONAL_PAGES = frozenset({
    "index.html", "about.html", "model_health_dashboard.html", "label_queue_dashboard.html",
})


# Order here is reading order: measurement first, explanation after.
SECTIONS = {
    "label-first": (
        "What to label first",
        "Which frames to send, and in what order."),
    # The queue page's second part. Same arrangement as the model-health page:
    # the thing a reader acts on first, the reasoning after it, closed.
    "queue-why": (
        "Why this order, and how far to trust it",
        "The reasoning behind the order above."),
    # A third item names the id: this heading runs past the eight words slug()
    # keeps and would otherwise ship as "...and-where-it".
    "model-health": (
        "Where the model is right, and where it is not",
        # No live figure in a lede: SECTIONS is a constant, so a number here
        # would not move with the snapshot and nothing would catch it.
        "Accuracy species by species, and the labels worth a second look.",
        "where-the-model-is-right"),
    "explanations": (
        "How to read the numbers above",
        # It explains the numbers rather than reporting them, so it sits after
        # the thing it explains and a reader who does not need it can stop.
        "Read this when a number above surprises you."),
    "limits": (
        "What this cannot tell you",
        # The method panel sits here too and is provenance, not a ceiling.
        "The limits on every number above, and where the numbers came from."),
}

# panel id -> (section key, builder). A panel belongs to the goal it serves, so
# the confidence evidence sits with the queue rule it justifies.
PANELS = {
    # The correction travels with the cards as one line on the first screen
    # (landing.py). This panel is the population behind that line, so it leads
    # the explanations rather than standing between the cards and the table.
    "floor": ("explanations", p_floor),
    "todo": ("label-first", p_todo),
    "send": ("label-first", p_send),
    "look": ("queue-why", p_look),
    "evidence": ("queue-why", p_evidence),
    "species": ("model-health", p_species),
    "review": ("model-health", p_review),
    # What the last Labelbox export changed, off the refresh manifest.
    "changes": ("model-health", p_changes),
    "confused": ("model-health", p_confused),
    # "weighting" carries the support-vs-accuracy chart. It is an explanation
    # of the two headline rates, so it belongs here.
    "weighting": ("explanations", p_weighting),
    # The crop-coverage sweep. It qualifies the four rates in "weighting" rather
    # than reporting a new headline, so it follows them, and it is the panel the
    # house rule about gated and ungated numbers has been asking for: the sweep
    # was measured on every build and reached no page.
    "coverage": ("explanations", p_coverage),
    # The calibration chart was measured for this page and drawn only on the
    # other one. It explains the confidence column rather than reporting a new
    # number, so it sits in the explanations section beside the weighting panel.
    "calibration": ("explanations", p_calibration),
    "terms": ("explanations", p_terms),
    "counts": ("explanations", p_counts),
    "ceiling": ("limits", p_ceiling),
    "method": ("limits", p_method),
}

# Internal is the labelling team's tool and stays thin, its deliverable being
# send_batches.csv. External leaves the lab, carrying the confident
# disagreements so they can be worked in Labelbox.
INTERNAL_PANELS = ("send", "todo", "look", "evidence")
# Order inside a section is the order these ids are listed in; the sections
# themselves order the page. The species table leads; definitions close.
EXTERNAL_PANELS = ("species", "review", "confused", "changes",
                   "floor", "weighting", "coverage", "calibration", "terms", "counts",
                   "ceiling", "method")

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
    for key, entry in SECTIONS.items():
        title, lede = entry[:2]
        anchor = entry[2] if len(entry) > 2 else None
        chosen = [PANELS[i][1](c) for i in ids if PANELS[i][0] == key]
        if not chosen:
            continue
        out.append(section(title, lede, "\n".join(chosen), anchor=anchor))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The bits of a page that are not a panel: command line, wrapper, file write.
# ---------------------------------------------------------------------------

def parse_args(doc: str, default_out: str):
    """The builder command line. Same flags on both pages, different --out."""
    import argparse

    ap = argparse.ArgumentParser(description=hc.summarise(doc))
    hc.add_input_flags(ap)
    hc.add_label_source_flag(ap)
    ap.add_argument("--verify-against", default=None,
                    help="directory holding the measurement CSVs to cross-check; "
                         "defaults to build/tables, what measure.py last wrote. Point it "
                         "at a model-health-<date>/ folder to rebuild an old page, and "
                         "expect a table the code has changed since to abort")
    ap.add_argument("--model-tag", default="unknown",
                    help="Pl@ntNet model iteration to record for a snapshot whose "
                         "run_log.txt does not name one")
    ap.add_argument("--out", default=None,
                    help=f"write the page here (default: build/{default_out})")
    ap.add_argument("--generated", default=None,
                    help="build date string; defaults to today (pass a fixed value for "
                         "byte-reproducible output)")
    args = ap.parse_args()
    if args.out is None:
        args.out = os.path.join(hc.REPO, "build", default_out)
    return args


def footer(c) -> str:
    """What a reader checks a number against after reading it, not before.

    States the request settings in words (answers asked for, nothing
    filtered out) and the run tag, the one string to quote back when asking
    which build a number came from.
    """
    return (f'<div class="subtitle">Pl@ntNet was asked the same way every time: '
            f'{hc.in_words(c.n_cand)} answers per photo, rejection off, related images '
            f'off. Run {esc(c.tag)}.{audit_footer(c)}</div>')


def document(title: str, body: str, *, current: str = "", available=None) -> str:
    """One self-contained file: every style and script inlined, nothing fetched.

    No footer: the subtitle already carries build date, snapshot and model tag.
    """
    available = OPERATIONAL_PAGES if available is None else available
    body = (navigation(current, available=available)
            + '<main id="main-content" tabindex="-1">' + body + '</main>')
    return ("<!DOCTYPE html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title}</title>{FAVICON}"
            f'<style>{css_for(strip_comments(CSS), body + JS)}</style></head><body data-workspace="reports">' + body
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


_LINKED_CSV = re.compile(r'href="([A-Za-z0-9_]+\.csv)"')


def copy_linked_csvs(page: str, verify_dir: str, out: str) -> None:
    """Put every CSV the page links next to the page itself.

    A panel that says "put these frames in front of a botanist" links the
    queue rather than naming it, so the file has to travel with the HTML. The
    list is read out of the rendered page, not declared beside it, because a
    declared list drifts the moment a panel adds a link.

    A missing file aborts: a link that 404s is worse than a filename in prose,
    and it fails here rather than in front of the reader.
    """
    dest = os.path.dirname(os.path.abspath(out))
    for name in sorted(set(_LINKED_CSV.findall(page))):
        src = os.path.join(verify_dir, name)
        if not os.path.exists(src):
            raise SystemExit(f"VERIFY FAIL: the page links {name}, absent from {verify_dir}")
        if os.path.abspath(src) != os.path.join(dest, name):
            shutil.copyfile(src, os.path.join(dest, name))
        print(f"  copied    {name}  beside the page")


def run(doc: str, out_name: str, build) -> str:
    """Load the data, build the page, write it: both builders' ``main()``.

    Returns the path written, so a builder can put a file beside the page.
    """
    args = parse_args(doc, out_name)
    verify_dir = args.verify_against or hc.TABLES_DIR
    h = hl.load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                       wcvp_cache=args.wcvp_cache, label_source=args.label_source)
    destination = os.path.dirname(os.path.abspath(args.out))
    available_pages = OPERATIONAL_PAGES | {
        name for name in os.listdir(destination)
        if name.endswith(".html") and os.path.isfile(os.path.join(destination, name))
    } if os.path.isdir(destination) else OPERATIONAL_PAGES
    page, checks = build(h, generated=args.generated or _dt.date.today().isoformat(),
                         verify_dir=verify_dir, fallback_tag=args.model_tag,
                         available_pages=available_pages)
    write_page(page, checks, args.out)
    copy_linked_csvs(page, verify_dir, args.out)
    return args.out
