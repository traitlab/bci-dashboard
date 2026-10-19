"""The t-SNE layout script positions every embedded photo and records its fidelity."""

import json
import runpy
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("openTSNE")
pytest.importorskip("sklearn")

ROOT = Path(__file__).resolve().parents[1]
MAIN = runpy.run_path(str(ROOT / "labelling/project_atlas_tsne.py"))["main"]


def test_blobs_get_finite_tsne_xy_and_fidelity_in_unit_range(tmp_path):
    rng = np.random.default_rng(0)
    centres = rng.normal(size=(3, 768)) * 5
    vectors = np.vstack([c + rng.normal(size=(20, 768)) for c in centres]).astype(np.float32)
    keys = [f"p{i}" for i in range(60)]
    for part, rows in (("labelled", slice(0, 30)), ("queue", slice(30, 60))):
        (tmp_path / f"embeddings_{part}").mkdir()
        np.savez(tmp_path / f"embeddings_{part}" / "embeddings.npz", keys=np.array(keys[rows]), embeddings=vectors[rows])
    points = [{"key": key, "model_available": True, "xy": [float(i), float(i % 7)]} for i, key in enumerate(keys)]
    points.append({"key": "no-embedding", "model_available": False})
    atlas = tmp_path / "atlas.json"
    atlas.write_text(json.dumps({"points": points, "provenance": {"projection": "PCA"}}))
    output = tmp_path / "out.json"
    MAIN(atlas, tmp_path, output)
    result = json.loads(output.read_text())
    plotted = result["points"][:60]
    assert all(len(p["xy"]) == 2 and all(np.isfinite(p["xy"])) for p in plotted)
    assert "xy" not in result["points"][60]
    assert "t-SNE" in result["provenance"]["projection"]
    fidelity = result["provenance"]["projection_fidelity"]
    assert set(fidelity) == {"knn_recall_at_10", "trustworthiness_at_10", "pca_knn_recall_at_10"}
    assert all(0 <= v <= 1 for v in fidelity.values())
