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
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from embeddings_io import l2_normalise, load_embeddings
from labelfirst.strategies.kcenter import greedy_kcenter
from speciesfirst import backtest_species_coverage

REPO = Path(__file__).resolve().parents[1]
DEFAULT_POOL_NPZ = REPO / "data" / "embeddings_queue" / "embeddings.npz"
DEFAULT_POOL_CACHE = REPO / "data" / "embeddings_queue" / "cache"
DEFAULT_ANCHOR_NPZ = REPO / "data" / "embeddings_labelled" / "embeddings.npz"
DEFAULT_ANCHOR_CACHE = REPO / "data" / "embeddings_labelled" / "cache"
DEFAULT_OUT = REPO / "data" / "next_batch" / "queue_novelty.csv"
DEFAULT_DISCOVERY = REPO / "data" / "next_batch" / "discovery_curve.csv"
DEFAULT_NOVELTY_CURVE = REPO / "data" / "next_batch" / "novelty_curve.csv"
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


def write_provenance(out: Path, sources: list[tuple[str, Path, int]]) -> None:
    """Say what the ranking was built from, so a stale file is visible.

    Same shape as ``data/gt_dominant_taxon.provenance.txt``: this file is
    generated by hand, outside ``bin/refresh.sh``, and nothing else records when.

    An npz that is not there is a normal state, not a fault: ``load_embeddings``
    falls back to the per-photo cache, which is what a checkout has while the
    fetch is still running. The sidecar says so rather than stopping, because a
    ranking built off a part-filled cache is exactly the one whose provenance a
    reader needs.
    """
    now = dt.datetime.now(dt.timezone.utc)
    lines = [f"written: {now.date().isoformat()}", f"by: {Path(__file__).name}"]
    for role, path, rows in sources:
        try:
            stamp = dt.datetime.fromtimestamp(path.stat().st_mtime,
                                              dt.timezone.utc).isoformat(timespec="seconds")
        except FileNotFoundError:
            stamp = "absent, read from the per-photo cache instead"
        lines.append(f"{role}: {path} rows={rows} mtime={stamp}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.backtest:
        return run_backtest(args)

    anchor_keys, anchor_emb = load_embeddings(args.anchor_npz, args.anchor_cache_dir)
    pool_keys, pool_emb = load_embeddings(args.pool_npz, args.pool_cache_dir)
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

    write_provenance(args.out.with_suffix(".provenance.txt"),
                     [("pool", args.pool_npz, len(pool_keys)),
                      ("anchors", args.anchor_npz, len(anchor_keys))])

    # The named photos are all one camera and the queue is not, so a photo can
    # read as new because of the lens rather than the species. Print the mix at
    # the head against the mix of the whole pool, and let a reader judge it.
    head = max(1, int(len(order) * TOP_DECILE))
    print(f"camera mix, whole queue: {camera_mix(pool_keys)}")
    print(f"camera mix, first {head}: {camera_mix([pool_keys[i] for i in order[:head]])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
