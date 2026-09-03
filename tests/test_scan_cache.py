"""Reading the cache directory, and turning frames into the species table.

`scan_cache` is the only reader of the whole cache directory, and the three
counts it returns are the ones the run log prints as invariants: how many
entries carry a coverage that differs from the score, how many lists are not in
descending order, and how long the longest list is. `figures.prepare` aborts a
build on that last one. `aggregate_per_species` turns the scored frames into
every row of the species table on the model-health page.

Both were reachable only through `load_health`, which needs a real cache
directory, a labels CSV and a splits CSV, so neither had a test of its own.

    .venv/bin/pytest tests/test_scan_cache.py
"""

from __future__ import annotations

import json

import pytest


def _entry(binomial, score, *, coverage=None, name=""):
    """One species entry in the shape the fetch writes: `binomial` is the name
    every page reads, `coverage` and `max_score` are two fields Pl@ntNet returns
    that should agree, and `name` is a vernacular that is usually blank."""
    return {"binomial": binomial, "name": name, "count": 1,
            "coverage": score if coverage is None else coverage,
            "max_score": score, "location": []}


def _cache(tmp_path, files):
    """files: {stem: [entry, ...] or raw text}."""
    for stem, sp in files.items():
        p = tmp_path / f"{stem}.json"
        p.write_text(sp if isinstance(sp, str)
                     else json.dumps({"results": {"species": sp}}), encoding="utf-8")
    return str(tmp_path)


# ---------------------------------------------------------------------------
# scan_cache: what it returns per photo
# ---------------------------------------------------------------------------

def test_the_key_is_the_file_stem_because_that_is_what_the_labels_join_on(health, tmp_path):
    # load_health strips GT_KEY_PREFIX off a label's global_key and looks the
    # rest up here, so the ".json" must be gone and nothing else with it.
    scan = health.scan_cache(_cache(tmp_path, {"DJI_0001_V_12zoom.JPG": [_entry("Ficus insipida", 0.9)]}))
    assert list(scan.predictions) == ["DJI_0001_V_12zoom.JPG"]


def test_only_json_files_are_read(health, tmp_path):
    _cache(tmp_path, {"a": [_entry("Ficus insipida", 0.9)]})
    (tmp_path / "notes.txt").write_text("not a response", encoding="utf-8")
    (tmp_path / "a.json.tmp").write_text("half a write", encoding="utf-8")
    scan = health.scan_cache(str(tmp_path))
    assert scan.files == ["a.json"]


def test_a_ranked_list_is_pairs_of_name_and_score(health, tmp_path):
    scan = health.scan_cache(_cache(tmp_path, {"a": [
        _entry("Ficus insipida", 0.9), _entry("Luehea seemannii", 0.4)]}))
    assert scan.predictions["a"] == [("Ficus insipida", 0.9), ("Luehea seemannii", 0.4)]


def test_an_entry_with_no_binomial_is_dropped_from_the_list(health, tmp_path):
    # Pl@ntNet returns a genus-only hit with an empty binomial. Nothing on
    # either page can score it, so it must not take a place in the list.
    scan = health.scan_cache(_cache(tmp_path, {"a": [
        _entry("Ficus insipida", 0.9), _entry("", 0.4, name="a vernacular")]}))
    assert scan.predictions["a"] == [("Ficus insipida", 0.9)]
    assert scan.length_hist == {1: 1}


def test_a_missing_score_reads_as_zero_rather_than_aborting(health, tmp_path):
    scan = health.scan_cache(_cache(tmp_path, {"a": [{"binomial": "Ficus insipida"}]}))
    assert scan.predictions["a"] == [("Ficus insipida", 0.0)]


def test_a_photo_with_no_species_is_an_empty_list_not_a_missing_key(health, tmp_path):
    # The queue page counts these as "got no answer at all", which it can only
    # do if the photo is present with nothing in it.
    scan = health.scan_cache(_cache(tmp_path, {"a": []}))
    assert scan.predictions == {"a": []}
    assert scan.length_hist == {0: 1}


def test_an_unreadable_file_is_counted_and_still_yields_a_photo(health, tmp_path):
    scan = health.scan_cache(_cache(tmp_path, {"a": '{"results": {"spec'}))
    assert scan.status_count == {"unreadable": 1}
    assert scan.predictions == {"a": []}


