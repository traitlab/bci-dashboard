"""The Labelbox deep link is read from a file, never guessed.

A data row opens only inside a project it belongs to, so a link is only
correct where an export stated both halves. These tests pin the two halves of
that contract: the URL shape, and silence rather than a guess when the pair is
not known.

They also pin the third thing, which cost a round of confusion: *which* project
the link opens in. A frame that was migrated exists in two projects, the legacy
one it was labelled in and the dispatch one it was moved to. Both URLs resolve,
so nothing here can fail loudly if the wrong one is picked; only a person
opening both can say which shows the botanist's boxes. What these tests can
hold is that the choice is a setting rather than an accident, that it never
changes how many frames are linked, and that a single build can emit links into
more than one project, because the legacy rows are spread over two.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "dashboard"))

import core as hc  # noqa: E402

LEGACY_A = "cmbgnzmhu0bed07027vmxezzd"
LEGACY_B = "cme99tjc606h4075147dfd6j6"


def write(tmp_path, *rows):
    p = tmp_path / "data_row_ids.csv"
    body = "global_key,data_row_id,project_id\n" + "".join(
        ",".join(r) + "\n" for r in rows)
    p.write_text(body, encoding="utf-8")
    return str(p)


def write_inventory(tmp_path, *rows):
    """The dataset inventory, in the shape `labelling/fetch_dataset.py` writes.

    Its keys are the migrated ones (`migrated/DJI_1.JPG`) while the id table's
    are the dispatch ones (`comb_DJI_1.JPG`), which is the whole reason the
    join has to normalise rather than compare strings.
    """
    p = tmp_path / "dataset_rows.jsonl"
    p.write_text("".join(
        json.dumps({"global_key": key,
                    "metadata": {"original_labelbox_url": url} if url else {}}) + "\n"
        for key, url in rows), encoding="utf-8")
    return str(p)


def lb_url(project_id, data_row_id):
    return f"https://app.labelbox.com/projects/{project_id}/data-rows/{data_row_id}"


def config(tmp_path, value):
    p = tmp_path / "config.yaml"
    p.write_text(f"labelbox:\n  project_id: pr_dispatch\n  link_project: {value}\n",
                 encoding="utf-8")
    return str(p)


def test_a_missing_file_is_an_empty_map_not_an_error(tmp_path):
    assert hc.labelbox_urls(str(tmp_path / "absent.csv")) == {}


def test_a_known_pair_builds_the_project_scoped_url(tmp_path):
    urls = hc.labelbox_urls(write(tmp_path, ("comb_a.JPG", "dr1", "pr1")),
                            mode=hc.LINK_PROJECT_CURRENT)
    assert urls == {"comb_a.JPG": "https://app.labelbox.com/projects/pr1/data-rows/dr1"}


@pytest.mark.parametrize("row", [("comb_a.JPG", "", "pr1"),
                                 ("comb_a.JPG", "dr1", ""),
                                 ("comb_a.JPG", "", "")])
def test_a_half_known_row_yields_no_link_rather_than_a_broken_one(tmp_path, row):
    assert hc.labelbox_urls(write(tmp_path, row), mode=hc.LINK_PROJECT_CURRENT) == {}


def test_rows_are_independent(tmp_path):
    urls = hc.labelbox_urls(write(tmp_path, ("comb_a.JPG", "dr1", "pr1"),
                                  ("comb_b.JPG", "", "pr1"),
                                  ("comb_c.JPG", "dr3", "pr2")),
                            mode=hc.LINK_PROJECT_CURRENT)
    assert sorted(urls) == ["comb_a.JPG", "comb_c.JPG"]


# --- Which project the link opens in ---
def test_the_legacy_url_is_preferred_where_the_inventory_carries_one(tmp_path):
    """The whole point of A13: the dispatch project holds the frame, the legacy
    project holds the annotations, and the reviewer wants the annotations."""
    ids = write(tmp_path, ("comb_a.JPG", "dr1", "pr_dispatch"))
    inv = write_inventory(tmp_path, ("migrated/a.JPG", lb_url(LEGACY_A, "old1")))
    urls = hc.labelbox_urls(ids, inv, mode=hc.LINK_PROJECT_LEGACY)
    assert urls == {"comb_a.JPG": lb_url(LEGACY_A, "old1")}


def test_a_frame_the_inventory_does_not_know_keeps_its_dispatch_link(tmp_path):
    """Fallback, not silence. A frame that was never migrated has only one
    known URL, and dropping it would trade a link for nothing."""
    ids = write(tmp_path, ("comb_a.JPG", "dr1", "pr_dispatch"))
    inv = write_inventory(tmp_path, ("migrated/somethingelse.JPG",
                                     lb_url(LEGACY_A, "old1")),
                          ("migrated/nourl.JPG", None))
    urls = hc.labelbox_urls(ids, inv, mode=hc.LINK_PROJECT_LEGACY)
    assert urls == {"comb_a.JPG":
                    "https://app.labelbox.com/projects/pr_dispatch/data-rows/dr1"}


def test_one_build_emits_links_into_more_than_one_project(tmp_path):
    """The 1,719 legacy URLs on disk span two projects, so a mixed table is the
    normal case. Per-run project ids would send half of them to the wrong
    place, which is exactly the bug this file now guards."""
    ids = write(tmp_path, ("comb_a.JPG", "dr1", "pr_dispatch"),
                ("comb_b.JPG", "dr2", "pr_dispatch"),
                ("comb_c.JPG", "dr3", "pr_dispatch"))
    inv = write_inventory(tmp_path, ("migrated/a.JPG", lb_url(LEGACY_A, "old1")),
                          ("migrated/b.JPG", lb_url(LEGACY_B, "old2")))
    urls = hc.labelbox_urls(ids, inv, mode=hc.LINK_PROJECT_LEGACY)
    assert urls == {
        "comb_a.JPG": lb_url(LEGACY_A, "old1"),
        "comb_b.JPG": lb_url(LEGACY_B, "old2"),
        "comb_c.JPG": lb_url("pr_dispatch", "dr3"),
    }
    assert len({u.split("/projects/")[1].split("/")[0] for u in urls.values()}) == 3


def test_switching_the_destination_never_changes_how_many_frames_are_linked(tmp_path):
    """The claim the commit message makes, held by a test rather than by
    someone remembering it: this changes destination and nothing else."""
    ids = write(tmp_path, ("comb_a.JPG", "dr1", "pr_dispatch"),
                ("comb_b.JPG", "dr2", "pr_dispatch"),
                ("comb_c.JPG", "", "pr_dispatch"))
    inv = write_inventory(tmp_path, ("migrated/a.JPG", lb_url(LEGACY_A, "old1")))
    legacy = hc.labelbox_urls(ids, inv, mode=hc.LINK_PROJECT_LEGACY)
    current = hc.labelbox_urls(ids, inv, mode=hc.LINK_PROJECT_CURRENT)
    assert sorted(legacy) == sorted(current) == ["comb_a.JPG", "comb_b.JPG"]
    assert legacy["comb_a.JPG"] != current["comb_a.JPG"]
    assert legacy["comb_b.JPG"] == current["comb_b.JPG"]


def test_a_url_that_is_not_a_labelbox_data_row_is_not_a_link(tmp_path):
    """The inventory's metadata is free text somebody typed once. A value that
    is not a data-row URL falls back rather than being rendered as an <a>."""
    ids = write(tmp_path, ("comb_a.JPG", "dr1", "pr_dispatch"))
    inv = write_inventory(tmp_path, ("migrated/a.JPG", "see the shared drive"))
    urls = hc.labelbox_urls(ids, inv, mode=hc.LINK_PROJECT_LEGACY)
    assert urls["comb_a.JPG"].endswith("/projects/pr_dispatch/data-rows/dr1")


@pytest.mark.parametrize("key, stem", [
    ("comb_DJI_1.JPG", "DJI_1"),
    ("migrated/DJI_1.JPG", "DJI_1"),
    ("DJI_1.JPG", "DJI_1"),
    ("migrated/comb_DJI_1.JPG", "DJI_1"),
])
def test_both_naming_eras_normalise_to_the_same_frame(key, stem):
    assert hc.frame_key(key) == stem


# --- The destination is a setting ---
def test_the_shipped_config_asks_for_the_legacy_project():
    """Default recorded where it can be re-read, because it is a decision
    somebody made about Labelbox's state, not a property of this code."""
    assert hc.link_project_mode() == hc.LINK_PROJECT_LEGACY


