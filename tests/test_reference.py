"""The reference labels a number is scored against, and the break in the series.

From ``core.REFERENCE_SWITCHED_ON`` the headline is scored on the reviewed
publication labels alone. The Labelbox frames no review covered are scored
beside it with their own counts and never pooled in, and a snapshot scored
against other labels is refused rather than compared.

    .venv/bin/pytest tests/test_reference.py
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from conftest import REPO, _on_path

REVIEWED, UNREVIEWED = "publication_reviewed", "labelbox_unreviewed"


@pytest.fixture(scope="module")
def reference():
    with _on_path(REPO / "dashboard"):
        import reference

        yield reference


def rec(key, gt, first, coverage=0.9):
    return {
        "global_key": key,
        "gt": gt,
        "ranked": [(first, 0.9), (gt, 0.1)],
        "crop_coverage": coverage,
        "crop_dominant": None,
    }


def fake_health(headline=REVIEWED):
    return SimpleNamespace(
        reference=headline,
        by_source={
            REVIEWED: [
                rec("r1", "A a", "A a"),
                rec("r2", "A a", "B b"),
                rec("r3", "C c", "C c"),
            ],
            UNREVIEWED: [rec("u1", "D d", "X x", coverage=0.1)],
        },
    )


def test_the_headline_default_is_the_reviewed_population(core):
    assert core.HEADLINE_LABEL_SOURCE == core.LABEL_SOURCE_REVIEWED == REVIEWED
    assert core.INPUT_FLAGS["--gt"][0] == core.PUBLICATION_GT_CSV

    import argparse

    p = argparse.ArgumentParser()
    core.add_label_source_flag(p)
    assert p.parse_args([]).label_source == REVIEWED


def test_the_reference_is_the_population_asked_for(reference):
    pooled = [{"global_key": "k", "label_source": REVIEWED}]
    assert reference.reference_of(pooled, REVIEWED) == REVIEWED
    assert reference.reference_of(pooled, UNREVIEWED) == UNREVIEWED
    assert reference.reference_of(pooled, "all") == reference.POOLED
    assert reference.reference_of([{"global_key": "k"}], None) == reference.LABELBOX
    assert reference.reference_of([], "all") == reference.LABELBOX


def test_a_snapshot_without_reference_json_was_scored_against_labelbox(
    reference, tmp_path
):
    assert reference.read(str(tmp_path)) == reference.LABELBOX
    (tmp_path / reference.REFERENCE_JSON).write_text(
        json.dumps({"reference": REVIEWED}), encoding="utf-8"
    )
    assert reference.read(str(tmp_path)) == REVIEWED


def test_the_break_sentence_names_the_date_and_both_references(reference, core):
    s = reference.break_sentence(reference.LABELBOX, REVIEWED)
    assert core.REFERENCE_SWITCHED_ON in s
    assert "the Labelbox labels" in s and "the reviewed publication labels" in s
    assert "change of reference, not of the model" in s


def test_each_population_carries_its_own_counts_headline_first(reference):
    rows = reference.population_stats(fake_health())
    assert [r["label_source"] for r in rows] == [REVIEWED, UNREVIEWED]
    head, beside = rows
    assert head["headline"] and not beside["headline"]
    assert (
        head["n_frames"],
        head["n_species"],
        head["n_correct_top1"],
        head["n_correct_top5"],
    ) == (3, 2, 2, 3)
    assert head["macro_top1"] == pytest.approx(0.75)
    assert (head["gated_n_frames"], head["gated_n_correct_top1"]) == (3, 2)
    # The unreviewed frame is scored on its own, never pooled into the headline.
    assert (beside["n_frames"], beside["n_species"], beside["n_correct_top1"]) == (
        1,
        1,
        0,
    )
    assert beside["gated_n_frames"] == 0 and beside["gated_macro_top1"] is None


def test_a_gt_without_the_column_has_no_populations_beside(reference):
    h = SimpleNamespace(reference=reference.LABELBOX, by_source={})
    assert reference.population_stats(h) == []


def test_tables_scored_against_other_labels_fail_verification(reference, tmp_path):
    with pytest.raises(SystemExit) as e:
        reference.check(str(tmp_path), REVIEWED, [])
    msg = str(e.value)
    assert msg.startswith("VERIFY FAIL")
    assert (
        "The reference labels changed on" in msg
        and "Re-run dashboard/measure.py" in msg
    )
    assert "absent" in reference.check(str(tmp_path), reference.LABELBOX, [])


def test_written_populations_verify_and_a_moved_count_does_not(reference, tmp_path):
    h = fake_health()
    h.by_source = dict(h.by_source)
    (tmp_path / "gt.csv").write_text(
        "global_key,wcvp_canonical_name\n", encoding="utf-8"
    )
    reference.write(str(tmp_path), h, str(tmp_path / "gt.csv"), REVIEWED)
    doc = json.loads((tmp_path / reference.REFERENCE_JSON).read_text(encoding="utf-8"))
    assert doc["reference"] == REVIEWED and doc["label_source"] == REVIEWED
    rows = reference.population_stats(h)
    assert "2 label_source populations match" in reference.check(
        str(tmp_path), REVIEWED, rows
    )
    rows[1] = {**rows[1], "n_frames": rows[1]["n_frames"] + 1}
    with pytest.raises(SystemExit, match="populations here differ"):
        reference.check(str(tmp_path), REVIEWED, rows)


def test_unreviewed_frames_stay_labelled_and_are_scored_beside(health):
    """The headline drops the unreviewed rows, but they are still labelled: out
    of the send queue, and scored on their own in ``by_source``."""
    gt_all = [
        {
            "global_key": "comb_a",
            "wcvp_canonical_name": "A a",
            "label_source": REVIEWED,
        },
        {
            "global_key": "comb_b",
            "wcvp_canonical_name": "B b",
            "label_source": UNREVIEWED,
        },
    ]
    gt_rows = gt_all[:1]
    sp_recs = [rec("comb_a", "A a", "A a")]
    predictions = {"a": [], "b": []}

    def records_of(joined):
        return [{**rec(k, name, name), "species_level": True} for k, _, name in joined]

    stems, by_source = health.other_populations(
        gt_all, gt_rows, sp_recs, predictions, records_of
    )
    assert stems == {"a", "b"}
    assert by_source[REVIEWED] == sp_recs
    assert [r["global_key"] for r in by_source[UNREVIEWED]] == ["comb_b"]


def test_a_missing_reviewed_gt_fails_without_falling_back(health, tmp_path):
    with pytest.raises(SystemExit) as e:
        health.load_health(
            gt_csv=str(tmp_path / "gt_publication_reviewed.csv"), label_source=REVIEWED
        )
    msg = str(e.value)
    assert "gt_publication_reviewed.csv" in msg
    assert "no fallback to the Labelbox labels" in msg


def test_a_renamed_crown_passes_the_gate_and_a_third_species_does_not(health, core):
    """The boxes carry the Labelbox name, the label the reviewed one. A crop
    filled by the frame's own Labelbox species is that crown, renamed; a crop
    filled by any other species is still another tree."""
    joined = [
        ("comb_a", "a", "Ceiba pentandra"),
        ("comb_b", "b", "Ceiba pentandra"),
        ("comb_c", "c", "Ceiba pentandra"),
    ]
    crop = {
        "a": {"dominant": "Pseudobombax septenatum", "coverage": 0.9},
        "b": {"dominant": "Ficus insipida", "coverage": 0.9},
        "c": {"dominant": "Pseudobombax septenatum", "coverage": 0.9},
    }
    predictions = {s: [("Ceiba pentandra", 0.9)] for s in "abc"}
    box_name_of = {
        "comb_a": "Pseudobombax septenatum",
        "comb_b": "Pseudobombax septenatum",
    }
    recs = health.frame_records(joined, {}, predictions, lambda n: n, crop, box_name_of)
    assert [r["crop_dominant"] for r in recs] == [
        "Ceiba pentandra",
        "Ficus insipida",
        "Pseudobombax septenatum",
    ]
    admitted, rejected = core.coverage_split(recs)
    assert [r["global_key"] for r in admitted] == ["comb_a"]
    # comb_c has no reviewed rename recorded, so its Labelbox-named crop is
    # another species, as before.
    assert [r["global_key"] for r in rejected] == ["comb_b", "comb_c"]
    assert [r["crop_by_name"] for r in recs] == [True, False, False]


def test_a_frame_already_named_alike_is_not_counted_as_let_in_by_the_rename(health):
    """The rename only counts where it changed the verdict: a reviewed name
    equal to the Labelbox one passed before the rule existed."""
    joined = [("comb_a", "a", "Ceiba pentandra")]
    crop = {"a": {"dominant": "Ceiba pentandra", "coverage": 0.9, "crowns": 2}}
    recs = health.frame_records(
        joined,
        {},
        {"a": [("Ceiba pentandra", 0.9)]},
        lambda n: n,
        crop,
        {"comb_a": "Ceiba pentandra"},
    )
    assert recs[0]["crop_by_name"] is False and recs[0]["crop_crowns"] == 2


def test_the_gate_counts_frames_where_another_crown_of_the_species_may_fill_it(core):
    """No box carries a crown id, so the rename cannot be checked against the
    crown the review read; the gate counts the admitted frames where a second
    crown of the filling species reaches into the crop."""

    def r(by_name, crowns, coverage=0.9):
        return {
            "gt": "A a",
            "ranked": [("A a", 0.9)],
            "crop_coverage": coverage,
            "crop_dominant": "A a",
            "crop_by_name": by_name,
            "crop_crowns": crowns,
        }

    gate = core.coverage_gate_stats(
        [r(True, 2), r(True, 1), r(False, 3), r(False, 1), r(True, 4, coverage=0.1)]
    )
    assert gate["n_admitted"] == 4
    assert (gate["n_by_name"], gate["n_by_name_several_crowns"]) == (2, 1)
    assert gate["n_several_crowns"] == 2
    # A record from before the fields existed counts as neither.
    assert core.coverage_gate_stats([rec("k", "A a", "A a")])["n_several_crowns"] == 0


def test_the_crop_counts_the_crowns_of_its_filling_species(tmp_path, monkeypatch):
    """One box is one crown. Two boxes of the filling species inside the crop
    are two crowns; a third outside it is not counted."""
    with _on_path(REPO / "dashboard"):
        import crop_overlap
    head = "base_image,x_min,y_min,x_max,y_max,width,height,lb_label\n"
    rows = [
        "f,1400,900,2400,2100,1000,1200,Ceiba pentandra",
        "f,2000,1500,2600,2100,600,600,Ceiba pentandra",
        "f,0,0,500,500,500,500,Ceiba pentandra",
        "f,2500,900,2640,1000,140,100,Ficus insipida",
    ]
    boxes = tmp_path / "boxes.csv"
    boxes.write_text(head + "\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(crop_overlap, "BOXES_CSV", str(boxes))
    monkeypatch.setattr(crop_overlap, "EXPORT_BOXES_CSV", None)
    frames, suspect = crop_overlap.build()
    assert suspect == []
    assert frames["f"]["dominant"] == "ceiba pentandra"
    assert frames["f"]["crowns"] == 2
