"""Two per-frame rates read on the same species mix.

A per-frame rate is a weighted average of per-species rates, weighted by how
many frames each species has. Two populations that hold different species in
different shares can differ by many points without the model doing better on
any one species. This compares them the way the reference analysis in
bci-dashboard-docs/rasha-qc-2026-09-28/source_group_composition.py did: keep
the species both populations hold, reweight each population's per-species rate
to one common mix (both populations' frames on that species, added), and
report the difference with a within-species bootstrap interval.

Species found in only one population cannot be matched and are counted, not
dropped quietly.

Read with the standard library only, like everything under dashboard/.
"""

from __future__ import annotations

import random
from collections import defaultdict

BOOTSTRAP = 2000
SEED = 0


def by_species(pairs) -> dict:
    """species -> list of bools from (species, hit) pairs."""
    out = defaultdict(list)
    for species, hit in pairs:
        out[species].append(bool(hit))
    return dict(out)


def _rate(hits) -> float:
    return sum(hits) / len(hits)


def _standardized(pop: dict, shared, weights: dict, total: int) -> float:
    return sum(weights[s] * _rate(pop[s]) for s in shared) / total


def compare(a: dict, b: dict, *, n_boot: int = BOOTSTRAP, seed: int = SEED) -> dict:
    """Species-mix-adjusted comparison of population ``b`` against ``a``.

    ``a`` and ``b`` map species -> list of per-frame hits (bools). Returns the
    shared-species count, each population's frames and raw per-frame rate on
    the shared species, each one's rate reweighted to the combined species mix,
    ``difference`` (b minus a, as a fraction) with a percentile bootstrap 95%
    interval, and the frames and species left out because only one population
    holds them. Frames are resampled within each species and population, the
    weights stay fixed, and the seed is fixed so a rebuild prints the same
    interval. No shared species gives None for every rate, not an error.
    """
    for name, pop in (("a", a), ("b", b)):
        empty = [s for s, hits in pop.items() if not hits]
        if empty:
            raise ValueError(
                f"population {name} has species with no frames: {empty[:3]}"
            )
    shared = sorted(set(a) & set(b))
    only = {k: sorted(set(p) - set(shared)) for k, p in (("a", a), ("b", b))}
    out = {
        "n_shared_species": len(shared),
        "excluded": {
            k: {"species": len(only[k]), "frames": sum(len(p[s]) for s in only[k])}
            for k, p in (("a", a), ("b", b))
        },
        "frames": {k: sum(len(p[s]) for s in shared) for k, p in (("a", a), ("b", b))},
        "raw": {"a": None, "b": None},
        "standardized": {"a": None, "b": None},
        "difference": None,
        "ci95": None,
        "n_boot": n_boot,
        "seed": seed,
    }
    if not shared:
        return out
    weights = {s: len(a[s]) + len(b[s]) for s in shared}
    total = sum(weights.values())
    out["raw"] = {
        k: sum(sum(p[s]) for s in shared) / out["frames"][k]
        for k, p in (("a", a), ("b", b))
    }
    std = {k: _standardized(p, shared, weights, total) for k, p in (("a", a), ("b", b))}
    out["standardized"] = std
    out["difference"] = std["b"] - std["a"]
    if n_boot > 0:
        rng = random.Random(seed)
        draws = []
        for _ in range(n_boot):
            sa = {s: rng.choices(a[s], k=len(a[s])) for s in shared}
            sb = {s: rng.choices(b[s], k=len(b[s])) for s in shared}
            draws.append(
                _standardized(sb, shared, weights, total)
                - _standardized(sa, shared, weights, total)
            )
        draws.sort()
        out["ci95"] = (
            draws[int(0.025 * n_boot)],
            draws[max(int(0.975 * n_boot) - 1, 0)],
        )
    return out
