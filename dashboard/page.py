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
import re
import shutil

import core as hc
import health as hl
from assets import css_for, esc, section, strip_comments
from style import CSS, EVERY_PAGE_JS, JS, TABLE_ID
from confirmatory_panels import p_floor
from panels import (
    p_calibration, p_ceiling, p_counts, p_coverage, p_method, p_review, p_species,
    p_terms, p_weighting)
from queue_panels import p_evidence, p_look, p_send, p_todo


# Order here is reading order. The measurement comes first and the explanation
# comes after it, which is the reverse of how this page used to be arranged.
# The reviewer, reading it cold on 2026-09-03: "split it in like a main section
# that's the actual dashboard at the top ... and then later another section
# where it's basically finishing the explanations", because "most people, once
# they get used to it, they will probably not look at [the prose]. They will
# just go straight for the [numbers]."
SECTIONS = {
    # The headline band belongs to the cards above it, so no heading of its own:
    # render() emits its panels bare when the title is None.
    "headline": (None, None),
    "label-first": (
        "What to label first",
        "Which frames to send, which can wait, and the evidence behind the wait rule."),
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
        # Everything here was above the species table until 2026-09-03. It
        # explains the numbers rather than reporting them, so it now sits after
        # the thing it explains and a reader who does not need it can stop.
        "Read this when a number above surprises you. Nothing here is a new "
        "measurement."),
    "limits": (
        "What this cannot tell you",
        # The method panel sits here too and is provenance, not a ceiling.
        "The ceilings on every number above, and where the numbers came from."),
}

# panel id -> (section key, builder). A panel belongs to the goal it serves, so
# the confidence evidence sits with the queue rule it justifies.
PANELS = {
    # "floor" stays in the headline band: it is a correction to the two cards
    # above it, not an explanation of them, so it has to travel with them.
    "floor": ("headline", p_floor),
    "todo": ("label-first", p_todo),
    "send": ("label-first", p_send),
    "look": ("label-first", p_look),
    "evidence": ("label-first", p_evidence),
    "species": ("model-health", p_species),
    "review": ("model-health", p_review),
    # The three that moved out of the headline band and out of "model-health".
    # "weighting" carries the support-vs-accuracy chart, which the reviewer could not
    # read cold ("I don't understand this graph") but kept once it was explained
    # ("No, I think it's good ... it's good to have all the information"). It is
    # an explanation of the two headline rates, so it belongs here.
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
INTERNAL_PANELS = ("todo", "send", "look", "evidence")
# Order inside a section is the order these ids are listed in; the sections
# themselves order the page. The species table now leads, because that is what
# a reader scrolls to. The glossary and the three-frame-counts panel used to
# lead and now close: they were put first so that "frame", "crown", "label" and
# "centre crop" were defined before first use, which is right for a first read
# and wrong for every read after it.
EXTERNAL_PANELS = ("floor", "species", "review",
                   "weighting", "coverage", "calibration", "terms", "counts",
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
        body = "\n".join(chosen)
        out.append(body if title is None else section(title, lede, body, anchor=anchor))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The bits of a page that are not a panel: command line, wrapper, file write.
# ---------------------------------------------------------------------------

def parse_args(doc: str, default_out: str, team_out: str | None = None):
    """The builder command line. Same flags on both pages, different --out.

    ``team_out`` is the file ``--team`` writes to. A page with no team copy
    refuses the flag rather than writing the public file under a name that
    promises more than it carries.
    """
    import argparse

    ap = argparse.ArgumentParser(description=hc.summarise(doc))
    hc.add_input_flags(ap)
    ap.add_argument("--verify-against", default=None,
                    help="directory holding the measurement CSVs to cross-check; "
                         "defaults to build/tables, what measure.py last wrote. Point it "
                         "at a model-health-<date>/ folder to rebuild an old page, and "
                         "expect a table the code has changed since to abort")
    ap.add_argument("--model-tag", default="unknown",
                    help="Pl@ntNet model iteration to record for a snapshot whose "
                         "run_log.txt does not name one")
    ap.add_argument("--team", action="store_true",
                    help="write the labelling team's copy instead: the same page plus "
                         "the parts that only work with the repository checked out")
    ap.add_argument("--out", default=None,
                    help=f"write the page here (default: build/{default_out})")
    ap.add_argument("--generated", default=None,
                    help="build date string; defaults to today (pass a fixed value for "
                         "byte-reproducible output)")
    args = ap.parse_args()
    if args.team and team_out is None:
        ap.error(f"--team: {default_out} has no team copy, so there is nothing the "
                 f"flag would add")
    if args.out is None:
        args.out = os.path.join(hc.REPO, "build",
                                team_out if args.team else default_out)
    return args


def footer(c) -> str:
    """What a reader checks a number against after reading it, not before.

    The request settings used to sit twice in the body, written as the flag
    names we send. A reader outside the lab cannot act on a flag name and does
    not need to: what changes how a number reads is how many answers we asked
    for and that nothing was filtered out, which is what this says in words.
    The run tag sits here for the same reason, as the one string to quote back
    when asking which build a number came from.
    """
    return (f'<div class="subtitle">Pl@ntNet was asked the same way every time: '
            f'{hc.in_words(c.n_cand)} answers per photo, rejection off, related images '
            f'off. Run {esc(c.tag)}.</div>')


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


def run(doc: str, out_name: str, build, team_name: str | None = None) -> None:
    """Load the data, build the page, write it: both builders' ``main()``.

    ``team_name`` is the file the page is written to under ``--team``. A page
    with no team copy refuses the flag rather than writing the public file
    under a name that promises more than it carries.
    """
    args = parse_args(doc, out_name, team_name)
    verify_dir = args.verify_against or hc.TABLES_DIR
    h = hl.load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                       wcvp_cache=args.wcvp_cache)
    page, checks = build(h, generated=args.generated or _dt.date.today().isoformat(),
                         verify_dir=verify_dir, fallback_tag=args.model_tag,
                         team=args.team)
    write_page(page, checks, args.out)
    copy_linked_csvs(page, verify_dir, args.out)
