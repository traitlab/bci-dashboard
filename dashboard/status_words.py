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
                    "Label these like any other row. We have not yet asked Pl@ntNet "
                    "whether it carries this species"),
    "out_of_scope": ("Not in the project's own species list",
                      "Skip. predict/fetch_checklist.py shows Pl@ntNet does not carry "
                      "this species under the project we predict from"),
}

# The rows a botanist can pass over, not simply the tail of STATUS.
#
# "Never returned on any BCI photo" is not one of them, and used to be. We only
# ever asked for hc.N_CANDIDATES names per photo, so a species the model carries
# but has never ranked that high looks exactly like one it does not carry.
# Telling a botanist to skip those rows spends an unproven absence as though it
# were a proven one, which is the opposite of what README.md says about that
# population. "Not in the project's own species list" is the proven version of
# that same absence: predict/fetch_checklist.py has shown the name is missing
# from the project's own species list, so it belongs in this tuple and
# "unreachable" still does not.
SKIP_STATUSES = ("hard", "reliable", "out_of_scope")


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
                   "species\u2019 own frames. That is what we saw, not what the model can "
                   f"do. We ask each photo for {hc.N_CANDIDATES} names. A species it "
                   "carries but never ranks that high looks the same to us as one it does "
                   "not carry at all. Other rows do show 0.0% in the "
                   f"\u201cTop-{hc.N_CANDIDATES} accuracy\u201d column under a different "
                   "status. There the model did produce the name, just never on the "
                   "frames of that species.",
    "out_of_scope": "Pl@ntNet's own species list, read by predict/fetch_checklist.py, "
                    "does not carry this name. That is a proven absence, not the "
                    "sample effect behind “never returned”.",
}

def status_precedence_note():
    """One sentence saying a species gets the first status that fits it.

    Built from ``hc.STATUS_PRECEDENCE``, so a reorder in ``diagnose`` cannot
    leave the page describing the old order.
    """
    names = [uncap(STATUS[k][0]) for k in hc.STATUS_PRECEDENCE]
    quoted = [f"&ldquo;{n}&rdquo;" for n in names]
    # Split the order into two sentences at the midpoint, not one long list:
    # a status added to STATUS_PRECEDENCE grows this list, and one sentence
    # holding all of it would eventually run over the page's sentence-length
    # ceiling.
    mid = (len(quoted) + 1) // 2
    order = ("Order: " + ", ".join(quoted[:mid]) + ". Then " + ", ".join(quoted[mid:]) + ".")
    return ("Each species gets one status: the first rule that fits. " + order +
            f" A few-frame species can still show as &ldquo;{names[2]}&rdquo;. "
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
