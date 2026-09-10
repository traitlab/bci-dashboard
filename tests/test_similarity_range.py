"""The similarity-range measurement, on vectors whose decay is known.

`labelling/measure_similarity_range.py` needs numpy, which the repo venv may
lack, so the behaviour tests skip without it. The run record needs labelfirst
and is not exercised here.

    .venv/bin/pytest tests/test_similarity_range.py
    "$SPECIESFIRST/.venv/bin/pytest" tests/test_similarity_range.py
"""

from __future__ import annotations

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def msr():
    pytest.importorskip("numpy", reason="numpy is not in this virtualenv")
    from conftest import load
    return load("_similarity_range_under_test",
                REPO / "labelling" / "measure_similarity_range.py")


def _decaying_frames(np, n=60, seed=0):
    """Frames along a 1 km line, one site. Two species alternate; a frame's
    vector is its species' centre plus noise that grows with position, so
    kin nearby look more alike than kin far apart."""
    rng = np.random.default_rng(seed)
    centres = {"a": rng.normal(size=8), "b": rng.normal(size=8)}
    xy, species, flights, vecs = [], [], [], []
    for k in range(n):
        s = "a" if k % 2 == 0 else "b"
        xy.append((k * 1000.0 / n, 0.0))
        species.append(s)
        flights.append(f"f{k // 10}")
        vecs.append(centres[s] + rng.normal(scale=0.05 * (1 + k / 5), size=8))
    X = np.asarray(vecs)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    return X, np.asarray(xy), species, flights, ["s"] * n


def test_only_within_site_pairs_under_the_cap_are_kept(msr):
    import numpy as np

    X = np.eye(4)
    xy = np.array([[0.0, 0.0], [5.0, 0.0], [3000.0, 0.0], [6.0, 0.0]])
    pairs = msr.pair_table(X, xy, ["a"] * 4, ["f"] * 4, ["s", "s", "s", "t"])
    assert sorted(zip(pairs["i"].tolist(), pairs["j"].tolist())) == [(0, 1)]
    assert pairs["metres"].tolist() == [5.0]
    assert pairs["cosine"].tolist() == [0.0]


def test_binning_edges_are_half_open_except_the_last(msr):
    import numpy as np

    metres = np.array([0.0, 10.0, 9.999, 2000.0, 1999.9])
    cosine = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    rows = msr.bin_table(metres, cosine, {"all": np.ones(5, dtype=bool)})
    by_lo = {r["lo_m"]: r["all"] for r in rows}
    assert by_lo[0] == {"n": 2, "mean": 2.0}
    assert by_lo[10] == {"n": 1, "mean": 2.0}
    assert by_lo[1000] == {"n": 2, "mean": 4.5}


def test_an_empty_bin_reports_none_not_zero(msr):
    import numpy as np

    rows = msr.bin_table(np.array([1.0]), np.array([0.5]), {"all": np.array([True])})
    assert rows[0]["all"] == {"n": 1, "mean": 0.5}
    assert all(r["all"] == {"n": 0, "mean": None} for r in rows[1:])


def _rows(means, n=1000):
    edges = list(zip(msr_edges[:-1], msr_edges[1:]))
    return [{"lo_m": lo, "hi_m": hi,
             "same_species": {"n": n if m is not None else 0, "mean": m}}
            for (lo, hi), m in zip(edges, means)]


msr_edges = (0, 10, 20, 30, 50, 75, 100, 150, 200, 300, 500, 1000, 2000)


def test_the_range_is_the_first_bin_at_the_plateau(msr):
    means = [0.80, 0.75, 0.72, 0.71, 0.705, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70]
    out = msr.plateau_range(_rows(means))
    assert out["range_m"] == 50
    assert out["plateau"] == pytest.approx(0.70)
    assert out["bins_leaving_plateau_after_range"] == []


def test_a_bin_that_leaves_the_plateau_again_is_named(msr):
    means = [0.80, 0.70, 0.75, 0.705, 0.705, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70]
    out = msr.plateau_range(_rows(means))
    assert out["range_m"] == 10
    assert out["bins_leaving_plateau_after_range"] == [20]


def test_no_plateau_is_reported_not_guessed(msr):
    means = [0.80, 0.75, 0.72, 0.71, 0.705, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.55]
    out = msr.plateau_range(_rows(means))
    assert out["range_m"] is None
    assert "no bin within" in out["reason"]


def test_a_thin_last_bin_does_not_vote_on_the_plateau(msr):
    means = [0.80, 0.75, 0.72, 0.71, 0.705, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.55]
    rows = _rows(means)
    rows[-1]["same_species"]["n"] = 16
    out = msr.plateau_range(rows, min_pairs=100)
    assert out["range_m"] == 50
    assert out["plateau_bins"] == [200, 300, 500]


def test_too_few_bins_for_a_plateau(msr):
    out = msr.plateau_range(_rows([0.8, 0.7, 0.7] + [None] * 9))
    assert out["range_m"] is None and out["plateau"] is None


def test_synthetic_decay_is_seen_end_to_end(msr):
    import numpy as np

    X, xy, species, flights, sites = _decaying_frames(np)
    used = {"X": X, "xy": xy, "species": species, "flights": flights, "sites": sites}
    out = msr.measure(used)
    same = [r["same_species"]["mean"] for r in out["bins"] if r["same_species"]["n"]]
    assert same[0] > same[-1]
    assert out["spearman_cosine_distance_vs_metres"] > 0
    assert out["nearest"]["n_frames"] == 60
    assert out["nearest"]["nearest_any_under_5m"] == 0
    xf = [r["same_species_other_flight"]["n"] for r in out["bins"]]
    assert sum(xf) < sum(r["same_species"]["n"] for r in out["bins"])


def test_spearman_matches_a_hand_case(msr):
    import numpy as np

    assert msr.spearman(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0])) == 1.0
    assert msr.spearman(np.array([1.0, 2.0, 3.0]), np.array([3.0, 2.0, 1.0])) == -1.0
    assert msr.rankdata(np.array([2.0, 1.0, 2.0])).tolist() == [2.5, 1.0, 2.5]


def test_tele_frames_are_excluded_and_counted(msr):
    import numpy as np

    keys = ["comb_DJI_1_0001zoom.JPG", "comb_DJI_1_0001tele.JPG", "comb_DJI_1_0002zoom.JPG",
            "comb_DJI_1_0003zoom.JPG"]
    emb = np.eye(4) + 1.0
    species = {k: "a" for k in keys}
    row = {"flight": "20240101_site_wp_m3e", "site": "site", "gps": (9.1, -79.8)}
    inventory = {keys[0]: row, keys[1]: row, keys[2]: {**row, "gps": None}}
    used, excluded = msr.assemble(keys, emb, species, inventory)
    assert used["keys"] == [keys[0]]
    assert excluded == {"tele": 1, "no_species": 0, "no_inventory_row": 1,
                        "no_gps": 1, "no_flight": 0}
    assert msr.is_tele("migrated/DJI_20240911_0001tele.jpg")
    assert not msr.is_tele("comb_DJI_20240911_0001zoom.JPG")
