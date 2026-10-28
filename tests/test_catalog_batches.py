"""Priority missions in the queue order, and the catalog pool packed into batches.

Missions with ground data on their crowns go first inside each queue, and the
catalog builder sends all their frames in their own first batches. The random
control stays a uniform draw over the whole pool, so the priority list must not
tilt it. The builder calls the real queue and packing code, so a tiny synthetic
pool with deep enough queues has to come out as the 65 / 20 / 15 mix.

    .venv/bin/pytest tests/test_catalog_batches.py
"""

from __future__ import annotations

import csv
from types import SimpleNamespace

PRIORITY = "20260424_bcishannon_wptsendero_m3e"
OTHER = "20260402_bcishannon_wptjaco7524_m3e"
BASE = "https://example.org/lefolab_drone_missions_wpt/"


def other(i):
    return OTHER.replace("7524", f"{7524 + i % 10}")


def url(mission, key):
    return f"{BASE}{mission}/{key}"


def synthetic_pool(n_rare=200, n_known=60, n_priority_rare=40):
    """(pool, predictions, per_species). Each rare frame is its own species, so
    nothing hits the per-batch species cap, and the non-priority frames spread
    over ten missions so nothing hits the per-batch mission cap; "Good sp" is
    well sampled, accurate and guessed at low confidence, so it lands in the
    low-confidence queue."""
    pool, predictions = {}, {}
    for i in range(n_rare):
        key = f"rare{i:03d}.JPG"
        mission = PRIORITY if i < n_priority_rare else other(i)
        pool[key] = url(mission, key)
        predictions[key] = [(f"Rare sp{i}", 0.4)]
    for i in range(n_known):
        key = f"known{i:03d}.JPG"
        pool[key] = url(other(i), key)
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
    built = catalog_batches.build(pool, predictions, health(per_species), set(), set())
    first = [b for b in built["batch_rows"] if b[0] == 1]
    assert len(first) == 100
    assert sum(b[4] == "control" for b in first) == 15
    queued = [b[3] for b in first if b[4] == "queue"]
    assert queued.count("low_conf_known") == 20
    assert queued.count("long_tail") == 65


def test_every_priority_frame_goes_first_whatever_its_queue(catalog_batches):
    """A census of the ground-data transects: low-confidence priority frames ride
    with the long-tail ones, no control is drawn into them, and the 65/20/15
    batches follow, numbered on."""
    pool, predictions, per_species = synthetic_pool(n_priority_rare=150)
    for i in range(10):
        pool[f"known{i:03d}.JPG"] = url(PRIORITY, f"known{i:03d}.JPG")
    built = catalog_batches.build(pool, predictions, health(per_species), set(), {PRIORITY})
    rows = built["batch_rows"]
    head = [b for b in rows if b[0] <= 2]
    assert {b[2] for b in head} == built["priority"]
    assert [sum(b[0] == n for b in head) for n in (1, 2)] == [80, 80]
    assert all(b[4] == "queue" for b in head)
    third = [b for b in rows if b[0] == 3]
    assert any(b[4] == "control" for b in third)


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
    assert len(list(tmp_path.glob("*.csv"))) == 4
    frames = (tmp_path / "frames.csv").read_text(encoding="utf-8").splitlines()
    assert len(frames) == len(pool) + 1


def test_a_file_with_every_row_id_blank_is_sent_for_lookup_not_refused(dispatch_round, tmp_path):
    """The catalog file has no ids on any row, and the dispatcher resolves them by
    global key. A file with only some blank is still refused, as before."""
    path = tmp_path / "send_batches.csv"
    path.write_text("batch_id,global_key,data_row_id,picked_by\n1,a.JPG,,queue\n1,b.JPG,,control\n",
                    encoding="utf-8")
    assert dispatch_round.load_selection_csv(path, "1") == ["a.JPG", "b.JPG"]


