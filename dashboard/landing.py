"""The model-health page's first screen: the numbers a reader came for.

Six cards, the correction they are read against, one button per status that
filters the species table, accuracy by how many labelled frames a species has,
and the review list in one line. Every figure is read off the prepared context,
never computed here, and each carries its population.

It led with a single card until 2026-09-11. A reader opening the page met one
rate and a paragraph saying which of two to quote, and had to open panels to
find anything else. The averaging argument stays in the explanations section;
this screen shows the numbers side by side and names the one to quote.
"""

from __future__ import annotations

import core as hc
from assets import esc, hero, pctf, svg_hbar
from confirmatory_panels import floor_note, require
from explain import BAND_SHORT, THIN_MAX
from status_words import STATUS
from style import SELECT_ID

# (metric, name, question, averaged over, note). Built from here rather than
# typed per card, so the card and the metric name cannot drift apart. The name
# is the metric's own and the question is its plain-English gloss.
HEADLINES = [
    ("macro_top1", "Top-1 accuracy", "The first guess is right", "per species",
     "each of the {n_sp} species counts once. Quote this one"),
    ("micro_top1", "Top-1 accuracy", "The first guess is right", "per frame",
     "each frame counts once, so common species dominate"),
    ("macro_top5", "Top-{k} accuracy", "The right name is among the {k} returned",
     "per species", "a ceiling on our {k}-name request, not on the model"),
    ("micro_top5", "Top-{k} accuracy", "The right name is among the {k} returned",
     "per frame", "we only ever asked Pl@ntNet for {k} names"),
]

# The chart's bar colour, the blue every other bar on the page uses.
BAR = "#1565c0"


def intro(c) -> str:
    """What is measured, on what, and why the model has not seen our labels."""
    return (f'<p class="intro">How often Pl@ntNet names the tree a botanist labelled, '
            f'over {c.n:,} drone frames of {c.n_sp} species. The model dates from '
            f'{esc(hc.plantnet_version_words())}, before any BCI label was sent to '
            f'Pl@ntNet. What to label next is on the '
            f'<a href="label_queue_dashboard.html">label queue page</a>.</p>')


def cards(c) -> str:
    """The four accuracy rates, precision, and how many species it usually gets
    right. The last is the "usually right" status count, so the card and the
    status bar under it cannot disagree."""
    k = c.n_cand
    out = [(f"{name.format(k=k)}, {averaged}", pctf(c.now[metric]),
            question.format(k=k), note.format(n_sp=c.n_sp, k=k))
           for metric, name, question, averaged, note in HEADLINES]
    thick = sum(1 for d in c.per_species
                if d["n_labelled_frames"] >= hc.WELL_SAMPLED_MIN_N)
    usually = sum(1 for st in c.status.values() if st == "reliable")
    out.insert(2, ("Precision, per species", pctf(c.now["macro_precision"]),
                   "When it offers a name, that name is right",
                   f"averaged over the {c.n_sp} species", "per_species_health.csv"))
    out.append(("Species it usually gets right", f"{usually} of {thick}",
                f"First guess right at least {100 * hc.RELIABLE_MIN_TOP1:.0f}% of the time",
                f"among species with {hc.WELL_SAMPLED_MIN_N} or more labelled frames",
                "per_species_health.csv"))
    return hero(out, cls="wide")


def status_bar(c) -> str:
    """How many species carry each status. A click filters the table to them.

    The script reaches the table through the status dropdown's own id, which
    the table's script already owns, and opens the panel around it.
    """
    counts = {k: 0 for k in STATUS}
    for st in c.status.values():
        counts[st] += 1
    buttons = "".join(
        f'<button type="button" class="tag {k}" data-status="{k}">'
        f'{esc(STATUS[k][0])}: {counts[k]}</button>'
        for k in STATUS if counts[k])
    # A div, not a paragraph: the buttons are controls, not a sentence.
    return (f'<div class="statusbar"><b>{c.n_sp} species by status.</b> {buttons}</div>'
            f'<script>(function(){{'
            f'var s=document.getElementById("{SELECT_ID}");if(!s)return;'
            f'Array.prototype.forEach.call(document.querySelectorAll(".statusbar button"),'
            f'function(b){{b.addEventListener("click",function(){{'
            f's.value=b.getAttribute("data-status");'
            f's.dispatchEvent(new Event("change"));'
            f'var d=s.closest("details");if(d){{d.open=true;d.scrollIntoView();}}'
            f'}});}});}})();</script>')


def by_frames(c) -> str:
    """Top-1 by how many labelled frames a species has, one bar per band."""
    rows, few = [], 0
    for lo, hi, lab in hc.SUPPORT_BUCKETS:
        b = c.buckets.get(lab)
        if not b or not b["n_crowns"]:
            continue
        if hi <= THIN_MAX:
            few += b["n_species"]
        rows.append((BAND_SHORT[lab], b["c1"] / b["n_crowns"],
                     f'{pctf(b["c1"] / b["n_crowns"])} of {b["n_crowns"]:,} frames, '
                     f'{b["n_species"]} species', BAR))
    return (svg_hbar(rows, title="first guess right, by labelled frames per species")
            + f'<p class="note">Species with more labelled frames are named far more '
              f'often. {few} of the {c.n_sp} species have {THIN_MAX} frames or fewer. '
              f'<a href="#why-the-two-headline-scores-differ">Why the two top-1 rates '
              f'differ</a>.</p>')


def review_line(c) -> str:
    """The review list in one line, linked to the panel and the file."""
    n = len(c.review)
    return (f'<p class="note"><b>{n} labels worth a second look.</b> The model is at '
            f'least {hc.REVIEW_CONF:.1f} confident in a different species, and at that '
            f'confidence it is right {pctf(c.confident_ok)} of the time '
            f'({c.confident_hits:,} of {len(c.confident):,}). '
            f'<a href="#labels-worth-a-second-look">See the list</a> or take '
            f'<a href="label_review_queue.csv">label_review_queue.csv</a>.</p>')


def landing(c) -> str:
    """Everything above the first section heading."""
    return "\n".join([intro(c), cards(c), floor_note(require(c.cf)),
                      status_bar(c), by_frames(c), review_line(c)])