def test_the_status_count_separates_clean_salvaged_and_unreadable(health, tmp_path):
    scan = health.scan_cache(_cache(tmp_path, {
        "clean": [_entry("Ficus insipida", 0.9)],
        "trailing": json.dumps({"results": {"species": [_entry("Luehea seemannii", 0.5)]}}) + "\n{",
        "broken": "not json at all",
    }))
    assert scan.status_count == {"ok": 1, "salvaged": 1, "unreadable": 1}
    assert scan.predictions["trailing"] == [("Luehea seemannii", 0.5)]


# ---------------------------------------------------------------------------
# scan_cache: the three invariants the run log prints
# ---------------------------------------------------------------------------

def test_coverage_matching_the_score_is_the_expected_case(health, tmp_path):
    scan = health.scan_cache(_cache(tmp_path, {"a": [_entry("Ficus insipida", 0.9)]}))
    assert (scan.n_entries, scan.n_cov_ne_score) == (1, 0)


def test_a_coverage_that_differs_from_the_score_is_counted(health, tmp_path):
    scan = health.scan_cache(_cache(tmp_path, {
        "a": [_entry("Ficus insipida", 0.9, coverage=0.5)]}))
    assert scan.n_cov_ne_score == 1


def test_an_entry_with_no_binomial_still_counts_toward_the_invariants(health, tmp_path):
    # The invariants describe what the fetch wrote, not what the pages score,
    # so a dropped entry with a mismatched coverage must still be visible.
    scan = health.scan_cache(_cache(tmp_path, {"a": [_entry("", 0.9, coverage=0.5)]}))
    assert (scan.n_entries, scan.n_cov_ne_score) == (1, 1)


def test_a_descending_list_is_not_counted_as_unsorted(health, tmp_path):
    scan = health.scan_cache(_cache(tmp_path, {"a": [
        _entry("A a", 0.9), _entry("B b", 0.9), _entry("C c", 0.1)]}))
    assert scan.n_unsorted == 0


def test_a_list_that_rises_is_counted_once_per_step_that_rises(health, tmp_path):
    scan = health.scan_cache(_cache(tmp_path, {"a": [
        _entry("A a", 0.1), _entry("B b", 0.9), _entry("C c", 0.95)]}))
    assert scan.n_unsorted == 2


def test_the_sort_check_tolerates_float_noise(health, tmp_path):
    # Scores arrive as decimal text and come back as binary floats, so two
    # values that are equal in the payload can differ in the last bit. Only a
    # real rise is a defect.
    scan = health.scan_cache(_cache(tmp_path, {"a": [
        _entry("A a", 0.3), _entry("B b", 0.1 + 0.2)]}))
    assert scan.n_unsorted == 0


def test_maxk_is_the_longest_list_in_the_directory(health, tmp_path):
    # figures.prepare aborts a build when this exceeds N_CANDIDATES, so it has
    # to be the longest list, not the most common one.
    scan = health.scan_cache(_cache(tmp_path, {
        "a": [_entry("A a", 0.9)],
        "b": [_entry("A a", 0.9), _entry("B b", 0.8)],
        "c": [_entry("A a", 0.9)],
    }))
    assert scan.maxk == 2
    assert scan.length_hist == {1: 2, 2: 1}


def test_the_vocabulary_is_normalized_and_counts_every_appearance(health, tmp_path, core):
    scan = health.scan_cache(_cache(tmp_path, {
        "a": [_entry("Ficus insipida", 0.9)],
        "b": [_entry("Ficus insipida", 0.4)],
    }))
    assert scan.corpus_vocab == {core.normalize("Ficus insipida"): 2}


def test_an_empty_cache_directory_aborts_with_something_a_reader_can_act_on(health, tmp_path):
    # Every count here is over the files found. With none, `maxk` has no
    # largest list to report, and the alternative to this message is a bare
    # ValueError from max() four call sites away from the empty directory.
    with pytest.raises(SystemExit, match="No cached Pl@ntNet answers"):
        health.scan_cache(str(tmp_path))


# ---------------------------------------------------------------------------
# aggregate_per_species: every row of the species table
# ---------------------------------------------------------------------------

def _rec(gt, ranked, *, gt_raw=None):
    return {"gt": gt, "gt_raw": gt_raw or gt, "ranked": ranked}


