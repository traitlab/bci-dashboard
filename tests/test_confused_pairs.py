"""The most-confused species pairs on the model-health page, their table, its
check, and the count an earlier refresh recorded for each pair.

    .venv/bin/pytest tests/test_confused_pairs.py
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import REPO, _on_path


@pytest.fixture(scope="session")
def mods():
    with _on_path(REPO / "dashboard"):
        import confused_pairs
        import history
        import history_panels
        yield SimpleNamespace(pairs=confused_pairs, history=history, panels=history_panels)


def recs(*pairs):
    """One scored frame per (label, top prediction)."""
    return [{"gt": gt, "ranked": [(guess, 0.9)]} for gt, guess in pairs]


SUPPORT = {"hura": 40, "ceiba": 10, "swartzia": 3}


def test_pairs_are_ordered_by_count_then_name_and_right_guesses_are_left_out(mods):
    frames = recs(*[("hura", "ceiba")] * 5, *[("ceiba", "hura")] * 2, *[("swartzia", "hura")] * 2,
                  *[("hura", "hura")] * 30)
    got = mods.pairs.pairs(frames, SUPPORT)
    assert got == [("hura", "ceiba", 5, 40), ("ceiba", "hura", 2, 10), ("swartzia", "hura", 2, 3)]


def test_only_the_top_fifteen_pairs_are_kept(mods):
    names = {f"sp{i:02d}": 5 for i in range(20)}
    frames = recs(*[(name, "other") for name in names])
    assert len(mods.pairs.pairs(frames, names)) == 15


def test_no_wrong_guess_gives_no_pairs_and_the_panel_says_so(mods):
    assert mods.pairs.pairs(recs(("hura", "hura")), SUPPORT) == []
    html = mods.panels.p_confused(SimpleNamespace(confused=[], n=1))
    assert "No top prediction is wrong." in html


def test_the_panel_prints_each_pair_with_its_count_and_label_support(mods):
    frames = recs(*[("hura", "ceiba")] * 5, *[("hura", "hura")] * 35)
    c = SimpleNamespace(confused=mods.pairs.pairs(frames, SUPPORT), n=len(frames))
    html = mods.panels.p_confused(c)
    assert 'id="species-the-model-mixes-up"' in html
    assert "<td><i>hura</i></td>\n<td><i>ceiba</i></td>\n<td class=\"num\">5</td>\n<td class=\"num\">40</td>" in html
    assert "Counted over the 40 frames labelled to a species" in html


PAIRS = [("hura", "ceiba", 5, 40), ("ceiba", "hura", 2, 10)]


def changes(prev_pairs, *, crossed=None):
    """A ``snapshot_delta.compute`` result whose earlier line holds ``prev_pairs``,
    or lacks the key altogether when that is None."""
    prev = {"export": "2026-10-15", **({} if prev_pairs is None else {"confused_pairs": prev_pairs})}
    cur = {"export": "2026-10-16", "confused_pairs": [["hura", "ceiba", 5]]}
    return {"runs": [cur, prev], "diff": {"prev": prev, "cur": cur, "crossed": crossed}}


def runs_changes(*per_run):
    """Manifest lines oldest to newest, one list of [label, guess, frames] each, as
    ``snapshot_delta.compute`` returns them (newest first) with the diff of the last two."""
    lines = [{"export": f"2026-10-{10 + i}", "reference": "r", "confused_pairs": p}
             for i, p in enumerate(per_run)]
    diff = ({"prev": lines[-2], "cur": lines[-1], "crossed": None} if len(lines) > 1 else None)
    return {"runs": lines[::-1], "diff": diff}


def test_the_panel_sets_each_pair_beside_its_earlier_count_or_says_new(mods):
    c = SimpleNamespace(confused=PAIRS, n=50, changes=changes([["hura", "ceiba", 3]]))
    html = mods.panels.p_confused(c)
    assert "Frames at exports 2026-10-15, 2026-10-16" in html
    assert '<td class="num">40</td>\n<td class="num">3 → 5</td>' in html
    assert '<td class="num">10</td>\n<td class="num">new</td>' in html
    assert "not among the 15 most common then" in html
    assert 'href="confused_pairs.csv"' in html


def test_three_runs_show_each_pairs_counts_oldest_to_newest_beside_the_support(mods):
    ch = runs_changes([["hura", "ceiba", 3]], [["hura", "ceiba", 5], ["ceiba", "hura", 1]],
                      [["hura", "ceiba", 8], ["ceiba", "hura", 2]])
    html = mods.panels.p_confused(SimpleNamespace(confused=PAIRS, n=50, changes=ch))
    assert "Frames at exports 2026-10-10, 2026-10-11, 2026-10-12" in html
    assert '<td class="num">40</td>\n<td class="num">3 → 5 → 8</td>' in html
    assert '<td class="num">10</td>\n<td class="num">new → 1 → 2</td>' in html


def test_the_trend_stops_at_a_run_without_pairs_or_with_other_reference_labels(mods):
    ch = runs_changes([["hura", "ceiba", 3]], [["hura", "ceiba", 5]], [["hura", "ceiba", 8]])
    ch["runs"][2]["reference"] = "other"
    assert mods.pairs.trend(ch) == (["2026-10-11", "2026-10-12"], {("hura", "ceiba"): [5, 8]})
    ch["runs"][2]["reference"] = "r"
    del ch["runs"][2]["confused_pairs"]
    assert mods.pairs.trend(ch)[0] == ["2026-10-11", "2026-10-12"]


def test_one_run_renders_the_table_without_a_trend_column(mods):
    ch = runs_changes([["hura", "ceiba", 8]])
    html = mods.panels.p_confused(SimpleNamespace(confused=PAIRS, n=50, changes=ch))
    assert "Frames at exports" not in html and "→" not in html
    assert '<td class="num">5</td>\n<td class="num">40</td>\n</tr>' in html


@pytest.mark.parametrize("earlier", [
    None,                                              # no manifest at all
    {"runs": [], "diff": None},                        # one line, nothing before it
    changes(None),                                     # a line older than the pair counts
    changes([["hura", "ceiba", 3]], crossed=("labelbox", "reviewed")),
])
def test_without_a_comparable_earlier_count_the_column_is_left_out(mods, earlier):
    html = mods.panels.p_confused(SimpleNamespace(confused=PAIRS, n=50, changes=earlier))
    assert "Frames at export" not in html and ">new<" not in html
    assert mods.pairs.earlier(earlier) is None and mods.pairs.trend(earlier) is None


def test_the_table_reads_back_in_the_manifest_form_and_is_checked(mods, tmp_path):
    assert mods.pairs.read(str(tmp_path)) is None
    assert "check skipped" in mods.history.check_confused(str(tmp_path), PAIRS)
    mods.pairs.write(str(tmp_path), PAIRS)
    assert mods.pairs.read(str(tmp_path)) == [["hura", "ceiba", 5], ["ceiba", "hura", 2]]
    assert mods.history.check_confused(str(tmp_path), PAIRS) == "confused_pairs.csv: 2 species pairs match"
    with pytest.raises(SystemExit, match="VERIFY FAIL: confused_pairs.csv"):
        mods.history.check_confused(str(tmp_path), [PAIRS[0], ("ceiba", "hura", 3, 10)])
    with pytest.raises(SystemExit, match="VERIFY FAIL: confused_pairs.csv"):
        mods.history.check_confused(str(tmp_path), PAIRS[:1])
