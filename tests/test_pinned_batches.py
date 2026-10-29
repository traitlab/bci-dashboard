"""Batches handed to the collaborator keep their frames and numbers across rebuilds.

The catalog batches are rebuilt from the latest labels every refresh, and the
collaborator sends them by hand. The pin file holds the batches handed out, topped
up to `--keep-ahead` unsent ones (`--hand-out K` adds K more), the send record (round ledgers) is written from the Labelbox export, and a sent
number is never reused.

    .venv/bin/pytest tests/test_pinned_batches.py
"""

from __future__ import annotations

import csv
import json

from test_catalog_batches import PRIORITY, health, synthetic_pool


def run(cb, per_species, pins_path, ledger, sent=frozenset(), hand_out=0, priority=frozenset(),
        n_rare=200, ahead=0):
    """One build as `main` does it: read the pins and the record, build, rewrite the pins."""
    pool, predictions, _ = synthetic_pool(n_rare)
    sent_nums = cb.sent_rounds(str(ledger))
    pins = cb.read_pins(pins_path)
    built = cb.build(pool, predictions, health(per_species), set(sent), set(priority),
                     pins=pins, sent_nums=sent_nums)
    cb.write_pins(pins_path, built["batch_rows"], pins, sent_nums, hand_out, ahead)
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
    first = run(catalog_batches, per_species, pins, tmp_path, hand_out=1)
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


def test_a_pinned_batch_stays_whole_while_the_rest_regroups_by_growth_form(
        catalog_batches, tmp_path):
    """A batch handed out before the tree and liana split keeps its mixed frames
    and number; the rest of the pool repacks into tree-only batches after it."""
    pins = tmp_path / "pins.csv"
    pool, predictions, per_species = synthetic_pool()
    first = run(catalog_batches, per_species, pins, tmp_path, hand_out=1)
    for i in range(0, 200, 2):
        predictions[f"rare{i:03d}.JPG"] = [(f"Vine sp{i}", 0.4)]
    forms = {f"Vine sp{i}": "liana" for i in range(200)}
    second = catalog_batches.build(pool, predictions, health(per_species), set(), set(),
                                   pins=catalog_batches.read_pins(pins), forms=forms)
    assert batch(second, 1) == batch(first, 1)
    group = second["group"]
    assert {group[k] for k in batch(second, 1)} == {"tree", "liana"}
    rest = {b[0] for b in second["batch_rows"]} - {1}
    assert all({group[k] for k in batch(second, n)} == {"tree"} for n in rest)


def send(ledger, number, keys):
    ledger.mkdir(exist_ok=True)
    with open(ledger / f"round_{number}.csv", "w", newline="") as f:
        csv.writer(f).writerows([["round", "global_key"], *[[number, k] for k in keys]])


def pinned_numbers(path):
    return sorted({int(r["batch_id"]) for r in read(path)})


def test_after_batch_1_is_recorded_as_sent_its_pin_leaves_and_1_is_not_reused(
        catalog_batches, tmp_path):
    pins, ledger = tmp_path / "pins.csv", tmp_path / "rounds"
    _, _, per_species = synthetic_pool()
    first = run(catalog_batches, per_species, pins, ledger, hand_out=2)
    sent = batch(first, 1)
    send(ledger, 1, sent)
    second = run(catalog_batches, per_species, pins, ledger, sent=set(sent))
    numbers = {b[0] for b in second["batch_rows"]}
    assert 1 not in numbers and min(numbers) == 2
    assert not set(sent) & {b[2] for b in second["batch_rows"]}
    assert batch(second, 2) == batch(first, 2)
    assert pinned_numbers(pins) == [2]
    assert second["pins_dropped"] == {"recorded as sent": len(sent)}


def test_pins_do_not_refill_after_a_send_and_hand_out_adds_exactly_the_next_batch(
        catalog_batches, tmp_path):
    pins, ledger = tmp_path / "pins.csv", tmp_path / "rounds"
    _, _, per_species = synthetic_pool(500)
    first = run(catalog_batches, per_species, pins, ledger, hand_out=4, n_rare=500)
    assert pinned_numbers(pins) == [1, 2, 3, 4]
    assert max(b[0] for b in first["batch_rows"]) >= 5
    send(ledger, 1, batch(first, 1))
    again = run(catalog_batches, per_species, pins, ledger, sent=set(batch(first, 1)), n_rare=500)
    assert pinned_numbers(pins) == [2, 3, 4]
    assert batch(again, 5) and not [r for r in read(pins) if r["batch_id"] == "5"]
    run(catalog_batches, per_species, pins, ledger, sent=set(batch(first, 1)), hand_out=1,
        n_rare=500)
    assert pinned_numbers(pins) == [2, 3, 4, 5]


