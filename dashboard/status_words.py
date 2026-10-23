"""The status vocabulary all three pages share: what each status is called,
why a species gets it, and how to check its model predictions.

One module, so a word changed here changes legend, table and to-do list together.
"""

from __future__ import annotations

import core as hc

# key -> (label, how to review model predictions). No status ranks biodiversity value.
STATUS = {
    "ranking": ("Right name in the list, not first",
                "Compare the candidates with the photo; a lower-ranked prediction may fit better"),
    "unmeasured": ("Too few labels to judge",
                   "Inspect photos and add labelled evidence before trusting this species' rate"),
    "hard": ("Often wrong on labelled frames",
             "Use manual identification or expert review; do not rely on the top prediction"),
    "adequate": ("Mixed", "Check the prediction against the photo; performance varies"),
    "reliable": ("Usually right", "Lower priority for checking model predictions. Keep labels needed for biodiversity work"),
    # core.diagnose reads in_corpus_vocabulary, true when the name came back on
    # ANY BCI photo, so 0.0% under a different status is not a contradiction.
    "unreachable": ("Never returned on any BCI photo",
                    "Use manual identification; absence from returned predictions does not establish absence from the model"),
    "out_of_scope": ("Not in the project's own species list",
                      "Use manual identification; this model's project checklist does not carry the species"),
}


def uncap(label):
    """A status label mid-sentence: only the first letter drops, since ``.lower()``
    turns "Never returned on any BCI photo" into "any bci photo"."""
    return label[:1].lower() + label[1:]

STATUS_REASON = {
    "ranking": f"The right name was often among the {hc.N_CANDIDATES} returned "
               f"candidates but below the top prediction. Check candidates against the photo.",
    "unmeasured": f"Fewer than {hc.WELL_SAMPLED_MIN_N} labelled frames, so the score is "
                  f"too thin to trust yet.",
    "hard": f"At least {hc.WELL_SAMPLED_MIN_N} labelled frames, but top predictions are right "
            f"less than {hc.HARD_MAX_TOP1:.0%} of the time. Use manual identification or expert review.",
    "adequate": "Mixed results on labelled frames. Check each prediction against the photo.",
    "reliable": "Usually right on labelled frames, so lower priority for checking model predictions. "
                "This does not measure the species' biodiversity importance.",
    "unreachable": "Pl@ntNet never returned this name on any BCI photo. We ask each "
                   f"photo for {hc.N_CANDIDATES} names. A species it carries but never "
                   "ranks that high looks the same to us as one it lacks. A 0.0% "
                   f"\u201cTop-{hc.N_CANDIDATES} accuracy\u201d under another status means "
                   "the name did come back, just never on that species\u2019 frames.",
    "out_of_scope": "Pl@ntNet's own list for this project does not carry it. "
                    "Manual identification and biodiversity labels remain useful.",
}

def status_precedence_note():
    """One sentence saying a species gets the first status that fits it.

    Built from ``hc.STATUS_PRECEDENCE``, so a reorder in ``diagnose`` cannot
    leave the page describing the old order.
    """
    # STATUS_PRECEDENCE stops where the order stops mattering; the last two go by accuracy.
    names = [uncap(STATUS[k][0]) for k in (*hc.STATUS_PRECEDENCE, "hard", "adequate")]
    quoted = [f"&ldquo;{n}&rdquo;" for n in names]
    # Split the order into two sentences at the midpoint, not one long list:
    # a status added to STATUS_PRECEDENCE grows this list, and one sentence
    # holding all of it would eventually run over the page's sentence-length
    # ceiling.
    mid = (len(quoted) + 1) // 2
    order = ("In order: " + ", ".join(quoted[:mid]) + ". Then " + ", ".join(quoted[mid:])
             + ".")
    return ("Each species gets the first status that fits. " + order +
            f" A species with few frames can still show as &ldquo;{names[2]}&rdquo;, "
            "because that status has no minimum frame count.")


def legend_entries():
    """The status legend's rows: ``(key, label, why)`` in read order.

    One definition, so a status added to ``STATUS`` reaches both pages' legends.
    """
    return [(k, STATUS[k][0], STATUS_REASON[k]) for k in STATUS]


def filter_options():
    """The status filter's options: ``(key, label)`` in read order."""
    return [(k, v[0]) for k, v in STATUS.items()]
