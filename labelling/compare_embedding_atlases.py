"""Compare independent encoder neighborhoods on the identical shared frame cohort."""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_embedding_atlas import canonical_key, canonical_index, load_labels, sha


def compare_matrices(first, second, labels=None, neighbours=12):
    """Compare finite nonzero vectors, allowing different encoder dimensions."""
    if neighbours <= 0:
        raise ValueError("Neighbour count must be positive")
    first_index, second_index = canonical_index(first), canonical_index(second)
    common = sorted(set(first_index) & set(second_index), key=lambda k: first_index[k])
    vectors = [[], []]
    keys, invalid = [], []
    dimensions = [None, None]
    for alias in common:
        pair = [
            np.asarray(pool[index[alias]], dtype=np.float64)
            for pool, index in [(first, first_index), (second, second_index)]
        ]
        for m, vector in enumerate(pair):
            if vector.ndim != 1 or not len(vector):
                raise ValueError("Each embedding must be a nonempty vector")
            if dimensions[m] is None:
                dimensions[m] = len(vector)
            if dimensions[m] != len(vector):
                raise ValueError("Inconsistent dimensions within an encoder")
        if any(not np.isfinite(v).all() or np.linalg.norm(v) == 0 for v in pair):
            invalid.append(first_index[alias])
            continue
        keys.append(first_index[alias])
        for m, vector in enumerate(pair):
            vectors[m].append(vector)
    if len(keys) < 2:
        raise ValueError("At least two valid common frames are required")
    k = min(neighbours, len(keys) - 1)
    labels = labels or {}
    results = [[0, []] for key in keys]
    neighbor_sets = [[], []]
    for m, rows in enumerate(vectors):
        matrix = np.asarray(rows)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        for start in range(0, len(keys), 128):
            similarities = matrix[start : start + 128] @ matrix.T
            for offset, scores in enumerate(similarities):
                i = start + offset
                scores[i] = -np.inf
                nearest = np.argsort(-scores, kind="stable")[:k]
                neighbor_sets[m].append(set(map(int, nearest)))
                results[i][1].append(
                    [
                        sum(keys[j] in labels for j in nearest),
                        sum(labels.get(keys[j]) == labels[keys[i]] for j in nearest)
                        if keys[i] in labels
                        else None,
                        [[int(j), round(float(scores[j]), 5)] for j in nearest],
                    ]
                )
    for i, key in enumerate(keys):
        results[i][0] = len(neighbor_sets[0][i] & neighbor_sets[1][i])
    return {
        "schema": {
            "cohort": ["frame_key", "recorded_label"],
            "frames": ["overlap_count", "models"],
            "model": ["labelled_support", "same_recorded_label", "neighbors"],
            "neighbor": ["cohort_index", "cosine_similarity"],
        },
        "cohort": [[key, labels.get(key)] for key in keys],
        "frames": results,
        "cohort_size": len(keys),
        "labelled_cohort_support": sum(key in labels for key in keys),
        "k": k,
        "requested_k": neighbours,
        "dimensions": dimensions,
        "invalid_common_keys": invalid,
        "unshared_counts": [
            len(first_index) - len(common),
            len(second_index) - len(common),
        ],
        "method": "Independent L2-normalized full-vector cosine neighbors in the same shared frame cohort; self excluded; ties sorted by frame key. Overlap measures agreement, not accuracy.",
    }


def export_comparison(data_root, crownfirst_embeddings, encoder_label, neighbours=12):
    first, sources, versions = {}, [], set()
    for directory in ["embeddings_labelled", "embeddings_queue"]:
        path = data_root / directory / "embeddings.npz"
        sources.append({"file": directory + "/embeddings.npz", "sha256": sha(path)})
        with np.load(path, allow_pickle=False) as data:
            keys, matrix = data["keys"], data["embeddings"]
            if matrix.ndim != 2 or len(keys) != len(matrix):
                raise ValueError("Embedding keys and matrix rows must align")
            for key, vector in zip(keys, matrix):
                key = str(key)
                if key in first:
                    raise ValueError("Duplicate Pl@ntNet frame key: " + key)
                first[key] = vector
                cache_path = data_root / directory / "cache" / (key + ".json")
                version = json.loads(cache_path.read_text()).get("version")
                if not version:
                    raise ValueError("Missing encoder version: " + key)
                versions.add(version)
    if len(versions) != 1:
        raise ValueError("Mixed Pl@ntNet encoder versions")
    second = json.loads(crownfirst_embeddings.read_text())
    labels, label_source = load_labels(data_root / "gt_dominant_taxon.csv")
    result = compare_matrices(first, second, labels, neighbours)
    sources.append(
        {"file": crownfirst_embeddings.name, "sha256": sha(crownfirst_embeddings)}
    )
    if label_source:
        sources.append(label_source)
    result.update(
        models=["Pl@ntNet " + next(iter(versions)), encoder_label],
        sources=sources,
        labels_available=label_source is not None,
        label_boundary="Recorded botanist frame labels, not independently verified ground truth. No label transfer.",
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--crownfirst-embeddings", type=Path, required=True)
    parser.add_argument("--encoder-label", required=True)
    parser.add_argument("--neighbours", type=int, default=12)
    parser.add_argument(
        "--output", type=Path, default=Path("build/embedding-comparison.json")
    )
    args = parser.parse_args()
    result = export_comparison(
        args.data_root, args.crownfirst_embeddings, args.encoder_label, args.neighbours
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False))
    print(
        f"Compared {result['cohort_size']} shared frames with top-{result['k']} neighborhoods"
    )
