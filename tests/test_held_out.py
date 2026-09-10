"""Top-1 on the test frames from flights the train set never saw.

`tests/test_split_blocking.py` pins that every test frame today shares a
flight with a train frame, so the test score is a floor. `dashboard/held_out.py`
measures the number that is not: top-1 on the test frames whose flight (one
date, one site) has no train frame at all. Today that population is empty and
the page says so; the day it is not, the page prints the rate beside the
overall one.

    .venv/bin/pytest tests/test_held_out.py
"""

from __future__ import annotations

import csv
import json
import re

import pytest

from conftest import REPO, _on_path


@pytest.fixture(scope="session")
def held_out():
    with _on_path(REPO / "dashboard"):
        import held_out
        yield held_out


def rec(key, split, gt, guess):
    return {"global_key": key, "split": split, "gt": gt, "ranked": [(guess, 0.9)]}


# Two flights: A has train and test frames, B has test frames only.
FLIGHTS = {"t1": ("20260101", "sitea"), "t2": ("20260101", "sitea"),
           "e1": ("20260101", "sitea"), "e2": ("20260102", "siteb"),
           "e3": ("20260102", "siteb")}
RECS = [rec("t1", "train", "x", "x"), rec("t2", "train", "y", "x"),
        rec("e1", "test", "x", "x"), rec("e2", "test", "y", "y"),
        rec("e3", "test", "y", "x")]


def test_the_flight_is_read_out_of_the_mission_folder(held_out):
    url = ("https://object-arbutus.cloud.computecanada.ca/20260114_bciarmour_wptne01_m3e/"
           "DJI_202601141304_014_bciarmour-wptne1/DJI_20260114132256_0037_V_2158zoom.JPG")
    assert held_out.flight_of(url) == ("20260114", "bciarmour")
    assert held_out.flight_of("https://x/no_mission_here.JPG") is None
    assert held_out.flight_of("") is None


def test_the_inventory_loader_keeps_only_rows_with_a_key_and_a_flight(held_out, tmp_path):
    p = tmp_path / "rows.jsonl"
    rows = [{"global_key": "a", "row_data": "https://h/20260101_sitea_wp1_m3e/f.JPG"},
            {"global_key": "b", "row_data": "https://h/plain/f.JPG"},
            {"row_data": "https://h/20260101_sitea_wp1_m3e/g.JPG"}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert held_out.load_flights(str(p)) == {"a": ("20260101", "sitea")}


def test_unseen_flight_frames_are_the_test_frames_with_no_train_frame_on_their_flight(held_out):
    got = held_out.measure(RECS, FLIGHTS)
    assert got["test"] == {"n": 3, "correct": 2, "top1": pytest.approx(2 / 3)}
    assert got["unseen"] == {"n": 2, "correct": 1, "top1": pytest.approx(0.5)}
    assert got["unplaced"] == 0


def test_when_every_test_flight_has_a_train_frame_the_unseen_count_is_zero(held_out):
    flights = {k: ("20260101", "sitea") for k in FLIGHTS}
    got = held_out.measure(RECS, flights)
    assert got["unseen"] == {"n": 0, "correct": 0, "top1": None}
    assert got["test"]["n"] == 3


def test_a_test_frame_with_no_flight_is_counted_and_left_out_of_the_unseen_rate(held_out):
    flights = dict(FLIGHTS)
    del flights["e2"]
    got = held_out.measure(RECS, flights)
    assert got["unplaced"] == 1
    assert got["unseen"] == {"n": 1, "correct": 0, "top1": 0.0}
    # Still graded in the overall test rate: the split put it there.
    assert got["test"]["n"] == 3


def test_a_train_frame_with_no_flight_cannot_vouch_for_any_flight(held_out):
    """Without the train frame's flight nothing says which test flight it
    shares, so the flight it was on reads as unseen. Counted separately, so
    the page can say how many train frames are in that state."""
    flights = dict(FLIGHTS)
    del flights["t1"]
    del flights["t2"]
    got = held_out.measure(RECS, flights)
    assert got["unseen"]["n"] == 3
    assert got["unplaced_train"] == 2


def test_no_test_frames_gives_no_rate_not_a_crash(held_out):
    got = held_out.measure([rec("t1", "train", "x", "x")], FLIGHTS)
    assert got["test"] == {"n": 0, "correct": 0, "top1": None}
    assert got["unseen"]["n"] == 0


def test_the_csv_carries_one_row_per_population(held_out, tmp_path):
    held_out.write_held_out(str(tmp_path), held_out.measure(RECS, FLIGHTS))
    rows = list(csv.DictReader((tmp_path / "held_out.csv").open(encoding="utf-8")))
    by = {r["population"]: r for r in rows}
    assert set(by) == {"test", "test_unseen_flight", "test_unplaced"}
    assert by["test"]["n_frames"] == "3" and by["test"]["n_correct_top1"] == "2"
    assert by["test"]["top1_accuracy"] == "0.6667"
    assert by["test_unseen_flight"]["n_frames"] == "2"
    assert by["test_unplaced"] == {"population": "test_unplaced", "n_frames": "0",
                                   "n_correct_top1": "", "top1_accuracy": ""}


def test_the_snapshot_check_passes_on_its_own_file_and_names_a_moved_count(
        held_out, history, tmp_path):
    got = held_out.measure(RECS, FLIGHTS)
    held_out.write_held_out(str(tmp_path), got)
    assert "held_out.csv" in history.check_held_out(str(tmp_path), got)
    moved = dict(got, test={"n": 4, "correct": 2, "top1": 0.5})
    with pytest.raises(SystemExit, match="held_out.csv"):
        history.check_held_out(str(tmp_path), moved)


def test_a_snapshot_without_the_file_is_skipped_with_a_line_saying_so(held_out, history, tmp_path):
    """Snapshots from before this file existed must still rebuild."""
    line = history.check_held_out(str(tmp_path), held_out.measure(RECS, FLIGHTS))
    assert "held_out.csv" in line and "skipped" in line


# ---------------- the page ----------------

TEST_LINE = re.compile(
    r"first guess is right on ([0-9.]+)% of the ([0-9,]+) test frames")
UNPLACED = re.compile(r"([0-9,]+) test frames? could not be placed on a flight")


def _held_out_csv():
    from conftest import SNAPSHOT_DIR
    with open(SNAPSHOT_DIR / "held_out.csv", encoding="utf-8") as fh:
        return {r["population"]: r for r in csv.DictReader(fh)}


def test_the_page_prints_the_numbers_the_csv_holds(external_page):
    html, _ = external_page
    by = _held_out_csv()
    m = TEST_LINE.search(html)
    assert m, "the species panel prints no held-out line"
    assert int(m.group(2).replace(",", "")) == int(by["test"]["n_frames"])
    assert abs(float(m.group(1)) - 100 * float(by["test"]["top1_accuracy"])) < 0.06
    n_unseen = int(by["test_unseen_flight"]["n_frames"])
    if n_unseen == 0:
        assert "no test frame comes from a flight the labels never saw" in html
    else:
        assert re.search(rf"the {n_unseen:,} test frames from flights with no train", html)
    n_unplaced = int(by["test_unplaced"]["n_frames"])
    if n_unplaced == 0:
        assert "Every test frame could be placed on a flight" in html
    else:
        m = UNPLACED.search(html)
        assert m and int(m.group(1).replace(",", "")) == n_unplaced


def test_the_page_says_what_a_gap_would_mean(external_page):
    html, _ = external_page
    assert "A large gap" in html
