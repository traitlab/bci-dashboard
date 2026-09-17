"""The pieces of the queue's evidence audits that are not the ranker.

``labelling/rank_queue.py --confound`` asks whether "looks unlike the labelled
photos" still tracks a rarely-labelled species once a covariate is held fixed.
This module holds the score, the target and the one-audit record it writes,
and the rule for a photo whose covariate cannot be read: it leaves the audit
and is counted, never grouped under "". A group named "" would be a site that
means "we did not look", and today two queued photos have no readable site.

``equalised_anchor_confound`` is the audit that cannot be done by holding a
group fixed. The number of labelled frames a species already has is not a
property of where a frame came from; it is the quantity the distance is
measured against, so the two are coupled before any photo is looked at. The
only way to hold it fixed is to redraw the reference set with every species
lending the same number of frames.

``seeds_agreeing`` serves the other sidecar, ``--audit``: how many of the
random starts came out in this order's favour, which a gain averaged over
starts cannot show. ``separability_other_flight`` serves it too: the
preflight's same-species-neighbour rate, with every neighbour from the frame's
own flight taken away, because frames from one flight overlap.

Needs numpy and labelfirst, like the ranker that imports it.
"""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
from labelfirst.eval.confound import confound_audit
# The verdict thresholds, the between-group variance share and the rank-vector
# correlation labelfirst's own audit uses. Imported rather than restated so the
# fifth audit is classified by the same rule as the four beside it; a copy here
# would drift the day labelfirst moves a threshold.
from labelfirst.eval.confound import _eta_squared, _pearson, _verdict
from scipy import stats


def loo_distance(X: np.ndarray) -> np.ndarray:
    """Each labelled frame's distance to the nearest *other* labelled frame:
    the score the queue uses, measured where the species is known."""
    sim = X @ X.T
    np.fill_diagonal(sim, -np.inf)
    return 1.0 - sim.max(axis=1)


def separability_other_flight(X: np.ndarray, labels, flights: list[str]) -> dict:
    """How often a labelled frame's nearest other frame has its species, as
    labelfirst's preflight counts it, and again with only frames from another
    flight allowed as that neighbour.

    Frames from one flight (one date at one site) overlap, so the first rate
    can rest on near-copies. Both rates are over the same rows: a frame whose
    flight cannot be read leaves both and is counted, as in ``one_confound``.
    """
    keep = [i for i, f in enumerate(flights) if f]
    y = np.asarray(labels)[keep]
    group = np.asarray([flights[i] for i in keep])
    sim = X[keep] @ X[keep].T
    np.fill_diagonal(sim, -np.inf)
    any_flight = float((y[sim.argmax(axis=1)] == y).mean())
    sim[group[:, None] == group[None, :]] = -np.inf
    # A frame on a flight that holds every labelled frame has no other-flight
    # neighbour; argmax would pick one at -inf, so it is refused instead.
    if not np.isfinite(sim.max(axis=1)).all():
        raise SystemExit("a labelled frame has no frame from another flight to compare with")
    other_flight = float((y[sim.argmax(axis=1)] == y).mean())
    return {"pct_any_flight": 100 * any_flight, "pct_other_flight": 100 * other_flight,
            "n_frames": len(keep), "n_flights": len(set(group)),
            "n_unreconciled": len(flights) - len(keep)}


def rarity(counts: dict[str, int], names) -> np.ndarray:
    """Higher for a species with fewer labelled frames. The audit's target: what
    the ordering claims to reach first."""
    return np.array([-np.log1p(counts.get(n, 0)) for n in names], dtype=np.float64)


def without_unreconciled(score, target, covariate: list[str]):
    """The rows whose covariate could be read, and how many could not.

    Returns ``((score, target, covariate), n_unreconciled)``. The audit that
    follows sees only rows with a real group, so the count is the only trace
    the left-out photos leave, and the page prints it beside the verdict.
    """
    keep = [i for i, c in enumerate(covariate) if c]
    kept = (np.asarray(score)[keep], np.asarray(target)[keep],
            [covariate[i] for i in keep])
    return kept, len(covariate) - len(keep)