def test_hand_out_never_reuses_a_sent_or_pinned_number(catalog_batches, tmp_path):
    pins, ledger = tmp_path / "pins.csv", tmp_path / "rounds"
    _, _, per_species = synthetic_pool(500)
    first = run(catalog_batches, per_species, pins, ledger, hand_out=2, n_rare=500)
    send(ledger, 1, batch(first, 1))
    sent = set(batch(first, 1))
    run(catalog_batches, per_species, pins, ledger, sent=sent, hand_out=2, n_rare=500)
    assert pinned_numbers(pins) == [2, 3, 4]
    send(ledger, 2, batch(first, 2))
    run(catalog_batches, per_species, pins, ledger, sent=sent | set(batch(first, 2)),
        hand_out=1, n_rare=500)
    assert pinned_numbers(pins) == [3, 4, 5]


def test_a_new_priority_mission_goes_into_the_first_batch_not_handed_out(
        catalog_batches, tmp_path):
    pins, ledger = tmp_path / "pins.csv", tmp_path / "rounds"
    _, _, per_species = synthetic_pool()
    run(catalog_batches, per_species, pins, ledger, hand_out=2)
    held = {r["global_key"] for r in read(pins)}
    built = run(catalog_batches, per_species, pins, ledger, priority={PRIORITY})
    assert {r["global_key"] for r in read(pins)} == held
    pool, _, _ = synthetic_pool()
    priority = {k for k, u in pool.items() if PRIORITY in u} - held
    assert priority and {b[0] for b in built["batch_rows"] if b[2] in priority} == {3}
    run(catalog_batches, per_species, pins, ledger, priority={PRIORITY}, hand_out=1)
    assert pinned_numbers(pins) == [1, 2, 3]


def test_an_empty_pin_file_with_no_hand_out_pins_nothing(catalog_batches, tmp_path):
    pins = tmp_path / "pins.csv"
    pins.write_text("batch_id,global_key,picked_by\n")
    built = run(catalog_batches, synthetic_pool()[2], pins, tmp_path)
    assert built["batch_rows"] and read(pins) == []


def test_a_sent_number_is_not_reused_when_nothing_is_pinned(catalog_batches, tmp_path):
    ledger = tmp_path / "rounds"
    ledger.mkdir()
    (ledger / "round_7.csv").write_text("round,global_key\n7,gone.JPG\n")
    built = run(catalog_batches, synthetic_pool()[2], tmp_path / "pins.csv", ledger)
    assert min(b[0] for b in built["batch_rows"]) == 8


def test_a_missing_pin_file_gives_the_old_output_and_pins_nothing(catalog_batches, tmp_path):
    pool, predictions, per_species = synthetic_pool()
    old = catalog_batches.build(pool, predictions, health(per_species), set(), set())
    pins = tmp_path / "input" / "pinned_batches.csv"
    new = run(catalog_batches, per_species, pins, tmp_path)
    assert new["batch_rows"] == old["batch_rows"]
    assert read(pins) == []


def test_a_pinned_frame_gone_from_the_pool_is_dropped_and_said(catalog_batches, tmp_path):
    pins = tmp_path / "pins.csv"
    _, _, per_species = synthetic_pool()
    first = run(catalog_batches, per_species, pins, tmp_path, hand_out=1)
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


def test_keep_ahead_tops_up_after_a_send_and_leaves_the_held_batches_alone(
        catalog_batches, tmp_path):
    """The refresh keeps four unsent batches handed out with no one asking."""
    pins, ledger = tmp_path / "pins.csv", tmp_path / "rounds"
    _, _, per_species = synthetic_pool(500)
    first = run(catalog_batches, per_species, pins, ledger, n_rare=500, ahead=4)
    assert pinned_numbers(pins) == [1, 2, 3, 4]
    send(ledger, 1, batch(first, 1))
    again = run(catalog_batches, per_species, pins, ledger, sent=set(batch(first, 1)),
                n_rare=500, ahead=4)
    assert pinned_numbers(pins) == [2, 3, 4, 5]
    assert all(batch(again, n) == batch(first, n) for n in (2, 3, 4))
    run(catalog_batches, per_species, pins, ledger, sent=set(batch(first, 1)), n_rare=500,
        ahead=4, hand_out=1)
    assert pinned_numbers(pins) == [2, 3, 4, 5, 6]
