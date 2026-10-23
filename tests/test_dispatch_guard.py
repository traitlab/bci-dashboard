"""The already-sent guard and --dry-run in `dispatch_round.main`.

The Labelbox client is a stub: any call through it is recorded, and a dry run
must record none.

    .venv/bin/pytest tests/test_dispatch_guard.py
"""

from __future__ import annotations

import csv
import sys
from types import SimpleNamespace

import pytest


def _write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


@pytest.fixture
def run(dispatch_round, tmp_path, monkeypatch):
    """Run main() on a 3-key batch where ``old.JPG`` is in the closed-round GT."""
    d = dispatch_round
    csv_path = tmp_path / "send_batches.csv"
    _write(csv_path, ["batch_id", "global_key", "picked_by", "queue"],
           [["1", "old.JPG", "queue", "q"], ["1", "new1.JPG", "queue", "q"],
            ["1", "new2.JPG", "control", "q"]])
    gt = tmp_path / "gt.csv"
    _write(gt, ["global_key", "wcvp_canonical_name"], [["old.JPG", "x"]])
    ledger = tmp_path / "rounds"
    _write(tmp_path / "send_first_queue.csv", ["global_key", "predicted_species", "confidence"],
           [["new1.JPG", "sp a", "0.9"], ["new2.JPG", "sp b", "0.4"]])
    monkeypatch.setattr(d, "GT_CSV", gt)
    monkeypatch.setattr(d, "LEDGER_DIR", ledger)
    monkeypatch.setattr(d.settings, "load_config", lambda: {"labelbox": {
        "combined_dataset_name": "ds", "project_b_name": "pb"}})
    calls = []

    class Client:
        def __init__(self, **kw):
            calls.append("client")

    monkeypatch.setattr(d.lb, "Client", Client)
    monkeypatch.setattr(d.settings, "api_key", lambda: "k")
    monkeypatch.setattr(d, "fetch_data_row_ids",
                        lambda c, n: {k: "id_" + k for k in ("old.JPG", "new1.JPG", "new2.JPG")})
    monkeypatch.setattr(d, "tag_round", lambda c, keys, ids, r: calls.append(("tag", list(keys))))
    failed = []  # data row ids the stub batch reports as refused

    def create_batch(c, p, keys, r, pri):
        # the ledger must already hold the rows when Labelbox is called
        calls.append(("batch", list(keys), (ledger / "round_2.csv").exists()))
        return SimpleNamespace(name="Round 2 - x", failed_data_row_ids=iter(failed))

    monkeypatch.setattr(d, "create_batch", create_batch)

    def go(*flags):
        monkeypatch.setattr(sys, "argv", ["dispatch_round", "--round", "2", "--csv",
                                          str(csv_path), "--batch", "1", *flags])
        d.main()
        return calls

    go.ledger = ledger
    go.failed = failed
    return go


def test_a_key_from_an_earlier_round_is_skipped_and_counted(run, capsys):
    calls = run()
    assert ("batch", ["new1.JPG", "new2.JPG"], True) in calls
    assert ("tag", ["new1.JPG", "new2.JPG"]) in calls
    assert "Skipped 1 keys already sent" in capsys.readouterr().out


def test_a_dispatched_batch_lands_in_the_round_ledger_and_is_skipped_next_time(run, capsys):
    run()
    with open(run.ledger / "round_2.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["global_key"] for r in rows] == ["new1.JPG", "new2.JPG"]
    assert list(rows[0]) == ["round", "batch_id", "global_key", "data_row_id", "picked_by",
                             "queue", "predicted_species", "confidence", "mission", "site",
                             "dispatched_at"]
    assert [(r["round"], r["batch_id"], r["picked_by"], r["data_row_id"],
             r["predicted_species"], r["confidence"]) for r in rows] == [
        ("2", "1", "queue", "id_new1.JPG", "sp a", "0.9"),
        ("2", "1", "control", "id_new2.JPG", "sp b", "0.4")]
    assert all(r["dispatched_at"] for r in rows)
    capsys.readouterr()
    with pytest.raises(SystemExit, match="every key"):
        run()  # the CSV has nothing left that was not sent


def test_dry_run_makes_no_client_no_write_and_no_ledger(run, capsys):
    assert run("--dry-run") == []
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "Skipped 1 keys" in out and "2 keys" in out
    assert not run.ledger.exists()  # nothing written, not even the directory


def test_no_ledger_and_no_gt_means_nothing_skipped(dispatch_round, tmp_path):
    assert dispatch_round.already_sent(tmp_path / "a.csv", tmp_path / "none") == set()
    assert dispatch_round.skip_sent([], {"x"}) == ([], [])


def test_a_real_send_stops_when_the_gt_file_is_absent(run, dispatch_round, tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch_round, "GT_CSV", tmp_path / "missing_gt.csv")
    with pytest.raises(SystemExit, match="ground-truth file"):
        run()
    assert not run.ledger.exists()
    run("--dry-run")  # a dry run writes nothing and stays allowed


def test_rows_labelbox_refused_are_dropped_from_the_ledger_and_re_sent(run):
    run.failed.append("id_new2.JPG")
    run()
    with open(run.ledger / "round_2.csv", newline="", encoding="utf-8") as f:
        assert [r["global_key"] for r in csv.DictReader(f)] == ["new1.JPG"]
    run.failed.clear()
    calls = run()  # new2 is not skipped as sent
    assert calls[-1][:2] == ("batch", ["new2.JPG"])


def test_a_zero_byte_ledger_gets_its_header(dispatch_round, tmp_path):
    (tmp_path / "round_3.csv").write_bytes(b"")
    path = dispatch_round.record_sent(["k"], 3, tmp_path / "none.csv", None, {"k": "id"}, tmp_path)
    assert path.read_text().splitlines()[0].startswith("round,batch_id,global_key")
