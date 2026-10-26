"""Catalogue joins preserve original labels, missing evidence and source authority."""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def exporter(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "labelling"))
    spec = importlib.util.spec_from_file_location(
        "explorer_under_test", ROOT / "labelling/export_explorer.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def checklist(rows=None):
    rows = (
        rows
        if rows is not None
        else [
            {
                "id": "100",
                "gbifId": 10,
                "scientificNameWithoutAuthor": "Dendropanax alaris",
                "genus": "Dendropanax",
                "family": "Araliaceae",
            },
            {
                "id": "101",
                "gbifId": 11,
                "scientificNameWithoutAuthor": "Dendropanax stenodontus",
                "genus": "Dendropanax",
                "family": "Araliaceae",
            },
            {
                "id": "200",
                "gbifId": 20,
                "scientificNameWithoutAuthor": "Virola fosteri",
                "genus": "Virola",
                "family": "Myristicaceae",
            },
        ]
    )
    return {
        "project": "k-central-america",
        "n_returned": len(rows),
        "declared_species_count": len(rows),
        "species": rows,
    }


def survey(rows, **extra):
    return {
        "project": "k-central-america",
        "project_source": "assumed",
        "results": {
            "species": [
                {
                    "binomial": name,
                    "gbif_id": str(key),
                    "max_score": score,
                    "coverage": score,
                }
                for name, key, score in rows
            ]
        },
        **extra,
    }


def inventory(root, keys):
    rows = [
        {
            "global_key": key,
            "row_data": "https://example.org/" + key,
            "metadata": {
                "mission": "flight-1",
                "original_labelbox_url": "https://app.labelbox.com/projects/project1/data-rows/row1",
            },
            "media_attributes": {"gpsPoint": "9.1,-79.8"},
        }
        for key in keys
    ]
    root.mkdir(parents=True, exist_ok=True)
    (root / "dataset_rows_combined.jsonl").write_text("\n".join(map(json.dumps, rows)))


def labels(root, rows):
    with (root / "gt_dominant_taxon.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["global_key", "wcvp_canonical_name"])
        writer.writerows(rows)


@pytest.fixture
def catalogue_sources(tmp_path):
    inventory(tmp_path, [f"comb_{name}.JPG" for name in "abcdefg"])
    labels(
        tmp_path,
        [
            ("a.JPG", "Dendropanax stenodontus"),
            ("b.JPG", "Dendropanax"),
            ("c.JPG", "Araliaceae"),
            ("d.JPG", "Virola fosteri-VIROFO"),
            ("e.JPG", "Swartzia simplex var. continentalis"),
            ("f.JPG", "Unknown recorded name"),
        ],
    )
    write_json(tmp_path / "checklist_k-central-america.json", checklist())
    write_json(
        tmp_path / "gbif_keys.json",
        {
            "by_legacy": {"dendropanax stenodontus": 11},
            "by_code": {"VIROFO": 20},
            "accepted": {"11": 10},
        },
    )
    write_json(
        tmp_path / "wcvp_cache.json",
        {
            "Swartzia simplex var. continentalis": {
                "rank": "VARIETY",
                "gbif_key": 9999999,
            },
            "Dendropanax": {"rank": "GENUS"},
            "Araliaceae": {"rank": "FAMILY"},
        },
    )
    cache = tmp_path / "predictions/cache"
    write_json(cache / "a.JPG.json", survey([("Dendropanax stenodontus", 11, 0.8)]))
    write_json(
        cache / "b.JPG.json",
        {
            "project": "k-central-america",
            "project_source": "recorded",
            "results": [
                {"scientific_name": "Virola fosteri", "gbif_id": 20, "score": 0.7}
            ],
            "raw": {"version": "prediction-v2"},
        },
    )
    write_json(cache / "c.JPG.json", survey([]))
    write_json(
        cache / "d.JPG.json",
        survey([("Virola fosteri", 20, 0.5), ("Dendropanax alaris", 10, 0.5)]),
    )
    write_json(cache / "e.JPG.json", survey([("Not in checklist", 99, 0.2)]))
    write_json(cache / "outside.JPG.json", survey([]))
    return tmp_path


def test_real_shapes_coarse_taxa_synonyms_and_independent_versions(
    exporter, catalogue_sources
):
    atlas = {
        "points": [
            {
                "key": "a.JPG",
                "version": "embedding-only-v1",
                "crop": 1280,
                "source_width": 4000,
                "source_height": 3000,
                "neighbours": [],
            }
        ],
        "provenance": {"encoder": "Pl@ntNet embeddings"},
    }
    result = exporter.export_catalogue(catalogue_sources, atlas)
    a, b, c, d, e, f, g = result["photos"]
    assert len(result["photos"]) == 7
    assert a["label"] == "Dendropanax stenodontus"
    assert a["recorded_taxon"] == a["prediction"]["taxon"] == "gbif:10"
    assert a["prediction"]["version"] is None
    assert a["representation"]["version"] == "embedding-only-v1"
    assert a["prediction"]["project_source"] == "assumed"
    assert b["recorded_taxon"] == "local:genus:Dendropanax"
    assert c["recorded_taxon"] == "local:family:Araliaceae"
    assert b["prediction"]["version"] == "prediction-v2"
    assert c["prediction"]["status"] == "empty"
    assert d["label"] == "Virola fosteri-VIROFO"
    assert d["recorded_taxon"] == "gbif:20"
    assert d["prediction"]["tied"] is True
    assert d["prediction"]["name"] == "Virola fosteri"
    assert e["label"] == "Swartzia simplex var. continentalis"
    assert e["recorded_status"] == e["prediction"]["status"] == "unresolved"
    assert e["recorded_taxon"] is None
    assert f["recorded_status"] == "unresolved"
    assert g["recorded_status"] == g["prediction"]["status"] == "missing"
    taxa = {r["id"]: r for r in result["taxa"]}
    assert taxa["gbif:10"]["parent"] == b["recorded_taxon"]
    assert taxa[b["recorded_taxon"]]["parent"] == c["recorded_taxon"]
    assert a["annotation_url"].endswith("/projects/project1/data-rows/row1")
    provenance = result["provenance"]["predictions"]
    assert (
        len(provenance["files"]) == 6
    )  # Includes a cache file outside this inventory.
    assert len(provenance["manifest_sha256"]) == 64
    assert provenance["unknown_version_count"] == 5
    assert result["coverage"]["representation"] == 1


def test_missing_optional_sources_keep_every_inventory_photo(exporter, tmp_path):
    inventory(tmp_path, ["comb_a.JPG"])
    result = exporter.export_catalogue(tmp_path)
    photo = result["photos"][0]
    assert photo["label"] is None
    assert photo["recorded_status"] == photo["prediction"]["status"] == "missing"
    assert photo["representation"] is None
    assert result["provenance"]["predictions"]["available"] is False
    assert result["taxa"] == []
    # The page carries no photo URL: private storage, thumbnails only.
    assert "image" not in photo and "example.org" not in json.dumps(result)


def test_missing_checklist_does_not_invent_parent_hierarchy(
    exporter, catalogue_sources
):
    (catalogue_sources / "checklist_k-central-america.json").unlink()
    result = exporter.export_catalogue(catalogue_sources)
    a, b, c = result["photos"][:3]
    assert a["prediction"]["status"] == "unresolved"
    assert a["prediction"]["name"] == "Dendropanax stenodontus"
    assert b["recorded_status"] == "unresolved"
    assert c["recorded_status"] == "ok"
    assert c["recorded_taxon"] == "local:family:Araliaceae"


def test_recorded_species_is_not_limited_to_prediction_checklist(
    exporter, catalogue_sources
):
    root = catalogue_sources
    labels(
        root,
        [
            ("a.JPG", "Virola surinamensis"),
            ("b.JPG", "Swartzia simplex var. grandiflora"),
        ],
    )
    write_json(
        root / "wcvp_cache.json",
        {
            "Virola surinamensis": {
                "rank": "SPECIES",
                "gbif_key": 207000001,
                "accepted_name": "Virola surinamensis (Rol. ex Rottb.) Warb.",
                "family": "Myristicaceae",
            },
            "Swartzia simplex var. grandiflora": {
                "rank": "SPECIES",
                "gbif_key": 207000002,
                "accepted_name": "Swartzia simplex (Sw.) Spreng.",
                "family": "Fabaceae",
            },
        },
    )
    result = exporter.export_catalogue(root)
    a, b = result["photos"][:2]
    assert a["label"] == "Virola surinamensis"
    assert a["recorded_taxon"] == "wcvp:207000001"
    assert a["recorded_status"] == "ok"
    node = next(t for t in result["taxa"] if t["id"] == a["recorded_taxon"])
    assert node["parent"] == "local:family:Myristicaceae"
    assert node["name"] == "Virola surinamensis (Rol. ex Rottb.) Warb."
    assert b["label"] == "Swartzia simplex var. grandiflora"
    assert b["recorded_taxon"] is None
    assert b["recorded_status"] == "unresolved"


@pytest.mark.parametrize("where", ["inventory", "labels", "predictions", "atlas"])
def test_canonical_frame_collisions_are_rejected(exporter, catalogue_sources, where):
    root = catalogue_sources
    atlas = None
    if where == "inventory":
        inventory(root, ["comb_a.JPG", "migrated/a.jpg"])
    elif where == "labels":
        labels(root, [("a.JPG", "Virola"), ("comb_a.JPG", "Dendropanax")])
    elif where == "predictions":
        write_json(root / "predictions/cache/comb_a.JPG.json", survey([]))
    else:
        atlas = {"points": [{"key": "a.JPG"}, {"key": "comb_a.JPG"}]}
    with pytest.raises(ValueError, match="collision"):
        exporter.export_catalogue(root, atlas)


@pytest.mark.parametrize(
    "change,match",
    [
        ("foreign-project", "project"),
        ("short-checklist", "Incomplete"),
        ("duplicate-id", "collision"),
        ("conflicting-genus", "Conflicting taxonomy"),
        ("conflicting-accepted", "Conflicting taxonomy"),
    ],
)
def test_taxonomy_source_conflicts_fail(exporter, catalogue_sources, change, match):
    path = catalogue_sources / "checklist_k-central-america.json"
    doc = json.loads(path.read_text())
    if change == "foreign-project":
        doc["project"] = "bcnm"
    elif change == "short-checklist":
        doc["n_returned"] -= 1
    elif change == "duplicate-id":
        doc["species"][1]["gbifId"] = 10
    elif change == "conflicting-genus":
        doc["species"][2]["genus"] = "Dendropanax"
    else:
        doc["species"][1]["family"] = "Another family"
    write_json(path, doc)
    with pytest.raises(ValueError, match=match):
        exporter.export_catalogue(catalogue_sources)


@pytest.mark.parametrize(
    "entry,match",
    [
        (survey([], project="bcnm"), "Foreign prediction"),
        (
            survey([], model_version="one", raw={"version": "two"}),
            "Conflicting prediction",
        ),
        (
            survey([("Virola fosteri", 20, 0.2), ("Dendropanax alaris", 10, 0.8)]),
            "score order",
        ),
        (survey([("Virola fosteri", 20, float("nan"))]), "Nonfinite"),
        (survey([], global_key="another.JPG"), "filename/global_key"),
    ],
)
def test_prediction_provenance_and_candidates_fail_closed(
    exporter, catalogue_sources, entry, match
):
    write_json(catalogue_sources / "predictions/cache/a.JPG.json", entry)
    with pytest.raises(ValueError, match=match):
        exporter.export_catalogue(catalogue_sources)


def test_representation_neighbours_resolve_keys_without_changing_order(
    exporter, catalogue_sources
):
    atlas = {
        "points": [
            {"key": "a.JPG", "neighbours": [[2, 0.8], [1, 0.8]]},
            {"key": "c.JPG"},
            {"key": "b.JPG"},
        ]
    }
    photo = exporter.export_catalogue(catalogue_sources, atlas)["photos"][0]
    assert photo["representation"]["neighbours"] == [
        {"key": "comb_b.JPG", "score": 0.8},
        {"key": "comb_c.JPG", "score": 0.8},
    ]
    assert photo["representation"]["version"] is None


def test_no_metadata_guesses_or_forged_annotation_urls(exporter, tmp_path):
    inventory(tmp_path, ["a.JPG"])
    path = tmp_path / "dataset_rows_combined.jsonl"
    row = json.loads(path.read_text())
    row["media_attributes"]["gpsPoint"] = None
    row["metadata"]["original_labelbox_url"] = "https://example.org/fake"
    path.write_text(json.dumps(row))
    photo = exporter.export_catalogue(tmp_path)["photos"][0]
    assert photo["lat"] is photo["lon"] is photo["annotation_url"] is None


def test_cli_builds_without_third_party_packages(tmp_path):
    inventory(tmp_path, ["a.JPG"])
    output = tmp_path / "catalogue.json"
    subprocess.run(
        [
            sys.executable,
            "-S",
            str(ROOT / "labelling/export_explorer.py"),
            "--data-root",
            str(tmp_path),
            "--output",
            str(output),
        ],
        check=True,
    )
    assert json.loads(output.read_text())["photos"][0]["key"] == "a.JPG"


@pytest.mark.parametrize(
    "name", ["wcvp_cache.json", "gbif_keys.json", "checklist_k-central-america.json"]
)
def test_present_optional_source_cannot_masquerade_as_missing(exporter, tmp_path, name):
    inventory(tmp_path, ["a.JPG"])
    write_json(tmp_path / name, None)
    with pytest.raises(TypeError, match="JSON source must be an object"):
        exporter.export_catalogue(tmp_path)


def test_coded_label_with_unknown_code_uses_verified_ontology_name(
    exporter, catalogue_sources
):
    labels(catalogue_sources, [("a.JPG", "Dendropanax alaris-UNKNOWN")])
    write_json(
        catalogue_sources / "gbif_keys.json", {"by_name": {"dendropanax alaris": 10}}
    )
    photo = exporter.export_catalogue(catalogue_sources)["photos"][0]
    assert photo["label"] == "Dendropanax alaris-UNKNOWN"
    assert photo["recorded_taxon"] == "gbif:10"


def test_representation_cannot_name_a_different_inventory(exporter, catalogue_sources):
    with pytest.raises(ValueError, match="absent from inventory"):
        exporter.export_catalogue(
            catalogue_sources, {"points": [{"key": "foreign.JPG"}]}
        )


def test_labelbox_rename_applies_to_guess_and_keeps_original_name(
    monkeypatch, catalogue_sources
):
    monkeypatch.syspath_prepend(str(ROOT / "labelling"))
    import atlas_taxonomy

    sources = catalogue_sources
    keys = json.loads((sources / "gbif_keys.json").read_text())
    keys["by_legacy"]["old virola name"] = 10
    taxonomy = atlas_taxonomy.Taxonomy(
        json.loads((sources / "checklist_k-central-america.json").read_text()), keys
    )
    renamed = atlas_taxonomy.prediction_record(
        survey([("Old Virola name", 20, 0.9)]), taxonomy
    )
    assert renamed["taxon"] == "gbif:10"
    assert renamed["name"] == "Dendropanax alaris"
    assert renamed["original_name"] == "Old Virola name"
    plain = atlas_taxonomy.prediction_record(
        survey([("Virola fosteri", 20, 0.9)]), taxonomy
    )
    assert plain["taxon"] == "gbif:20" and plain["original_name"] is None
