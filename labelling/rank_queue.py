"""
Order the label queue by how unlike the labelled photos each one looks.

The queue in ``build/tables/send_first_queue.csv`` sorts each of its four queues
by the model's confidence. Confidence says nothing about a species with almost
no labels, and it does not mean the same thing on both cameras, so it is a weak
answer to "which photo next". This gives a better one: inside a queue, send the
photo that looks least like everything already labelled.

"Looks like" is the Pl@ntNet embedding (``predict/embed.py``): 768 numbers per
centre crop, where two photos with close numbers look alike to the model. The
order is farthest-first, ``labelfirst.strategies.kcenter.greedy_kcenter``: pick
the photo furthest from every labelled photo, then the one furthest from the
labelled photos *and* from what has been picked, and so on. No label and no
prediction steers it, which is what makes ``--backtest`` an honest claim.

The output is a plain CSV. ``dashboard/`` reads it with the standard library and
never sees a vector: with the file absent every frame ties and the queue keeps
the confidence order it has today.

Runs against the speciesfirst virtualenv, which carries labelfirst. Point
``SPECIESFIRST`` at that checkout:

  "$SPECIESFIRST/.venv/bin/python" labelling/rank_queue.py
  "$SPECIESFIRST/.venv/bin/python" labelling/rank_queue.py --backtest \
      --species-csv data/gt_dominant_taxon.csv
  "$SPECIESFIRST/.venv/bin/python" labelling/rank_queue.py --audit \
      --species-csv data/gt_dominant_taxon.csv
  "$SPECIESFIRST/.venv/bin/python" labelling/rank_queue.py --confound \
      --species-csv data/gt_dominant_taxon.csv

A frame that carries a split in ``data/splits.csv``, or that the flight holdout
in ``input/holdout_v1.csv`` holds, is never sent, so it is dropped from the pool
before ranking: left in, farthest-first keeps spending picks on frames that can
never be labelled, and those picks are ranks the sendable frames behind them
never get. ``labelling/pool_filters.py`` does both drops and the run record
counts them apart.

``--audit`` and ``--confound`` write the two evidence files the queue page
reads beside the ordering: whether this order finds rare species faster than a
random one on the labelled frames, over several random starts, and whether
"looks unlike the labelled frames" tracks a rarely-labelled species once the
site, the flight, or the export batch, is held fixed. Both are labelfirst's own
tests, so the page quotes a number it did not make up.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from draw_field_sample import load_flights, load_sites
from embeddings_io import l2_normalise, load_embeddings
from labelfirst.eval.audit import audit, render_markdown
from labelfirst.eval.diagnose.separability import predict_al_benefit
from labelfirst.eval.efficiency import annotation_efficiency
from labelfirst.eval.simulate import simulate
from labelfirst.io.queue import RunRecord, sha256_file
from labelfirst.strategies.kcenter import greedy_kcenter
from pool_filters import (
    drop_holdout_frames, drop_split_frames, load_holdout, load_splits)
from rank_confound import (loo_distance, one_confound, rarity, seeds_agreeing,
                           separability_other_flight)
from speciesfirst import backtest_species_coverage

REPO = Path(__file__).resolve().parents[1]
DEFAULT_POOL_NPZ = REPO / "data" / "embeddings_queue" / "embeddings.npz"
DEFAULT_POOL_CACHE = REPO / "data" / "embeddings_queue" / "cache"
DEFAULT_ANCHOR_NPZ = REPO / "data" / "embeddings_labelled" / "embeddings.npz"
DEFAULT_ANCHOR_CACHE = REPO / "data" / "embeddings_labelled" / "cache"
DEFAULT_OUT = REPO / "data" / "next_batch" / "queue_novelty.csv"
DEFAULT_DISCOVERY = REPO / "data" / "next_batch" / "discovery_curve.csv"
DEFAULT_NOVELTY_CURVE = REPO / "data" / "next_batch" / "novelty_curve.csv"
DEFAULT_SPLITS = REPO / "data" / "splits.csv"
# The whole-flight holdout labelling/draw_holdout.py drew. Tracked under
# input/ rather than data/ because the pool it was drawn from moves.
DEFAULT_HOLDOUT = REPO / "input" / "holdout_v1.csv"
DEFAULT_QUEUE_CSV = REPO / "build" / "tables" / "send_first_queue.csv"
DEFAULT_INVENTORY = REPO / "data" / "dataset_rows_combined.jsonl"
DEFAULT_AUDIT = REPO / "data" / "next_batch" / "selection_audit.json"
DEFAULT_CONFOUND = REPO / "data" / "next_batch" / "selection_confound.json"
# The sidecar labelfirst writes beside a queue: `<csv>.run.json`. The page reads
# it through `dashboard/queues.novelty_provenance`.
RUN_RECORD_SUFFIX = ".run.json"
STRATEGY = "coreset"
# The audit's shape. Eight random starts is the floor at which a one-sided
# paired test can reach p < 0.005 at all (1/2^8), which is what the labelfirst
# reference audit on BCI used. Twenty rounds of twenty is 400 picks on top of a
# 200-frame random start: a third of the labelled frames, enough for the two
# orders to part and short enough to run in minutes.
AUDIT_SEEDS = 8
AUDIT_ROUNDS = 20
AUDIT_K = 20
AUDIT_SEED_POOL = 200
# A species with this many labelled frames or fewer is "rare" for the audit,
# labelfirst's own default.
RARE_THRESHOLD = 5
TOP_DECILE = 0.10
# Both curve files are drawn on a page 620 pixels wide, so a point per photo
# would be four thousand points nobody can see and a path nobody can read.
CURVE_POINTS = 120


def camera_of(key: str) -> str:
    """Which drone camera shot a frame, read off its key. The same rule as
    ``dashboard/figures.py:camera_of``, so the two agree on the count."""
    low = key.lower()
    for c in ("zoom", "tele"):
        if c in low:
            return c
    return "unknown"


def load_species(path: Path, key_col: str, species_col: str) -> dict[str, str]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {key_col, species_col} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{path}: missing column(s) {sorted(missing)}")
        return {r[key_col]: r[species_col] for r in reader if r[key_col] and r[species_col]}


def camera_mix(keys: list[str]) -> dict[str, float]:
    counts = Counter(camera_of(k) for k in keys)
    total = sum(counts.values()) or 1
    return {c: n / total for c, n in sorted(counts.items())}


def rank_pool(anchor_emb: np.ndarray, pool_emb: np.ndarray) -> tuple[list[int], np.ndarray]:
    """Farthest-first order over the pool, and each row's distance to the
    labelled set.

    The order is what ``greedy_kcenter`` returns. The distance is computed here
    and separately, because the greedy pick shrinks its own working distance as
    it goes: reporting that number under a column named "distance to the nearest
    labelled photo" would be reporting a different quantity.
    """
    anchors = l2_normalise(anchor_emb)
    pool = l2_normalise(pool_emb)
    stacked = np.vstack([anchors, pool])
    anchor_idx = np.arange(len(anchors))
    pool_idx = np.arange(len(anchors), len(stacked))
    order = greedy_kcenter(stacked, pool_idx, anchor_idx, len(pool_idx))
    distance = 1.0 - (pool @ anchors.T).max(axis=1)
    return [i - len(anchors) for i in order], distance


def bin_means(values, points: int = CURVE_POINTS) -> list[tuple[int, float, int]]:
    """Split ``values`` into at most ``points`` equal bins, one mean each.

    Returns ``(last_index_1_based, mean, n_in_bin)`` per bin. Binning, not every
    Nth point: the distance to the labelled set falls with rank but is noisy
    photo to photo, and sampling would draw that noise as if it were the trend.
    """
    n = len(values)
    if n == 0:
        return []
    edges = [round(i * n / min(points, n)) for i in range(min(points, n) + 1)]
    out = []
    for lo, hi in itertools.pairwise(edges):
        if hi <= lo:
            continue
        chunk = np.asarray(values[lo:hi], dtype=np.float64)
        out.append((hi, float(chunk.mean()), hi - lo))
    return out


def sample_curve(values, points: int = CURVE_POINTS, keep=()) -> list[int]:
    """Indices spread evenly over ``values``, plus every index in ``keep``.

    The species-coverage curves rise and never fall, so an evenly spread sample
    is the curve, not a summary of it. ``keep`` is for the points a reader is
    given a number for: the page reports where each line crosses half the
    species, and reading that off a thinned curve would print the next sampled
    photo instead of the one the backtest counted.
    """
    n = len(values)
    if n <= points:
        return list(range(n))
    idx = {round(i * (n - 1) / (points - 1)) for i in range(points)}
    idx |= {n - 1} | {k for k in keep if 0 <= k < n}
    return sorted(idx)


def write_discovery_curve(out: Path, result: dict) -> None:
    """The backtest curve, thinned, for the page to draw.

    Population is written into the file, not left to the caller to remember: the
    curve is measured on the photos that already carry a name, which is not the
    queue it is shown beside.
    """
    directed, random_mean = result["directed_curve"], result["random_curve_mean"]
    # The two photo counts the report prints, kept as exact sample points so the
    # page reads the same crossing the backtest counted.
    keep = [int(v) - 1 for v in result["crowns_to_50pct_species"].values()]
    idx = sample_curve(directed, keep=keep)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["photos_named", "species_directed", "species_random"])
        for i in idx:
            w.writerow([i + 1, directed[i], f"{random_mean[i]:.4f}"])
    print(f"wrote {len(idx)} discovery-curve points to {out}")


def write_novelty_curve(out: Path, order: list[int], distance: np.ndarray) -> None:
    """Distance to the labelled set against queue position, in bins.

    This is the stopping cue: where the line flattens, the ordering has stopped
    separating photos and the queue is back to confidence order underneath.
    """
    ordered = [float(distance[i]) for i in order]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["novelty_rank", "mean_distance_to_nearest_labelled", "photos_in_bin"])
        for rank, mean, n in bin_means(ordered):
            w.writerow([rank, f"{mean:.6f}", n])
    print(f"wrote {len(bin_means(ordered))} novelty-curve points to {out}")


def sha_or_absent(path: Path) -> str:
    """The file's SHA-256, or a sentence saying why there is none.

    An npz that is not there is a normal state, not a fault: ``load_embeddings``
    falls back to the per-photo cache, which is what a checkout has while the
    fetch is still running. The record says so rather than stopping, because a
    ranking built off a part-filled cache is exactly the one whose provenance a
    reader needs.
    """
    try:
        return sha256_file(path)
    except FileNotFoundError:
        return "absent, read from the per-photo cache instead"


def run_record(pool_npz: Path, n_pool: int, anchor_npz: Path, n_anchors: int,
               **extra) -> RunRecord:
    """labelfirst's reproducibility envelope, one per ordering file.

    Replaces the hand-written ``.provenance.txt``: same three facts (when, how
    many labelled frames anchored it, how many photos were ranked), plus the
    hash of each embedding file and the library version, which is what lets a
    reader tell a re-run from a copy. The ordering is one run of farthest-first
    over the whole pool, so ``k`` is the pool and the seed is fixed at 0: the
    pick is deterministic and the seed changes nothing.
    """
    return RunRecord(
        strategy=STRATEGY, seed=0, k=n_pool, n_pool=n_pool, n_labeled=n_anchors,
        embedding_path=str(pool_npz), embedding_sha256=sha_or_absent(pool_npz),
        extra={"by": Path(__file__).name,
               "written": dt.datetime.now(dt.timezone.utc).date().isoformat(),
               "anchor_path": str(anchor_npz),
               "anchor_sha256": sha_or_absent(anchor_npz), **extra})


def write_run_record(out: Path, record: RunRecord) -> Path:
    """``<out>.run.json`` beside the CSV, the way ``labelfirst.io.queue`` lays
    a queue out, so a labelfirst reader finds it where it expects to."""
    path = out.with_suffix(out.suffix + RUN_RECORD_SUFFIX)
    path.write_text(record.to_json() + "\n", encoding="utf-8")
    return path


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pool-npz", type=Path, default=DEFAULT_POOL_NPZ,
                   help="vectors for the photos waiting for a label")
    p.add_argument("--pool-cache-dir", type=Path, default=DEFAULT_POOL_CACHE,
                   help="per-photo cache, read when the pool npz is absent")
    p.add_argument("--anchor-npz", type=Path, default=DEFAULT_ANCHOR_NPZ,
                   help="vectors for the photos a botanist has already named")
    p.add_argument("--anchor-cache-dir", type=Path, default=DEFAULT_ANCHOR_CACHE)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--species-csv", type=Path, default=None,
                   help="named photos, for --backtest only")
    p.add_argument("--species-key-col", default="global_key")
    p.add_argument("--species-col", default="wcvp_canonical_name")
    p.add_argument("--backtest", action="store_true",
                   help="score the order against a random one and exit")
    p.add_argument("--seeds", type=int, default=16,
                   help="how many random starts --backtest scores over")
    p.add_argument("--discovery-out", type=Path, default=DEFAULT_DISCOVERY,
                   help="where --backtest writes its curve for the page to draw")
    p.add_argument("--novelty-curve-out", type=Path, default=DEFAULT_NOVELTY_CURVE,
                   help="where the ranking run writes distance against position")
    p.add_argument("--splits-csv", type=Path, default=DEFAULT_SPLITS,
                   help="frames carrying a split here are dropped from the pool")
    p.add_argument("--holdout-csv", type=Path, default=DEFAULT_HOLDOUT,
                   help="frames this holdout holds are dropped from the pool")
    p.add_argument("--audit", action="store_true",
                   help="score this order against random over several starts and exit")
    p.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT)
    p.add_argument("--confound", action="store_true",
                   help="test whether 'looks new' survives holding site or batch fixed")
    p.add_argument("--confound-out", type=Path, default=DEFAULT_CONFOUND)
    p.add_argument("--queue-csv", type=Path, default=DEFAULT_QUEUE_CSV,
                   help="send_first_queue.csv, for --confound's target on the pool")
    p.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY,
                   help="Labelbox inventory, for the site of each frame")
    return p.parse_args(argv)


def run_backtest(args) -> int:
    """The bar this ranking has to clear before it orders anything.

    Runs on the labelled photos, where the answer is known: does the directed
    order reach more distinct species per photo than a random draw. Exits
    non-zero if it does not, on any start.
    """
    if not args.species_csv:
        raise SystemExit("--backtest needs --species-csv")
    keys, emb = load_embeddings(args.anchor_npz, args.anchor_cache_dir)
    species = load_species(args.species_csv, args.species_key_col, args.species_col)
    idx = [i for i, k in enumerate(keys) if k in species]
    if len(idx) < 2:
        raise SystemExit(f"backtest needs >= 2 named photos; {len(idx)} of "
                         f"{len(keys)} keys matched {args.species_csv}")
    print(f"backtest on {len(idx)} of {len(keys)} photos that carry a species")
    result = backtest_species_coverage(l2_normalise(emb[idx]),
                                       [species[keys[i]] for i in idx],
                                       n_seeds=args.seeds)
    report = {k: v for k, v in result.items() if not isinstance(v, (list, np.ndarray))}
    print(json.dumps(report, indent=2, default=float))
    write_discovery_curve(args.discovery_out, result)
    return 0 if result["directed_beats_random"] else 1


def labelled_rows(args):
    """The labelled frames that carry a species, unit-normalised, with names."""
    if not args.species_csv:
        raise SystemExit("this step needs --species-csv")
    keys, emb = load_embeddings(args.anchor_npz, args.anchor_cache_dir)
    species = load_species(args.species_csv, args.species_key_col, args.species_col)
    idx = [i for i, k in enumerate(keys) if k in species]
    if len(idx) < 2:
        raise SystemExit(f"need >= 2 named photos; {len(idx)} of {len(keys)} keys "
                         f"matched {args.species_csv}")
    return [keys[i] for i in idx], l2_normalise(emb[idx]), [species[keys[i]] for i in idx]


def run_audit(args) -> int:
    """Does this order find rare species faster than a random one, and is the
    difference more than chance.

    labelfirst's audit, on the labelled frames where the answer is known:
    farthest-first against random, AUDIT_SEEDS random starts each, paired
    Wilcoxon on the area under the rare-species curve, a resampled range on
    the gain. Written as JSON for the queue page, which quotes the gain, the
    range, the p-value and how many starts agreed, and never the paper's number
    for a different embedding.
    """
    keys, X, labels = labelled_rows(args)
    counts = Counter(labels)
    rare = {s for s, n in counts.items() if n <= RARE_THRESHOLD}
    if not rare:
        raise SystemExit(f"no species with <= {RARE_THRESHOLD} labelled frames; "
                         f"nothing for the audit to find")
    print(f"audit on {len(keys)} labelled frames, {len(counts)} species, "
          f"{len(rare)} rare at <= {RARE_THRESHOLD} frames")
    runs = simulate(X, labels=labels, rare_classes=rare, strategies=(STRATEGY, "random"),
                    seeds=list(range(AUDIT_SEEDS)), rounds=AUDIT_ROUNDS,
                    k_per_round=AUDIT_K, seed_pool_size=AUDIT_SEED_POOL)
    panel = audit(runs, challenger=STRATEGY, baseline_for_h1="random",
                  embedding_sha256=sha_or_absent(args.anchor_npz))
    efficiency = annotation_efficiency(panel.per_seed_trajectories, STRATEGY, "random",
                                       AUDIT_K)
    preflight = predict_al_benefit(X, labels)
    flights = load_flights(args.inventory)
    # labelfirst's panel carries every start's area under the curve but not
    # the count of starts this order won, and that count is what the page
    # prints beside the gain. Written next to library_version, in the audit.
    report = json.loads(panel.to_json())
    report["n_seeds_agreeing"] = seeds_agreeing(panel.per_seed_aucs[STRATEGY],
                                                panel.per_seed_aucs["random"])
    out = {
        "audit": report,
        "efficiency": asdict(efficiency),
        "preflight": preflight,
        "separability_other_flight": separability_other_flight(
            X, labels, [flights.get(k, "") for k in keys]),
        "population": {"n_frames": len(keys), "n_species": len(counts),
                       "n_rare_species": len(rare), "rare_threshold": RARE_THRESHOLD},
        "params": {"seeds": AUDIT_SEEDS, "rounds": AUDIT_ROUNDS, "k_per_round": AUDIT_K,
                   "seed_pool_size": AUDIT_SEED_POOL},
        "run": asdict(run_record(args.anchor_npz, len(keys), args.anchor_npz, len(keys))),
    }
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)
    args.audit_out.write_text(json.dumps(out, indent=2, sort_keys=True, default=float)
                              + "\n", encoding="utf-8")
    print(render_markdown(panel))
    print(f"wrote {args.audit_out}")
    return 0


def run_confound(args) -> int:
    """Does "looks unlike the labelled frames" track a rarely-labelled species
    once the site, the flight, or the export batch, is held fixed.

    Four of labelfirst's confound audits, written as one JSON for the page: on
    the labelled frames with site held fixed, and on the queue with the export
    batch, the site, and the flight (one date at one site) held fixed. The
    queue's target is the labelled-frame count of the species the model
    guessed, read off send_first_queue.csv, since no queued frame carries a
    label yet. A frame whose site cannot be read leaves the site and flight
    audits and is counted in the record as n_unreconciled.
    """
    keys, X, labels = labelled_rows(args)
    counts = Counter(labels)
    sites, flights = load_sites(args.inventory), load_flights(args.inventory)
    audits = []
    site_of_anchor = [sites.get(k, "") for k in keys]
    audits.append(one_confound(
        "labelled frames", loo_distance(X), rarity(counts, labels), site_of_anchor,
        score_name="distance to the nearest other labelled frame",
        target_name="fewer labelled frames for its species",
        covariate_name="site"))

    if not args.out.exists() or not args.queue_csv.exists():
        raise SystemExit(f"--confound on the queue needs {args.out} and {args.queue_csv}")
    with open(args.out, newline="", encoding="utf-8") as f:
        distance = {r["global_key"]: float(r["distance_to_nearest_labelled"])
                    for r in csv.DictReader(f)}
    with open(args.queue_csv, newline="", encoding="utf-8") as f:
        support = {r["global_key"]: int(r["species_labelled_crowns"] or 0)
                   for r in csv.DictReader(f)}
    queued = [k for k in support if k in distance]
    q_score = np.array([distance[k] for k in queued])
    q_target = np.array([-np.log1p(support[k]) for k in queued])
    for name, cov in (("export batch", [camera_of(k) for k in queued]),
                      ("site", [sites.get(k, "") for k in queued]),
                      ("flight", [flights.get(k, "") for k in queued])):
        audits.append(one_confound(
            "queued photos", q_score, q_target, cov,
            score_name="distance to the nearest labelled frame",
            target_name="fewer labelled frames for the species the model guessed",
            covariate_name=name))
    for a in audits:
        print(f"{a['population']}, {a['covariate']} held fixed: {a['verdict']}, "
              f"raw {a['raw_corr']:+.3f} -> partial {a['partial_corr']:+.3f} "
              f"(p={a['partial_p']:.3g}), covariate explains {a['covariate_eta2']:.0%} "
              f"of the score, n={a['n']}, {a['n_unreconciled']} left out with no "
              f"readable {a['covariate']}")
    out = {"audits": audits,
           "run": asdict(run_record(args.pool_npz, len(queued), args.anchor_npz,
                                    len(keys)))}
    args.confound_out.parent.mkdir(parents=True, exist_ok=True)
    args.confound_out.write_text(json.dumps(out, indent=2, sort_keys=True, default=float)
                                 + "\n", encoding="utf-8")
    print(f"wrote {args.confound_out}")
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.backtest:
        return run_backtest(args)
    if args.audit:
        return run_audit(args)
    if args.confound:
        return run_confound(args)

    anchor_keys, anchor_emb = load_embeddings(args.anchor_npz, args.anchor_cache_dir)
    pool_keys, pool_emb = load_embeddings(args.pool_npz, args.pool_cache_dir)
    pool_keys, pool_emb, n_dropped = drop_split_frames(pool_keys, pool_emb,
                                                       load_splits(args.splits_csv))
    print(f"{n_dropped} photos dropped from the pool for carrying a split in "
          f"{args.splits_csv.name}: the queue never sends them")
    pool_keys, pool_emb, n_held = drop_holdout_frames(pool_keys, pool_emb,
                                                      load_holdout(args.holdout_csv))
    print(f"{n_held} photos dropped from the pool for being held by "
          f"{args.holdout_csv.name}: their flight has no train frame on it")
    if anchor_emb.shape[1] != pool_emb.shape[1]:
        raise SystemExit(f"{anchor_emb.shape[1]} numbers a photo on one side and "
                         f"{pool_emb.shape[1]} on the other; not comparable")
    overlap = set(anchor_keys) & set(pool_keys)
    if overlap:
        raise SystemExit(f"{len(overlap)} photos are in both sets, so they would be "
                         f"ranked against themselves, first: {min(overlap)}")
    print(f"{len(pool_keys)} photos to order against {len(anchor_keys)} named ones, "
          f"{pool_emb.shape[1]} numbers each")

    order, distance = rank_pool(anchor_emb, pool_emb)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "novelty_rank", "distance_to_nearest_labelled", "camera"])
        for rank, i in enumerate(order, start=1):
            w.writerow([pool_keys[i], rank, f"{distance[i]:.6f}", camera_of(pool_keys[i])])
    print(f"wrote {len(order)} rows to {args.out}")
    write_novelty_curve(args.novelty_curve_out, order, distance)

    record = run_record(args.pool_npz, len(pool_keys), args.anchor_npz, len(anchor_keys),
                        dropped_for_split=n_dropped, dropped_for_holdout=n_held)
    print(f"wrote {write_run_record(args.out, record)}")

    # The named photos are all one camera and the queue is not, so a photo can
    # read as new because of the lens rather than the species. Print the mix at
    # the head against the mix of the whole pool, and let a reader judge it.
    head = max(1, int(len(order) * TOP_DECILE))
    print(f"camera mix, whole queue: {camera_mix(pool_keys)}")
    print(f"camera mix, first {head}: {camera_mix([pool_keys[i] for i in order[:head]])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
