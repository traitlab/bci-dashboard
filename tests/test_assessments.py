"""What the pages say off ``data/model_health/``, and when they refuse to.

`labelling/assess_species.py` runs labelfirst and speciesfirst in their own
virtualenv and writes four JSON files. `dashboard/assessments.py` is the only
reader, and the external page refuses to build when a file is missing or was
computed from a ground truth other than today's. These tests write small files
under tmp_path and never run the library.

    .venv/bin/pytest tests/test_assessments.py
"""

from __future__ import annotations

import csv
import json
import pathlib
import re
from collections import Counter

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
GT_SHA = "a" * 64
EMB_SHA = "b" * 64


def doc(*, gt_sha=GT_SHA, emb_sha=EMB_SHA, **fields):
    d = {"kind": "transductive", "inputs": {"gt_sha256": gt_sha},
         "library": {"speciesfirst": "0.1.0"}}
    if emb_sha:
        d["inputs"]["embeddings_sha256"] = emb_sha
    return {**d, **fields}


def transductive(n_seeds=8, **per_species):
    return doc(population={"n_frames": 100, "n_species": len(per_species),
                           "n_seeds": n_seeds},
               summary=Counter(v["limit"] for v in per_species.values()),
               method={"k": 5}, per_species=per_species)


def species(limit, n_frames, agreeing=8):
    return {"limit": limit, "n_frames": n_frames, "seeds_agreeing": agreeing}


# ---------------------------------------------------------------------------
# refusing: missing or stale
# ---------------------------------------------------------------------------

def test_a_missing_file_is_a_complaint_that_names_the_fix(assessments):
    msg = assessments.complaint("x.json", None, gt_sha=GT_SHA)
    assert "x.json is missing" in msg
    assert "assess_species.py" in msg


def test_a_file_from_another_ground_truth_is_stale(assessments):
    msg = assessments.complaint("x.json", doc(gt_sha="0" * 64), gt_sha=GT_SHA)
    assert "stale" in msg and "ground truth" in msg


def test_a_file_from_another_embedding_file_is_stale(assessments):
    msg = assessments.complaint("x.json", doc(emb_sha="0" * 64), gt_sha=GT_SHA,
                                embeddings_sha=EMB_SHA)
    assert "stale" in msg and "embedding" in msg


def test_a_current_file_is_no_complaint(assessments):
    assert assessments.complaint("x.json", doc(), gt_sha=GT_SHA,
                                 embeddings_sha=EMB_SHA) == ""


def test_the_embedding_check_is_skipped_for_files_that_do_not_use_one(assessments):
    """status.json and disagreement.json read the labels alone."""
    assert assessments.complaint("x.json", doc(emb_sha=None), gt_sha=GT_SHA) == ""


def test_the_external_builder_refuses_on_every_complaint():
    """The refusal is in the builder, before verify_snapshot, like the queue
    page's novelty check. Read off the source so the guard cannot quietly move
    behind the rendering."""
    src = (REPO / "dashboard" / "build_external.py").read_text(encoding="utf-8")
    assert src.index("assessment_complaints") < src.index("verify_snapshot(\n")
    assert re.search(r"for msg in c\.assessment_complaints:\s+fail\(msg\)", src)


def test_the_internal_builder_prints_none_of_it_and_so_does_not_gate_on_it():
    src = (REPO / "dashboard" / "build_internal.py").read_text(encoding="utf-8")
    assert "assessment_complaints" not in src


def test_review_frames_the_file_never_saw_make_it_stale(assessments):
    d = {"frames": {"k1": {"mechanism": "species_conflict"}}}
    assert assessments.unassessed(d, ["k1", "k2"]) == ["k2"]
    assert assessments.unassessed(None, ["k1"]) == ["k1"]


# ---------------------------------------------------------------------------
# the limit column
# ---------------------------------------------------------------------------

def test_the_floor_is_the_one_the_status_column_uses(assessments, core):
    """Blank exactly where the row already reads "too few labels to judge",
    so the two columns cannot say "trust nothing" and "better model" at once."""
    assert assessments.LIMIT_MIN_FRAMES == core.WELL_SAMPLED_MIN_N


def test_a_species_under_the_floor_is_blank(assessments):
    t = transductive(**{"a b": species("resolved", assessments.LIMIT_MIN_FRAMES - 1),
                        "c d": species("classifier_limited",
                                       assessments.LIMIT_MIN_FRAMES, agreeing=6)})
    assert assessments.limit_of(t, "a b") == ("", "")
    assert assessments.limit_of(t, "c d") == ("classifier_limited", "6/8")


def test_a_species_with_no_viewed_frame_is_blank_and_so_is_a_missing_file(assessments):
    t = transductive(**{"a b": species("resolved", 20)})
    assert assessments.limit_of(t, "e f") == ("", "")
    assert assessments.limit_of(None, "a b") == ("", "")