def test_rarity_orders_inside_a_queue_threatened_then_fewest_stems_then_unlisted(catalog_batches):
    """Three one-species frames, all long tail, confidence pointing the other way."""
    pool = {k: url(OTHER, k) for k in ("common.JPG", "rare.JPG", "listed.JPG", "unknown.JPG")}
    predictions = {"common.JPG": [("Common sp", 0.1)], "rare.JPG": [("Rare sp", 0.2)],
                   "listed.JPG": [("Listed sp", 0.3)], "unknown.JPG": [("Unknown sp", 0.05)]}
    built = catalog_batches.build(pool, predictions, health([]), set(), set(),
                                  census={"common sp": "900", "rare sp": "2", "listed sp": "400"},
                                  iucn={"listed sp": "EN"})
    assert [r[1] for r in built["queue_rows"]] == ["listed.JPG", "rare.JPG", "common.JPG", "unknown.JPG"]
    assert built["rarity"]["listed.JPG"] == ["400", "EN"]
    assert built["rarity"]["unknown.JPG"] == ["", ""]


def test_rarity_never_moves_a_frame_between_queues(catalog_batches):
    pool, predictions, per_species = synthetic_pool(n_rare=5, n_known=5)
    with_rarity = catalog_batches.build(pool, predictions, health(per_species), set(), set(),
                                        census={"good sp": "1"}, iucn={"good sp": "CR"})
    plain = catalog_batches.build(pool, predictions, health(per_species), set(), set(),
                                  census={}, iucn={})
    def queue_of(b):
        return {r[1]: r[0] for r in b["queue_rows"]}
    assert queue_of(with_rarity) == queue_of(plain)


def test_the_input_rarity_files_read_and_an_absent_file_is_empty(catalog_batches, tmp_path):
    assert catalog_batches.read_species_column(tmp_path / "none.csv", "n") == {}
    census = catalog_batches.read_species_column(catalog_batches.CENSUS_CSV, "n")
    iucn = catalog_batches.read_species_column(catalog_batches.IUCN_CSV, "iucn_category")
    assert census["faramea occidentalis"] == "1717"
    assert "LC" not in set(iucn.values())


def test_a_second_frame_of_a_crown_is_not_queued_and_names_the_frame_its_label_comes_from(
        catalog_batches, tmp_path):
    pool = {"DJI_1_V_7524tele.JPG": url(OTHER, "DJI_1_V_7524tele.JPG"),
            "DJI_2_V_7524tele.JPG": url(OTHER, "DJI_2_V_7524tele.JPG"),
            "DJI_3_V_7524tele.JPG": url(PRIORITY, "DJI_3_V_7524tele.JPG")}
    predictions = {k: [("Sp", 0.3)] for k in pool}
    built = catalog_batches.build(pool, predictions, health([]), set(), set(), census={}, iucn={})
    assert built["same_crown"] == {"DJI_2_V_7524tele.JPG": "DJI_1_V_7524tele.JPG"}
    assert [r[1] for r in built["queue_rows"]] == ["DJI_1_V_7524tele.JPG", "DJI_3_V_7524tele.JPG"]
    catalog_batches.write_files(tmp_path, built, pool)
    frames = list(csv.DictReader((tmp_path / "frames.csv").open(encoding="utf-8")))
    second = next(f for f in frames if f["global_key"] == "DJI_2_V_7524tele.JPG")
    assert (second["status"], second["label_from"]) == ("same_crown", "DJI_1_V_7524tele.JPG")
    assert second["crown_id"] == f"{OTHER}/7524"


def test_the_low_confidence_rule_reads_the_margin_in_the_catalog(queues):
    """Top-1 0.55 with top-2 0.45: sure enough by top-1, ambiguous by margin."""
    support, top1 = {"Sure": 50}, {"Sure": 0.95}
    preds = {"a": [("Sure", 0.55), ("Other", 0.45)]}
    plain, _, _ = queues.send_first_rows(preds, set(), lambda n: n, support, top1)
    margin, _, _ = queues.send_first_rows(preds, set(), lambda n: n, support, top1, by_margin=True)
    assert (plain[0][0], margin[0][0]) == ("normal", "low_conf_known")
    assert margin[0][3] == 0.55  # the confidence column stays the top-1 score