def test_the_first_guess_is_the_head_of_the_list(health):
    rows = health.aggregate_per_species(
        [_rec("ficus insipida", [("ficus insipida", 0.9), ("luehea seemannii", 0.1)])],
        set(), set())
    assert (rows[0]["n_correct_top1"], rows[0]["top1_accuracy"]) == (1, 1.0)


def test_the_right_name_further_down_is_not_a_right_first_guess(health):
    rows = health.aggregate_per_species(
        [_rec("ficus insipida", [("luehea seemannii", 0.9), ("ficus insipida", 0.1)])],
        set(), set())
    assert rows[0]["n_correct_top1"] == 0
    assert rows[0]["n_correct_top5"] == 1


def test_the_list_is_cut_at_the_length_the_pages_state(health, core):
    # Past N_CANDIDATES the name does not count, whatever the cache holds.
    n = core.N_CANDIDATES
    inside = [("wrong sp", 0.9)] * (n - 1) + [("ficus insipida", 0.1)]
    outside = [("wrong sp", 0.9)] * n + [("ficus insipida", 0.1)]
    assert health.aggregate_per_species([_rec("ficus insipida", inside)], set(), set())[0]["n_correct_top5"] == 1
    assert health.aggregate_per_species([_rec("ficus insipida", outside)], set(), set())[0]["n_correct_top5"] == 0


def test_the_mean_confidence_is_over_every_frame_and_the_other_over_the_right_ones(health):
    rows = health.aggregate_per_species([
        _rec("ficus insipida", [("ficus insipida", 0.8)]),
        _rec("ficus insipida", [("luehea seemannii", 0.4)]),
    ], set(), set())
    assert rows[0]["mean_top1_confidence"] == pytest.approx(0.6)
    assert rows[0]["mean_top1_confidence_when_correct"] == pytest.approx(0.8)


def test_a_species_never_guessed_right_has_no_confidence_when_correct(health):
    # None, not zero: the table prints an em-rule for "no such frame", and a
    # zero would read as a confident model that is confidently wrong.
    rows = health.aggregate_per_species(
        [_rec("ficus insipida", [("luehea seemannii", 0.4)])], set(), set())
    assert rows[0]["mean_top1_confidence_when_correct"] is None


def test_every_raw_label_behind_a_row_is_listed_once_in_order(health):
    # The canonical name is the row; the raw labels are what a botanist typed,
    # and the table shows them so a reader can see what was merged into it.
    rows = health.aggregate_per_species([
        _rec("pachira quinata", [("pachira quinata", 0.9)], gt_raw="Bombacopsis quinata"),
        _rec("pachira quinata", [("pachira quinata", 0.9)], gt_raw="Pachira quinata"),
        _rec("pachira quinata", [("pachira quinata", 0.9)], gt_raw="Bombacopsis quinata"),
    ], set(), set())
    assert rows[0]["gt_raw_labels"] == "Bombacopsis quinata|Pachira quinata"


def test_a_species_is_in_the_vocabulary_under_either_spelling(health):
    # corpus_norm is what the cache returned; corpus_canon is the same list put
    # through the crosswalk. A label matching either was a name the model could
    # have said, and the ceiling panel counts on that.
    rec = [_rec("pachira quinata", [("luehea seemannii", 0.9)])]
    assert health.aggregate_per_species(rec, {"pachira quinata"}, set())[0]["in_corpus_vocabulary"]
    assert health.aggregate_per_species(rec, set(), {"pachira quinata"})[0]["in_corpus_vocabulary"]
    assert not health.aggregate_per_species(rec, set(), set())[0]["in_corpus_vocabulary"]


def test_the_support_bucket_is_the_one_core_assigns(health, core):
    rows = health.aggregate_per_species(
        [_rec("ficus insipida", [("ficus insipida", 0.9)])] * 3, set(), set())
    assert rows[0]["n_labelled_frames"] == 3
    assert rows[0]["support_bucket"] == core.bucket_label(3)


def test_the_table_is_ordered_by_label_count_then_by_name(health):
    # The reader's first question is which species has enough labels to judge,
    # so the most-labelled row leads. Ties break alphabetically, which is what
    # keeps a rebuild from reshuffling rows that did not change.
    rows = health.aggregate_per_species(
        [_rec("b b", [("b b", 0.9)])] * 2
        + [_rec("a a", [("a a", 0.9)])]
        + [_rec("c c", [("c c", 0.9)])], set(), set())
    assert [r["species"] for r in rows] == ["b b", "a a", "c c"]
