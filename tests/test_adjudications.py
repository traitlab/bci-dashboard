"""Adjudication carry: a confirmed label stops the frame reappearing.

A confident disagreement is either a label error or a model error. Once a
botanist has ruled the label correct, the prediction never changes, so the
review queue would raise the same frame on every build forever. These tests pin
the suppression, the things it must not suppress, and the invariant that both
producers of the queue apply it identically.

    .venv/bin/pytest tests/test_adjudications.py
"""

from __future__ import annotations

import csv

import pytest


def _write(path, rows, header=("global_key", "verdict", "adjudicated_by",
                               "adjudicated_on", "note")):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return str(path)


# ---------------- adjudicated_keys ----------------

def test_missing_file_is_an_empty_set_not_an_error(core, tmp_path):
    """A checkout without the file still builds, on the labelbox_urls terms."""
    assert core.adjudicated_keys(str(tmp_path / "nope.csv")) == set()


def test_header_only_file_is_an_empty_set(core, tmp_path):
    assert core.adjudicated_keys(_write(tmp_path / "a.csv", [])) == set()


def test_confirmed_label_is_carried(core, tmp_path):
    p = _write(tmp_path / "a.csv", [
        ["frame_a", core.LABEL_CONFIRMED, "AC", "2026-09-01", "checked in the field"],
    ])
    assert core.adjudicated_keys(p) == {"frame_a"}


def test_other_verdicts_are_ignored_rather_than_rejected(core, tmp_path):
    """The file may record a ruling the queue does not act on."""
    p = _write(tmp_path / "a.csv", [
        ["frame_a", core.LABEL_CONFIRMED, "AC", "2026-09-01", ""],
        ["frame_b", "label_wrong_prediction_right", "AC", "2026-09-01", "fixed in Labelbox"],
        ["frame_c", "unresolved", "AC", "2026-09-01", "needs a second botanist"],
    ])
    assert core.adjudicated_keys(p) == {"frame_a"}


def test_a_row_with_no_global_key_is_skipped(core, tmp_path):
    p = _write(tmp_path / "a.csv", [["", core.LABEL_CONFIRMED, "AC", "2026-09-01", ""]])
    assert core.adjudicated_keys(p) == set()


def test_a_verdict_is_matched_exactly_not_by_prefix(core, tmp_path):
    p = _write(tmp_path / "a.csv", [
        ["frame_a", core.LABEL_CONFIRMED + "_maybe", "AC", "2026-09-01", ""],
    ])
    assert core.adjudicated_keys(p) == set()


def test_duplicate_rows_for_one_frame_collapse(core, tmp_path):
    p = _write(tmp_path / "a.csv", [
        ["frame_a", core.LABEL_CONFIRMED, "AC", "2026-09-01", ""],
        ["frame_a", core.LABEL_CONFIRMED, "EL", "2026-09-02", "same call"],
    ])
    assert core.adjudicated_keys(p) == {"frame_a"}


# ---------------- the shipped file ----------------

def test_the_tracked_file_has_the_documented_header(core):
    """The schema metrics.md documents, pinned so a silent rename fails here."""
    with open(core.ADJUDICATIONS_CSV, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == ["global_key", "verdict", "adjudicated_by", "adjudicated_on", "note"]


def test_every_verdict_in_the_tracked_file_is_one_of_the_known_words(core):
    """Catches a typo that would silently fail to suppress a frame."""
    known = {core.LABEL_CONFIRMED, "label_wrong_prediction_right", "unresolved"}
    unknown = {r["verdict"] for r in core.read_csv_rows(core.ADJUDICATIONS_CSV)} - known
    assert not unknown, f"unknown verdicts: {sorted(unknown)}"


# ---------------- the invariant between the two producers ----------------

def _recs():
    """Three confident frames: one agreeing, two disagreeing."""
    return [
        {"global_key": "agree", "split": "train", "gt": "cecropia insignis",
         "ranked": [("cecropia insignis", 0.95)]},
        {"global_key": "raised", "split": "train", "gt": "ficus insipida",
         "ranked": [("ficus yoponensis", 0.91)]},
        {"global_key": "ruled", "split": "test", "gt": "apeiba membranacea",
         "ranked": [("luehea seemannii", 0.88)]},
    ]


def _measure_side(core, recs, adjudicated):
    """The filter measure.py applies when writing label_review_queue.csv."""
    raised = [r for r in recs
              if r["ranked"][0][0] != r["gt"] and r["ranked"][0][1] >= core.REVIEW_CONF]
    return [r for r in raised if r["global_key"] not in adjudicated], len(raised)


def _panels_side(core, recs, adjudicated):
    """The filter panels.py applies when building the page."""
    confident = [r for r in recs if r["ranked"][0][1] >= core.REVIEW_CONF]
    raised = [r for r in confident if r["ranked"][0][0] != r["gt"]]
    return [r for r in raised if r["global_key"] not in adjudicated], len(raised)


@pytest.mark.parametrize("adjudicated", [set(), {"ruled"}, {"ruled", "raised"}])
def test_both_producers_of_the_queue_agree(core, adjudicated):
    """verify_snapshot aborts the build if these two ever disagree.

    history.verify_snapshot compares the page's review_counts against the rows
    in label_review_queue.csv, so a filter applied on one side only is a hard
    build failure, not a quiet drift. This asserts the agreement directly.
    """
    m_rows, m_raised = _measure_side(core, _recs(), adjudicated)
    p_rows, p_raised = _panels_side(core, _recs(), adjudicated)
    assert [r["global_key"] for r in m_rows] == [r["global_key"] for r in p_rows]
    assert m_raised == p_raised


def test_an_adjudicated_frame_leaves_the_queue(core):
    rows, raised = _measure_side(core, _recs(), {"ruled"})
    assert [r["global_key"] for r in rows] == ["raised"]
    assert raised == 2


def test_an_adjudicated_frame_still_counts_as_a_model_miss(core):
    """It must not silently improve the confident-first-guess accuracy claim."""
    recs = _recs()
    confident = [r for r in recs if r["ranked"][0][1] >= core.REVIEW_CONF]
    _, raised_with = _panels_side(core, recs, {"ruled"})
    _, raised_without = _panels_side(core, recs, set())
    assert raised_with == raised_without
    assert (len(confident) - raised_with) / len(confident) == pytest.approx(1 / 3)


def test_adjudicating_a_frame_the_queue_never_raised_changes_nothing(core):
    """A ruling on an agreeing frame is inert, not a way to hide a hit."""
    rows, raised = _measure_side(core, _recs(), {"agree"})
    assert [r["global_key"] for r in rows] == ["raised", "ruled"]
    assert raised == 2
