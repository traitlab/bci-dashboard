"""Source annotation links preserve exact photo and representation provenance."""

import copy
import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "dashboard/build_embedding_atlas.py"
LINK = "https://app.labelbox.com/projects/project1/data-rows/rowA"


def inputs(tmp_path):
    inventory = {"file": "dataset_rows_combined.jsonl", "sha256": "a" * 64}
    sources = [inventory, {"file": "embeddings.npz", "sha256": "b" * 64}]
    atlas = {
        "points": [
            {"key": "a.JPG", "lat": 9.2, "lon": -79.9, "label": "Canopia alba", "neighbours": [[1, 0.9]], "xy": [1, 2]},
            {"key": "b.JPG", "lat": 9.1, "lon": -79.8, "label": None, "neighbours": [[0, 0.9]], "xy": [3, 4]},
        ],
        "provenance": {"sources": sources, "encoder": "Recorded encoder"},
    }
    catalogue = {
        "photos": [
            {"key": "b.JPG", "lat": 9.1, "lon": -79.8},
            {"key": "extra.JPG", "annotation_url": None},
            {"key": "a.JPG", "annotation_url": LINK, "lat": 9.2, "lon": -79.9},
        ],
        "provenance": {"sources": [copy.deepcopy(inventory)]},
    }
    source, annotations = tmp_path / "atlas.json", tmp_path / "explorer.json"
    source.write_text(json.dumps(atlas))
    annotations.write_text(json.dumps(catalogue))
    return atlas, catalogue, source, annotations


def payload(output):
    return json.loads(output.read_text().split('<script id="atlas-data" type="application/json">')[1].split("</script>")[0])


def test_exact_catalogue_join_preserves_all_representation_evidence_and_input_files(tmp_path):
    atlas, _, source, annotations = inputs(tmp_path)
    original_source, original_catalogue = source.read_bytes(), annotations.read_bytes()
    output = tmp_path / "atlas.html"
    runpy.run_path(str(BUILDER))["build"](source, output, catalogue=annotations)
    result = payload(output)
    assert [p.pop("annotation_url") for p in result["points"]] == [None, LINK]
    for point in result["points"]:
        assert point.pop("model_available") is True
        assert (point.pop("family"), point.pop("genus")) == (None, None)
        point["neighbours"][0][0] = 1 - point["neighbours"][0][0]
    result["points"].reverse()
    provenance = result["provenance"].pop("annotation_links")
    inventory = result["provenance"].pop("photo_inventory")
    assert inventory["excluded_position_count"] == 1
    assert result == atlas
    assert provenance["matched_count"] == 1
    assert provenance["pool_size"] == 2
    assert provenance["inventory_sha256"] == "a" * 64
    assert provenance["source"] == {
        "file": "explorer.json", "sha256": hashlib.sha256(original_catalogue).hexdigest()
    }
    assert source.read_bytes() == original_source
    assert annotations.read_bytes() == original_catalogue


def test_optional_catalogue_preserves_existing_builder_and_comparison_contract(tmp_path):
    atlas, _, source, annotations = inputs(tmp_path)
    comparison = tmp_path / "comparison.json"
    comparison_data = {"sources": atlas["provenance"]["sources"], "cohort": [["a.JPG", "Canopia alba"]]}
    comparison.write_text(json.dumps(comparison_data))
    build = runpy.run_path(str(BUILDER))["build"]
    old_output, enriched_output = tmp_path / "old.html", tmp_path / "enriched.html"
    build(source, old_output, comparison=comparison)
    assert payload(old_output) == {**atlas, "comparison": comparison_data}
    build(source, enriched_output, comparison=comparison, catalogue=annotations)
    enriched = payload(enriched_output)
    assert enriched["comparison"] == comparison_data
    assert enriched["provenance"]["sources"] == atlas["provenance"]["sources"]
    runpy.run_path(str(BUILDER))["validate_comparison"](enriched, comparison_data)


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "http://app.labelbox.com/projects/p/data-rows/r",
    "https://app.labelbox.com.evil.org/projects/p/data-rows/r",
    "https://app.labelbox.com@evil.org/projects/p/data-rows/r",
    "https://app.labelbox.com/projects/p/data-rows/r?redirect=evil",
    "https://app.labelbox.com/projects/p/data-rows/r#x", "", 123,
])
def test_annotation_join_rejects_untrusted_or_ambiguous_urls(tmp_path, url):
    _, catalogue, source, annotations = inputs(tmp_path)
    catalogue["photos"][2]["annotation_url"] = url
    annotations.write_text(json.dumps(catalogue))
    output = tmp_path / "atlas.html"
    with pytest.raises(ValueError, match="Invalid source Labelbox"):
        runpy.run_path(str(BUILDER))["build"](source, output, catalogue=annotations)
    assert not output.exists()


@pytest.mark.parametrize("mutation,error", [
    ("hash", "inventory source hash mismatch"),
    ("missing_provenance", "one hashed inventory source"),
    ("duplicate_provenance", "one hashed inventory source"),
    ("duplicate_photo", "unique, nonempty frame keys"),
    ("blank_photo", "unique, nonempty frame keys"),
    ("alias_only", "Atlas frame absent"),
    ("duplicate_atlas", "unique, nonempty frame keys"),
    ("unknown_atlas", "Atlas frame absent"),
])
def test_annotation_join_refuses_mismatched_inventory_and_nonexact_identity(tmp_path, mutation, error):
    atlas, catalogue, source, annotations = inputs(tmp_path)
    if mutation == "hash":
        catalogue["provenance"]["sources"][0]["sha256"] = "c" * 64
    elif mutation == "missing_provenance":
        catalogue["provenance"]["sources"] = []
    elif mutation == "duplicate_provenance":
        catalogue["provenance"]["sources"] *= 2
    elif mutation == "duplicate_photo":
        catalogue["photos"].append(copy.deepcopy(catalogue["photos"][2]))
    elif mutation == "blank_photo":
        catalogue["photos"][0]["key"] = "  "
    elif mutation == "alias_only":
        catalogue["photos"][2]["key"] = "a"
    elif mutation == "duplicate_atlas":
        atlas["points"].append(copy.deepcopy(atlas["points"][0]))
    elif mutation == "unknown_atlas":
        atlas["points"][0]["key"] = "unknown.JPG"
    source.write_text(json.dumps(atlas))
    annotations.write_text(json.dumps(catalogue))
    with pytest.raises(ValueError, match=error):
        runpy.run_path(str(BUILDER))["build"](source, tmp_path / "out.html", catalogue=annotations)


def test_annotation_join_cli_is_rebuildable_offline(tmp_path):
    _, _, source, annotations = inputs(tmp_path)
    output = tmp_path / "nested/atlas.html"
    subprocess.run([
        sys.executable, str(BUILDER), "--input", str(source), "--output", str(output),
        "--catalogue", str(annotations),
    ], check=True, capture_output=True, text=True)
    assert payload(output)["points"][1]["annotation_url"] == LINK
