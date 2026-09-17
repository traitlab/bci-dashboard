"""The one line that says whether a labelling round moved the numbers.

`dashboard/snapshot_delta.py` finds the newest `model-health-<date>/` folder
dated before the page's build date and reports two things then and now: the
species with at least `figures.WAIT_SUPPORT_MIN` labelled frames, and the
overall test top-1 when the older snapshot recorded one.

    .venv/bin/pytest tests/test_snapshot_delta.py
"""

from __future__ import annotations

import pytest

from conftest import REPO, _on_path


@pytest.fixture(scope="session")
def snapshot_delta():
    with _on_path(REPO / "dashboard"):
        import snapshot_delta
        yield snapshot_delta


def snapshot(root, date, counts, *, column="n_labelled_frames", held_out=None):
    d = root / f"model-health-{date}"
    d.mkdir()
    lines = [f"species,{column},top1_accuracy"]
    lines += [f"sp{i},{n},0.5" for i, n in enumerate(counts)]
    (d / "per_species_health.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if held_out is not None:
        n, correct = held_out
        (d / "held_out.csv").write_text(
            "population,n_frames,n_correct_top1,top1_accuracy\n"
            f"test,{n},{correct},{correct / n:.4f}\n"
            "test_unseen_flight,0,0,\ntest_unplaced,0,,\n", encoding="utf-8")
    return d


NOW = {"n_species_floor": 12, "test_n": 200, "test_top1": 0.8}


def test_the_newest_snapshot_before_the_build_date_is_the_one_compared(snapshot_delta, tmp_path):
    for date in ("2026-08-03", "2026-08-27", "2026-09-10", "2026-09-12"):
        snapshot(tmp_path, date, [1])
    assert snapshot_delta.previous_snapshot(str(tmp_path), "2026-09-10").endswith("2026-08-27")
    assert snapshot_delta.previous_snapshot(str(tmp_path), "2026-08-25-test").endswith("2026-08-03")
    assert snapshot_delta.previous_snapshot(str(tmp_path), "2026-08-03") is None


def test_a_folder_that_is_not_a_snapshot_is_ignored(snapshot_delta, tmp_path):
    (tmp_path / "model-health-latest").mkdir()
    (tmp_path / "notes").mkdir()
    assert snapshot_delta.previous_snapshot(str(tmp_path), "2026-09-10") is None


def test_the_first_snapshot_says_so(snapshot_delta, tmp_path):
    d = snapshot_delta.compute(NOW, str(tmp_path), "2026-09-10", floor=10)
    assert d["previous"] is None
    note = snapshot_delta.note(d, floor=10)
    assert "first snapshot" in note
    assert "12 species" in note


def test_species_at_the_floor_then_and_now(snapshot_delta, tmp_path):
    snapshot(tmp_path, "2026-08-27", [9, 10, 25, 3])
    d = snapshot_delta.compute(NOW, str(tmp_path), "2026-09-10", floor=10)
    assert d["previous"] == "2026-08-27"
    assert d["then"]["n_species_floor"] == 2
    assert d["now"]["n_species_floor"] == 12
    note = snapshot_delta.note(d, floor=10)
    assert "2026-08-27" in note and "2 species" in note and "12 species" in note


def test_an_older_snapshot_counts_its_frames_under_the_old_column_name(snapshot_delta, tmp_path):
    """Snapshots up to 2026-08-27 call the column n_labelled_crowns."""
    snapshot(tmp_path, "2026-08-27", [10, 10, 1], column="n_labelled_crowns")
    d = snapshot_delta.compute(NOW, str(tmp_path), "2026-09-10", floor=10)
    assert d["then"]["n_species_floor"] == 2


def test_test_top1_is_reported_only_when_the_older_snapshot_recorded_it(snapshot_delta, tmp_path):
    snapshot(tmp_path, "2026-08-27", [10])
    d = snapshot_delta.compute(NOW, str(tmp_path), "2026-09-10", floor=10)
    assert d["then"]["test_top1"] is None
    assert "not recorded" in snapshot_delta.note(d, floor=10)

    snapshot(tmp_path, "2026-09-01", [10], held_out=(100, 70))
    d = snapshot_delta.compute(NOW, str(tmp_path), "2026-09-10", floor=10)
    assert d["then"]["test_n"] == 100
    assert d["then"]["test_top1"] == pytest.approx(0.7)
    note = snapshot_delta.note(d, floor=10)
    assert "70.0%" in note and "80.0%" in note and "n = 100" in note and "n = 200" in note


def test_an_unchanged_count_with_no_recorded_top1_says_nothing_moved(snapshot_delta, tmp_path):
    """The count is the same then and now, and there is no top-1 to compare, so
    the note used to restate the same number twice and name an absent one. One
    clause instead."""
    snapshot(tmp_path, "2026-08-27", [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10])
    d = snapshot_delta.compute(NOW, str(tmp_path), "2026-09-10", floor=10)
    assert d["then"]["n_species_floor"] == 12
    assert d["then"]["test_top1"] is None
    note = snapshot_delta.note(d, floor=10)
    assert note == ('<p class="note"><b>Since the last snapshot:</b> nothing has moved '
                     'since 2026-08-27, the date the counts were last saved.</p>')


def test_a_build_date_that_is_not_a_date_compares_against_nothing(snapshot_delta, tmp_path):
    snapshot(tmp_path, "2026-08-27", [10])
    d = snapshot_delta.compute(NOW, str(tmp_path), "today", floor=10)
    assert d["previous"] is None
    assert "not a date" in snapshot_delta.note(d, floor=10)


def test_the_page_prints_the_line_in_the_frame_counts_panel(external_page):
    """Beside the three frame counts, where the Chao1 line already sits."""
    html, _ = external_page
    assert html.index("Why three different frame counts") < html.index("Since the last snapshot")