def test_limits_for_covers_every_row_of_the_species_table(assessments):
    t = transductive(**{"a b": species("resolved", 20)})
    rows = [{"species": "a b"}, {"species": "e f"}]
    assert assessments.limits_for(t, rows) == {"a b": ("resolved", "8/8"),
                                               "e f": ("", "")}


def test_every_word_the_file_can_carry_has_a_page_word(assessments):
    """labelfirst's three verdicts, in the page's words. A fourth verdict
    upstream would KeyError in the cell renderer rather than print raw."""
    assert set(assessments.LIMIT_WORDS) == {"sampling_limited", "classifier_limited",
                                            "resolved"}


def test_the_csv_carries_the_column_the_table_shows(measure, tmp_path):
    rows = [{"species": "a b", "n_labelled_frames": 12, "top1_accuracy": 0.9,
             "top5_accuracy": 0.95, "in_corpus_vocabulary": True,
             "in_project_checklist": True}]
    transductive = {"population": {"n_seeds": 8},
                    "per_species": {"a b": {"n_frames": 12, "limit": "classifier_limited",
                                            "seeds_agreeing": 7}}}
    measure.write_per_species_health(str(tmp_path), rows, transductive)
    got = list(csv.DictReader((tmp_path / "per_species_health.csv").open()))
    assert got[0]["limit"] == "classifier_limited"
    assert got[0]["limit_agreement"] == "7/8"


def test_verify_compares_the_limit_word_when_the_page_prints_one(history, tmp_path):
    from snapshot_harness import PER_SPECIES, species_csv_rows, write_csv
    rows = [{**r, "limit": "resolved"} for r in species_csv_rows()]
    write_csv(tmp_path / "per_species_health.csv", rows, list(rows[0]))
    limits = {d["species"]: ("resolved", "8/8") for d in PER_SPECIES}
    assert "limit words" in history.check_per_species(str(tmp_path), PER_SPECIES, limits)
    limits[PER_SPECIES[0]["species"]] = ("classifier_limited", "8/8")
    with pytest.raises(SystemExit, match="limit for"):
        history.check_per_species(str(tmp_path), PER_SPECIES, limits)


def test_verify_names_the_missing_column_rather_than_a_key_error(history, tmp_path):
    from snapshot_harness import PER_SPECIES, species_csv_rows, write_csv
    rows = species_csv_rows()
    write_csv(tmp_path / "per_species_health.csv", rows, list(rows[0]))
    with pytest.raises(SystemExit, match="no limit column"):
        history.check_per_species(str(tmp_path), PER_SPECIES,
                                  {d["species"]: ("", "") for d in PER_SPECIES})


def test_verify_without_limits_ignores_the_column(history, tmp_path):
    from snapshot_harness import PER_SPECIES, species_csv_rows, write_csv
    rows = species_csv_rows()
    write_csv(tmp_path / "per_species_health.csv", rows, list(rows[0]))
    assert "limit" not in history.check_per_species(str(tmp_path), PER_SPECIES)


# ---------------------------------------------------------------------------
# the mechanism column
# ---------------------------------------------------------------------------

def test_the_mechanism_is_read_by_frame_key_and_blank_when_unassessed(assessments):
    d = {"frames": {"k1": {"mechanism": "species_conflict"}}}
    assert assessments.mechanism_of(d, "k1") == "species_conflict"
    assert assessments.mechanism_of(d, "k2") == ""
    assert assessments.mechanism_of(None, "k1") == ""


def test_verify_compares_mechanism_counts_when_the_page_groups_by_them(history, tmp_path):
    from snapshot_harness import review_rows_for, write_csv
    rows = [{**r, "mechanism": "species_conflict"} for r in review_rows_for()]
    write_csv(tmp_path / "label_review_queue.csv", rows, list(rows[0]))
    ok = history.check_review_queue(str(tmp_path), (len(rows), 2),
                                    {"species_conflict": len(rows)})
    assert "mechanism counts" in ok
    with pytest.raises(SystemExit, match="review mechanisms"):
        history.check_review_queue(str(tmp_path), (len(rows), 2),
                                   {"species_conflict": len(rows) - 1, "": 1})


def test_every_mechanism_the_file_can_carry_has_a_page_word():
    """The mechanisms the script gives, in the page's words, read off the two
    sources so one added upstream shows up here."""
    script = (REPO / "labelling" / "assess_species.py").read_text(encoding="utf-8")
    page = (REPO / "dashboard" / "assess_panels.py").read_text(encoding="utf-8")
    named = set(re.findall(r'"(species_conflict|synonym_artifact|coarser_label|'
                           r'liana_overgrowth)"', script))
    worded = set(re.findall(r'^\s+"(\w+)": "', page, re.MULTILINE))
    # The same three on both sides. speciesfirst's fourth, liana_overgrowth,
    # needs a growth-habit table nothing writes, so neither side names it.
    assert named == worded and len(named) == 3


