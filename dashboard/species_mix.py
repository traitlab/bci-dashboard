"""Two per-frame rates read on the same species mix.

A per-frame rate is a weighted average of per-species rates, weighted by how
many frames each species has. Two populations that hold different species in
different shares can differ by many points without the model doing better on
any one species. This compares them the way the reference analysis in
bci-dashboard-docs/rasha-qc-2026-09-28/source_group_composition.py did: keep
the species both populations hold, reweight each population's per-species rate
to one common mix, and report the difference with its range.

The common mix is read three ways, because the sign of the difference can turn
on which one is used: both populations' frames on each species added (the
headline), the first population's own mix, and the second's.

The range draws whole sites, not single frames: frames from one site are alike,
so a frame-level draw is too narrow. The draw is score_confirmatory's, reused
with its 10,000 draws and its seed.

Species found in only one population cannot be matched and are counted, not
dropped quietly.

Read with the standard library only, like everything under dashboard/.
"""

from __future__ import annotations

from collections import defaultdict

from score_confirmatory import BOOTSTRAP_DRAWS, SEED, cluster_bootstrap

POPS = ("a", "b")
# The three common mixes. "combined" is the headline; "a" and "b" are each
# population's own frames per species.
WEIGHTINGS = ("combined", "a", "b")


def by_site(frames) -> dict:
    """site -> species -> [hits, frames] from (species, site, hit) triples."""
    out = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for species, site, hit in frames:
        cell = out[site][species]
        cell[0] += bool(hit)
        cell[1] += 1
    return {
        site: {s: tuple(c) for s, c in cells.items()} for site, cells in out.items()
    }


def _pool(cells) -> dict:
    """species -> (hits, frames) summed over an iterable of site cells."""
    out = defaultdict(lambda: [0, 0])
    for species_cells in cells:
        for s, (h, n) in species_cells.items():
            out[s][0] += h
            out[s][1] += n
    return {s: tuple(c) for s, c in out.items()}


def _standardized(pooled: dict, species, weights: dict) -> float:
    """The per-species rates on ``species`` averaged by ``weights``, which are
    renormalised over the species given."""
    total = sum(weights[s] for s in species)
    return sum(weights[s] * pooled[s][0] / pooled[s][1] for s in species) / total


def _range(sites: dict, shared, weights: dict, n_draws: int, seed: int):
    """95% range of b minus a, drawing whole sites at random with replacement.

    A drawn site brings its frames in both populations. A shared species that
    the draw left with no frame in either population is dropped from both
    sides for that draw, and the weights renormalised over the species left;
    such draws are counted as ``short``. A draw that leaves no shared species
    on both sides has no difference and is counted as ``empty``.
    """
    rows = [{"site": s, **cells} for s, cells in sites.items()]
    count = {"short": 0, "empty": 0}

    def diff(sample):
        pooled = {k: _pool(r[k] for r in sample) for k in POPS}
        kept = [s for s in shared if s in pooled["a"] and s in pooled["b"]]
        if not kept:
            count["empty"] += 1
            return None
        if len(kept) < len(shared):
            count["short"] += 1
        return _standardized(pooled["b"], kept, weights) - _standardized(
            pooled["a"], kept, weights
        )

    ci = cluster_bootstrap(rows, "site", diff, n_draws, seed)
    return (None if count["empty"] == n_draws else ci), count


def compare(a, b, *, n_draws: int = BOOTSTRAP_DRAWS, seed: int = SEED) -> dict:
    """Species-mix-adjusted comparison of population ``b`` against ``a``.

    ``a`` and ``b`` are iterables of (species, site, hit) per frame. Returns
    the shared-species count, each population's frames and raw per-frame rate
    on the shared species, and under ``weightings`` each common mix
    (``WEIGHTINGS``): both rates reweighted to it, ``difference`` (b minus a,
    as a fraction) and its 95% range ``ci95``. Also the frames and species
    left out because only one population holds them, the sites, and how many
    of the ``n_draws`` draws came up short or empty (``_range``). The draws
    and the seed are the same for every weighting, so the counts are too. No
    shared species gives None for every rate, not an error.
    """
    sites = {k: by_site(p) for k, p in (("a", a), ("b", b))}
    pooled = {k: _pool(sites[k].values()) for k in POPS}
    shared = sorted(set(pooled["a"]) & set(pooled["b"]))
    only = {k: sorted(set(pooled[k]) - set(shared)) for k in POPS}
    out = {
        "n_shared_species": len(shared),
        "excluded": {
            k: {
                "species": len(only[k]),
                "frames": sum(pooled[k][s][1] for s in only[k]),
            }
            for k in POPS
        },
        "frames": {k: sum(pooled[k][s][1] for s in shared) for k in POPS},
        "raw": {"a": None, "b": None},
        "weightings": {},
        "n_sites": len(set(sites["a"]) | set(sites["b"])),
        "n_draws": n_draws,
        "draws_short": 0,
        "draws_empty": 0,
        "seed": seed,
    }
    if not shared:
        return out
    out["raw"] = {
        k: sum(pooled[k][s][0] for s in shared) / out["frames"][k] for k in POPS
    }
    both = {
        s: {k: sites[k].get(s, {}) for k in POPS}
        for s in set(sites["a"]) | set(sites["b"])
    }
    for name in WEIGHTINGS:
        weights = {
            s: sum(pooled[k][s][1] for k in POPS if name in (k, "combined"))
            for s in shared
        }
        std = {k: _standardized(pooled[k], shared, weights) for k in POPS}
        ci, count = (
            _range(both, shared, weights, n_draws, seed) if n_draws > 0 else (None, {})
        )
        out["weightings"][name] = {
            "standardized": std,
            "difference": std["b"] - std["a"],
            "ci95": ci,
        }
        out["draws_short"] = count.get("short", 0)
        out["draws_empty"] = count.get("empty", 0)
    return out
