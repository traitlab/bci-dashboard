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
SHA256 = "4a47a992915f7d72483de5cfa80f018dbc27d36222142b4ec4b0f3f1e6bc3406"


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

    def test_the_stratification_note_describes_the_committed_pool(
            self, draw_confirmatory):
        """The docstring says how many days and sites carry the pool and how
        much of it the largest site holds. That is the argument for drawing by
        site at all, and it was written against a pool of 2,685 frames. A1 cut
        the pool to 1,607 and the sentence stayed, so it named 47 flight days
        and a third of the pool when the manifest had 40 and a quarter.

        The manifest is committed, so the sentence can simply be counted."""
        import collections
        import csv
        import re
        pool = draw_confirmatory.POOL
        if not pool.exists():
            pytest.skip("the pool manifest is not present")
        with open(pool, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        sites = collections.Counter(r["site"] for r in rows)
        doc = draw_confirmatory.__doc__
        m = re.search(r"(\d+) flight days and (\d+) sites", doc)
        assert m, "the docstring no longer says what carries the pool"
        assert (int(m.group(1)), int(m.group(2))) == (
            len({r["flight_day"] for r in rows}), len(sites)), (
            f"{pool.name} holds {len({r['flight_day'] for r in rows})} flight "
            f"days over {len(sites)} sites; the docstring says {m.group(1)} and "
            f"{m.group(2)}.")
        share = re.search(r"one site holds ([\d.]+)% of the pool", doc)
        assert share, "the docstring no longer says how dominant the largest site is"
        assert float(share.group(1)) == round(100 * max(sites.values()) / len(rows), 1), (
            f"the largest site is {100 * max(sites.values()) / len(rows):.1f}% of "
            f"{len(rows)} pool frames and the docstring says {share.group(1)}%.")

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
