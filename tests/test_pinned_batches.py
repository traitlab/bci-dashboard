"""Batches handed to the collaborator keep their frames and numbers across rebuilds.

The catalog batches are rebuilt from the latest labels every refresh, and the
collaborator sends them by hand. The pin file holds the next four unsent batches,
the send record (round ledgers) is written from the Labelbox export, and a sent
number is never reused.

    .venv/bin/pytest tests/test_pinned_batches.py
"""

from __future__ import annotations

import csv
import json

from test_catalog_batches import health, synthetic_pool


def run(cb, per_species, pins_path, ledger, sent=frozenset()):
    """One build as `main` does it: read the pins and the record, build, rewrite the pins."""
    pool, predictions, _ = synthetic_pool()
    sent_nums = cb.sent_rounds(str(ledger))
    built = cb.build(pool, predictions, health(per_species), set(sent), set(),
                     pins=cb.read_pins(pins_path), sent_nums=sent_nums)
    cb.write_pins(pins_path, built["batch_rows"], sent_nums)
    return built


def batch(built, n):
    return sorted(b[2] for b in built["batch_rows"] if b[0] == n)


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def queue_of(built):
    return {b[2]: b[3] for b in built["batch_rows"]}


def test_batch_1_keeps_its_frames_when_the_labels_move_frames_between_queues(
        catalog_batches, tmp_path):
    pins = tmp_path / "pins.csv"
    _, _, per_species = synthetic_pool()
    first = run(catalog_batches, per_species, pins, tmp_path)
    # New labels make 60 rare species well sampled: they move to the low-confidence queue.
    labels_changed = per_species + [
        {"species": f"Rare sp{i}", "n_labelled_frames": 100, "top1_accuracy": 0.95}
        for i in range(60)]
    second = run(catalog_batches, labels_changed, pins, tmp_path)
    assert queue_of(first) != queue_of(second)
    assert len(batch(first, 1)) == 100
    assert batch(second, 1) == batch(first, 1)
    # Without the pins the same label change reshuffles batch 1.
    pool, predictions, _ = synthetic_pool()
    loose = catalog_batches.build(pool, predictions, health(labels_changed), set(), set())
    assert batch(loose, 1) != batch(first, 1)


def test_after_batch_1_is_recorded_as_sent_the_window_starts_at_2_and_1_is_not_reused(
        catalog_batches, tmp_path):
    pins, ledger = tmp_path / "pins.csv", tmp_path / "rounds"
    _, _, per_species = synthetic_pool()
    first = run(catalog_batches, per_species, pins, ledger)
    sent = batch(first, 1)
    ledger.mkdir()
    with open(ledger / "round_1.csv", "w", newline="") as f:
        csv.writer(f).writerows([["round", "global_key"], *[[1, k] for k in sent]])
    second = run(catalog_batches, per_species, pins, ledger, sent=set(sent))
    numbers = {b[0] for b in second["batch_rows"]}
    assert 1 not in numbers and min(numbers) == 2
    assert not set(sent) & {b[2] for b in second["batch_rows"]}
    assert batch(second, 2) == batch(first, 2)
    assert {r["batch_id"] for r in read(pins)} <= {"2", "3", "4", "5"}
    assert second["pins_dropped"] == {"recorded as sent": len(sent)}


def test_a_sent_number_is_not_reused_when_nothing_is_pinned(catalog_batches, tmp_path):
    ledger = tmp_path / "rounds"
    ledger.mkdir()
    (ledger / "round_7.csv").write_text("round,global_key\n7,gone.JPG\n")
    built = run(catalog_batches, synthetic_pool()[2], tmp_path / "pins.csv", ledger)
    assert min(b[0] for b in built["batch_rows"]) == 8


def test_a_missing_pin_file_gives_the_old_output_and_writes_the_file(catalog_batches, tmp_path):
    pool, predictions, per_species = synthetic_pool()
    old = catalog_batches.build(pool, predictions, health(per_species), set(), set())
    pins = tmp_path / "input" / "pinned_batches.csv"
    new = run(catalog_batches, per_species, pins, tmp_path)
    assert new["batch_rows"] == old["batch_rows"]
    rows = read(pins)
    assert {int(r["batch_id"]) for r in rows} == {b[0] for b in old["batch_rows"]}
    assert len(rows) == len(new["batch_rows"])


def test_a_pinned_frame_gone_from_the_pool_is_dropped_and_said(catalog_batches, tmp_path):
    pins = tmp_path / "pins.csv"
    _, _, per_species = synthetic_pool()
    first = run(catalog_batches, per_species, pins, tmp_path)
    gone = batch(first, 1)[0]
    pool, predictions, _ = synthetic_pool()
    del pool[gone]
    built = catalog_batches.build(pool, predictions, health(per_species), set(), set(),
                                  pins=catalog_batches.read_pins(pins), sent_nums=set())
    assert batch(built, 1) == [k for k in batch(first, 1) if k != gone]
    assert built["pins_dropped"] == {"no longer in the pool or queued": 1}
    assert "no longer in the pool or queued" in catalog_batches.summary(pool, built)


def export_row(key, batch_name, project="P1"):
    details = {"batch_name": batch_name} if batch_name else {}
    return {"data_row": {"id": "id_" + key, "global_key": f"flight/{key}"},
            "projects": {project: {"project_details": details}}}


def write_export(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def ledger_rows(ledger):
    return {p.name: read(p) for p in sorted(ledger.glob("round_*.csv"))}


def test_recording_from_an_export_is_idempotent(record_sends, tmp_path):
    export = write_export(tmp_path / "e.ndjson", [
        export_row("a.JPG", "batch0001_2026-10"), export_row("b.JPG", "batch0001_2026-10"),
        export_row("c.JPG", "batch0002_2026-10"),
        export_row("d.JPG", "batch0003_2026-10", project="other"),  # not 2024_bci
        export_row("e.JPG", "not a batch"), export_row("f.JPG", None)])
    ledger, sent = tmp_path / "rounds", tmp_path / "send_batches.csv"
    sent.write_text("batch_id,global_key,picked_by,queue\n1,a.JPG,control,long_tail\n")
    assert record_sends.record([export], sent, ledger, "P1") == {1: 2, 2: 1}
    once = ledger_rows(ledger)
    assert sorted(once) == ["round_1.csv", "round_2.csv"]
    assert {r["global_key"] for r in once["round_1.csv"]} == {"a.JPG", "b.JPG"}
    a = next(r for r in once["round_1.csv"] if r["global_key"] == "a.JPG")
    assert (a["round"], a["batch_id"], a["picked_by"], a["queue"], a["data_row_id"]) == (
        "1", "1", "control", "long_tail", "id_a.JPG")
    assert record_sends.record([export], sent, ledger, "P1") == {}
    assert ledger_rows(ledger) == once


def test_an_empty_export_or_one_without_batch_names_records_nothing(record_sends, tmp_path):
    ledger = tmp_path / "rounds"
    empty = write_export(tmp_path / "empty.ndjson", [])
    plain = write_export(tmp_path / "plain.ndjson", [export_row("a.JPG", None),
                                                     export_row("b.JPG", "Batch1")])
    assert record_sends.record([empty, plain], tmp_path / "none.csv", ledger, "P1") == {}
    assert not ledger.exists()
