"""The pieces of the queue's evidence audits that are not the ranker.

``labelling/rank_queue.py --confound`` asks whether "looks unlike the labelled
photos" still tracks a rarely-labelled species once a covariate is held fixed.
This module holds the score, the target and the one-audit record it writes,
and the rule for a photo whose covariate cannot be read: it leaves the audit
and is counted, never grouped under "". A group named "" would be a site that
means "we did not look", and today two queued photos have no readable site.

``seeds_agreeing`` serves the other sidecar, ``--audit``: how many of the
random starts came out in this order's favour, which a gain averaged over
starts cannot show.

Needs numpy and labelfirst, like the ranker that imports it.
"""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
from labelfirst.eval.confound import confound_audit


def loo_distance(X: np.ndarray) -> np.ndarray:
    """Each labelled frame's distance to the nearest *other* labelled frame:
    the score the queue uses, measured where the species is known."""
    sim = X @ X.T
    np.fill_diagonal(sim, -np.inf)
    return 1.0 - sim.max(axis=1)


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
