"""The extra columns the send CSVs carry, joined on at write time."""
import csv
import json

URL = "https://app.labelbox.com/projects/projA/data-rows/rowA"
LEGACY = "https://object-arbutus.cloud.computecanada.ca/"


def test_data_row_id_parses_the_link_and_is_blank_without_one(core):
    assert core.data_row_id(URL) == "rowA"
    assert core.data_row_id(URL + "?x=1") == ""  # not a link the builder makes
    assert core.data_row_id("") == core.data_row_id(None) == ""


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_both_send_csvs_carry_ids_mission_and_site(core, queues, measure, tmp_path, monkeypatch):
    urls = {"k1": URL, "k2": "https://app.labelbox.com/projects/projB/data-rows/rowB"}
    monkeypatch.setattr(measure, "labelbox_urls", lambda: urls)
    monkeypatch.setattr(measure, "inventory_image_urls", lambda: {"k1": LEGACY + "20260114_bciarmour_wptne01_m3e/DJI_x/a.JPG"})
    monkeypatch.setattr(measure, "inventory_row_ids", lambda: {"k3": "rowC"})
    monkeypatch.setattr(measure, "load_novelty_distance", lambda path: {})
    monkeypatch.setattr(measure, "inventory_origins",
                        lambda: {"k1": ("20260114_bciarmour_wptne01_m3e", "bciarmour")})
    monkeypatch.setattr(measure.growth_form, "load", lambda: {"sp": "liana"})
    qrows = [["long_tail", k, "train", "sp", 0.5, 0, 0.0, i, "", ""]
             for i, k in enumerate(["k1", "k2", "k3"], 1)]
    brows = queues.chunk_send_batches(qrows, control_fraction=0)
    measure.write_send_first_queue(str(tmp_path), qrows)
    measure.write_send_batches(str(tmp_path), brows, qrows)

    first = _read(tmp_path / "send_first_queue.csv")
    batches = _read(tmp_path / "send_batches.csv")
    assert len(first) == len(batches) == 3
    for r in batches:
        assert r["data_row_id"] == (core.data_row_id(r["labelbox_url"]) or "rowC")
    assert {r["global_key"]: r["data_row_id"] for r in first} == {
        "k1": "rowA", "k2": "rowB", "k3": "rowC"}  # k3 has no link, only a dispatch row
    assert [r["labelbox_url"] for r in batches if r["global_key"] == "k3"] == [""]
    assert list(first[0]) == queues.SEND_FIRST_HEADER
    for rows in (first, batches):
        by_key = {r["global_key"]: (r["mission"], r["site"]) for r in rows}
        assert by_key["k1"] == ("20260114_bciarmour_wptne01_m3e", "bciarmour")
        assert by_key["k2"] == by_key["k3"] == ("", "")  # inventory does not name them
    assert {r["growth_form"] for r in batches} == {"liana"}
    assert "image_url" not in batches[0]
    assert {r["global_key"]: r["s3_uri"] for r in batches} == {
        "k1": "s3://2024-bci/drone_missions/2026/20260114_bciarmour_wptne01_m3e/DJI_x/a.JPG", "k2": "", "k3": ""}
    assert list(batches[0]) == queues.SEND_BATCH_HEADER


def test_inventory_origins_reads_metadata_then_the_url_folder(core, tmp_path):
    inv = tmp_path / "inv.jsonl"
    base = "https://h/20260114_bciarmour_wptne01_m3e/DJI_x/DJI_20260114132256_0037.JPG"
    rows = [{"global_key": "a", "row_data": base, "metadata": {"mission": "20260114_bciarmour_wptne01_m3e"}},
            {"global_key": "b", "row_data": base, "metadata": {}},  # falls back to the URL
            {"global_key": "c", "row_data": "https://h/DJI_20260114132256_0037.JPG"},  # no folder
            {"global_key": "d", "row_data": "", "metadata": {"mission": "20240911_bcifairchild_wpt_m3e"}}]
    inv.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    got = core.inventory_origins(str(inv))
    assert got["a"] == got["b"] == ("20260114_bciarmour_wptne01_m3e", "bciarmour")
    assert "c" not in got
    assert got["d"] == ("20240911_bcifairchild_wpt_m3e", "bcifairchild")
    assert core.inventory_origins(str(tmp_path / "absent.jsonl")) == {}


def test_inventory_row_ids_reads_the_dispatch_uid_and_skips_what_is_unnamed(core, tmp_path):
    inv = tmp_path / "inv.jsonl"
    inv.write_text('{"global_key": "comb_a.JPG", "uid": "u1"}\n{"global_key": "comb_b.JPG"}\nnot json\n')
    assert core.inventory_row_ids(str(inv)) == {"comb_a.JPG": "u1"}
    assert core.inventory_row_ids(str(tmp_path / "absent.jsonl")) == {}
    assert core.send_row_id("comb_a.JPG", {"comb_a.JPG": URL}, {"comb_a.JPG": "u1"}) == "rowA"
    assert core.send_row_id("comb_a.JPG", {}, {"comb_a.JPG": "u1"}) == "u1"
    assert core.send_row_id("comb_z.JPG", {}, {}) == ""


def test_send_batches_stop_on_a_mission_the_bucket_table_lacks(measure, tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(measure, "inventory_image_urls", lambda: {"k1": LEGACY + "20990101_nowhere_m3e/DJI_x/a.JPG"})
    monkeypatch.setattr(measure, "labelbox_urls", dict)
    monkeypatch.setattr(measure, "inventory_row_ids", dict)
    monkeypatch.setattr(measure, "inventory_origins", dict)
    monkeypatch.setattr(measure, "load_novelty_distance", lambda path: {})
    monkeypatch.setattr(measure.growth_form, "load", dict)
    qrows = [["long_tail", "k1", "train", "sp", 0.5, 0, 0.0, 1, "", ""]]
    with pytest.raises(LookupError, match="20990101_nowhere_m3e"):
        measure.write_send_batches(str(tmp_path), [["1", "sp", "k1", "long_tail", "queue"]], qrows)
