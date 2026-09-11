"""Four rates that have no value when the population behind them is empty.

Every one of them divides by a count that today is comfortably non-zero, so
none of these has ever fired. Each becomes reachable for a different reason,
and none of the four is a hypothetical:

- The crop-coverage sweep runs a threshold high enough to admit nothing, and
  `core.coverage_gate_stats` answers `macro_top1: None` for an empty subset.
  `run_log.log_gate_comparison` formatted that with `* 100`, a `TypeError`.
- Nothing requires a frame to reach `REVIEW_CONF`. A model that is never sure
  raises no labels for review, and `figures._review` divided by that count.
- The unlabelled pool empties when every photo has a botanist label, which is
  the labelling programme finishing. `queue_panels.send_notes` divided the
  long-lens share by it.
- A corpus can carry genus-only labels and no species-level ones, scoring no
  species at all. `measure.headline_counts` divided by that count, and the two
  macro averages it produces are read again by `log_headline`.

A rate over nothing is not zero, it is absent, so all four now answer `None`
and every reader prints "n/a".

    .venv/bin/pytest tests/test_empty_populations.py
"""

from __future__ import annotations

import re
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# The gated macro average, when the gate admits nothing
# ---------------------------------------------------------------------------

def test_coverage_gate_reports_no_macro_average_over_an_empty_subset(core):
    """`None`, not 0.0: no species was scored, so no average exists."""
    rejected = [{"gt": "a b", "ranked": [("a b", 1.0)], "crop_coverage": 0.1,
                 "crop_dominant": "a b"}]
    gate = core.coverage_gate_stats(rejected, 0.9)
    assert gate["n_admitted"] == 0
    assert gate["macro_top1"] is None


def test_the_gate_comparison_prints_na_rather_than_raising(core, run_log):
    """The bug in its original shape: `macro_top1 * 100` on a None."""
    rl = run_log
    lines = []
    empty = core.coverage_gate_stats([], 0.5)
    rl.log_gate_comparison(lines.append, [], [empty], empty,
                           n=0, n_sp=0, c1=0, macro1=None)
    macro = next(ln for ln in lines if "macro per-species top-1" in ln)
    assert macro.count("n/a") == 2, macro


def test_the_na_column_is_as_wide_as_the_number_it_stands_in_for(run_log):
    """A sweep row that reads n/a has to line up under the same heading, or the
    table stops being a table on the run it matters most."""
    rl = run_log
    number = rl._macro(0.5, 12)
    absent = rl._macro(None, 12)
    assert len(number) == len(absent) == 13


def test_the_headline_macro_averages_survive_a_genus_only_corpus(measure):
    """A corpus whose labels all stop at the genus scores no species, so there
    is nothing to average over. The genus rates beside it are still measured,
    which is why this reports absent rather than aborting the pass."""
    gen = [{"gt": "Inga", "ranked": [("Inga edulis", 0.9)]},
           {"gt": "Inga", "ranked": [("Ficus insipida", 0.7)]}]
    h = SimpleNamespace(sp_recs=[], genus_recs=gen, per_species=[])
    counts = measure.headline_counts(h)
    assert counts.macro1 is None
    assert counts.macro5 is None
    # The measurement that does exist is still reported.
    assert (counts.gn, counts.gg1) == (2, 1)


# ---------------------------------------------------------------------------
# The confident-and-right rate, when the model is never confident
# ---------------------------------------------------------------------------

def test_review_reports_no_rate_when_no_frame_is_confident(core, figures):
    """`_review` filters on `REVIEW_CONF` and then divides by what survives."""
    timid = [{"gt": "a b", "ranked": [("a b", core.REVIEW_CONF - 0.01)],
              "global_key": "k1"}]
    got = figures._review(timid)
    assert got["confident"] == []
    assert got["confident_ok"] is None
    assert got["review_counts"] == (0, 0)


def test_review_still_reports_a_rate_when_one_frame_is_confident(figures):
    """The guard must not swallow the ordinary case."""
    sure = [{"gt": "a b", "ranked": [("a b", 1.0)], "global_key": "k1"},
            {"gt": "a b", "ranked": [("c d", 1.0)], "global_key": "k2"}]
    assert figures._review(sure)["confident_ok"] == 0.5


def test_a_rate_of_none_prints_as_na(assets):
    """What the panels do with it, so `None` reaches a reader as a word."""
    assert assets.pctf(None) == "n/a"


# ---------------------------------------------------------------------------
# The long-lens share, when the queue is empty
# ---------------------------------------------------------------------------

def test_the_long_lens_share_is_absent_rather_than_dividing_by_an_empty_queue(
        queue_panels, core):
    """`send_notes` divides the tele count by the whole queue. Both are zero
    once every photo carries a label, which is the programme succeeding."""
    from collections import Counter
    from types import SimpleNamespace

    c = SimpleNamespace(
        lt_species={}, n_no_answer=0,
        scored_cams=Counter({"zoom": 1, "tele": 0}),
        queue_cams=Counter({"zoom": 0, "tele": 0}))
    body = queue_panels.send_notes(c)
    assert "n/a" in body
    assert not re.search(r"\d+ of the queue \(\)", body)


# ---------------------------------------------------------------------------
# The two link columns, when no row carries either link
# ---------------------------------------------------------------------------

def _links_note(queue_panels, monkeypatch, n_img, n_linked):
    """`links_note` over a two-row queue with the given link coverage.

    Both lookups are patched on the module `queue_panels` itself imported, not
    on the `core` fixture: the fixture loads its own copy under another name,
    so patching it would leave the panel reading the real inventory.
    """
    from types import SimpleNamespace

    from queues import SEND_FIRST_COLUMNS

    keys = ["comb_a.JPG", "comb_b.JPG"]
    at = SEND_FIRST_COLUMNS.index("global_key")
    rows = []
    for key in keys:
        made = [""] * len(SEND_FIRST_COLUMNS)
        made[at] = key
        rows.append(made)
    monkeypatch.setattr(queue_panels.hc, "labelbox_link_coverage",
                        lambda _keys: {"n_linked": n_linked,
                                       "n_unlinked": len(keys) - n_linked})
    monkeypatch.setattr(queue_panels.hc, "inventory_image_urls",
                        lambda: {k: "http://example/photo" for k in keys[:n_img]})
    return queue_panels.links_note(SimpleNamespace(queue_rows=rows))


def test_the_links_panel_does_not_promise_links_no_row_carries(
        queue_panels, monkeypatch):
    """It opened "Every row carries two links" and then reported both columns
    filled on no row at all, so the panel refuted itself inside three
    sentences. With nothing filled there is one sentence instead."""
    body = _links_note(queue_panels, monkeypatch, n_img=0, n_linked=0)
    assert body == ('<p class="note">No frame links to its photo or its Labelbox row '
                    'yet.</p>')


def test_the_links_panel_explains_the_columns_once_a_row_carries_one(
        queue_panels, monkeypatch):
    """The explanation is worth its length only when there is a link to
    explain, so one filled cell is enough to bring it back."""
    body = _links_note(queue_panels, monkeypatch, n_img=1, n_linked=0)
    assert "Two link columns" in body
    assert "1 of 2 rows" in body