@pytest.mark.parametrize("value, expected", [
    ("legacy", hc.LINK_PROJECT_LEGACY),
    ("current", hc.LINK_PROJECT_CURRENT),
    ("legasy", hc.LINK_PROJECT_DEFAULT),
    ("", hc.LINK_PROJECT_DEFAULT),
])
def test_the_setting_is_read_from_config_and_a_typo_does_not_break_it(
        tmp_path, value, expected):
    assert hc.link_project_mode(config(tmp_path, value)) == expected


def test_an_absent_config_falls_back_rather_than_raising(tmp_path):
    assert hc.link_project_mode(str(tmp_path / "gone.yaml")) == hc.LINK_PROJECT_DEFAULT


# --- Coverage, so a page never ships a half-empty column silently ---
def test_coverage_counts_the_frames_and_names_the_projects(tmp_path):
    ids = write(tmp_path, ("comb_a.JPG", "dr1", "pr_dispatch"),
                ("comb_b.JPG", "dr2", "pr_dispatch"))
    inv = write_inventory(tmp_path, ("migrated/a.JPG", lb_url(LEGACY_A, "old1")))
    urls = hc.labelbox_urls(ids, inv, mode=hc.LINK_PROJECT_LEGACY)
    cov = hc.labelbox_link_coverage(["comb_a.JPG", "comb_b.JPG", "comb_z.JPG"], urls)
    assert cov["n_frames"] == 3
    assert cov["n_linked"] == 2
    assert cov["n_unlinked"] == 1
    assert abs(cov["share"] - 2 / 3) < 1e-9
    assert cov["by_project"] == {LEGACY_A: 1, "pr_dispatch": 1}


