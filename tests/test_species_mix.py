"""Two per-frame rates read on the same species mix.

`dashboard/species_mix.py` keeps the species two populations share, reweights
each population's per-species rate to a common species mix (both populations
added, and each one's own) and reports the difference with a range that draws
whole sites at random.

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


def frames(pop: dict, site="s1"):
    """(species, site, hit) triples from species -> hits, all on one site."""
    return [(s, site, h) for s, hits in pop.items() for h in hits]


def test_a_hand_computed_example(species_mix):
    # x: a 2/4, b 2/2. y: a 1/1, b 1/3. z only in a (2 frames), w only in b (1).
    a = {"x": [True, True, False, False], "y": [True], "z": [True, False]}
    b = {"x": [True, True], "y": [True, False, False], "w": [False]}
    got = species_mix.compare(frames(a), frames(b), n_draws=0)
    assert got["n_shared_species"] == 2
    assert got["frames"] == {"a": 5, "b": 5}
    assert got["raw"] == {"a": pytest.approx(3 / 5), "b": pytest.approx(3 / 5)}
    w = got["weightings"]
    # Combined weights: x 6 frames, y 4 frames, total 10.
    assert w["combined"]["standardized"]["a"] == pytest.approx((6 * 0.5 + 4 * 1.0) / 10)
    assert w["combined"]["standardized"]["b"] == pytest.approx((6 * 1.0 + 4 / 3) / 10)
    assert w["combined"]["difference"] == pytest.approx((6 + 4 / 3) / 10 - 0.7)
    # a's own mix: x 4, y 1. b's own mix: x 2, y 3.
    assert w["a"]["difference"] == pytest.approx(
        (4 * 1.0 + 1 / 3) / 5 - (4 * 0.5 + 1) / 5
    )
    assert w["b"]["difference"] == pytest.approx(
        (2 * 1.0 + 3 / 3) / 5 - (2 * 0.5 + 3) / 5
    )
    assert got["excluded"] == {
        "a": {"species": 1, "frames": 2},
        "b": {"species": 1, "frames": 1},
    }
    assert all(v["ci95"] is None for v in w.values())


def test_the_three_weightings_can_disagree_in_sign(species_mix):
    # b is better on x, worse on y. a is mostly x, b mostly y.
    a = {"x": [False] * 8 + [True] * 1, "y": [True]}
    b = {"x": [True], "y": [False] * 8 + [True] * 1}
    got = species_mix.compare(frames(a), frames(b), n_draws=0)["weightings"]
    assert got["a"]["difference"] > 0 > got["b"]["difference"]
    assert got["combined"]["difference"] == pytest.approx(0.0)


def test_a_raw_gap_from_species_mix_alone_vanishes(species_mix):
    # Same per-species rates, opposite shares: raw rates differ, adjusted do not.
    a = {"easy": [True] * 9, "hard": [False] * 1}
    b = {"easy": [True] * 1, "hard": [False] * 9}
    got = species_mix.compare(frames(a), frames(b), n_draws=0)
    assert got["raw"]["a"] == pytest.approx(0.9)
    assert got["raw"]["b"] == pytest.approx(0.1)
    for w in got["weightings"].values():
        assert w["difference"] == pytest.approx(0.0)


def test_identical_populations_give_zero_difference(species_mix):
    pop = [
        ("x", "s1", True),
        ("x", "s2", False),
        ("y", "s1", False),
        ("y", "s2", True),
        ("z", "s3", True),
    ]
    got = species_mix.compare(pop, list(pop), n_draws=500)
    for w in got["weightings"].values():
        assert w["difference"] == pytest.approx(0.0)
        # Both sets draw the same sites, so every draw gives zero.
        assert w["ci95"] == (pytest.approx(0.0), pytest.approx(0.0))


def test_disjoint_species_say_no_shared_species_rather_than_crash(species_mix):
    got = species_mix.compare(
        [("x", "s1", True)], [("y", "s1", False), ("y", "s2", True)]
    )
    assert got["n_shared_species"] == 0
    assert got["weightings"] == {}
    assert got["raw"] == {"a": None, "b": None}
    assert got["excluded"] == {
        "a": {"species": 1, "frames": 1},
        "b": {"species": 1, "frames": 2},
    }


def test_empty_populations_say_no_shared_species(species_mix):
    got = species_mix.compare([], [])
    assert got["n_shared_species"] == 0 and got["weightings"] == {}


def _clustered():
    """Four sites; every frame on a site has the same answer, so the frames
    are four pieces of evidence per set, not forty."""
    a = [("x", f"s{i}", i % 2 == 0) for i in range(4) for _ in range(10)]
    b = [("x", f"s{i}", i < 3) for i in range(4) for _ in range(10)]
    return a, b


def test_drawing_whole_sites_is_wider_than_drawing_single_frames(species_mix):
    a, b = _clustered()
    by_site = species_mix.compare(a, b, n_draws=2000)["weightings"]["combined"]["ci95"]
    # Every frame its own site is a frame-level draw.
    one = [(s, f"{site}-{i}", h) for i, (s, site, h) in enumerate(a)]
    two = [(s, f"{site}-{i}", h) for i, (s, site, h) in enumerate(b)]
    by_frame = species_mix.compare(one, two, n_draws=2000)["weightings"]["combined"][
        "ci95"
    ]
    assert by_site[1] - by_site[0] > by_frame[1] - by_frame[0]


def test_a_draw_missing_a_species_drops_it_and_is_counted(species_mix):
    # y lives on s2 only, so every draw without s2 has no y in either set.
    a = [("x", "s1", True), ("y", "s2", False)]
    b = [("x", "s1", False), ("y", "s2", True)]
    got = species_mix.compare(a, b, n_draws=1000)
    # Half the two-site draws hold one site twice: a short draw, never empty.
    assert 400 < got["draws_short"] < 600
    assert got["draws_empty"] == 0
    lo, hi = got["weightings"]["combined"]["ci95"]
    assert lo == pytest.approx(-1.0) and hi == pytest.approx(1.0)


def test_a_draw_with_no_shared_species_left_is_counted_empty(species_mix):
    # x is in a on s1 and in b on s2: only draws holding both sites compare.
    got = species_mix.compare([("x", "s1", True)], [("x", "s2", False)], n_draws=1000)
    assert 350 < got["draws_empty"] < 650
    assert got["weightings"]["combined"]["ci95"] == (
        pytest.approx(-1.0),
        pytest.approx(-1.0),
    )


def test_the_range_is_deterministic_and_seeded(species_mix):
    # Mixed answers on each of eight sites, so the draws spread finely.
    a = [
        (sp, f"s{i}", (i * j + len(sp)) % 3 == 0)
        for i in range(8)
        for j in range(i + 2)
        for sp in ("x", "yy")
    ]
    b = [
        (sp, f"s{i}", (i + j) % 4 != 0)
        for i in range(8)
        for j in range(3)
        for sp in ("x", "yy")
    ]
    one, two = species_mix.compare(a, b), species_mix.compare(a, b)
    assert one["n_draws"] == 10000
    assert one["weightings"] == two["weightings"]
    ci = one["weightings"]["combined"]["ci95"]
    assert ci[0] < one["weightings"]["combined"]["difference"] < ci[1]
    assert species_mix.compare(a, b, seed=1)["weightings"]["combined"]["ci95"] != ci


def test_by_site_counts_hits_and_frames(species_mix):
    got = species_mix.by_site(
        [("x", "s1", 1), ("y", "s1", 0), ("x", "s1", 0), ("x", "s2", 1)]
    )
    assert got == {"s1": {"x": (1, 2), "y": (0, 1)}, "s2": {"x": (1, 1)}}