# ---------------------------------------------------------------------------
# the sweep table
# ---------------------------------------------------------------------------

SWEEP = {"population": {"n_frames": 100, "n_species": 5},
         "rows": [{"max_set_size": 1, "n_accepted": 80, "accept_rate": 0.8,
                   "accepted_accuracy": 0.95}]}


def test_the_sweep_csv_is_the_sidecar_rows_and_nothing_else(assessments, tmp_path):
    assessments.write_reject_sweep(str(tmp_path), SWEEP)
    got = list(csv.DictReader((tmp_path / "reject_sweep.csv").open()))
    assert got == [{"max_set_size": "1", "n_accepted": "80", "n_frames": "100",
                    "accept_rate": "0.8", "accepted_accuracy": "0.95"}]


def test_an_absent_sidecar_writes_a_header_only_csv(assessments, tmp_path):
    """measure.py runs on a fresh clone; the builder is what refuses."""
    assessments.write_reject_sweep(str(tmp_path), None)
    assert (tmp_path / "reject_sweep.csv").read_text().splitlines() == [
        ",".join(assessments.REJECT_SWEEP_COLUMNS)]


def test_verify_compares_the_sweep_against_the_sidecar(assessments, history, tmp_path):
    assessments.write_reject_sweep(str(tmp_path), SWEEP)
    assert "1 plausible-name caps" in history.check_reject_sweep(str(tmp_path), SWEEP)
    moved = {**SWEEP, "rows": [{**SWEEP["rows"][0], "n_accepted": 81}]}
    with pytest.raises(SystemExit, match="reject sweep row 1 counts"):
        history.check_reject_sweep(str(tmp_path), moved)


# ---------------------------------------------------------------------------
# the script's side of the contract, read off the source
# ---------------------------------------------------------------------------

def test_the_script_writes_the_files_the_reader_names(assessments):
    src = (REPO / "labelling" / "assess_species.py").read_text(encoding="utf-8")
    for name in ("transductive", "disagreement", "reject_sweep", "status"):
        assert f'"{name}.json"' in src, f"the script never writes {name}.json"
        assert pathlib.Path(getattr(assessments, f"{name.upper()}_JSON")).name == f"{name}.json"


def test_the_script_records_what_the_reader_checks():
    src = (REPO / "labelling" / "assess_species.py").read_text(encoding="utf-8")
    for key in ("gt_sha256", "embeddings_sha256", "speciesfirst", "labelfirst"):
        assert f'"{key}"' in src


def test_the_script_uses_the_floor_free_verdict_and_the_reader_applies_the_floor():
    """The sidecar carries every species; the floor is one place, the reader."""
    src = (REPO / "labelling" / "assess_species.py").read_text(encoding="utf-8")
    assert "WELL_SAMPLED_MIN_N" not in src
    assert "LIMIT_MIN_FRAMES" not in src


def test_a_sidecar_on_disk_matches_what_the_reader_expects(assessments):
    """When the real files are there, the shape the tests fake above is the
    shape on disk. Skipped on a clone that has not run the script."""
    path = pathlib.Path(assessments.TRANSDUCTIVE_JSON)
    if not path.exists():
        pytest.skip("no transductive.json on disk")
    d = json.loads(path.read_text(encoding="utf-8"))
    rec = next(iter(d["per_species"].values()))
    assert {"limit", "n_frames", "seeds_agreeing"} <= set(rec)
    assert set(d["summary"]) <= set(assessments.LIMIT_WORDS)


def test_the_legend_counts_the_words_the_column_shows_and_not_the_file(assess_panels):
    """The sidecar summarises every species down to one frame; the column is
    blank under the floor. The legend's counts are the column's."""
    t = {"population": {"n_frames": 100, "n_species": 3, "n_seeds": 8},
         "summary": {"resolved": 2, "sampling_limited": 1}, "method": {"k": 5}}
    limits = {"a b": ("resolved", "8/8"), "c d": ("", ""), "e f": ("", "")}
    html = assess_panels.limit_note(t, limits)
    assert "Over the 1 species with that many: 1 no gap found, 0 better model, 0 more labels" in html


def test_the_review_csv_stamps_each_row_with_its_mechanism(assessments, tmp_path):
    """The mechanism is added at write time off the frame key, so the rows
    measure.py builds stay the six columns they were, and a frame the file
    never saw gets a blank rather than a guess."""
    rows = [["k1", "train", "a b", "c d", "0.990000", ""],
            ["k2", "val", "e f", "g h", "0.950000", ""]]
    assessments.write_label_review_queue(
        str(tmp_path), rows, {"frames": {"k1": {"mechanism": "species_conflict"}}})
    got = list(csv.DictReader((tmp_path / "label_review_queue.csv").open()))
    assert [d["mechanism"] for d in got] == ["species_conflict", ""]
    assert list(got[0]) == ["global_key", "split", "gt_species", "predicted_species",
                            "confidence", "labelbox_url", "mechanism"]
