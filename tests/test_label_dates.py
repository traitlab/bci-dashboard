"""The label-date sidecar.

No page plots these dates. The point of writing them down is that a trend
across model versions needs dated labels to have existed beforehand, and the
export we have today dates the migration rather than the labelling. These
tests pin the accumulation so the material is trustworthy when there is
finally enough of it.
"""
import csv
import json

import pytest


@pytest.fixture()
def gfe():
    from conftest import REPO, load
    return load("_gt_from_export_dates_under_test",
                REPO / "labelling" / "gt_from_export.py")


PROJECT = "cmbgnzmhu0bed07027vmxezzd"


def line(global_key, *made, species="Ficus insipida"):
    """One NDJSON row carrying one label per date in ``made``."""
    labels = [{"label_details": {"created_at": m},
               "annotations": {"objects": [{
                   "bounding_box": {"left": 0, "top": 0, "width": 10, "height": 10},
                   "classifications": [{"radio_answer": {"name": species}}],
               }]}} for m in made]
    return json.dumps({
        "data_row": {"id": "dr_" + global_key, "global_key": global_key},
        "projects": {PROJECT: {"labels": labels}},
    }) + "\n"


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return {r["global_key"]: r["labelled_at"] for r in csv.DictReader(f)}


def test_the_date_comes_from_the_export_not_the_file_mtime(gfe, tmp_path):
    """An mtime is when the file was written, which is the defect this
    replaces. ``label_details.created_at`` is when the botanist drew."""
    p = tmp_path / "e.ndjson"
    p.write_text(line("DJI_1.JPG", "2026-07-20T09:00:00.000Z"), encoding="utf-8")
    _, _, _, dates = gfe.export_dominants(p)
    assert dates == {"DJI_1.JPG": "2026-07-20T09:00:00.000Z"}


def test_a_relabelled_frame_keeps_the_later_of_its_labels(gfe, tmp_path):
    p = tmp_path / "e.ndjson"
    p.write_text(line("DJI_1.JPG", "2026-07-20T09:00:00.000Z",
                      "2026-08-02T11:00:00.000Z"), encoding="utf-8")
    _, _, _, dates = gfe.export_dominants(p)
    assert dates["DJI_1.JPG"] == "2026-08-02T11:00:00.000Z"


def test_an_undated_label_is_left_out_rather_than_guessed(gfe, tmp_path):
    """Older exports carry no ``label_details``. A frame with no date is
    absent from the sidecar, which is different from being dated today."""
    p = tmp_path / "e.ndjson"
    p.write_text(json.dumps({
        "data_row": {"id": "dr1", "global_key": "DJI_1.JPG"},
        "projects": {PROJECT: {"labels": [{"annotations": {"objects": []}}]}},
    }) + "\n", encoding="utf-8")
    _, _, _, dates = gfe.export_dominants(p)
    assert dates == {}


def test_the_union_takes_the_later_date_whichever_export_carries_it(gfe, tmp_path):
    """Arguments are oldest first, but a date is not a file ordering: a stale
    re-export must not walk a frame's date backwards."""
    old = tmp_path / "old.ndjson"
    old.write_text(line("DJI_1.JPG", "2026-08-02T11:00:00.000Z"), encoding="utf-8")
    new = tmp_path / "new.ndjson"
    new.write_text(line("DJI_1.JPG", "2026-07-20T09:00:00.000Z")
                   + line("DJI_2.JPG", "2026-08-05T08:00:00.000Z"), encoding="utf-8")
    _, _, _, dates = gfe.union_exports([str(old), str(new)])
    assert dates == {"DJI_1.JPG": "2026-08-02T11:00:00.000Z",
                     "DJI_2.JPG": "2026-08-05T08:00:00.000Z"}


def test_only_frames_the_corpus_knows_about_are_written(gfe, tmp_path):
    """An export can carry photos outside the frame list. The frame list
    defines the population, here as everywhere else."""
    out = tmp_path / "gt_label_dates.csv"
    gfe.merge_label_dates({"DJI_1.JPG": "2026-08-01T00:00:00.000Z",
                           "STRAY.JPG": "2026-08-01T00:00:00.000Z"},
                          {"comb_DJI_1.JPG"}, out)
    assert read(out) == {"comb_DJI_1.JPG": "2026-08-01T00:00:00.000Z"}


def test_dates_accumulate_across_runs_instead_of_being_replaced(gfe, tmp_path):
    """The whole value of the sidecar is that it grows. A run that exports
    one project must not erase the dates an earlier run learned."""
    out = tmp_path / "gt_label_dates.csv"
    corpus = {"comb_DJI_1.JPG", "comb_DJI_2.JPG"}
    gfe.merge_label_dates({"DJI_1.JPG": "2026-07-20T09:00:00.000Z"}, corpus, out)
    gfe.merge_label_dates({"DJI_2.JPG": "2026-08-05T08:00:00.000Z"}, corpus, out)
    assert read(out) == {"comb_DJI_1.JPG": "2026-07-20T09:00:00.000Z",
                         "comb_DJI_2.JPG": "2026-08-05T08:00:00.000Z"}


def test_a_relabel_moves_a_date_forward_and_never_back(gfe, tmp_path):
    out = tmp_path / "gt_label_dates.csv"
    corpus = {"comb_DJI_1.JPG"}
    gfe.merge_label_dates({"DJI_1.JPG": "2026-08-05T08:00:00.000Z"}, corpus, out)
    gfe.merge_label_dates({"DJI_1.JPG": "2026-07-20T09:00:00.000Z"}, corpus, out)
    assert read(out)["comb_DJI_1.JPG"] == "2026-08-05T08:00:00.000Z"
    gfe.merge_label_dates({"DJI_1.JPG": "2026-09-01T08:00:00.000Z"}, corpus, out)
    assert read(out)["comb_DJI_1.JPG"] == "2026-09-01T08:00:00.000Z"


def test_one_day_carrying_most_of_the_rows_is_called_out(gfe, tmp_path, capsys):
    """This is today's state: 1,718 of 1,900 labels share 2026-07-20. The
    NOTE is what stops someone plotting a trend against a migration stamp."""
    corpus = {f"comb_DJI_{i}.JPG" for i in range(4)}
    dates = {f"DJI_{i}.JPG": "2026-07-20T09:00:00.000Z" for i in range(3)}
    dates["DJI_3.JPG"] = "2026-08-05T08:00:00.000Z"
    gfe.merge_label_dates(dates, corpus, tmp_path / "d.csv")
    out = capsys.readouterr().out
    assert "3 of 4 share 2026-07-20" in out
    assert "NOTE" in out


def test_a_real_spread_is_reported_without_the_warning(gfe, tmp_path, capsys):
    """The run that first produces a genuine labelling history should look
    different from the ones before it."""
    corpus = {f"comb_DJI_{i}.JPG" for i in range(4)}
    dates = {f"DJI_{i}.JPG": f"2026-08-0{i + 1}T09:00:00.000Z" for i in range(4)}
    gfe.merge_label_dates(dates, corpus, tmp_path / "d.csv")
    out = capsys.readouterr().out
    assert "4 distinct days, 2026-08-01 to 2026-08-04" in out
    assert "NOTE" not in out


def test_no_dates_at_all_writes_a_header_and_says_nothing_more(gfe, tmp_path):
    """An export with no ``label_details`` anywhere is the old shape, not an
    error. It leaves an empty sidecar for the next run to fill."""
    out = tmp_path / "d.csv"
    gfe.merge_label_dates({}, {"comb_DJI_1.JPG"}, out)
    assert out.read_text(encoding="utf-8").strip() == "global_key,labelled_at"
