"""`dispatch_round` reads the CSV the queue page downloads, as a path.

The downloaded file is `send_batches.csv`'s columns: `send_batch_<n>.csv` for
the next-batch button, `send_batches_filtered.csv` for the filtered one. A file
without data_row_id, batch_id and global_key is not one, and stops at the door.

    .venv/bin/pytest tests/test_dispatch_download.py
"""

from __future__ import annotations

import csv
import sys

import pytest

HEADER = ["batch_id", "species_group", "global_key", "queue", "picked_by",
          "how_new_it_looks", "image_url", "labelbox_url", "data_row_id", "mission",
          "site", "group_by"]


def _row(batch, key):
    return [batch, "sp", key, "normal", "queue", "0.5", "", "", "r_" + key, "m", "s", "species"]


def _write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


@pytest.fixture
def dry(dispatch_round, tmp_path, monkeypatch, capsys):
    """Run main() --dry-run on a downloaded file; `old.JPG` is in the closed-round GT."""
    d = dispatch_round
    _write(tmp_path / "gt.csv", ["global_key", "wcvp_canonical_name"], [["old.JPG", "x"]])
    ledger = tmp_path / "rounds"
    ledger.mkdir()
    (ledger / "round_1.csv").write_text("round,global_key\n1,k0\n", encoding="utf-8")
    monkeypatch.setattr(d, "GT_CSV", tmp_path / "gt.csv")
    monkeypatch.setattr(d, "LEDGER_DIR", ledger)
    monkeypatch.setattr(d.settings, "load_config", lambda: {"labelbox": {
        "combined_dataset_name": "ds", "project_b_name": "pb"}})
    monkeypatch.setattr(d.lb, "Client", lambda **kw: pytest.fail("a dry run made a client"))

    def go(*args):
        monkeypatch.setattr(sys, "argv", ["dispatch_round", *map(str, args), "--dry-run"])
        d.main()
        return capsys.readouterr().out

    return go


def test_a_downloaded_batch_file_is_read_by_path_and_skips_what_was_sent(dry, tmp_path):
    f = _write(tmp_path / "send_batch_1.csv", HEADER,
               [_row("1", "old.JPG"), _row("1", "a.JPG"), _row("1", "b.JPG")])
    out = dry(f)
    assert "Skipped 1 keys already sent" in out and "Loaded 2 global keys" in out
    assert "as round 2" in out  # the round after the one ledger on disk


def test_a_filtered_download_goes_as_one_batch_without_picking_a_batch_id(dry, tmp_path):
    f = _write(tmp_path / "send_batches_filtered.csv", HEADER,
               [_row("1", "a.JPG"), _row("3", "b.JPG"), _row("3", "c.JPG")])
    assert "Loaded 3 global keys" in dry(f)


def test_csv_flag_still_works_and_an_explicit_round_wins(dry, tmp_path):
    f = _write(tmp_path / "send_batch_1.csv", HEADER, [_row("1", "a.JPG")])
    assert "as round 7" in dry("--csv", f, "--round", 7)


@pytest.mark.parametrize("missing", ["data_row_id", "batch_id", "global_key"])
def test_a_file_without_a_required_column_stops_and_names_it(dry, tmp_path, missing):
    at = HEADER.index(missing)
    row = _row("1", "a.JPG")
    f = _write(tmp_path / "x.csv", HEADER[:at] + HEADER[at + 1:], [row[:at] + row[at + 1:]])
    with pytest.raises(SystemExit, match=f"has no {missing} column"):
        dry(f)


def test_a_file_that_is_not_a_queue_download_lists_what_it_has(dry, tmp_path):
    f = _write(tmp_path / "x.csv", ["photo", "label"], [["a", "b"]])
    with pytest.raises(SystemExit, match="has no data_row_id, batch_id, global_key column.*photo, label"):
        dry(f)


def test_an_empty_file_stops_rather_than_sending_nothing(dry, tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="no header"):
        dry(f)


def test_no_csv_at_all_is_a_usage_error(dry):
    with pytest.raises(SystemExit):
        dry()
