"""Priority missions in the queue order, and the catalog pool packed into batches.

Missions with ground data on their crowns go first inside each queue. The random
control stays a uniform draw over the whole pool, so the priority list must not
tilt it. The builder calls the real queue and packing code, so a tiny synthetic
pool with deep enough queues has to come out as the 65 / 20 / 15 mix.

    .venv/bin/pytest tests/test_catalog_batches.py
"""

from __future__ import annotations

from types import SimpleNamespace

PRIORITY = "20260424_bcishannon_wptsendero_m3e"
OTHER = "20260402_bcishannon_wptjaco7524_m3e"
BASE = "https://example.org/lefolab_drone_missions_wpt/"


def url(mission, key):
    return f"{BASE}{mission}/{key}"


def synthetic_pool(n_rare=200, n_known=60, n_priority_rare=40):
    """(pool, predictions, per_species). Each rare frame is its own species, so
    nothing hits the per-batch species cap; "Good sp" is well sampled, accurate
    and guessed at low confidence, so it lands in the low-confidence queue."""
    pool, predictions = {}, {}
    for i in range(n_rare):
        key = f"rare{i:03d}.JPG"
        mission = PRIORITY if i < n_priority_rare else OTHER
        pool[key] = url(mission, key)
        predictions[key] = [(f"Rare sp{i}", 0.4)]
    for i in range(n_known):
        key = f"known{i:03d}.JPG"
        pool[key] = url(OTHER, key)
        predictions[key] = [("Good sp", 0.1 + i / 1000)]
    per_species = [{"species": "Good sp", "n_labelled_frames": 100, "top1_accuracy": 0.95}]
    return pool, predictions, per_species


def health(per_species):
    return SimpleNamespace(per_species=per_species, canon=lambda name: name)


def test_a_priority_frame_sorts_before_the_rest_of_its_queue(queues):
    preds = {"a": [("Sp a", 0.1)], "b": [("Sp b", 0.2)], "c": [("Sp c", 0.3)]}
    rows, _, _ = queues.send_first_rows(preds, set(), lambda n: n, {}, {}, priority={"c"})
    assert [r[1] for r in rows] == ["c", "a", "b"]


def test_priority_does_not_move_a_frame_between_queues(queues):
    """Reordering inside a queue only: a priority can-wait frame is still last."""
    support, top1 = {"Sure": 50}, {"Sure": 0.95}
    preds = {"a": [("Sure", 0.99)], "b": [("Rare", 0.2)]}
    rows, _, _ = queues.send_first_rows(preds, set(), lambda n: n, support, top1, priority={"a"})
    assert [(r[1], r[0]) for r in rows] == [("b", "long_tail"), ("a", "can_wait")]


def test_no_priority_is_the_old_order(queues):
    preds = {"a": [("Sp a", 0.3)], "b": [("Sp b", 0.1)]}
    plain = queues.send_first_rows(preds, set(), lambda n: n, {}, {})
    assert plain == queues.send_first_rows(preds, set(), lambda n: n, {}, {}, priority=frozenset())
    assert [r[1] for r in plain[0]] == ["b", "a"]


def test_the_priority_list_skips_comments_and_an_absent_file_is_empty(queues, tmp_path):
    path = tmp_path / "priority.txt"
    path.write_text("# why\n\nm1\nm2  # trailing\n", encoding="utf-8")
    assert queues.load_priority_missions(str(path)) == {"m1", "m2"}
    assert queues.load_priority_missions(str(tmp_path / "absent.txt")) == frozenset()


def test_the_priority_list_does_not_steer_the_control_toward_priority_frames(queues):
    """The control is a seeded draw from what the batch's queue picks left, so it
    never reads the priority list. Priority frames are a quarter of this pool and
    are all taken by the queue first; the control must not be richer in them."""
    n, n_priority = 400, 100
    preds = {f"f{i:03d}": [(f"Sp {i}", 0.3)] for i in range(n)}
    priority = {f"f{i:03d}" for i in range(n_priority)}
    rows, _, _ = queues.send_first_rows(preds, set(), lambda m: m, {}, {}, priority=priority)
    queue_rows = [[q, stem, "", sp, f"{c:.6f}", 0, "", "", ""] for q, stem, sp, c, _ in rows]
    drawn = total = 0
    for seed in range(40):
        batches = queues.chunk_send_batches(queue_rows, seed=seed)
        control = [b for b in batches if b[4] == "control"]
        assert len([b for b in control if b[0] == 1]) == 15
        total += len(control)
        drawn += sum(b[2] in priority for b in control)
    assert drawn / total <= n_priority / n


def test_a_synthetic_pool_comes_out_65_20_15(catalog_batches):
    pool, predictions, per_species = synthetic_pool()
    built = catalog_batches.build(pool, predictions, health(per_species), set(), {PRIORITY})
    first = [b for b in built["batch_rows"] if b[0] == 1]
    assert len(first) == 100
    assert sum(b[4] == "control" for b in first) == 15
    queued = [b[3] for b in first if b[4] == "queue"]
    assert queued.count("low_conf_known") == 20
    assert queued.count("long_tail") == 65


def test_priority_frames_fill_the_first_batch_first(catalog_batches):
    pool, predictions, per_species = synthetic_pool(n_priority_rare=40)
    built = catalog_batches.build(pool, predictions, health(per_species), set(), {PRIORITY})
    first = {b[2] for b in built["batch_rows"] if b[0] == 1 and b[4] == "queue"}
    assert built["priority"] <= first | {b[2] for b in built["batch_rows"] if b[4] == "control"}


def test_frames_with_no_cached_answer_are_reported_not_dropped(catalog_batches):
    pool, predictions, per_species = synthetic_pool(n_rare=30, n_known=0)
    del predictions["rare003.JPG"]
    built = catalog_batches.build(pool, predictions, health(per_species), set(), set())
    assert built["missing"] == ["rare003.JPG"]
    assert "rare003.JPG" in catalog_batches.summary(pool, built)
    assert len(built["queue_rows"]) == 29


def test_a_key_already_in_a_ledger_is_left_out(catalog_batches):
    pool, predictions, per_species = synthetic_pool(n_rare=30, n_known=0)
    built = catalog_batches.build(pool, predictions, health(per_species), {"rare001.JPG"}, set())
    assert built["already_sent"] == ["rare001.JPG"]
    assert all(r[1] != "rare001.JPG" for r in built["queue_rows"])


def test_the_written_files_have_the_dispatch_columns_and_blank_row_ids(
        catalog_batches, queues, tmp_path):
    pool, predictions, per_species = synthetic_pool(n_rare=130, n_known=40)
    built = catalog_batches.build(pool, predictions, health(per_species), set(), {PRIORITY})
    catalog_batches.write_files(tmp_path, built, pool)
    lines = (tmp_path / "send_batches.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].split(",") == queues.SEND_BATCH_HEADER
    assert len(list(tmp_path.glob("*.csv"))) == 3
    frames = (tmp_path / "frames.csv").read_text(encoding="utf-8").splitlines()
    assert len(frames) == len(pool) + 1


def test_a_file_with_every_row_id_blank_is_sent_for_lookup_not_refused(dispatch_round, tmp_path):
    """The catalog file has no ids on any row, and the dispatcher resolves them by
    global key. A file with only some blank is still refused, as before."""
    path = tmp_path / "send_batches.csv"
    path.write_text("batch_id,global_key,data_row_id,picked_by\n1,a.JPG,,queue\n1,b.JPG,,control\n",
                    encoding="utf-8")
    assert dispatch_round.load_selection_csv(path, "1") == ["a.JPG", "b.JPG"]
