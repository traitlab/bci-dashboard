"""The per-run manifest: one line per export, nothing appended on a rerun.

    .venv/bin/pytest tests/test_manifest.py
"""

from __future__ import annotations

import pytest
from conftest import REPO, _on_path


@pytest.fixture(scope="session")
def manifest():
    with _on_path(REPO / "dashboard"):
        import manifest
        yield manifest


def tables(root, counts, *, correct=70, n=100):
    root.mkdir()
    lines = ["species,n_labelled_frames"] + [f"{sp},{k}" for sp, k in counts.items()]
    (root / "per_species_health.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "held_out.csv").write_text(
        "population,n_frames,n_correct_top1,top1_accuracy\n"
        f"test,{n},{correct},{correct / n:.4f}\n", encoding="utf-8")
    return str(root)


def test_an_entry_carries_the_counts_the_change_log_needs(manifest, tmp_path):
    e = manifest.entry(tables(tmp_path / "t", {"a": 12, "b": 3}), run_date="2026-10-20",
                       export="2026-10-19", frames=20)
    assert (e["frames"], e["labelled"], e["species"]) == (20, 15, 2)
    assert (e["test_n"], e["test_correct"], e["test_top1"]) == (100, 70, 0.7)
    assert e["species_counts"] == {"a": 12, "b": 3}
    assert e["model_version"] and e["reference"] == "labelbox"
    # Tables older than confused_pairs.csv give a line that says so.
    assert e["confused_pairs"] is None


def test_an_entry_keeps_the_pair_counts_and_an_old_line_still_reads(manifest, tmp_path):
    import json
    d = tables(tmp_path / "t", {"a": 12, "b": 3})
    (tmp_path / "t" / "confused_pairs.csv").write_text(
        "label,first_guess,n_frames,n_label_frames\na,b,4,12\n", encoding="utf-8")
    e = manifest.entry(d, run_date="2026-10-20", export="2026-10-19", frames=20)
    assert e["confused_pairs"] == [["a", "b", 4]]
    path = tmp_path / "manifest.jsonl"
    old = {k: v for k, v in e.items() if k != "confused_pairs"}
    path.write_text(json.dumps(old) + "\n" + json.dumps(e) + "\n", encoding="utf-8")
    assert [x.get("confused_pairs") for x in manifest.read(str(path))] == [None, [["a", "b", 4]]]


def test_two_exports_give_two_lines_and_the_same_export_gives_one(manifest, tmp_path):
    path = str(tmp_path / "history" / "manifest.jsonl")
    first = manifest.entry(tables(tmp_path / "t1", {"a": 12}), run_date="2026-10-20",
                           export="2026-10-19", frames=12)
    second = manifest.entry(tables(tmp_path / "t2", {"a": 14}), run_date="2026-10-23",
                            export="2026-10-22", frames=14)
    assert manifest.append(path, first) is True
    assert manifest.append(path, first) is False
    assert manifest.append(path, second) is True
    assert manifest.append(path, {**second, "run_date": "2026-10-24"}) is False
    lines = manifest.read(path)
    assert [x["export"] for x in lines] == ["2026-10-19", "2026-10-22"]


def test_a_missing_manifest_reads_as_no_history(manifest, tmp_path):
    assert manifest.read(str(tmp_path / "none.jsonl")) == []


def test_tables_without_a_test_row_are_refused(manifest, tmp_path):
    d = tables(tmp_path / "t", {"a": 1})
    (tmp_path / "t" / "held_out.csv").write_text("population,n_frames,n_correct_top1,top1_accuracy\n")
    with pytest.raises(ValueError, match="no test row"):
        manifest.entry(d, run_date="2026-10-20", export="x", frames=1)


def _entry(manifest, tmp_path, name, export, count, **kw):
    return manifest.entry(tables(tmp_path / name, {"a": count}), run_date="2026-10-30",
                          export=export, frames=count, **kw)


def test_an_older_export_is_refused_so_the_delta_never_runs_backwards(manifest, tmp_path):
    path = str(tmp_path / "m.jsonl")
    manifest.append(path, _entry(manifest, tmp_path, "t1", "2026-10-22", 14))
    assert manifest.append(path, _entry(manifest, tmp_path, "t2", "2026-10-19", 12)) is False
    assert [x["export"] for x in manifest.read(path)] == ["2026-10-22"]


def test_the_same_export_with_new_numbers_replaces_only_the_newest_line(manifest, tmp_path):
    path = str(tmp_path / "m.jsonl")
    manifest.append(path, _entry(manifest, tmp_path, "t1", "2026-10-19", 12))
    manifest.append(path, _entry(manifest, tmp_path, "t2", "2026-10-22", 14))
    assert manifest.append(path, _entry(manifest, tmp_path, "t3", "2026-10-22", 15)) is True
    lines = manifest.read(path)
    assert [(x["export"], x["labelled"]) for x in lines] == [("2026-10-19", 12), ("2026-10-22", 15)]


def test_an_unreadable_line_is_skipped_with_a_warning(manifest, tmp_path, capsys):
    path = tmp_path / "m.jsonl"
    manifest.append(str(path), _entry(manifest, tmp_path, "t1", "2026-10-19", 12))
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"export": "2026-10-2\n{"export": "x"}\n')
    assert [x["export"] for x in manifest.read(str(path))] == ["2026-10-19"]
    out = capsys.readouterr().out
    assert "::warning::" in out and "line 2" in out and "line 3" in out
