"""The flight holdout has to redraw, or it is a set chosen afterwards.

`input/holdout_v1.csv` is the one set of labelled frames whose flights no train
frame is on. What makes that claim checkable later is that the committed list
reproduces from its seed and its committed pool, and that the three properties
the draw promises hold on the file itself: no flight is split across held and
train, every held species has a train flight, and every buffered frame is
within the buffer of a held one.

The draw needs `speciesfirst.grouped_holdout`; the checks on the committed
files need only the standard library, so they run on any interpreter.

    .venv/bin/pytest tests/test_holdout_draw.py
"""

from __future__ import annotations

import collections
import csv
import hashlib
import json
import math
import pathlib
import subprocess
import sys

import pytest
from conftest import REPO, _on_path, load

POOL = REPO / "input" / "holdout_v1_pool.csv"
ROLES = REPO / "input" / "holdout_v1.csv"
META = REPO / "input" / "holdout_v1.json"
SHA256 = "06eea9709248724594e08d7d5c5a3c40b5a2b0b410520e273a8d35d12a960fd2"


@pytest.fixture(scope="session")
def draw_holdout():
    """`labelling/draw_holdout.py`, loaded with `labelling/` on the path for
    its two sibling imports. Skips when the grouped holdout is not importable."""
    pytest.importorskip("speciesfirst.grouped_holdout",
                        reason="draw_holdout needs speciesfirst.grouped_holdout")
    with _on_path(REPO / "labelling"):
        yield load("_draw_holdout_under_test", REPO / "labelling" / "draw_holdout.py")


