"""A frame a reviewer sent back to rework leaves the GT until it is relabelled."""
import csv
import json

from conftest import REPO, load

gfe = load("_gt_from_export_rework_under_test", REPO / "labelling" / "gt_from_export.py")


def line(stem, status):
    return json.dumps({
        "data_row": {"id": "dr_" + stem, "global_key": "missions/" + stem},
        "projects": {"p": {"project_details": {"workflow_status": status}, "labels": []}},
    }) + "\n"


def test_the_latest_export_decides_whether_a_frame_is_in_rework(tmp_path):
    old = tmp_path / "old.ndjson"
    old.write_text(line("a.JPG", "IN_REWORK") + line("b.JPG", "DONE"))
    new = tmp_path / "new.ndjson"
    new.write_text(line("a.JPG", "DONE") + line("c.JPG", "IN_REWORK") + line("d.JPG", "IN_REVIEW"))
    assert gfe.rework_frames([old]) == {"a.JPG"}
    assert gfe.rework_frames([old, new]) == {"c.JPG"}


def test_a_rework_frame_drops_its_bundled_label_too(tmp_path):
    path = tmp_path / "gt.csv"
    out, _, _ = gfe.merge_gt({"comb_a": "Ficus", "comb_b": "Cecropia"}, {"comb_b": "Inga"},
                             path, drop={"comb_a", "comb_z"})
    assert out == [("comb_b", "Inga")]
    with open(path, newline="") as f:
        assert [r["global_key"] for r in csv.DictReader(f)] == ["comb_b"]
