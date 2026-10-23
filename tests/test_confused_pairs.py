"""The most-confused species pairs on the model-health page.

    .venv/bin/pytest tests/test_confused_pairs.py
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import REPO, _on_path


@pytest.fixture(scope="session")
def mods():
    with _on_path(REPO / "dashboard"):
        import figures
        import history_panels
        yield SimpleNamespace(figures=figures, panels=history_panels)


def recs(*pairs):
    """One scored frame per (label, first guess)."""
    return [{"gt": gt, "ranked": [(guess, 0.9)]} for gt, guess in pairs]


SUPPORT = {"hura": 40, "ceiba": 10, "swartzia": 3}


def test_pairs_are_ordered_by_count_then_name_and_right_guesses_are_left_out(mods):
    frames = recs(*[("hura", "ceiba")] * 5, *[("ceiba", "hura")] * 2, *[("swartzia", "hura")] * 2,
                  *[("hura", "hura")] * 30)
    got = mods.figures._confused_pairs(frames, SUPPORT)
    assert got == [("hura", "ceiba", 5, 40), ("ceiba", "hura", 2, 10), ("swartzia", "hura", 2, 3)]


def test_only_the_top_fifteen_pairs_are_kept(mods):
    names = {f"sp{i:02d}": 5 for i in range(20)}
    frames = recs(*[(name, "other") for name in names])
    assert len(mods.figures._confused_pairs(frames, names)) == 15


def test_no_wrong_guess_gives_no_pairs_and_the_panel_says_so(mods):
    assert mods.figures._confused_pairs(recs(("hura", "hura")), SUPPORT) == []
    html = mods.panels.p_confused(SimpleNamespace(confused=[], n=1))
    assert "No first guess is wrong." in html


def test_the_panel_prints_each_pair_with_its_count_and_label_support(mods):
    frames = recs(*[("hura", "ceiba")] * 5, *[("hura", "hura")] * 35)
    c = SimpleNamespace(confused=mods.figures._confused_pairs(frames, SUPPORT), n=len(frames))
    html = mods.panels.p_confused(c)
    assert 'id="species-the-model-mixes-up"' in html
    assert "<td><i>hura</i></td>\n<td><i>ceiba</i></td>\n<td class=\"num\">5</td>\n<td class=\"num\">40</td>" in html
    assert "Counted over the 40 frames labelled to a species" in html
