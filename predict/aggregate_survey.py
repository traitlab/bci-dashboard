"""Aggregate Pl@ntNet survey predictions into per-photo embeddings and scores.

Reads the per-image survey JSON files produced by the Pl@ntNet multi-species
endpoint and outputs two files that the send-first queue (dashboard/measure.py) can consume:

1. ``survey_embeddings.json``: coverage-weighted aggregated embeddings
   (same format as embeddings.json: ``{global_key: [float x 768]}``)
2. ``survey_species_scores.json``: species-coverage priority scores
   (``{global_key: float}`` keyed by coverage × rarity)

The embeddings use labelfirst.aggregate.weighted_mean_pool to collapse
per-tile/per-species embeddings into a single L2-normalised vector per
photo, weighted by each species' estimated coverage.

The species scores use labelfirst.eval.species_priority.batch_scores to
compute rarity-weighted coverage scores from predicted species composition.

Usage:
    python predict/aggregate_survey.py \\
        --survey-dir /path/to/survey/jsons \\
        --gt data/gt_dominant_taxon.csv \\
        --rare-threshold 5

    # Cold-start (no GT yet):
    python predict/aggregate_survey.py \\
        --survey-dir /path/to/survey/jsons
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from labelfirst.aggregate import weighted_mean_pool
from labelfirst.eval.species_priority import SpeciesPrediction, batch_scores

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data"
EMBEDDING_DIMS = 768


def _norm_key(filename: str) -> str:
    stem = filename.replace(".json", "").replace(".JPG", "").replace(".jpg", "")
    if not stem.startswith("comb_"):
        stem = f"comb_{stem}"
    return f"{stem}.JPG"


def parse_survey_json(path: Path) -> dict | None:
    """Extract species predictions and tile embeddings from one survey JSON."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    results = data.get("results", {})
    species_list = results.get("species", [])
    tile_embeddings = results.get("per_tiles_embeddings", [])

    species_preds: list[SpeciesPrediction] = []
    species_embs: list[tuple[np.ndarray, float]] = []

    for sp in species_list:
        sp_id = sp.get("binomial", str(sp.get("gbif_id", "")))
        coverage = float(sp.get("coverage", 0.0))
        confidence = float(sp.get("max_score", 0.0))

        species_preds.append({
            "species_id": sp_id,
            "coverage": coverage,
            "confidence": confidence,
        })

        for tile in sp.get("location", []):
            emb = tile.get("embeddings", [])
            if len(emb) == EMBEDDING_DIMS:
                species_embs.append(
                    (np.asarray(emb, dtype=np.float32), coverage)
                )

    all_tile_embs: list[np.ndarray] = []
    if not species_embs:
        for tile in tile_embeddings:
            emb = tile.get("embeddings", [])
            if len(emb) == EMBEDDING_DIMS:
                all_tile_embs.append(np.asarray(emb, dtype=np.float32))

    return {
        "species": species_preds,
        "species_embs": species_embs,
        "tile_embs": all_tile_embs,
    }


def aggregate_photo_embedding(parsed: dict) -> np.ndarray | None:
    """Produce a single coverage-weighted embedding for one photo."""
    if parsed["species_embs"]:
        embs = np.stack([e for e, _ in parsed["species_embs"]])
        weights = np.array([w for _, w in parsed["species_embs"]], dtype=np.float64)
        return weighted_mean_pool(embs, weights)
    elif parsed["tile_embs"]:
        embs = np.stack(parsed["tile_embs"])
        return weighted_mean_pool(embs)
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--survey-dir", type=Path, required=True,
                    help="directory of *.JPG.json survey result files")
    ap.add_argument("--gt", type=Path, default=OUT / "gt_dominant_taxon.csv",
                    help="GT CSV with (global_key, wcvp_canonical_name)")
    ap.add_argument("--rare-threshold", type=int, default=5)
    ap.add_argument("--method", choices=["sum", "max"], default="sum",
                    help="scoring method: sum (total rare coverage) or max (rarest dominates)")
    ap.add_argument("--unseen-weight", type=float, default=None,
                    help="weight for species not in GT (novel species)")
    ap.add_argument("--out-dir", type=Path, default=OUT,
                    help="output directory (default: data/)")
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(args.survey_dir.glob("*.JPG.json"))
    if not json_files:
        json_files = sorted(args.survey_dir.glob("*.json"))
    if not json_files:
        sys.exit(f"No JSON files found in {args.survey_dir}")

    print(f"Processing {len(json_files)} survey files ...")

    embeddings: dict[str, list[float]] = {}
    dataset_species: dict[str, list[SpeciesPrediction]] = {}
    skipped = 0

    for jf in json_files:
        global_key = _norm_key(jf.name)
        parsed = parse_survey_json(jf)
        if parsed is None:
            skipped += 1
            continue

        emb = aggregate_photo_embedding(parsed)
        if emb is not None:
            embeddings[global_key] = emb.tolist()

        if parsed["species"]:
            dataset_species[global_key] = parsed["species"]

    print(f"  Embeddings: {len(embeddings)} photos ({skipped} skipped)")
    print(f"  Species predictions: {len(dataset_species)} photos")

    emb_path = out_dir / "survey_embeddings.json"
    with open(emb_path, "w") as f:
        json.dump(embeddings, f)
    print(f"  -> {emb_path}")

    labeled_counts: dict[str, int] = {}
    if args.gt.exists():
        gt = pd.read_csv(args.gt)
        labeled_counts = gt["wcvp_canonical_name"].value_counts().to_dict()
        print(f"  GT loaded: {len(labeled_counts)} species, "
              f"{len(gt)} labeled photos")
    else:
        print("  No GT file, species scores will be zero (cold-start)")

    scores = batch_scores(
        dataset_species,
        labeled_counts,
        rare_threshold=args.rare_threshold,
        method=args.method,
        unseen_weight=args.unseen_weight,
    )

    score_path = out_dir / "survey_species_scores.json"
    with open(score_path, "w") as f:
        json.dump(scores, f)
    print(f"  -> {score_path}")

    if scores:
        vals = list(scores.values())
        nonzero = [v for v in vals if v > 0]
        print(f"\n  Score stats: {len(vals)} photos, "
              f"{len(nonzero)} with score > 0")
        if nonzero:
            print(f"  min={min(nonzero):.4f}  max={max(nonzero):.4f}  "
                  f"mean={sum(nonzero)/len(nonzero):.4f}")

    print("\nDone. Use with the send-first queue (dashboard/measure.py):")
    print(f"  --embeddings {emb_path}")
    print("  (species scores can replace the novelty axis)")


if __name__ == "__main__":
    main()
