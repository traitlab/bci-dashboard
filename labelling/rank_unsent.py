"""
Rank the unsent photos by how much a botanist label on each would be worth.

This is the "which picture to send next" answer. It replaces the dispatch order
in ``queue_photos.csv``, which sorted by flight and file size and was never a
priority ranking.

The ordering is **label-free**. It runs the CoreSet coverage objective from
speciesfirst over the Pl@ntNet embeddings (``predict/embed.py``): each pick is
the photo that looks least like everything picked so far, so distinct-species
coverage fills as fast as an unlabelled selector can make it. No prediction and
no species name steers the order, which is what makes the backtest below an
honest claim rather than a label leak.

``--species-csv`` supplies held-out species for two optional extras: the
species-coverage curve reported alongside the order, and, with ``--backtest``,
the falsifiable bar (does the directed order cover species faster than a random
draw, on every seed). Those labels score the order. They never choose it.

Runs against the speciesfirst virtualenv, which already carries speciesfirst and
labelfirst. Point ``SPECIESFIRST`` at that checkout:

  "$SPECIESFIRST/.venv/bin/python" labelling/rank_unsent.py \
      --backtest --species-csv data/gt_dominant_taxon.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from speciesfirst import (
    CrownWeights,
    backtest_species_coverage,
    crowns_from_arrays,
    select_crowns,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_NPZ = REPO / "data" / "embeddings" / "embeddings.npz"
DEFAULT_CACHE = REPO / "data" / "embeddings" / "cache"
DEFAULT_OUT = REPO / "data" / "next_batch" / "queue_ranked.csv"


def load_embeddings(npz: Path, cache_dir: Path) -> tuple[list[str], np.ndarray]:
    """Read vectors from the packed npz, falling back to the per-photo cache.

    ``predict/embed.py`` writes the npz only when it finishes, so ranking a run
    that is still going, or one that stopped on quota, has to read the cache the
    same way the fetcher does when it resumes.
    """
    if npz.exists():
        with np.load(npz, allow_pickle=False) as z:
            return [str(k) for k in z["keys"]], np.asarray(z["embeddings"], dtype=np.float64)
    if not cache_dir.is_dir():
        raise SystemExit(f"no embeddings: neither {npz} nor {cache_dir}")
    keys, vectors = [], []
    for p in sorted(cache_dir.glob("*.json")):
        entry = json.loads(p.read_text(encoding="utf-8"))
        if entry.get("embedding"):
            keys.append(entry["global_key"])
            vectors.append(entry["embedding"])
    if not keys:
        raise SystemExit(f"no cached embeddings under {cache_dir}")
    return keys, np.asarray(vectors, dtype=np.float64)


def load_species(path: Path, key_col: str, species_col: str) -> dict[str, str]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {key_col, species_col} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{path}: missing column(s) {sorted(missing)}")
        return {r[key_col]: r[species_col] for r in reader if r[key_col] and r[species_col]}


def load_urls(path: Path) -> dict[str, str]:
    with open(path, newline="", encoding="utf-8") as f:
        return {r["global_key"]: r["image_url"] for r in csv.DictReader(f)}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE,
                   help="per-photo cache, read when the npz is absent")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--urls-csv", type=Path,
                   default=REPO / "data" / "next_batch" / "unsent_for_plantnet.csv")
    p.add_argument("--species-csv", type=Path, default=None,
                   help="held-out species, for the coverage curve and --backtest")
    p.add_argument("--species-key-col", default="global_key")
    p.add_argument("--species-col", default="lb_label")
    p.add_argument("--backtest", action="store_true",
                   help="report directed-vs-random species coverage and exit")
    p.add_argument("--top", type=int, default=0,
                   help="write only the first N rows (0 = all)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    keys, emb = load_embeddings(args.npz, args.cache_dir)
    print(f"{len(keys)} photos, {emb.shape[1]} dims")

    species = load_species(args.species_csv, args.species_key_col,
                           args.species_col) if args.species_csv else {}

    if args.backtest:
        # The bar needs a real label per row; rows without one cannot be scored.
        idx = [i for i, k in enumerate(keys) if k in species]
        if len(idx) < 2:
            raise SystemExit(
                f"backtest needs >= 2 photos carrying a species; "
                f"{len(idx)} of {len(keys)} keys matched {args.species_csv}"
            )
        print(f"backtest on {len(idx)} of {len(keys)} photos that carry a species")
        result = backtest_species_coverage(emb[idx], [species[keys[i]] for i in idx])
        report = {k: v for k, v in result.items() if not isinstance(v, (list, np.ndarray))}
        print(json.dumps(report, indent=2, default=float))
        return 0 if result["directed_beats_random"] else 1

    # Coverage only. rarity and complement need species for the photos being
    # ranked, and the unsent pool has none, so those terms would read predictions
    # back in as if they were labels.
    candidates = crowns_from_arrays(
        keys, emb,
        species=[species.get(k, "") for k in keys] if species else None,
    )
    selection = select_crowns(candidates, CrownWeights(coverage=1.0))
    print(f"mode={selection.metadata.get('mode')} "
          f"reward={selection.metadata.get('reward')}")

    urls = load_urls(args.urls_csv) if args.urls_csv.exists() else {}
    curve = selection.coverage_curve
    ordered = selection.ordered_ids[:args.top] if args.top else selection.ordered_ids

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "global_key", "image_url", "species_covered_after"])
        for rank, gk in enumerate(ordered, start=1):
            w.writerow([rank, gk, urls.get(gk, ""),
                        curve[rank - 1] if rank <= len(curve) else ""])
    print(f"wrote {len(ordered)} rows to {args.out}")
    if curve:
        print(f"distinct species covered: {curve[-1]} over {len(curve)} photos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
