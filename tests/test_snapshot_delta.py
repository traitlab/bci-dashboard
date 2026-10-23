"""The change log: what the last Labelbox export changed.

`dashboard/snapshot_delta.py` diffs the last two refresh-manifest lines and
`dashboard/history_panels.py` lays the diff out on the model-health page.

    .venv/bin/pytest tests/test_snapshot_delta.py
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import public_snapshot as fixture
import pytest
from conftest import REPO, _on_path


@pytest.fixture(scope="session")
def mods():
    with _on_path(REPO / "dashboard"):
        import history_panels
        import snapshot_delta
        yield SimpleNamespace(delta=snapshot_delta, panels=history_panels)


def line(export, counts, *, top1=0.7, n=100, version="2026-03-20 (7.5)", reference="labelbox",
         frames=None):
    return {"run_date": export, "export": export, "frames": frames or sum(counts.values()),
            "labelled": sum(counts.values()), "species": len(counts), "test_n": n,
            "test_correct": None if top1 is None else round(top1 * n), "test_top1": top1,
            "model_version": version, "reference": reference, "species_counts": counts}


A = line("2026-10-01", {"hura": 20, "ceiba": 5, "old": 2}, top1=0.70)
B = line("2026-10-08", {"hura": 25, "ceiba": 5, "swartzia": 3}, top1=0.75)


def test_the_diff_names_new_labels_new_species_and_moved_counts(mods):
    d = mods.delta.diff(A, B)
    assert d["new_labelled"] == 33 - 27
    assert d["new_species"] == [("swartzia", 3)]
    assert d["lost_species"] == ["old"]
    assert d["moved"] == [("hura", 20, 25), ("swartzia", 0, 3), ("old", 2, 0)]
    assert d["top1_delta"] == pytest.approx(0.05)
    assert d["crossed"] is None


def test_no_change_between_two_lines_moves_nothing(mods):
    d = mods.delta.diff(A, {**A, "export": "2026-10-08"})
    assert d["moved"] == [] and d["new_species"] == [] and d["new_labelled"] == 0
    assert d["top1_delta"] == 0


def test_a_reference_break_withholds_the_top1_delta(mods):
    d = mods.delta.diff(A, {**B, "reference": "publication_reviewed"})
    assert d["crossed"] == ("labelbox", "publication_reviewed")
    assert d["top1_delta"] is None


def test_history_keeps_the_last_eight_lines_newest_first(mods):
    lines = [line(f"2026-10-{i:02d}", {"hura": i}) for i in range(1, 12)]
    got = mods.delta.compute(lines)
    assert [r["export"] for r in got["runs"]] == [f"2026-10-{i:02d}" for i in range(11, 3, -1)]
    assert got["diff"]["cur"]["export"] == "2026-10-11"


def test_zero_and_one_line_have_no_diff(mods):
    assert mods.delta.compute([]) == {"runs": [], "diff": None}
    assert mods.delta.compute([A])["diff"] is None


def render(mods, lines, built="2026-10-22"):
    return mods.panels.p_changes(
        SimpleNamespace(changes=mods.delta.compute(lines), generated=built))


def test_the_panel_carries_each_rate_with_its_frame_count(mods):
    html = render(mods, [A, B])
    assert 'id="since-the-last-update"' in html
    assert "70.0% of 100 test frames" in html and "75.0% of 100 test frames" in html
    assert "+5.0 points" in html
    assert "New species: <i>swartzia</i> (3 frames)." in html
    assert "No longer labelled: <i>old</i>." in html
    assert html.index("<i>hura</i></td>") < html.index("<i>swartzia</i></td>")
    assert "—" not in html


def test_the_panel_without_history_says_so_plainly(mods):
    assert "No update has been recorded yet." in render(mods, [])
    one = render(mods, [A])
    assert "The first recorded update is the export of 2026-10-01" in one
    assert "Export 2026-10-01" not in one


def test_the_panel_caps_the_moved_table(mods):
    big = line("2026-10-08", {f"sp{i:02d}": 1 for i in range(20)})
    html = render(mods, [line("2026-10-01", {}), big])
    assert "And 5 more species moved." in html


@pytest.mark.parametrize("version, built, words", [
    ("2026-03-20 (7.5)", "2026-10-22", "7 months old"),
    ("2026-03-20 (7.5)", "2026-10-19", "6 months old"),
    ("2026-03-20 (7.5)", "2026-04-20", "1 month old"),
    ("2026-03-20 (7.5)", "2026-04-19", "under a month old"),
    ("2026-03-20 (7.5)", "2026-03-01", None),
    ("2026-03-20 (7.5)", "not a date", None),
    ("2026-03-20 (7.5)", "2026-10-22-test", "7 months old"),
    ("unknown", "2026-10-22", None),
])
def test_the_model_age_is_whole_months_on_the_build_date(mods, version, built, words):
    assert mods.delta.model_age_words(version, built) == words


def test_the_panel_states_the_model_date_and_age(mods):
    html = render(mods, [A])
    assert "20 March 2026 (release 7.5), 7 months old on the day this page was built" in html


def test_a_model_version_change_is_flagged_in_the_summary_and_the_history(mods):
    new = {**B, "model_version": "2026-10-01 (8.0)"}
    d = mods.delta.diff(A, new)
    assert d["version_changed"] == ("2026-03-20 (7.5)", "2026-10-01 (8.0)")
    html = render(mods, [A, new])
    assert ">changed</td>" in html
    assert html.count("(new model)") == 1
    assert "2026-10-01 (8.0) (new model)" in html
    same = render(mods, [A, B])
    assert ">same</td>" in same and "(new model)" not in same


@pytest.fixture(scope="module")
def synthetic_root(tmp_path_factory):
    root = fixture.write_inputs(tmp_path_factory.mktemp("delta-snapshot"))
    proc = fixture.measure(root)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return root


def test_the_model_health_page_prints_the_panel_from_the_manifest(synthetic_root):
    path = synthetic_root / "history" / "manifest.jsonl"
    path.parent.mkdir(exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in (A, B)), encoding="utf-8")
    proc = fixture.build(synthetic_root, "build_external.py", "model_health_dashboard.html")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html = (synthetic_root / "pages" / "model_health_dashboard.html").read_text(encoding="utf-8")
    assert "Since the last update" in html and "swartzia" in html
    # The old single line is gone, not printed beside the table.
    assert "Since the last snapshot" not in html
    path.unlink()
    proc = fixture.build(synthetic_root, "build_external.py", "model_health_dashboard.html")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html = (synthetic_root / "pages" / "model_health_dashboard.html").read_text(encoding="utf-8")
    assert "No update has been recorded yet." in html


def test_the_diff_is_between_the_two_newest_exports_whatever_the_file_order(mods):
    c = mods.delta.compute([B, A])
    assert c["diff"]["prev"] is A and c["diff"]["cur"] is B
    assert [r["export"] for r in c["runs"]] == ["2026-10-08", "2026-10-01"]


def test_the_model_note_gives_the_version_and_the_date_it_was_checked(mods):
    html = render(mods, [A, B])
    assert "still what the endpoint reported on" in html
    assert "changes when the recorded model version is updated" in html
    assert "A new model would show" not in html
