"""The t-SNE layout script positions every embedded photo and records its fidelity."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("openTSNE")
pytest.importorskip("sklearn")

ROOT = Path(__file__).resolve().parents[1]
MAIN = runpy.run_path(str(ROOT / "labelling/project_atlas_tsne.py"))["main"]


def blobs():
    rng = np.random.default_rng(0)
    centres = rng.normal(size=(3, 768)) * 5
    return np.vstack([c + rng.normal(size=(20, 768)) for c in centres]).astype(np.float32)


def atlas_for(tmp_path, keys, sources=()):
    points = [{"key": key, "model_available": True, "xy": [float(i), float(i % 7)]} for i, key in enumerate(keys)]
    points.append({"key": "no-embedding", "model_available": False})
    atlas = tmp_path / "atlas.json"
    atlas.write_text(json.dumps({"points": points, "provenance": {"projection": "PCA", "sources": list(sources)}}))
    return atlas


def check(output):
    result = json.loads(output.read_text())
    plotted = result["points"][:60]
    assert all(len(p["xy"]) == 2 and all(np.isfinite(p["xy"])) for p in plotted)
    assert "xy" not in result["points"][60]
    assert "t-SNE" in result["provenance"]["projection"]
    fidelity = result["provenance"]["projection_fidelity"]
    assert set(fidelity) == {"knn_recall_at_10", "trustworthiness_at_10", "pca_knn_recall_at_10"}
    assert all(0 <= v <= 1 for v in fidelity.values())


def test_blobs_get_finite_tsne_xy_and_fidelity_in_unit_range(tmp_path):
    vectors = blobs()
    keys = [f"p{i}" for i in range(60)]
    for part, rows in (("labelled", slice(0, 30)), ("queue", slice(30, 60))):
        (tmp_path / f"embeddings_{part}").mkdir()
        np.savez(tmp_path / f"embeddings_{part}" / "embeddings.npz", keys=np.array(keys[rows]), embeddings=vectors[rows])
    MAIN(atlas_for(tmp_path, keys), tmp_path, tmp_path / "out.json")
    check(tmp_path / "out.json")


def test_json_dict_joins_by_canonical_key_and_must_match_the_recorded_hash(tmp_path):
    stems = [f"DJI_{i}_V_1zoom" for i in range(60)]
    embeddings = tmp_path / "plantclef.json"
    embeddings.write_text(json.dumps(dict(zip(stems, blobs().tolist(), strict=True))))
    digest = hashlib.sha256(embeddings.read_bytes()).hexdigest()
    keys = ["comb_" + stem + ".JPG" for stem in stems]
    source = {"file": "plantclef.json", "sha256": digest}
    MAIN(atlas_for(tmp_path, keys, [source]), embeddings, tmp_path / "out.json")
    check(tmp_path / "out.json")
    for sources in ([], [{**source, "sha256": "0" * 64}]):
        with pytest.raises(ValueError, match="does not match the source recorded"):
            MAIN(atlas_for(tmp_path, keys, sources), embeddings, tmp_path / "bad.json")
    assert not (tmp_path / "bad.json").exists()
