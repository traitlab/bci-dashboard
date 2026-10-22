"""The per-run manifest: one line per export, nothing appended on a rerun.

    .venv/bin/pytest tests/test_manifest.py
"""

from __future__ import annotations

import json

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
    lines = [json.loads(x) for x in open(path, encoding="utf-8")]
    assert [x["export"] for x in lines] == ["2026-10-19", "2026-10-22"]


def test_a_missing_manifest_reads_as_no_history(manifest, tmp_path):
    assert manifest.read(str(tmp_path / "none.jsonl")) == []


def test_tables_without_a_test_row_are_refused(manifest, tmp_path):
    d = tables(tmp_path / "t", {"a": 1})
    (tmp_path / "t" / "held_out.csv").write_text("population,n_frames,n_correct_top1,top1_accuracy\n")
    with pytest.raises(ValueError, match="no test row"):
        manifest.entry(d, run_date="2026-10-20", export="x", frames=1)
