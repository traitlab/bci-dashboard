"""Display names cannot stand in for recorded encoder versions."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def encoder_pool(tmp_path):
    np = pytest.importorskip("numpy")
    spec = importlib.util.spec_from_file_location(
        "export_embedding_atlas", ROOT / "labelling/export_embedding_atlas.py"
    )
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    vectors = {"a": [1.0, 0, 0], "b": [0.8, 0.6, 0], "c": [0, 0, 1.0]}
    rows = [
        {
            "global_key": key,
            "media_attributes": {"gpsPoint": "9.1,-79.8"},
            "metadata": {"mission": "flight-a" if key == "a" else "flight-b"},
            "row_data": "https://example.org/" + key + ".jpg",
        }
        for key in vectors
    ]
    (tmp_path / "dataset_rows_combined.jsonl").write_text(
        "\n".join(map(json.dumps, rows))
    )
    (tmp_path / "gt_dominant_taxon.csv").write_text(
        "global_key,wcvp_canonical_name\na,Luehea seemannii\n"
    )
    caches = []
    for directory, keys in [
        ("embeddings_labelled", ["a", "b"]),
        ("embeddings_queue", ["c"]),
    ]:
        folder = tmp_path / directory
        (folder / "cache").mkdir(parents=True)
        np.savez(
            folder / "embeddings.npz",
            keys=keys,
            embeddings=[vectors[key] for key in keys],
        )
        for key in keys:
            cache = folder / "cache" / (key + ".json")
            cache.write_text(
                json.dumps(
                    {
                        "version": "recorded-api-v7",
                        "crop_size": 1280,
                        "orig_width": 4000,
                        "orig_height": 3000,
                    }
                )
            )
            caches.append(cache)
    source = tmp_path / "vectors.json"
    source.write_text(json.dumps(vectors))
    return exporter.export, tmp_path, source, caches


def test_external_display_name_is_not_a_recorded_version(encoder_pool):
    export, root, source, _ = encoder_pool
    result = export(root, crownfirst_embeddings=source, encoder_label="Imported model")

    assert result["provenance"]["encoder"] == "Imported model"
    assert result["provenance"]["versions"] == []
    assert all(point["version"] is None for point in result["points"])
    assert result["provenance"]["encoder_identity"] == {
        "name_basis": "supplied_at_import",
        "version_source": "not_recorded",
    }
    assert all(
        point[field] is None
        for point in result["points"]
        for field in ("crop", "source_width", "source_height")
    )
    # Renaming an import does not change the scientific representation or ranks.
    renamed = export(root, crownfirst_embeddings=source, encoder_label="Another name")
    original = copy.deepcopy(result)
    original["provenance"]["encoder"] = "Another name"
    assert renamed == original


def test_api_versions_remain_recorded_cache_values(encoder_pool):
    export, root, _, _ = encoder_pool
    result = export(root)

    assert result["provenance"]["encoder"] == "Pl@ntNet /v2/embeddings"
    assert result["provenance"]["encoder_identity"] == {
        "name_basis": "endpoint_label",
        "version_source": "cached_response",
    }
    assert result["provenance"]["versions"] == ["recorded-api-v7"]
    assert {point["version"] for point in result["points"]} == {"recorded-api-v7"}
    assert all(point["crop"] == 1280 for point in result["points"])
    assert all(point["source_width"] == 4000 for point in result["points"])
    assert all(point["source_height"] == 3000 for point in result["points"])


@pytest.mark.parametrize("metadata", [{}, {"version": None}, {"version": ""}])
def test_api_missing_or_empty_version_still_rejected(encoder_pool, metadata):
    export, root, _, caches = encoder_pool
    caches[-1].write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="Missing encoder version: c"):
        export(root)


def test_api_mixed_recorded_versions_still_rejected(encoder_pool):
    export, root, _, caches = encoder_pool
    caches[-1].write_text(json.dumps({"version": "recorded-api-v8"}))
    with pytest.raises(ValueError, match="Mixed encoder versions"):
        export(root)


@pytest.mark.parametrize("display_name", [None, ""])
def test_external_import_still_requires_explicit_display_name(encoder_pool, display_name):
    export, root, source, _ = encoder_pool
    with pytest.raises(ValueError, match="explicit encoder label"):
        export(root, crownfirst_embeddings=source, encoder_label=display_name)
