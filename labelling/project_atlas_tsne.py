"""Replace the atlas plot's PCA x/y with a t-SNE layout of the same embedding pool, offline.

    uv run --with numpy --with openTSNE --with scikit-learn labelling/project_atlas_tsne.py \
        --atlas docs/embedding-atlas.html --data data --output build/embedding-atlas.json

--data is a directory holding embeddings_labelled/ and embeddings_queue/, or one JSON dict of frame stem to
vector (PlantCLEF); the JSON must hash to the atlas page's recorded source of the same name.
Then: python3 dashboard/build_embedding_atlas.py --input build/embedding-atlas.json --output docs/embedding-atlas.html
Reads the atlas JSON (or the payload embedded in a built page), joins embeddings by frame key,
and records how well the 2-d layout keeps each photo's 10 closest matches.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from openTSNE import TSNE
from sklearn.manifold import trustworthiness
from sklearn.neighbors import NearestNeighbors

K = 10
PROJECTION = "t-SNE (openTSNE, cosine, perplexity 30, PCA init) of L2-normalized vectors, fitted on this pool"


def canonical_key(key):
    return key.removeprefix("comb_").removesuffix(".JPG")


def read_vectors(data, atlas):
    data = Path(data)
    if data.is_dir():
        vectors = {}
        for part in ("labelled", "queue"):
            found = np.load(data / f"embeddings_{part}" / "embeddings.npz")
            vectors.update(zip(found["keys"].tolist(), found["embeddings"].astype(np.float64), strict=True))
        return vectors
    raw = data.read_bytes()
    recorded = [s["sha256"] for s in atlas["provenance"].get("sources", []) if s["file"] == data.name]
    if recorded != [hashlib.sha256(raw).hexdigest()]:
        raise ValueError(f"{data.name} does not match the source recorded in the atlas provenance")
    return {key: np.asarray(vector, dtype=np.float64) for key, vector in json.loads(raw).items()}


def vector_for(vectors, key):
    return vectors.get(key, vectors.get(canonical_key(key)))


def read_atlas(path):
    text = Path(path).read_text()
    found = re.search(r'<script id="atlas-data" type="application/json">(.*?)</script>', text, re.DOTALL)
    return json.loads(found[1].replace("\\u003c", "<") if found else text)


def knn(points, metric):
    return NearestNeighbors(n_neighbors=K + 1, metric=metric).fit(points).kneighbors(points, return_distance=False)[:, 1:]


def recall(high, layout):
    low = knn(layout, "euclidean")
    return float(np.mean([len(set(a) & set(b)) / K for a, b in zip(high, low, strict=True)]))


def main(atlas_path, data, output):
    atlas = read_atlas(atlas_path)
    vectors = read_vectors(data, atlas)
    pool = [p for p in atlas["points"] if p.get("model_available") is not False and vector_for(vectors, p["key"]) is not None]
    if len(pool) < K + 2:
        raise ValueError(f"Only {len(pool)} atlas points have embeddings; t-SNE needs more")
    x = np.stack([vector_for(vectors, p["key"]) for p in pool])
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    centered = x - x.mean(axis=0)
    _, _, axes = np.linalg.svd(centered, full_matrices=False)
    init = centered @ axes[:2].T
    init = init / init[:, 0].std() * 1e-4
    layout = np.asarray(TSNE(perplexity=30, metric="cosine", initialization=init, random_state=0, n_jobs=-1).fit(x))
    high = knn(x, "cosine")
    old = np.array([p["xy"][:2] if p.get("xy") else [np.nan, np.nan] for p in pool], dtype=np.float64)
    if np.isnan(old).any():
        raise ValueError("Every pool point needs its stored PCA xy to measure the old layout")
    for p in atlas["points"]:
        p.pop("xy", None)
    for p, (px, py) in zip(pool, layout, strict=True):
        p["xy"] = [round(float(px), 7), round(float(py), 7)]
    atlas["provenance"]["projection"] = PROJECTION
    atlas["provenance"]["projection_fidelity"] = {
        "knn_recall_at_10": round(recall(high, layout), 3),
        "trustworthiness_at_10": round(float(trustworthiness(x, layout, n_neighbors=K, metric="cosine")), 3),
        "pca_knn_recall_at_10": round(recall(high, old), 3),
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(atlas, separators=(",", ":"), allow_nan=False))
    print(len(pool), "points", atlas["provenance"]["projection_fidelity"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--atlas", default="docs/embedding-atlas.html")
    parser.add_argument("--data", default="data")
    parser.add_argument("--output", default="build/embedding-atlas.json")
    args = parser.parse_args()
    main(args.atlas, args.data, args.output)
