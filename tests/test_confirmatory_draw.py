"""The frozen list has to be the same list every time, or it is not frozen.

A confirmatory claim rests on the sample having been chosen before the data
existed. The only thing that makes that checkable months later is that the draw
reproduces from its seed, so the reproduction is a test and not a habit.

    .venv/bin/pytest tests/test_confirmatory_draw.py
"""

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
FROZEN = REPO / "input" / "confirmatory_frames_2026-08.csv"
SHA256 = "eccc8d06472cdfa578064da74896793f716daace8d4eb3382a6d31a5e51d4704"


class TestAllocationHonoursTheCap:
    def test_a_dominant_stratum_is_capped_and_its_excess_moves_on(
            self, draw_confirmatory):
        sizes = {"big": 900, "a": 200, "b": 150, "c": 100, "d": 50}
        quota = draw_confirmatory.allocate(sizes, 100, 0.4)
        assert quota["big"] == 40
        assert sum(quota.values()) == 100
        assert quota["a"] > quota["b"] > quota["c"] > quota["d"]

    def test_parts_sum_to_n_when_nothing_is_capped(self, draw_confirmatory):
        quota = draw_confirmatory.allocate({"a": 7, "b": 5, "c": 3}, 10, 0.9)
        assert sum(quota.values()) == 10

    def test_a_stratum_never_gives_more_frames_than_it_holds(self, draw_confirmatory):
        quota = draw_confirmatory.allocate({"a": 2, "b": 500}, 50, 0.99)
        assert quota["a"] <= 2
        assert sum(quota.values()) == 50

    def test_ceilings_that_cannot_reach_n_are_an_error_not_a_short_sample(
            self, draw_confirmatory):
        with pytest.raises(ValueError):
            draw_confirmatory.allocate({"only": 500}, 30, 0.25)


class TestTheDrawIsReproducible:
    def test_the_same_seed_draws_the_same_rows(self, draw_confirmatory):
        pool = [{"base_image": f"F{i:04d}.JPG", "site": f"s{i % 8}",
                 "flight_day": "20250101", "gt_species": "x", "n_crowns": 1}
                for i in range(400)]
        first, _ = draw_confirmatory.draw(pool, n=50, seed=1)
        second, _ = draw_confirmatory.draw(pool, n=50, seed=1)
        other, _ = draw_confirmatory.draw(pool, n=50, seed=2)
        assert [r["base_image"] for r in first] == [r["base_image"] for r in second]
        assert [r["base_image"] for r in first] != [r["base_image"] for r in other]

    def test_rows_come_back_sorted_and_unique(self, draw_confirmatory):
        pool = [{"base_image": f"F{i:04d}.JPG", "site": f"s{i % 8}",
                 "flight_day": "20250101", "gt_species": "x", "n_crowns": 1}
                for i in range(200)]
        rows, _ = draw_confirmatory.draw(pool, n=30, seed=7)
        keys = [r["base_image"] for r in rows]
        assert keys == sorted(keys)
        assert len(set(keys)) == 30


class TestTheCommittedListIsTheOneThatWasFrozen:
    def test_the_file_matches_the_sha256_in_the_hypothesis(self, draw_confirmatory):
        import hashlib
        if not FROZEN.exists():
            pytest.skip("the frozen list is not present")
        digest = hashlib.sha256(FROZEN.read_bytes()).hexdigest()
        assert digest == SHA256

    def test_no_site_carries_more_than_the_cap(self, draw_confirmatory):
        import collections
        import csv
        if not FROZEN.exists():
            pytest.skip("the frozen list is not present")
        with open(FROZEN, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 300
        counts = collections.Counter(r["site"] for r in rows)
        assert max(counts.values()) <= draw_confirmatory.CAP * len(rows)