def rows_of(path: pathlib.Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def committed():
    if not (POOL.exists() and ROLES.exists() and META.exists()):
        pytest.skip("the pool, the roles and the json are not all present")
    return rows_of(POOL), rows_of(ROLES), json.loads(META.read_text(encoding="utf-8"))


def a_pool(n_flights=10, per_flight=6, species=4):
    """Flights 30 m apart in x, frames 1 m apart inside a flight, so a buffer
    of 5 m reaches nothing and a buffer of 40 m reaches the neighbours."""
    rows = []
    for f in range(n_flights):
        for i in range(per_flight):
            rows.append({"global_key": f"comb_f{f:02d}_{i:02d}.JPG",
                         "species": f"sp{(f + i) % species}",
                         "flight": f"2026010{f % 9 + 1}/site{f}",
                         "x": f"{30.0 * f + i:.2f}", "y": "0.00"})
    return rows


class TestTheDrawIsReproducible:
    def test_the_same_seed_draws_the_same_roles(self, draw_holdout):
        first, _ = draw_holdout.draw(a_pool(), seed=1, buffer=0.0)
        second, _ = draw_holdout.draw(a_pool(), seed=1, buffer=0.0)
        other, _ = draw_holdout.draw(a_pool(), seed=2, buffer=0.0)
        roles = [r["role"] for r in first]
        assert roles == [r["role"] for r in second]
        assert roles != [r["role"] for r in other]

    def test_a_flight_is_held_whole_or_not_at_all(self, draw_holdout):
        rows, fold = draw_holdout.draw(a_pool(), seed=3, buffer=0.0)
        by_flight = collections.defaultdict(set)
        for r in rows:
            by_flight[r["flight"]].add(r["role"])
        assert all(roles in ({"held"}, {"train"}) for roles in by_flight.values())
        assert fold.held_groups == {f for f, roles in by_flight.items() if roles == {"held"}}

    def test_the_buffer_moves_train_frames_near_a_held_one_and_only_those(self, draw_holdout):
        pool = {r["global_key"]: r for r in a_pool()}
        near, _ = draw_holdout.draw(a_pool(), seed=3, buffer=5.0)
        wide, _ = draw_holdout.draw(a_pool(), seed=3, buffer=40.0)
        assert not [r for r in near if r["role"] == "buffered"]
        buffered = [pool[r["global_key"]] for r in wide if r["role"] == "buffered"]
        assert buffered
        held = [pool[r["global_key"]] for r in wide if r["role"] == "held"]
        assert {r["role"] for r in wide} == {"held", "train", "buffered"}
        assert all(_nearest(r, held) <= 40.0 for r in buffered)

    def test_rows_come_back_sorted_in_the_declared_columns(self, draw_holdout):
        rows, _ = draw_holdout.draw(a_pool(), seed=5, buffer=0.0)
        keys = [r["global_key"] for r in rows]
        assert keys == sorted(keys) and len(set(keys)) == len(keys)
        assert all(set(r) == set(draw_holdout.FIELDS) for r in rows)


class TestThePoolCountsWhatItLeavesOut:
    def test_a_frame_with_no_row_no_flight_or_no_gps_is_counted_by_name(self, draw_holdout):
        species = {"a": "x", "b": "x", "c": "x", "d": "x"}
        inventory = {"a": {"flight": "20260101/s", "gps": (9.1, -79.8)},
                     "b": {"flight": "", "gps": (9.1, -79.8)},
                     "c": {"flight": "20260101/s", "gps": None}}
        rows, excluded = draw_holdout.eligible(species, inventory)
        assert [r["global_key"] for r in rows] == ["a"]
        assert excluded == {"no_inventory_row": 1, "no_flight": 1, "no_gps": 1}

    def test_the_inventory_loader_reads_the_flight_and_the_position(
            self, draw_holdout, tmp_path):
        p = tmp_path / "rows.jsonl"
        p.write_text(
            '{"global_key":"a","row_data":"https://h/20260101_sitea_wp1_m3e/f.JPG",'
            '"media_attributes":{"gpsPoint":"9.1,-79.8"}}\n'
            '{"global_key":"b","row_data":"https://h/plain/f.JPG"}\n'
            '{"row_data":"https://h/20260101_sitea_wp1_m3e/g.JPG"}\n', encoding="utf-8")
        assert draw_holdout.load_flights(p) == {
            "a": {"flight": "20260101/sitea", "gps": (9.1, -79.8)},
            "b": {"flight": "", "gps": None}}

    def test_local_metres_scale_longitude_by_the_latitude(self, draw_holdout):
        x0, y0 = draw_holdout.local_xy(9.0, -79.8)
        x1, y1 = draw_holdout.local_xy(9.0, -79.8 + 1 / draw_holdout.METRES_PER_DEGREE)
        assert y1 == y0
        assert x1 - x0 == pytest.approx(math.cos(math.radians(9.0)), abs=1e-6)


def _nearest(row: dict, held: list[dict]) -> float:
    x, y = float(row["x"]), float(row["y"])
    return min(math.hypot(x - float(h["x"]), y - float(h["y"])) for h in held)


class TestTheCommittedListIsTheOneThatWasDrawn:
    def test_the_file_matches_the_recorded_sha256(self):
        if not ROLES.exists():
            pytest.skip("the drawn list is not present")
        assert hashlib.sha256(ROLES.read_bytes()).hexdigest() == SHA256

    def test_the_committed_list_redraws_from_the_committed_pool(self, draw_holdout):
        pool, _, meta = committed()
        rows, _ = draw_holdout.draw(
            pool, seed=meta["seed"], held_frac=meta["held_frac"],
            min_train_groups=meta["min_train_groups"], buffer=meta["buffer_m"])
        assert draw_holdout.to_csv_text(rows, draw_holdout.FIELDS) == ROLES.read_text(
            encoding="utf-8")

    def test_verify_exits_zero(self, draw_holdout):
        committed()
        proc = subprocess.run(
            [sys.executable, str(REPO / "labelling" / "draw_holdout.py"), "--verify"],
            capture_output=True, text=True, cwd=REPO, check=False)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "byte for byte" in proc.stdout

    def test_every_row_is_a_pool_frame_with_one_of_the_three_roles(self):
        pool, roles, _ = committed()
        assert [r["global_key"] for r in roles] == [r["global_key"] for r in pool]
        assert {r["role"] for r in roles} <= {"held", "train", "buffered"}

    def test_no_flight_has_both_held_and_train_rows(self):
        _, roles, meta = committed()
        by_flight = collections.defaultdict(set)
        for r in roles:
            by_flight[r["flight"]].add(r["role"])
        split = sorted(f for f, s in by_flight.items() if {"held", "train"} <= s)
        assert not split, f"flights with held and train frames: {split}"
        held = {f for f, s in by_flight.items() if "held" in s}
        assert held == set(meta["held_flights"])

    def test_every_held_species_appears_in_train(self):
        _, roles, meta = committed()
        held = {r["species"] for r in roles if r["role"] == "held"}
        train = {r["species"] for r in roles if r["role"] == "train"}
        assert held <= train, f"held species with no train frame: {sorted(held - train)}"
        assert not held & set(meta["ungradeable_species"])

    def test_every_buffered_row_is_within_the_buffer_of_a_held_row(self):
        pool, roles, meta = committed()
        xy = {r["global_key"]: r for r in pool}
        held = [xy[r["global_key"]] for r in roles if r["role"] == "held"]
        buffered = [xy[r["global_key"]] for r in roles if r["role"] == "buffered"]
        assert held
        far = [r["global_key"] for r in buffered if _nearest(r, held) > meta["buffer_m"]]
        assert not far, f"buffered frames beyond {meta['buffer_m']} m: {far}"

    def test_the_json_counts_are_the_counts_in_the_file(self):
        pool, roles, meta = committed()
        counts = collections.Counter(r["role"] for r in roles)
        stats = meta["stats"]
        assert stats["n_items"] == len(pool) == meta["n_pool"]
        assert stats["n_held"] == counts["held"]
        assert stats["n_train"] == counts["train"]
        assert stats["n_buffered"] == counts["buffered"]
        assert stats["n_groups"] == len({r["flight"] for r in pool})
        assert stats["n_held_groups"] == len(meta["held_flights"])
        assert meta["n_labelled"] == meta["n_pool"] + sum(meta["excluded"].values())
