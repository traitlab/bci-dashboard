"""The status vocabulary all three pages share: what each status is called,
why a species gets it, and which ones a botanist can pass over.

One module, so a word changed here changes legend, table and to-do list together.
"""

from __future__ import annotations

import core as hc

# key -> (label, what to do about it). Order is the order of the to-do list:
# cheapest useful work first, safe-to-skip last.
STATUS = {
    "ranking": ("Right name in the list, not first",
                "Cheapest work here. Confirm the name from the short list instead of "
                "identifying from scratch"),
    "unmeasured": ("Too few labels to judge",
                   "Label a few more before trusting any number for it"),
    "hard": ("Wrong even with enough labels",
             "More labels will not fix this one. Treat it as a model limit"),
    "adequate": ("Mixed", "Keep it in the normal review queue"),
    "reliable": ("Usually right", "Lowest priority. Spot-check a few and move on"),
    # core.diagnose reads in_corpus_vocabulary, true when the name came back on
    # ANY BCI photo, so 0.0% under a different status is not a contradiction.
    "unreachable": ("Never returned on any BCI photo",
                    "Nothing to do until we know whether Pl@ntNet carries this "
                    "species at all"),
}

# The rows a botanist can pass over, not simply the tail of STATUS.
SKIP_STATUSES = ("hard", "reliable", "unreachable")


def uncap(label):
    """A status label mid-sentence: only the first letter drops, since ``.lower()``
    turns "Never returned on any BCI photo" into "any bci photo"."""
    return label[:1].lower() + label[1:]

STATUS_REASON = {
    "ranking": f"The right name is already in the {hc.N_CANDIDATES}, so this is the "
               f"cheapest confirmation work.",
    "unmeasured": f"Fewer than {hc.WELL_SAMPLED_MIN_N} labelled frames, so the score is "
                  f"too thin to trust yet.",
    "hard": "Enough frames, but the first guess is still weak, so more labels will not fix it.",
    "adequate": "Mixed results, so keep it in the normal review queue.",
    "reliable": "Usually right, so this species is low priority for extra work.",
    "unreachable": "Pl@ntNet never returned this name on any BCI photo, not just on this "
                   "species\u2019 own frames. Labelling will not recover it. Other rows do "
                   "show 0.0% in the \u201cRight name in the list\u201d column under a "
                   "different status. There the model did produce the name, just never on "
                   "the frames of that species.",
}

def status_precedence_note():
    """One sentence saying a species gets the first status that fits it.

    Built from ``hc.STATUS_PRECEDENCE``, so a reorder in ``diagnose`` cannot
    leave the page describing the old order.
    """
    names = [uncap(STATUS[k][0]) for k in hc.STATUS_PRECEDENCE]
    return ("Each species gets one status: the first rule that fits. Order: "
            + ", ".join(f"&ldquo;{n}&rdquo;" for n in names)
            + f". So a few-frame species can still show as &ldquo;{names[2]}&rdquo;. "
            "That is the point: it is cheap work whatever its count. Read the "
            "labelled-frames column next to the status.")


def legend_entries():
    """The status legend's rows: ``(key, label, why)`` in read order.

    One definition, so a status added to ``STATUS`` reaches both pages' legends.
    """
    return [(k, STATUS[k][0], STATUS_REASON[k]) for k in STATUS]


def filter_options():
    """The status filter's options: ``(key, label)`` in read order."""
    return [(k, v[0]) for k, v in STATUS.items()]
