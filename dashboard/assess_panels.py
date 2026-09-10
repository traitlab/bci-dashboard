"""The four things the pages say off ``data/model_health/``, rendered.

Each helper reads one file ``assessments.prepared`` loaded and hands back a
fragment a panel in ``panels.py`` drops in place. Kept out of panels.py, which
is over the 500-line rule already, and out of assessments.py, which knows
nothing about HTML. Every number here carries the population it was counted on,
and every one is a queue position or a flag for a second look, never a label.
"""

from __future__ import annotations

from assessments import LIMIT_MIN_FRAMES, LIMIT_WORDS
from assets import esc, table

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
    method, pop = disagreement["method"], disagreement["population"]
    out = (f'<p class="note"><b>Why the two names differ, over all {n} frames:</b> '
           f'{named or "not assessed"}'
           f'{f", {blank} not assessed" if blank else ""}. '
           f'A pair that is one species under two names is dropped before it reaches '
           f'this list. That check reads the accepted name in '
           f'<code>{esc(method["synonyms_from"].split("/")[-1])}</code>, and dropped '
           f'{pop["n_conflicts"] - pop["n_flagged"]} of {pop["n_conflicts"]} conflicts.')
    return out + '</p>'


def reject_table(sweep: dict) -> str:
    """If only frames with at most k plausible names are trusted: what share of
    frames that keeps and how often their first guess is right. A queue
    position, never a label: it says which frames a botanist can look at last."""
    pop, method = sweep["population"], sweep["method"]
    rows = [[f'{r["max_set_size"]}', f'{100 * r["accept_rate"]:.1f}%',
             f'{100 * r["accepted_accuracy"]:.1f}%',
             f'{r["n_accepted"]:,} of {pop["n_frames"]:,}']
            for r in sweep["rows"]]
    return (f'<p class="note"><b>Trusting a frame only when few names are plausible.</b> '
            f'A separate check over the {pop["n_frames"]:,} labelled frames the model '
            f'has a view of, {pop["n_species"]} species. A plain classifier is fitted to '
            f'how the photos look, in {method["n_folds"]} folds. Each frame is then asked '
            f'how many names it cannot rule out, at {100 * (1 - method["alpha"]):.0f}% '
            f'coverage. This is not Pl@ntNet and its first guess is not Pl@ntNet&rsquo;s. '
            f'It says how far a plausible-name count could order a queue.</p>'
            + table([("At most this many plausible names", True),
                     ("Frames kept", True), ("First guess right, kept frames", True),
                     ("Frames", True)], rows, source="reject_sweep.csv")
            + '<p class="note">Read a row as a queue position: frames with many '
              'plausible names go in front of a botanist first. Nothing here labels a '
              'frame. The classifier and seed behind the rows are recorded in '
              '<code>data/model_health/reject_sweep.json</code>.</p>')


def richness_note(status: dict) -> str:
    """How many species the labels have reached, and how many the singletons say
    are still out there. Chao1 over every frame labelled to species. Sits in
    the frame-counts panel, beside the count it qualifies."""
    r, pop = status["richness"], status["population"]
    return (f'<p class="note"><b>Species the labels have reached:</b> the labels so far '
            f'name {r["observed"]} species over the {pop["n_species_level"]:,} of '
            f'{pop["n_labelled"]:,} labelled frames that reach a species. '
            f'{r["singletons"]} of those species were seen once and {r["doubletons"]} '
            f'twice. By the Chao1 rule that suggests about {r["unseen_estimate"]} more '
            f'species the labels have not reached yet, so the list is about '
            f'{100 * r["completeness"]:.0f}% complete. This is a different population '
            f'from the species with a Pl@ntNet answer above. Every labelled frame counts '
            f'here, cached answer or not.</p>')