def one_confound(population, score, target, covariate, *, score_name, target_name,
                 covariate_name) -> dict:
    """One of labelfirst's confound audits as the record the page reads, with
    the unreadable-covariate rows left out and counted."""
    (score, target, covariate), n_unreconciled = without_unreconciled(
        score, target, covariate)
    res = confound_audit(score, target, covariate)
    d = asdict(res)
    d["within_group"] = {g: {"spearman": r, "n": n} for g, (r, n) in res.within_group.items()}
    return {"population": population, "score": score_name, "target": target_name,
            "covariate": covariate_name, "n_groups": len(res.within_group),
            "n_unreconciled": n_unreconciled, **d}


def seeds_agreeing(challenger_aucs, baseline_aucs) -> int:
    """How many random starts this order beat the random one on, by area under
    the rare-species curve. A tie is not a start in this order's favour."""
    return sum(1 for c, b in zip(challenger_aucs, baseline_aucs) if c > b)


# The fifth audit's covariate, named once: the ranker writes it into the record
# and the page's PLURAL table reads the same string back.
ANCHOR_COVARIATE = "labelled-frames count per species"
# How many labelled frames each species contributes to the reference set when
# that count is held fixed, how many draws the mean is taken over, and the seed.
# One anchor a species is the setting the independent control at
# where-to-blitz-docs/voi-controls/bci_support_control.py reports, so the two
# numbers can be read against each other; twenty draws is that control's count.
ANCHORS_PER_SPECIES = 1
EQUALISED_DRAWS = 20
EQUALISED_SEED = 0
# Label shuffles behind the permutation p, matching labelfirst's own default in
# ``confound_audit`` so the smallest reportable p is the same 1/5001 the other
# four audits print.
EQUALISED_PERMUTATIONS = 5000


