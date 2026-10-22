"""The extra columns the send CSVs carry, joined on at write time."""
import csv

import core
import measure
import queues

URL = "https://app.labelbox.com/projects/projA/data-rows/rowA"


def test_data_row_id_parses_the_link_and_is_blank_without_one():
    assert core.data_row_id(URL) == "rowA"
    assert core.data_row_id(URL + "?x=1") == ""  # not a link the builder makes
    assert core.data_row_id("") == core.data_row_id(None) == ""


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_both_send_csvs_carry_data_row_id_matching_labelbox_url(tmp_path, monkeypatch):
    urls = {"k1": URL, "k2": "https://app.labelbox.com/projects/projB/data-rows/rowB"}
    monkeypatch.setattr(measure, "labelbox_urls", lambda: urls)
    monkeypatch.setattr(measure, "inventory_image_urls", lambda: {})
    monkeypatch.setattr(measure, "load_novelty_distance", lambda path: {})
    qrows = [["long_tail", k, "train", "sp", 0.5, 0, 0.0, i, "", ""]
             for i, k in enumerate(["k1", "k2", "k3"], 1)]
    brows = queues.chunk_send_batches(qrows, control_fraction=0)
    measure.write_send_first_queue(str(tmp_path), qrows)
    measure.write_send_batches(str(tmp_path), brows)

    first = _read(tmp_path / "send_first_queue.csv")
    batches = _read(tmp_path / "send_batches.csv")
    assert len(first) == len(batches) == 3
    for r in batches:
        assert r["data_row_id"] == core.data_row_id(r["labelbox_url"])
    assert {r["global_key"]: r["data_row_id"] for r in first} == {
        "k1": "rowA", "k2": "rowB", "k3": ""}  # k3 has no link, so no id
    assert list(first[0]) == queues.SEND_FIRST_HEADER
