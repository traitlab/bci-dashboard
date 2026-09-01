"""Direct tests for the prose panels in dashboard/explain.py.

`candidates_panel`, `weighting_panel` and `method_panel` are pure functions of
their arguments, so every test here calls them with hand-built records rather
than building a page or reading a snapshot.

    .venv/bin/pytest tests/test_explain.py
"""

from __future__ import annotations

import re

import pytest

# A string carrying all four HTML metacharacters a caller-text argument has to
# survive: the raw angle brackets and ampersand must never reach the output.
INJECT = '<script>&"</script>'


def _balanced(html):
    return html.count("<details") == html.count("</details>")


# --- band dicts and constants -----------------------------------------------

def test_band_dicts_share_the_same_keys(explain):
    assert set(explain.BAND_COLOR) == set(explain.BAND_WORD) == set(explain.BAND_SHORT)


def test_band_keys_match_core_support_buckets(explain, core):
    labels = {lab for _, _, lab in core.SUPPORT_BUCKETS}
    assert set(explain.BAND_COLOR) == labels


def test_band_color_values_are_hex_rrggbb(explain):
    for value in explain.BAND_COLOR.values():
        assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), value


def test_thin_max_is_below_fat_min(explain):
    assert explain.THIN_MAX < explain.FAT_MIN


def test_thin_max_and_fat_min_are_ints(explain):
    assert isinstance(explain.THIN_MAX, int)
    assert isinstance(explain.FAT_MIN, int)


# --- _near_miss --------------------------------------------------------------

def test_near_miss_of_a_wrong_guess_whose_right_answer_is_still_in_the_five(explain):
    recs = [{"gt": "sp1", "ranked": [("other", 0.9), ("sp1", 0.05)]}]
    wrong_n, share = explain._near_miss(recs)
    assert wrong_n == 1
    assert share == 1.0


def test_near_miss_of_a_wrong_guess_whose_right_answer_is_nowhere_in_the_five(explain):
    recs = [{"gt": "sp1", "ranked": [("other", 0.9), ("another", 0.05)]}]
    wrong_n, share = explain._near_miss(recs)
    assert wrong_n == 1
    assert share == 0.0


def test_near_miss_ignores_a_correct_first_guess(explain):
    recs = [{"gt": "sp1", "ranked": [("sp1", 0.9)]}]
    wrong_n, share = explain._near_miss(recs)
    assert wrong_n == 0
    assert share == 0.0


def test_near_miss_of_the_empty_list_is_zero_and_zero(explain):
    assert explain._near_miss([]) == (0, 0.0)


# --- candidates_panel ---------------------------------------------------------

def _candidates_recs():
    return [
        {"ranked": [("sp1", 0.6)]},
        {"ranked": [("sp2", 0.3), ("sp3", 0.2)]},
    ]


def test_candidates_panel_returns_a_balanced_string_with_the_given_numbers(explain):
    out = explain.candidates_panel(recs=_candidates_recs(), gen_n=7, gen_none=3)
    assert isinstance(out, str)
    assert _balanced(out)
    assert "7" in out
    assert "3" in out


def test_candidates_panel_names_the_longest_list_length_returned(explain):
    # top = max list length across recs, so a 1-guess and a 2-guess record
    # must report 2 as the cap, not the number of records.
    out = explain.candidates_panel(recs=_candidates_recs(), gen_n=0, gen_none=0)
    assert "2 guesses" in out


# --- weighting_panel -----------------------------------------------------------

def _weighting_kwargs(*, big_species="sp2"):
    support = {"sp1": 1, "sp2": 25}
    sp_recs = [
        {"gt": "sp1", "ranked": [("other", 0.9), ("sp1", 0.05)]},
        {"gt": "sp2", "ranked": [("sp2", 0.9)]},
    ]
    per_species = [
        {"species": "sp1", "n_labelled_crowns": 1, "top1_accuracy": 0.0},
        {"species": big_species, "n_labelled_crowns": 25, "top1_accuracy": 1.0},
    ]
    buckets = {
        "1": {"n_species": 1, "n_crowns": 1, "c1": 0},
        "25+": {"n_species": 1, "n_crowns": 1, "c1": 1},
    }
    now = {"micro_top1": 0.5, "macro_top1": 0.5}
    return {"per_species": per_species, "sp_recs": sp_recs, "support": support,
            "buckets": buckets, "now": now, "n": 2, "n_sp": 2,
            "corpus_block": "<p>dummy</p>"}


def test_weighting_panel_returns_a_balanced_string_with_the_given_numbers(explain):
    out = explain.weighting_panel(**_weighting_kwargs())
    assert isinstance(out, str)
    assert _balanced(out)
    assert "2" in out


def test_weighting_panel_escapes_the_biggest_species_name(explain):
    out = explain.weighting_panel(**_weighting_kwargs(big_species=INJECT))
    assert "<script>&" not in out
    assert "&lt;script&gt;" in out


def test_weighting_panel_raises_zero_division_when_no_species_is_well_sampled(explain):
    # well = [r for r in sp_recs if support[r["gt"]] >= WELL_SAMPLED_MIN_N (10)].
    # With every species under that threshold, `well` and `well_sp` are both
    # empty and `well_micro = sum(...) / len(well)` divides by zero. This is a
    # finding, not something this test works around: see the report.
    support = {"sp1": 1, "sp2": 4}
    sp_recs = [
        {"gt": "sp1", "ranked": [("sp1", 0.9)]},
        {"gt": "sp2", "ranked": [("sp2", 0.9)]},
    ]
    per_species = [
        {"species": "sp1", "n_labelled_crowns": 1, "top1_accuracy": 1.0},
        {"species": "sp2", "n_labelled_crowns": 4, "top1_accuracy": 1.0},
    ]
    now = {"micro_top1": 1.0, "macro_top1": 1.0}
    with pytest.raises(ZeroDivisionError):
        explain.weighting_panel(per_species=per_species, sp_recs=sp_recs, support=support,
                                buckets={}, now=now, n=2, n_sp=2, corpus_block="")


# --- method_panel --------------------------------------------------------------

def test_method_panel_returns_a_balanced_string_with_the_given_numbers(explain):
    out = explain.method_panel(tag="run-1", n=100, n_sp=12, n_cand=5, checks=["check a"])
    assert isinstance(out, str)
    assert _balanced(out)
    assert "100" in out
    assert "12" in out


def test_method_panel_renders_every_check_as_its_own_li(explain):
    out = explain.method_panel(tag="run-1", n=1, n_sp=1, n_cand=5, checks=["first check", "second check"])
    assert "<li>first check</li>" in out
    assert "<li>second check</li>" in out


def test_method_panel_escapes_a_check_containing_html(explain):
    out = explain.method_panel(tag="run-1", n=1, n_sp=1, n_cand=5, checks=[INJECT])
    assert "<script>&" not in out
    assert "&lt;script&gt;" in out


def test_method_panel_escapes_the_model_tag(explain):
    out = explain.method_panel(tag=INJECT, n=1, n_sp=1, n_cand=5, checks=[])
    assert "<script>&" not in out
    assert "&lt;script&gt;" in out
