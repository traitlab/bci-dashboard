"""Model-health panels that read the refresh manifest: what changed between updates.

Each takes the figure namespace and returns HTML, like ``panels.py``. The
arithmetic is in ``snapshot_delta.py`` and ``confused_pairs.py``; this only
lays it out.
"""

from __future__ import annotations

import confused_pairs
import core as hc
import reference
from assets import esc, panel, pctf, table
from snapshot_delta import model_age_words

# A long list of moved species is a table nobody reads past the top.
MOVED_SHOWN = 15


def _signed(n: int) -> str:
    return f"{n:+,}"


def _relabels(e: dict) -> str:
    """Frames whose label differs from the baseline ground truth, a dash when unknown."""
    n = e.get("relabels_vs_baseline")
    return "-" if n is None else f"{n:,}"


def _top1(e: dict) -> str:
    """The rate with the population and frame count it is over."""
    return (f"{pctf(e['test_top1'])} of {e['test_n']:,} test frames"
            if e["test_top1"] is not None else f"not scored ({e['test_n']:,} test frames)")


def _summary_table(d: dict) -> str:
    prev, cur = d["prev"], d["cur"]
    top1 = ("not compared" if d["top1_delta"] is None
            else f"{100 * d['top1_delta']:+.1f} points")
    rows = [
        ["Frames labelled to a species", f"{prev['labelled']:,}", f"{cur['labelled']:,}",
         _signed(d["new_labelled"])],
        ["Frames labelled at all", f"{prev['frames']:,}", f"{cur['frames']:,}",
         _signed(d["new_frames"])],
        ["Species", f"{prev['species']:,}", f"{cur['species']:,}",
         _signed(cur["species"] - prev["species"])],
        ["Top prediction right", _top1(prev), _top1(cur), top1],
        ["Model", esc(prev["model_version"]), esc(cur["model_version"]),
         "changed" if d["version_changed"] else "same"],
    ]
    return table([("", False), (esc(f"Export {prev['export']}"), True),
                  (esc(f"Export {cur['export']}"), True), ("Change", True)], rows)


def _moved_table(d: dict) -> str:
    moved = d["moved"]
    if not moved:
        return '<p class="note">No species has a different number of labelled frames.</p>'
    rows = [[f"<i>{esc(sp)}</i>", f"{a:,}", f"{b:,}", _signed(b - a)]
            for sp, a, b in moved[:MOVED_SHOWN]]
    more = (f'<p class="note">And {len(moved) - MOVED_SHOWN} more species moved.</p>'
            if len(moved) > MOVED_SHOWN else "")
    return (table([("Species", False), ("Labelled frames before", True),
                   ("Labelled frames now", True), ("Change", True)], rows) + more)


def _history_table(runs: list[dict]) -> str:
    # Newest first, so a line's model is compared with the next line down.
    older = runs[1:] + [None]
    rows = [[esc(e["run_date"]), esc(e["export"]), f"{e['labelled']:,}", f"{e['species']:,}",
             _top1(e), _relabels(e),
             esc(e["model_version"])
             + (" (new model)" if o and o["model_version"] != e["model_version"] else "")]
            for e, o in zip(runs, older)]
    return table([("Refreshed", False), ("Export", False), ("Labelled frames", True),
                  ("Species", True), ("Top prediction right", False), ("Labels changed since baseline", True),
                  ("Model", False)], rows)


def _model_note(built: str) -> str:
    """The model the cached answers came from, and how old it was at the build."""
    age = model_age_words(hc.PLANTNET_MODEL_VERSION, built)
    return (f'<p class="note">The Pl@ntNet model is {esc(hc.plantnet_version_words())}'
            + (f", {age} on the day this page was built" if age else "")
            + f", still what the endpoint reported on {esc(hc.date_words(hc.PLANTNET_VERSION_CHECKED))}"
            + ". The Model column changes when the recorded model version is updated.</p>")


def p_confused(c):
    """The wrong top predictions that repeat: which two species the model swaps,
    and, once an earlier refresh recorded them, each pair's count back then."""
    then = confused_pairs.trend(getattr(c, "changes", None))
    rows = [[f"<i>{esc(gt)}</i>", f"<i>{esc(guess)}</i>", f"{n:,}", f"{support:,}"]
            + ([" → ".join("new" if m is None else f"{m:,}" for m in then[1].get((gt, guess), [None]))]
               if then else [])
            for gt, guess, n, support in c.confused]
    headers = [("Label", False), ("Top prediction", False), ("Frames", True),
               ("Labelled frames of the label species", True)]
    if then:
        headers.append((esc(f"Frames at exports {', '.join(then[0])}"), True))
    body = (f'<p class="note">Counted over the {c.n:,} frames labelled to a species, '
            f"every wrong top prediction."
            + (f" The last column is the pair's frame count at each recent export, oldest first; "
               f"new means the pair was not among the {confused_pairs.SHOWN} most common then. "
               f"Counts, not rates: the label species' labelled frames are in the column before, "
               f"as of now." if then else "")
            + "</p>"
            + table(headers, rows, source=confused_pairs.NAME)
            if rows else '<p class="note">No top prediction is wrong.</p>')
    return panel("Species the model mixes up",
                 f"<b>The pairs behind most repeated errors.</b> The {len(rows)} most common "
                 f"wrong top predictions, as a label and the species the model named instead.",
                 body, anchor="species-the-model-mixes-up")


def p_changes(c):
    """What the last export changed, and the last few updates in one table."""
    runs = c.changes["runs"]
    d = c.changes["diff"]
    if d is None:
        first = runs[0] if runs else None
        body = ('<p class="note">'
                + (f"The first recorded update is the export of {esc(first['export'])}, "
                   f"with {first['labelled']:,} frames labelled to {first['species']:,} "
                   f"species. The next refresh will show what changed."
                   if first else "No update has been recorded yet.")
                + "</p>")
    else:
        new = d["new_species"]
        body = (_summary_table(d)
                + (f'<p class="note">{reference.break_sentence(*d["crossed"])}</p>'
                   if d["crossed"] else "")
                + '<p class="note">'
                + ("New species: " + ", ".join(f"<i>{esc(sp)}</i> ({n:,} frame{'' if n == 1 else 's'})" for sp, n in new)
                   + "." if new else "No new species.")
                + (" No longer labelled: "
                   + ", ".join(f"<i>{esc(sp)}</i>" for sp in d["lost_species"]) + "."
                   if d["lost_species"] else "")
                + "</p>"
                + _moved_table(d))
    if runs:
        body += (f'<p class="note">The last {len(runs)} update{"" if len(runs) == 1 else "s"}, '
                 f"newest first.</p>" + _history_table(runs)
                 + '<p class="note">Labels changed since baseline counts frames labelled in both '
                 'the baseline ground truth and now with a different species. It is cumulative, '
                 'not per refresh, and only the count is recorded.</p>')
    body = _model_note(c.generated) + body
    return panel("Since the last update",
                 "<b>Read this before comparing today's rates with an earlier visit.</b> "
                 "It compares the last two Labelbox exports.",
                 body, anchor="since-the-last-update")
