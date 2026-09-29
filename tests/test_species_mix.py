"""Two per-frame rates read on the same species mix.

`dashboard/species_mix.py` keeps the species two populations share, reweights
each population's per-species rate to the combined species mix and reports
the difference with a within-species bootstrap interval.

    .venv/bin/pytest tests/test_species_mix.py
"""

from __future__ import annotations

import pytest
from conftest import REPO, _on_path


@pytest.fixture(scope="session")
def species_mix():
    with _on_path(REPO / "dashboard"):
        import species_mix

        yield species_mix


def test_a_hand_computed_example(species_mix):
    # x: a 2/4, b 2/2. y: a 1/1, b 1/3. z only in a (2 frames), w only in b (1).
    a = {"x": [True, True, False, False], "y": [True], "z": [True, False]}
    b = {"x": [True, True], "y": [True, False, False], "w": [False]}
    got = species_mix.compare(a, b, n_boot=0)
    assert got["n_shared_species"] == 2
    assert got["frames"] == {"a": 5, "b": 5}
    assert got["raw"] == {"a": pytest.approx(3 / 5), "b": pytest.approx(3 / 5)}
    # Weights: x 6 frames, y 4 frames, total 10.
    assert got["standardized"]["a"] == pytest.approx((6 * 0.5 + 4 * 1.0) / 10)
    assert got["standardized"]["b"] == pytest.approx((6 * 1.0 + 4 * (1 / 3)) / 10)
    assert got["difference"] == pytest.approx((6 + 4 / 3) / 10 - 0.7)
    assert got["excluded"] == {
        "a": {"species": 1, "frames": 2},
        "b": {"species": 1, "frames": 1},
    }
    assert got["ci95"] is None


def test_a_raw_gap_from_species_mix_alone_vanishes(species_mix):
    # Same per-species rates, opposite shares: raw rates differ, adjusted do not.
    a = {"easy": [True] * 9, "hard": [False] * 1}
    b = {"easy": [True] * 1, "hard": [False] * 9}
    got = species_mix.compare(a, b)
    assert got["raw"]["a"] == pytest.approx(0.9)
    assert got["raw"]["b"] == pytest.approx(0.1)
    assert got["difference"] == pytest.approx(0.0)


def test_identical_populations_give_zero_difference(species_mix):
    pop = {"x": [True, False, True], "y": [False, False], "z": [True]}
    got = species_mix.compare(pop, {k: list(v) for k, v in pop.items()})
    assert got["difference"] == pytest.approx(0.0)
    assert got["standardized"]["a"] == pytest.approx(got["standardized"]["b"])
    lo, hi = got["ci95"]
    assert lo <= 0 <= hi


def test_disjoint_species_say_no_shared_species_rather_than_crash(species_mix):
    got = species_mix.compare({"x": [True]}, {"y": [False, True]})
    assert got["n_shared_species"] == 0
    assert got["difference"] is None and got["ci95"] is None
    assert got["raw"] == {"a": None, "b": None}
    assert got["excluded"] == {
        "a": {"species": 1, "frames": 1},
        "b": {"species": 1, "frames": 2},
    }


def test_empty_populations_say_no_shared_species(species_mix):
    got = species_mix.compare({}, {})
    assert got["n_shared_species"] == 0 and got["difference"] is None


def test_a_species_with_no_frames_is_refused(species_mix):
    with pytest.raises(ValueError, match="no frames"):
        species_mix.compare({"x": []}, {"x": [True]})


def test_single_frame_species_have_no_bootstrap_spread(species_mix):
    # One frame per species per population: every resample is the sample itself.
    got = species_mix.compare({"x": [True], "y": [False]}, {"x": [False], "y": [False]})
    assert got["difference"] == pytest.approx(-0.5)
    assert got["ci95"] == (pytest.approx(-0.5), pytest.approx(-0.5))


def test_the_bootstrap_is_deterministic_and_seeded(species_mix):
    a = {"x": [True, False, True, True], "y": [False, True]}
    b = {"x": [True, True, False], "y": [False, False, True]}
    one, two = species_mix.compare(a, b), species_mix.compare(a, b)
    assert one["ci95"] == two["ci95"]
    assert one["ci95"][0] < one["difference"] < one["ci95"][1]
    assert species_mix.compare(a, b, seed=1)["ci95"] != one["ci95"]


def test_by_species_groups_hits(species_mix):
    got = species_mix.by_species([("x", 1), ("y", 0), ("x", 0)])
    assert got == {"x": [True, False], "y": [False]}
