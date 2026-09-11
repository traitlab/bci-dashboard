"""The four things the pages say off ``data/model_health/``, rendered.

Each helper reads one file ``assessments.prepared`` loaded and hands back a
fragment a panel in ``panels.py`` drops in place. Kept out of panels.py, which
is over the 500-line rule already, and out of assessments.py, which knows
nothing about HTML. Every number here carries the population it was counted on,
and every one is a queue position or a flag for a second look, never a label.
"""

from __future__ import annotations

from assessments import LIMIT_MIN_FRAMES, LIMIT_WORDS
from assets import esc, more, table

# What the disagreement file's words mean on the page. speciesfirst has a fourth,
# liana_overgrowth, which the script never gives without a growth-habit table,
# so the page does not word it: a word with no row behind it is a claim.
MECHANISM_WORDS = {
    "species_conflict": "two different species",
    "synonym_artifact": "one species under two names",
    "coarser_label": "a label that stops at genus or family",
}

LIMIT_HINT = ("Whether more labels or a better model would move this row. "
              "Judged by hiding half the labels and asking how the photos look "
              "to the model, eight times over.")


def limit_cell(limit: str, agreement: str) -> str:
    """One cell of the species table's last column: the verdict in the page's
    words with how many draws agreed, or blank."""
    if not limit:
        return ""
    n, of = agreement.split("/")
    return f'{esc(LIMIT_WORDS[limit])} <span class="tally">{n} of {of} draws</span>'


def limit_note(transductive: dict, limits: dict) -> str:
    """The one-line legend for that column, population and count included.

    The counts are taken off ``limits``, the words the table prints, and not
    off the sidecar's summary, which covers every species down to one frame:
    a legend saying 22 rows read "more labels" over a column showing none
    would be the page describing a file it is not using.
    """
    pop = transductive["population"]
    shown = [v for v, _ in limits.values() if v]
    count = {k: sum(1 for v in shown if v == k) for k in LIMIT_WORDS}
    return (f'<p class="note"><b>What would help</b> is judged on the '
            f'{pop["n_frames"]:,} labelled frames the model has a view of, '
            f'{pop["n_species"]} species. Half the labels are hidden. Each hidden '
            f'frame is then named from its {transductive["method"]["k"]} nearest '
            f'labelled ones, {pop["n_seeds"]} times over with a different half. '
            f'<i>{LIMIT_WORDS["resolved"]}</i>: the hidden frames come back right. '
            f'<i>{LIMIT_WORDS["classifier_limited"]}</i>: the labels are there and the '
            f'nearest-photo rule still misses, so more labels will not close it. '
            f'<i>{LIMIT_WORDS["sampling_limited"]}</i>: too few labels for the rule to '
            f'work from. Blank under {LIMIT_MIN_FRAMES} viewed frames. Over the '
            f'{len(shown)} species with that many: {count["resolved"]} no gap found, '
            f'{count["classifier_limited"]} better model, '
            f'{count["sampling_limited"]} more labels.</p>')


def mechanism_note(disagreement: dict, counts) -> str:
    """Why the two names differ, for the review queue as a whole.

    ``counts`` is mechanism to frame count over the rows on the page. Grouped
    in prose rather than as a second table: every row here is one mechanism so
    far, and a heading over 51 rows saying so is a heading over the table.
    """
    n = sum(counts.values())
    named = ", ".join(f'{c} {MECHANISM_WORDS.get(m, m)}'
                      for m, c in sorted(counts.items(), key=lambda kv: -kv[1]) if m)
    blank = counts.get("", 0)
    pop = disagreement["population"]
    # The count is the answer. How the synonym check was run, and how many rows
    # it removed, is a question about the list's making rather than about any
    # row in it, so it waits one click in.
    return (f'<p class="note"><b>Why the two names differ, over all {n} frames:</b> '
            f'{named or "not assessed"}'
            f'{f", {blank} not assessed" if blank else ""}.</p>'
            + more("What was dropped before this list",
                   f'<p class="note">A pair that is one species under two names is '
                   f'dropped before it reaches this list. That check reads the accepted '
                   f'name from a cached copy of the world checklist of vascular plants, '
                   f'and dropped {pop["n_conflicts"] - pop["n_flagged"]} of '
                   f'{pop["n_conflicts"]} conflicts.</p>'))