def spearman_rho(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman's rho, average ranks for ties. The target is ``-log1p`` of a
    species' labelled-frame count, so it ties heavily and ordinal ranks would
    break those ties in whatever order the rows happen to sit in."""
    rho, _ = stats.spearmanr(a, b)
    return float(rho)


def _standard_ranks(values: np.ndarray) -> np.ndarray:
    """Average ranks, centred and scaled so a dot product of two such vectors is
    their Spearman rho. A shuffle of one of them leaves both the centring and
    the scale alone, which is what makes a permutation null one dot product."""
    ranks = np.asarray(stats.rankdata(values, method="average"), dtype=np.float64)
    ranks -= ranks.mean()
    norm = float(np.linalg.norm(ranks))
    if norm == 0.0:
        raise SystemExit("a draw has no spread to correlate")
    return ranks / norm


def frames_by_species(labels) -> dict[str, list[int]]:
    """Row numbers per species, in the order the frames are read."""
    by: dict[str, list[int]] = {}
    for i, s in enumerate(labels):
        by.setdefault(s, []).append(i)
    return by


def _equalised_draw(X, by, elig, counts, labels, rng, per_species: int):
    """One draw: every eligible species contributes ``per_species`` anchors, and
    every other eligible frame is a query scored against that reference set.

    Returns ``(distance, target, n_anchors)``. The query's own frame is never an
    anchor, so this is the same quantity the queue scores a photo on, with the
    one thing the shipped audit leaves free, how many anchors a species has,
    held fixed by construction rather than residualised away.
    """
    anchors: list[int] = []
    for s in elig:
        anchors.extend(int(i) for i in rng.choice(by[s], size=per_species, replace=False))
    taken = set(anchors)
    queries = [i for s in elig for i in by[s] if i not in taken]
    distance = 1.0 - (X[queries] @ X[anchors].T).max(axis=1)
    target = np.array([-np.log1p(counts[labels[i]]) for i in queries], dtype=np.float64)
    return distance, target, len(anchors)


def equalised_anchor_confound(X: np.ndarray, labels, counts, *,
                              per_species: int = ANCHORS_PER_SPECIES,
                              draws: int = EQUALISED_DRAWS,
                              seed: int = EQUALISED_SEED,
                              n_permutations: int = EQUALISED_PERMUTATIONS) -> dict:
    """The audit the other four cannot do: hold the number of labelled frames a
    species already has fixed.

    ``distance`` is one minus the largest cosine to any labelled frame, and the
    target is minus ``log1p`` of the species' labelled-frame count. A species
    with a single labelled frame cannot score low on that distance, because the
    only frame it could be close to is itself, so the two quantities are coupled
    by how the score is built and not by anything about the species. Holding
    the site, the flight or the export batch fixed leaves that coupling alone.

    Equalising does break it: every eligible species puts the same number of
    frames into the reference set, so no species is easier to be far from than
    another. ``raw_corr`` is the shipped leave-one-out correlation on exactly
    the frames that survive the equalisation, so the drop to ``partial_corr``
    is the equalisation and not the narrower set of species. The record has the
    same keys as ``one_confound``'s, so the page reads it with the others.
    """
    labels = list(labels)
    by = frames_by_species(labels)
    elig = [s for s, rows in by.items() if len(rows) >= per_species + 1]
    if len(elig) < 2:
        raise SystemExit(f"fewer than two species have {per_species + 1} labelled "
                         f"frames; there is no anchor count to equalise")
    kept = np.array([i for s in elig for i in by[s]])
    target_kept = rarity(counts, [labels[i] for i in kept])
    loo = loo_distance(X[kept])
    raw_corr, raw_p = stats.spearmanr(loo, target_kept)
    # How much of the distance is the species' labelled-frame count alone, by
    # the same one-way measure labelfirst uses for a site or an export batch.
    eta2 = _eta_squared(loo, np.array([str(counts[labels[i]]) for i in kept], dtype=object))

    rng = np.random.default_rng(seed)
    per_draw, standardised, n_anchors = [], [], 0
    for _ in range(draws):
        distance, target, n_anchors = _equalised_draw(
            X, by, elig, counts, labels, rng, per_species)
        per_draw.append((spearman_rho(distance, target), len(distance)))
        standardised.append((_standard_ranks(distance), _standard_ranks(target)))
    rhos = np.array([r for r, _ in per_draw], dtype=np.float64)
    partial = float(rhos.mean())

    # The p-value, on the same rule the other four use: shuffle the target and
    # see how often chance alone reaches this far. Shuffled once per draw and
    # averaged over the draws, so the null is a null for the number reported and
    # not for one draw of it, which would be a wider null and a kinder p.
    # Spearman on standardised ranks is their dot product, and a shuffle leaves
    # the standardisation alone, so each shuffle is one dot product.
    perm = np.random.default_rng(seed + 1)
    null = np.array([float(np.mean([s_hat @ perm.permutation(t_hat)
                                    for s_hat, t_hat in standardised]))
                     for _ in range(n_permutations)], dtype=np.float64)
    partial_p = float((1 + int((np.abs(null) >= abs(partial)).sum()))
                      / (n_permutations + 1))

    retained = abs(partial) / abs(raw_corr) if abs(raw_corr) > 0 else 0.0
    return {
        "population": "labelled frames",
        "score": "distance to the nearest labelled frame of any species",
        "target": "fewer labelled frames for its species",
        "covariate": ANCHOR_COVARIATE,
        "n_groups": len(elig),
        "n_unreconciled": len(labels) - len(kept),
        "raw_corr": float(raw_corr),
        "raw_p": float(raw_p),
        "covariate_eta2": float(eta2),
        "partial_corr": partial,
        "partial_p": partial_p,
        "retained_fraction": float(retained),
        "within_group": {f"draw {i + 1:02d}": {"spearman": r, "n": n}
                         for i, (r, n) in enumerate(per_draw)},
        "verdict": _verdict(float(raw_corr), partial, partial_p, float(retained)),
        "n": per_draw[0][1],
        "anchors_per_species": per_species,
        "n_anchors": n_anchors,
        "n_draws": draws,
        "draw_seed": seed,
        "partial_corr_min": float(rhos.min()),
        "partial_corr_max": float(rhos.max()),
        "n_permutations": n_permutations,
    }
