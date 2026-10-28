"""A batch sent by hand is recorded from the live batch list, before the export carries it.

No network and no credential: the batch list is a file, the client a fake.

    .venv/bin/pytest tests/test_live_batches.py
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from test_pinned_batches import export_row, ledger_rows, write_export


@pytest.fixture(scope="session")
def fetch_live_batches():
    from conftest import REPO, _on_path, load
    with _on_path(REPO / "labelling"):
        return load("_fetch_live_batches_under_test", REPO / "labelling" / "fetch_live_batches.py")


def setup(tmp_path, live, pins=("1,a.JPG", "1,b.JPG", "2,c.JPG")):
    pins_csv = tmp_path / "pins.csv"
    pins_csv.write_text("batch_id,global_key,picked_by\n" + "".join(f"{p},queue\n" for p in pins))
    live_json = tmp_path / "live.json"
    live_json.write_text(json.dumps({"status": "checked", "batches": [
        {"name": n, "size": s} for n, s in live]}))
    return live_json, pins_csv, tmp_path / "send_batches.csv", tmp_path / "rounds"


def test_a_matching_size_records_the_pinned_frames(record_sends, tmp_path):
    live, pins, sent, ledger = setup(tmp_path, [("batch0001_2026-10", 2)])
    assert record_sends.record([], sent, ledger, "P1", live, pins) == {1: 2}
    rows = ledger_rows(ledger)["round_1.csv"]
    assert {r["global_key"] for r in rows} == {"a.JPG", "b.JPG"}
    assert {r["data_row_id"] for r in rows} == {""}
    assert record_sends.record([], sent, ledger, "P1", live, pins) == {}


def test_a_size_mismatch_records_nothing_and_says_it_waits(record_sends, tmp_path, capsys):
    live, pins, sent, ledger = setup(tmp_path, [("batch0001_2026-10", 3)])
    assert record_sends.record([], sent, ledger, "P1", live, pins) == {}
    assert not ledger.exists()
    out = capsys.readouterr().out
    assert "live batch 1" in out and "waits for the export" in out


def test_a_batch_already_in_a_ledger_is_untouched(record_sends, tmp_path):
    live, pins, sent, ledger = setup(tmp_path, [("batch0001_2026-10", 2)])
    ledger.mkdir()
    (ledger / "round_1.csv").write_text("round,batch_id,global_key,data_row_id\n1,1,z.JPG,id_z\n")
    before = ledger_rows(ledger)
    assert record_sends.record([], sent, ledger, "P1", live, pins) == {}
    assert ledger_rows(ledger) == before


def test_a_live_name_that_does_not_parse_is_ignored(record_sends, tmp_path):
    live, pins, sent, ledger = setup(tmp_path, [("batch1_2026-10", 2), ("scratch", 2)])
    assert record_sends.record([], sent, ledger, "P1", live, pins) == {}
    assert not ledger.exists()


def test_a_list_that_was_not_checked_records_nothing(record_sends, tmp_path):
    _, pins, sent, ledger = setup(tmp_path, [])
    live = tmp_path / "nc.json"
    live.write_text(json.dumps({"status": "not checked", "reason": "RuntimeError"}))
    assert record_sends.record([], sent, ledger, "P1", live, pins) == {}


def test_the_export_later_carrying_the_same_frames_changes_nothing(record_sends, tmp_path, capsys):
    live, pins, sent, ledger = setup(tmp_path, [("batch0001_2026-10", 2)])
    record_sends.record([], sent, ledger, "P1", live, pins)
    once = ledger_rows(ledger)
    export = write_export(tmp_path / "e.ndjson", [export_row("a.JPG", "batch0001_2026-10"),
                                                  export_row("b.JPG", "batch0001_2026-10")])
    assert record_sends.record([export], sent, ledger, "P1", live, pins) == {}
    assert ledger_rows(ledger) == once
    assert "WARNING" not in capsys.readouterr().out


def test_an_export_with_other_frames_warns_and_leaves_the_ledger(record_sends, tmp_path, capsys):
    live, pins, sent, ledger = setup(tmp_path, [("batch0001_2026-10", 2)])
    record_sends.record([], sent, ledger, "P1", live, pins)
    once = ledger_rows(ledger)
    export = write_export(tmp_path / "e.ndjson", [export_row("a.JPG", "batch0001_2026-10"),
                                                  export_row("x.JPG", "batch0001_2026-10")])
    record_sends.record([export], sent, ledger, "P1", live, pins)
    out = capsys.readouterr().out
    assert "WARNING: batch 1: the export has 2 frames, the ledger 2, 2 differ" in out
    # The frames already recorded stay exactly as they were.
    assert ledger_rows(ledger)["round_1.csv"][:2] == once["round_1.csv"]


def fake_client(batches):
    project = SimpleNamespace(batches=lambda: iter(
        [SimpleNamespace(name=n, size=s) for n, s in batches]))
    return SimpleNamespace(get_project=lambda pid: project)


def test_the_fetch_writes_name_and_size(fetch_live_batches, tmp_path, monkeypatch):
    monkeypatch.setenv("LABELBOX_API_KEY", "x")
    out = tmp_path / "live.json"
    got = fetch_live_batches.run(str(out), lambda key: fake_client([("batch0001_2026-10", 2)]))
    assert got["status"] == "checked" and got["batches"] == [{"name": "batch0001_2026-10", "size": 2}]
    assert json.loads(out.read_text()) == got


def test_the_fetch_error_is_not_checked_and_leaks_nothing(fetch_live_batches, tmp_path, monkeypatch):
    monkeypatch.setenv("LABELBOX_API_KEY", "x")

    def boom(key):
        raise ConnectionError("https://signed.example/?token=secret")
    out = tmp_path / "live.json"
    got = fetch_live_batches.run(str(out), boom)
    assert got["status"] == "not checked" and got["reason"] == "ConnectionError"
    assert "secret" not in out.read_text()


def test_the_fetch_without_a_key_exits_zero(fetch_live_batches, tmp_path, monkeypatch):
    monkeypatch.delenv("LABELBOX_API_KEY", raising=False)
    out = tmp_path / "live.json"
    assert fetch_live_batches.main(["--out", str(out)]) == 0
    assert json.loads(out.read_text())["status"] == "not checked"