def unplaced_note(pop: dict) -> str:
    """How many frames the new-flight columns could not place on a flight, or
    nothing when every one was placed."""
    n = pop.get("n_unplaced", 0)
    if not n:
        return ""
    return (f'<p class="note">{n:,} frame{"s" if n != 1 else ""} could not be placed '
            f'on a flight. In the new-flight columns each stands alone.</p>')


def reject_table(sweep: dict) -> str:
    """If only frames with at most k plausible names are trusted: what share of
    frames that keeps and how often their first guess is right. A queue
    position, never a label: it says which frames a botanist can look at last."""
    pop, method = sweep["population"], sweep["method"]

    def kept(r):
        return f'{100 * r["accept_rate"]:.1f}% ({r["n_accepted"]:,})'

    rows = [[f'{r["max_set_size"]}', kept(r), kept(g),
             f'{100 * r["accepted_accuracy"]:.1f}%', f'{100 * g["accepted_accuracy"]:.1f}%']
            for r, g in zip(sweep["rows"], sweep["grouped_rows"], strict=True)]
    return (f'<p class="note"><b>Trusting a frame only when few names are plausible.</b> '
            f'A separate check over the {pop["n_frames"]:,} labelled frames the model has '
            f'a view of, {pop["n_species"]} species.</p>'
            # The rows are a queue order, and a reader taking the order does not
            # need the method under it. A reader asking whether the order is
            # worth taking needs all four sentences, so they stay, one click in.
            + more("How the plausible-name count is worked out",
                   f'<p class="note">A plain classifier is fitted to how the photos '
                   f'look, in {method["n_folds"]} folds. Each frame is then asked how '
                   f'many names it cannot rule out, at '
                   f'{100 * (1 - method["alpha"]):.0f}% coverage. This is not Pl@ntNet '
                   f'and its first guess is not Pl@ntNet&rsquo;s.</p>')
            + table([("At most this many plausible names", True),
                     ("Frames kept", True), ("Frames kept, new flight", True),
                     ("First guess right, kept frames", True),
                     ("First guess right, new flight", True)], rows,
                    source="reject_sweep.csv")
            # The frames a queue orders sit on flights with no labelled frame, so
            # the rate beside the frame-by-frame one is the one that describes
            # them. Never printed alone: assessments.prepared refuses a sidecar
            # without it.
            + '<p class="note">Photos from one flight overlap. The new-flight columns '
              'judge each frame with a classifier that saw no photo from its flight. '
              'That is the case for any flight with no labels yet. The others can lean '
              'on near-copies from the same flight.</p>'
            + unplaced_note(pop)
            + '<p class="note">Read a row as a queue position: frames with many '
              'plausible names go in front of a botanist first. Nothing here labels a '
              'frame. The classifier and random seed are recorded, so the sweep '
              'reproduces exactly.</p>')


def richness_note(status: dict) -> str:
    """How many species the labels have reached, and how many the singletons say
    are still out there. Chao1 over every frame labelled to species. Sits in
    the frame-counts panel, beside the count it qualifies."""
    r, pop = status["richness"], status["population"]
    return (f'<p class="note"><b>Species the labels have reached:</b> {r["observed"]}, '
            f'over the {pop["n_species_level"]:,} of {pop["n_labelled"]:,} labelled '
            f'frames that name a species. {r["singletons"]} were seen once and '
            f'{r["doubletons"]} twice. By the Chao1 rule that suggests about '
            f'{r["unseen_estimate"]} more not yet reached, so the list is about '
            f'{100 * r["completeness"]:.0f}% complete. Every labelled frame counts here, '
            f'cached answer or not.</p>')