def test_coverage_of_nothing_is_a_share_of_none_not_a_crash():
    cov = hc.labelbox_link_coverage([], {})
    assert cov["n_frames"] == 0 and cov["share"] is None and cov["by_project"] == {}


# --- The union of several exports ---
def export_line(global_key, data_row_id, project_id, species="Ficus insipida"):
    """One NDJSON row in the shape a Labelbox project export writes."""
    return json.dumps({
        "data_row": {"id": data_row_id, "global_key": global_key},
        "projects": {project_id: {"labels": [{"annotations": {"objects": [{
            "bounding_box": {"left": 0, "top": 0, "width": 10, "height": 10},
            "classifications": [{"radio_answer": {"name": species}}],
        }]}}]}},
    }) + "\n"


def test_the_id_table_is_built_from_the_union_of_every_export(tmp_path):
    """One export can only ever mint ids for one project's rows, which is why
    coverage sat at 1,719 of 3,781. The union is what lifts it, and each frame
    has to keep the project it was actually found in."""
    from conftest import REPO, load

    gt_from_export = load("_gt_from_export_under_test",
                          REPO / "labelling" / "gt_from_export.py")
    a = tmp_path / "a.ndjson"
    a.write_text(export_line("DJI_1.JPG", "dr1", LEGACY_A), encoding="utf-8")
    b = tmp_path / "b.ndjson"
    b.write_text(export_line("DJI_2.JPG", "dr2", LEGACY_B)
                 + export_line("DJI_3.JPG", "dr3", LEGACY_B), encoding="utf-8")

    dominants, boxes, row_ids, _ = gt_from_export.union_exports([str(a), str(b)])
    assert sorted(dominants) == ["DJI_1.JPG", "DJI_2.JPG", "DJI_3.JPG"]
    assert len(boxes) == 3
    assert row_ids == {"DJI_1.JPG": ("dr1", LEGACY_A),
                       "DJI_2.JPG": ("dr2", LEGACY_B),
                       "DJI_3.JPG": ("dr3", LEGACY_B)}

    out = tmp_path / "data_row_ids.csv"
    corpus = {"comb_DJI_1.JPG", "comb_DJI_2.JPG", "comb_DJI_3.JPG"}
    gt_from_export.merge_row_ids(row_ids, corpus, len(corpus), out)
    urls = hc.labelbox_urls(str(out), write_inventory(tmp_path),
                            mode=hc.LINK_PROJECT_CURRENT)
    assert hc.labelbox_link_coverage(sorted(corpus), urls)["by_project"] == {
        LEGACY_A: 1, LEGACY_B: 2}


def test_a_later_export_wins_over_an_earlier_one_for_the_same_frame(tmp_path):
    """Arguments are oldest first, so a re-export of a project supersedes it
    rather than being dropped or duplicated."""
    from conftest import REPO, load

    gt_from_export = load("_gt_from_export_union_under_test",
                          REPO / "labelling" / "gt_from_export.py")
    old = tmp_path / "old.ndjson"
    old.write_text(export_line("DJI_1.JPG", "dr_old", LEGACY_A, "Cecropia insignis"),
                   encoding="utf-8")
    new = tmp_path / "new.ndjson"
    new.write_text(export_line("DJI_1.JPG", "dr_new", LEGACY_B, "Ficus insipida"),
                   encoding="utf-8")
    dominants, _, row_ids, _ = gt_from_export.union_exports([str(old), str(new)])
    assert dominants == {"DJI_1.JPG": "Ficus insipida"}
    assert row_ids == {"DJI_1.JPG": ("dr_new", LEGACY_B)}
