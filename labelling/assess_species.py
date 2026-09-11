"""
Say, per species, what would help: more labels, or a better model.

The species table on the model-health page says where Pl@ntNet is wrong. It
cannot say why, or what to do about it, because every rule that can is in
labelfirst and speciesfirst and ``dashboard/`` is standard library only. So
this script runs those rules here, in the speciesfirst virtualenv, and writes
what they found into ``data/model_health/`` as JSON that the page reads with
the standard library. Nothing is re-derived on the page. Every file carries the
sha256 of the inputs it was computed from, and the builder refuses to build a
page on a file whose inputs have moved.

Four files, one question each:

``transductive.json``
    Hold back half the labelled frames of every species, at random, and ask
    whether a nearest-neighbour rule over how the photos look to the model
    recovers the other half. ``labelfirst.eval.transductive`` then says per
    species whether the gap is sampling-limited (the rule saw no example),
    classifier-limited (it saw examples and still failed) or resolved. Drawn
    ``SEEDS`` times, so a verdict that flips with the draw is reported as such.

``disagreement.json``
    Every labelled frame where the first guess is confidently wrong, and why
    the two names conflict, from ``speciesfirst.disagreement``: two names for
    one accepted taxon is an artefact and not a disagreement; a label coarser
    than the guess is not one either. The page shows the review queue grouped
    by that reason.

``reject_sweep.json``
    ``speciesfirst.reject.sweep_thresholds_cv``: if only frames whose plausible
    names fit in a set of k are trusted, how many frames is that and how often
    is the first of them right. The classifier swept is a logistic regression
    over the embeddings, cross-validated, not Pl@ntNet's own answer. The page
    says so, and reads it as queue position, never as a label. Swept twice:
    ``rows`` with folds drawn frame by frame, ``grouped_rows`` with every
    flight whole in one fold, so no frame is judged by a model that trained on
    its near-copies from the same flight.

``status.json``
    Chao1 over every frame labelled to species: how many species the labels
    have reached and how many more the singleton count suggests are still out
    there. No embeddings needed.

Runs against the speciesfirst virtualenv, which carries labelfirst. Point
``SPECIESFIRST`` at that checkout:

  "$SPECIESFIRST/.venv/bin/python" labelling/assess_species.py

Re-running on unchanged inputs rewrites every file byte for byte: no clock is
written, only the inputs' hashes and the library versions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "dashboard"))

import core as hc
import health as hl
import labelfirst
import numpy as np
import sklearn
import speciesfirst
from draw_field_sample import load_flights
from embeddings_io import l2_normalise, load_embeddings
from labelfirst.eval.diagnose.richness import estimate_richness
from labelfirst.eval.transductive import (
    DEFAULT_FRAC_LABELED_FLOOR,
    DEFAULT_RESOLVED_ACC,
)
from labelfirst.io.queue import sha256_file
from sklearn.preprocessing import LabelEncoder
from speciesfirst.disagreement import crown_map_disagreement
from speciesfirst.reject import sweep_thresholds_cv
from speciesfirst.transductive import transductive_report

REPO = Path(__file__).resolve().parents[1]
DEFAULT_NPZ = REPO / "data" / "embeddings_labelled" / "embeddings.npz"
DEFAULT_CACHE = REPO / "data" / "embeddings_labelled" / "cache"
DEFAULT_OUT_DIR = REPO / "data" / "model_health"

# The transductive draw. Half the frames labelled, as labelfirst's own CLI
# defaults to, and as many draws as rank_queue.py's audit uses, so one
# unlucky draw cannot decide a verdict on its own.
LABELED_FRAC = 0.5
SEEDS = tuple(range(8))
K_NEIGHBOURS = 5
# The accept-set sizes the sweep tries. 50 is left out: with five names
# requested per photo, a set that wide is every name.
SWEEP_SIZES = (1, 2, 3, 5, 10)
SWEEP_ALPHA = 0.10
SWEEP_FOLDS = 5
SWEEP_SEED = 42


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=hc.summarise(__doc__))
    p.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return p.parse_args(argv)


def provenance(h, *, gt_csv: str, npz: Path | None) -> dict:
    """What every file was computed from: hashes, not dates, so an unchanged
    input rewrites an unchanged file and a changed one is caught by the reader."""
    inputs = {"gt_csv": os.path.relpath(gt_csv, REPO),
              "gt_sha256": sha256_file(gt_csv),
              "gt_provenance": hc.gt_provenance(gt_csv)}
    if npz is not None:
        inputs["embeddings_npz"] = os.path.relpath(npz, REPO)
        inputs["embeddings_sha256"] = sha256_file(npz)
    return {"inputs": inputs,
            "library": {"speciesfirst": speciesfirst.__version__,
                        "labelfirst": labelfirst.__version__,
                        "scikit-learn": sklearn.__version__,
                        "numpy": np.__version__}}


def embedded_frames(h, keys: list[str], emb: np.ndarray):
    """The frames both scored on the page and carrying an embedding, in
    ``h.sp_recs`` order, with their canonical label. The population every
    embedding-based file below is measured over."""
    at = {k: i for i, k in enumerate(keys)}
    recs = [r for r in h.sp_recs if r["global_key"] in at]
    X = l2_normalise(emb[[at[r["global_key"]] for r in recs]])
    return recs, X, [r["gt"] for r in recs]


def assess_transductive(X, labels: list[str]) -> dict:
    """One verdict per species, the majority over ``SEEDS`` draws, with how
    many draws agreed. Every species is written; the page applies its own
    floor, so the floor is a page decision and not buried here."""
    verdicts: dict[str, Counter] = defaultdict(Counter)
    acc: dict[str, list] = defaultdict(list)
    for seed in SEEDS:
        mask = np.random.default_rng(seed).random(len(labels)) < LABELED_FRAC
        rep = transductive_report(X, labels, mask, k=K_NEIGHBOURS, seed=seed)
        for sp, rec in rep.per_species.items():
            verdicts[sp][rec["limit"]] += 1
            acc[sp].append(rec["transductive_acc"])
    n_total = Counter(labels)
    per_species = {}
    for sp in sorted(verdicts):
        limit, agreeing = verdicts[sp].most_common(1)[0]
        per_species[sp] = {
            "n_frames": n_total[sp],
            "limit": limit,
            "seeds_agreeing": agreeing,
            "verdicts": dict(sorted(verdicts[sp].items())),
            "mean_transductive_acc": round(float(np.mean(acc[sp])), 6),
        }
    return {
        "method": {"rule": "labelfirst.eval.transductive.transductive_eval",
                   "labeled_frac": LABELED_FRAC, "seeds": list(SEEDS),
                   "k": K_NEIGHBOURS, "resolved_acc": DEFAULT_RESOLVED_ACC,
                   "frac_labeled_floor": DEFAULT_FRAC_LABELED_FLOOR},
        "population": {"n_frames": len(labels), "n_species": len(n_total),
                       "n_seeds": len(SEEDS)},
        "summary": dict(Counter(v["limit"] for v in per_species.values())),
        "per_species": per_species,
    }


def mechanism_of(gt: str, guess: str, accepted) -> str:
    """The builder's verdict on why a label and a guess differ, in the
    vocabulary ``crown_map_disagreement`` takes. Liana overgrowth needs a
    growth-habit table and none is on disk, so it is never returned here."""
    if not hc.is_species_level(gt):
        return "coarser_label"
    if accepted(gt) and accepted(gt) == accepted(guess):
        return "synonym_artifact"
    return "species_conflict"


def assess_disagreement(h) -> dict:
    """Every confident first-guess-versus-label conflict, with why."""
    wcvp = {}
    if hc.WCVP_CACHE_JSON:
        with open(hc.WCVP_CACHE_JSON, encoding="utf-8") as f:
            wcvp = {k.lower(): v for k, v in json.load(f).items()}

    def accepted(name: str) -> str:
        return (wcvp.get(name.lower()) or {}).get("accepted_name") or ""

    conflicts = [r for r in h.sp_recs
                 if r["ranked"][0][0] != r["gt"] and r["ranked"][0][1] >= hc.REVIEW_CONF]
    guesses = [r["ranked"][0][0] for r in conflicts]
    mechanisms = [mechanism_of(r["gt"], g, accepted) for r, g in zip(conflicts, guesses)]
    result = crown_map_disagreement(guesses, [r["gt"] for r in conflicts],
                                    mechanisms=mechanisms)
    reason = dict(zip(result.indices.tolist(), result.reasons))
    frames = {}
    for i, r in enumerate(conflicts):
        frames[r["global_key"]] = {
            "predicted": guesses[i], "crown_species": r["gt"],
            "predicted_score": round(float(r["ranked"][0][1]), 6),
            "mechanism": mechanisms[i],
            # None where the library suppressed the frame: nothing to review.
            "reason": reason.get(i),
        }
    return {
        "method": {"rule": "speciesfirst.disagreement.crown_map_disagreement",
                   "review_conf": hc.REVIEW_CONF,
                   "synonyms_from": os.path.relpath(hc.WCVP_CACHE_JSON, REPO)
                   if hc.WCVP_CACHE_JSON else None,
                   "habit_source": None},
        "population": {"n_scored": len(h.sp_recs), "n_conflicts": len(conflicts),
                       "n_flagged": int(result.n_flagged)},
        "summary": dict(sorted(Counter(mechanisms).items())),
        "frames": dict(sorted(frames.items())),
    }


def flight_groups(keys: list[str], flights: dict[str, str]) -> list[str]:
    """One fold group per frame: its flight, or the frame itself when its URL
    carries no mission folder. An unplaced frame can share a fold with nothing
    it is known to be a near-copy of, so it stands alone and is counted."""
    return [flights.get(k) or f"unplaced:{k}" for k in keys]


def assess_reject_sweep(X, labels: list[str], groups: list[str]) -> dict:
    y = LabelEncoder().fit_transform(labels)
    kw = {"alpha": SWEEP_ALPHA, "n_folds": SWEEP_FOLDS, "seed": SWEEP_SEED,
          "thresholds": list(SWEEP_SIZES)}
    unplaced = sum(1 for g in groups if g.startswith("unplaced:"))
    return {
        "method": {"rule": "speciesfirst.reject.sweep_thresholds_cv",
                   "classifier": "StandardScaler + LogisticRegression(C=1.0) over "
                                 "the embeddings, cross-conformal; not Pl@ntNet",
                   "alpha": SWEEP_ALPHA, "n_folds": SWEEP_FOLDS, "seed": SWEEP_SEED,
                   "max_set_sizes": list(SWEEP_SIZES),
                   "grouped_by": "flight (yyyymmdd/site from the frame URL's mission "
                                 "folder), GroupKFold"},
        "population": {"n_frames": len(labels), "n_species": len(set(labels)),
                       "n_flights": len(set(groups)) - unplaced,
                       "n_unplaced": unplaced},
        "rows": sweep_thresholds_cv(X, y, **kw),
        "grouped_rows": sweep_thresholds_cv(X, y, groups=np.asarray(groups), **kw),
    }


def assess_status(h) -> dict:
    """Chao1 over every frame labelled to species, cached answer or not."""
    names = [h.canon(r["wcvp_canonical_name"]) for r in h.gt_rows
             if r.get("wcvp_canonical_name")]
    species = [n for n in names if hc.is_species_level(n)]
    est = estimate_richness(species)
    return {
        "method": {"rule": "labelfirst.eval.diagnose.richness.estimate_richness",
                   "estimator": "Chao1"},
        "population": {"n_labelled": len(h.gt_rows), "n_species_level": len(species)},
        "richness": {"observed": est.observed, "singletons": est.singletons,
                     "doubletons": est.doubletons, "chao1": round(est.chao1, 3),
                     "unseen_estimate": est.unseen_estimate,
                     "completeness": round(est.completeness, 6),
                     "sample_coverage": round(est.sample_coverage, 6),
                     "discovery_phase": est.discovery_phase},
    }


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
        f.write("\n")


def main(argv=None) -> int:
    args = parse_args(argv)
    h = hl.load_health()
    keys, emb = load_embeddings(args.npz, args.cache_dir)
    recs, X, labels = embedded_frames(h, keys, emb)
    print(f"{len(recs)} of {len(h.sp_recs)} scored frames carry an embedding, "
          f"{len(set(labels))} species")
    npz = args.npz if args.npz.exists() else None
    with_emb = provenance(h, gt_csv=hc.GT_CSV, npz=npz)
    without = provenance(h, gt_csv=hc.GT_CSV, npz=None)

    files = {
        "transductive.json": {"kind": "transductive", **with_emb,
                              **assess_transductive(X, labels)},
        "disagreement.json": {"kind": "disagreement", **without,
                              **assess_disagreement(h)},
        "reject_sweep.json": {"kind": "reject_sweep", **with_emb,
                              **assess_reject_sweep(
                                  X, labels, flight_groups(
                                      [r["global_key"] for r in recs], load_flights()))},
        "status.json": {"kind": "status", **without, **assess_status(h)},
    }
    for name, doc in files.items():
        write_json(args.out_dir / name, doc)
        print(f"  wrote {args.out_dir / name}: {json.dumps(doc.get('summary') or doc.get('richness') or doc['population'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
