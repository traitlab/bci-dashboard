"""Read what ``predict/embed.py`` wrote.

Split out of ``labelling/rank_unsent.py`` when ``labelling/rank_queue.py`` came
to need the same two-source read. One copy, so a change to how the fetcher packs
its output cannot leave one ranker reading the old shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


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


def l2_normalise(emb: np.ndarray) -> np.ndarray:
    """Unit rows, so a dot product is a cosine similarity.

    The fetcher stores what Pl@ntNet returned, whose rows have norms around 42
    to 50. Every distance below is cosine, so the normalisation happens here and
    not in each caller, where one of them would forget.
    """
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    if not np.all(norms > 0):
        raise SystemExit("an embedding is all zeros, which has no direction to compare")
    return emb / norms
