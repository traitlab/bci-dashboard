"""Model-health panels that read the refresh manifest: what changed between updates.

Each takes the figure namespace and returns HTML, like ``panels.py``. The
arithmetic is in ``snapshot_delta.py``; this only lays it out.
"""

from __future__ import annotations

import reference
from assets import esc, panel, pctf, table

# A long list of moved species is a table nobody reads past the top.
MOVED_SHOWN = 15


def _signed(n: int) -> str:
    return f"{n:+,}"


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
        ["First guess right", _top1(prev), _top1(cur), top1],
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
    rows = [[esc(e["run_date"]), esc(e["export"]), f"{e['labelled']:,}", f"{e['species']:,}",
             _top1(e), esc(e["model_version"])] for e in runs]
    return table([("Refreshed", False), ("Export", False), ("Labelled frames", True),
                  ("Species", True), ("First guess right", False), ("Model", False)], rows)


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
                 f"newest first.</p>" + _history_table(runs))
    return panel("Since the last update",
                 "<b>Read this before comparing today's rates with an earlier visit.</b> "
                 "It compares the last two Labelbox exports.",
                 body, anchor="since-the-last-update")