def test_every_mission_gets_its_cap_before_any_mission_gets_more(queues, catalog_batches):
    """120 frames of one mission, 120 species, and a second mission with 60 ranked
    after them: batch 1 holds the first MISSION_CAP of each before the fill pass
    tops it up from the capped rows, in rank order, and nothing is lost."""
    rows = [["long_tail", f"m1_{i:03d}", "", f"Sp {i}", "0.300000", 0, "", "", ""] for i in range(120)]
    rows += [["long_tail", f"m2_{i:03d}", "", f"Sq {i}", "0.400000", 0, "", "", ""] for i in range(60)]
    mission = {r[1]: r[1][:2] for r in rows}
    cap = catalog_batches.MISSION_CAP
    batches = queues.chunk_send_batches(rows, group_caps=((mission, cap),))
    first = [b[2] for b in batches if b[0] == 1 and b[4] == "queue"]
    assert len(first) == 85
    assert [k for k in first if mission[k] == "m2"] == [f"m2_{i:03d}" for i in range(cap)]
    assert [k for k in first if mission[k] == "m1"] == [f"m1_{i:03d}" for i in range(85 - cap)]
    assert sorted(b[2] for b in batches) == sorted(r[1] for r in rows)


def test_a_cap_never_shortens_a_batch_when_only_capped_rows_are_left(queues):
    """One mission of 150 frames: the cap cannot be met, so each batch still fills."""
    rows = [["long_tail", f"m1_{i:03d}", "", f"Sp {i}", "0.300000", 0, "", "", ""] for i in range(150)]
    batches = queues.chunk_send_batches(rows, group_caps=(({r[1]: "m1" for r in rows}, 20),))
    sizes = [sum(b[0] == n for b in batches) for n in range(1, 3)]
    assert sizes == [100, 50]


def test_site_and_season_caps_mix_a_batch_while_the_other_site_and_season_have_frames(
        queues, catalog_batches):
    """200 dry-season frames at one site, 50 wet-season at another: batch 1 takes at
    most SITE_CAP of the first and the rest from the second, in rank order."""
    dry, wet = "20260402_bcione_wpt01_m3e", "20260513_bcitwo_wpt01_m3e"
    rows = [["long_tail", f"d_{i:03d}", "", f"Sp {i}", "0.300000", 0, "", "", ""] for i in range(200)]
    rows += [["long_tail", f"w_{i:03d}", "", f"Sq {i}", "0.300000", 0, "", "", ""] for i in range(50)]
    mission = {r[1]: dry if r[1][0] == "d" else wet for r in rows}
    caps = catalog_batches.spread_caps(mission)
    assert [c for _, c in caps] == [catalog_batches.MISSION_CAP, catalog_batches.SITE_CAP,
                                    catalog_batches.SEASON_CAP]
    assert (catalog_batches.season_of(dry), catalog_batches.season_of(wet)) == ("2026-dry", "2026-wet")
    batches = queues.chunk_send_batches(rows, group_caps=caps[1:])
    first = [b[2] for b in batches if b[0] == 1 and b[4] == "queue"]
    assert sum(k[0] == "d" for k in first) == catalog_batches.SITE_CAP
    assert [k for k in first if k[0] == "w"] == [f"w_{i:03d}" for i in range(85 - catalog_batches.SITE_CAP)]


def test_a_held_frame_takes_the_label_of_the_frame_it_was_held_behind(catalog_batches, tmp_path):
    pool = {"DJI_1_V_7524tele.JPG": url(OTHER, "DJI_1_V_7524tele.JPG"),
            "DJI_2_V_7524tele.JPG": url(OTHER, "DJI_2_V_7524tele.JPG")}
    predictions = {k: [("Sp", 0.3)] for k in pool}
    labels = {"DJI_1_V_7524tele.JPG": "Ceiba pentandra"}
    built = catalog_batches.build(pool, predictions, health([]), set(), set(), census={}, iucn={},
                                  labels=labels)
    assert built["propagated"] == {"DJI_2_V_7524tele.JPG": "Ceiba pentandra"}
    catalog_batches.write_files(tmp_path, built, pool)
    out = list(csv.DictReader((tmp_path / "propagated_labels.csv").open(encoding="utf-8")))
    assert out == [{"global_key": "DJI_2_V_7524tele.JPG", "wcvp_canonical_name": "Ceiba pentandra",
                    "label_from": "DJI_1_V_7524tele.JPG"}]
    frames = {f["global_key"]: f for f in csv.DictReader((tmp_path / "frames.csv").open(encoding="utf-8"))}
    assert frames["DJI_2_V_7524tele.JPG"]["propagated_label"] == "Ceiba pentandra"
    assert "labelled through it: 1" in catalog_batches.summary(pool, built)
