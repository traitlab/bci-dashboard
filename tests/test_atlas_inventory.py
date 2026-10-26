"""A shared map inventory does not invent or silently replace model evidence."""

import copy
import json
import re
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JOIN = runpy.run_path(str(ROOT / "dashboard/atlas_inventory.py"))[
    "join_photo_inventory"
]
SOURCE = {"file": "explorer.json", "sha256": "f" * 64}
INVENTORY = {"file": "dataset_rows_combined.jsonl", "sha256": "a" * 64}


def fixture():
    atlas = {
        "points": [
            {
                "key": "a.JPG",
                "lat": 9,
                "lon": -79,
                "label": "A alba",
                "crop": 1280,
                "version": "recorded-v1",
                "xy": [0.1, 0.2],
                "rgb": [1, 2, 3],
                "neighbours": [[1, 0.91234]],
                "other_mission_neighbours": [[1, 0.81234]],
            },
            {
                "key": "b.JPG",
                "lat": 8,
                "lon": -78,
                "label": None,
                "xy": [0.3, 0.4],
                "neighbours": [[0, 0.91234]],
                "other_mission_neighbours": None,
            },
        ],
        "provenance": {
            "input_count": 2,
            "labels": {"matched_count": 1},
            "sources": [INVENTORY],
        },
        "comparison": {"cohort": ["a.JPG"]},
    }
    catalogue = {
        "photos": [
            {
                "key": "missing.JPG",
                "lat": 9.4,
                "lon": -79.2,
                "label": "B beta",
                "mission": "recorded-flight",
            },
            {"key": "b.JPG", "lat": 8, "lon": -78},
            {"key": "a.JPG", "lat": 9, "lon": -79},
        ],
        "provenance": {"sources": [INVENTORY]},
    }
    return atlas, catalogue


def test_exact_remap_preserves_model_pixels_projection_labels_and_rank():
    atlas, catalogue = fixture()
    before = copy.deepcopy(atlas)
    result = JOIN(atlas, catalogue, SOURCE)
    assert atlas == before
    assert [point["key"] for point in result["points"]] == [
        "missing.JPG",
        "b.JPG",
        "a.JPG",
    ]
    for old, new in zip(atlas["points"], reversed(result["points"][1:]), strict=True):
        for field in old:
            if "neighbours" not in field:
                assert new[field] == old[field]
        for field in ("neighbours", "other_mission_neighbours"):
            if old[field] is None:
                assert new[field] is None
            else:
                assert [
                    (result["points"][index]["key"], score)
                    for index, score in new[field]
                ] == [
                    (atlas["points"][index]["key"], score)
                    for index, score in old[field]
                ]
    for field in ("input_count", "labels", "sources"):
        assert result["provenance"][field] == atlas["provenance"][field]
    assert result["comparison"] == atlas["comparison"]
    assert result["provenance"]["photo_inventory"]["model_count"] == 2
    assert result["provenance"]["photo_inventory"]["source"] == SOURCE


def test_missing_model_photo_has_no_invented_representation_and_join_is_idempotent():
    atlas, catalogue = fixture()
    first = JOIN(atlas, catalogue, SOURCE)
    assert first["points"][0] == {
        "key": "missing.JPG",
        "lat": 9.4,
        "lon": -79.2,
        "label": "B beta",
        "mission": "recorded-flight",
        "annotation_url": None,
        "group": "Labelled",
        "model_available": False,
        "neighbours": [],
        "other_mission_neighbours": None,
        "family": None,
        "genus": None,
    }
    assert JOIN(first, catalogue, SOURCE) == first


@pytest.mark.parametrize(
    "value", [None, "9.4", float("nan"), float("inf"), True, 91, -91]
)
def test_missing_or_invalid_gps_is_excluded_without_a_zero_fallback(value):
    atlas, catalogue = fixture()
    catalogue["photos"][0]["lat"] = value
    result = JOIN(atlas, catalogue, SOURCE)
    assert len(result["points"]) == 2
    assert result["provenance"]["photo_inventory"]["excluded_position_count"] == 1
    assert result["provenance"]["photo_inventory"]["catalogue_count"] == 3


@pytest.mark.parametrize("field", ["points", "photos"])
def test_duplicate_frame_keys_fail_without_alias_matching(field):
    atlas, catalogue = fixture()
    rows = atlas["points"] if field == "points" else catalogue["photos"]
    rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError, match="unique, nonempty frame keys"):
        JOIN(atlas, catalogue, SOURCE)


@pytest.mark.parametrize("index", [-1, 2, True, 0.5])
def test_corrupt_neighbour_index_cannot_select_an_unrelated_photo(index):
    atlas, catalogue = fixture()
    atlas["points"][0]["neighbours"][0][0] = index
    with pytest.raises(ValueError, match="outside its model pool"):
        JOIN(atlas, catalogue, SOURCE)


def test_empty_model_pool_can_still_show_recorded_photos():
    atlas, catalogue = fixture()
    atlas["points"] = []
    result = JOIN(atlas, catalogue, SOURCE)
    assert len(result["points"]) == 3
    assert all(not point["model_available"] for point in result["points"])
    assert result["provenance"]["photo_inventory"]["model_count"] == 0


def test_actual_published_models_get_identical_inventory_and_unchanged_rankings():
    def embedded(name, identifier):
        page = (ROOT / "docs" / name).read_text()
        return json.loads(
            re.search(
                rf'<script id="{identifier}" type="application/json">(.*?)</script>',
                page,
                re.DOTALL,
            )[1]
        )

    catalogue = embedded("explorer.html", "explorer-data")
    unified = []
    for filename in ("embedding-atlas.html", "crownfirst-atlas.html"):
        atlas = embedded(filename, "atlas-data")
        result = JOIN(atlas, catalogue, SOURCE)
        keyed = {point["key"]: point for point in result["points"]}
        for old in atlas["points"]:
            new = keyed[old["key"]]
            for field in ("neighbours", "other_mission_neighbours"):
                if old[field] is None:
                    assert new[field] is None
                else:
                    assert [
                        (result["points"][i]["key"], score) for i, score in new[field]
                    ] == [(atlas["points"][i]["key"], score) for i, score in old[field]]
        assert JOIN(result, catalogue, SOURCE) == result
        unified.append([point["key"] for point in result["points"]])
    assert unified[0] == unified[1]


@pytest.mark.parametrize("field", ["points", "photos"])
def test_non_photo_rows_fail_with_a_clear_inventory_error(field):
    atlas, catalogue = fixture()
    rows = atlas["points"] if field == "points" else catalogue["photos"]
    rows.append(None)
    with pytest.raises(TypeError, match="requires photo objects"):
        JOIN(atlas, catalogue, SOURCE)


def test_empty_inventory_has_no_fabricated_position_or_model_photo():
    atlas, catalogue = fixture()
    atlas["points"] = []
    catalogue["photos"] = []
    result = JOIN(atlas, catalogue, SOURCE)
    assert result["points"] == []
    assert result["provenance"]["photo_inventory"]["positioned_count"] == 0
    assert result["provenance"]["photo_inventory"]["model_count"] == 0


@pytest.mark.parametrize("latitude", [None, "9", 91, float("nan")])
def test_isolated_model_photo_with_invalid_catalogue_position_cannot_be_silently_dropped(
    latitude,
):
    atlas, catalogue = fixture()
    for point in atlas["points"]:
        point["neighbours"] = []
        point["other_mission_neighbours"] = None
    catalogue["photos"][2]["lat"] = latitude
    before = copy.deepcopy(atlas)
    with pytest.raises(
        ValueError,
        match="Recorded atlas model photo lacks a valid catalogue position: a.JPG",
    ):
        JOIN(atlas, catalogue, SOURCE)
    assert atlas == before


def test_already_missing_model_photo_with_invalid_position_remains_excluded():
    atlas, catalogue = fixture()
    joined = JOIN(atlas, catalogue, SOURCE)
    catalogue["photos"][0]["lat"] = None
    result = JOIN(joined, catalogue, SOURCE)
    assert [point["key"] for point in result["points"]] == ["b.JPG", "a.JPG"]
    assert result["provenance"]["photo_inventory"]["model_count"] == 2
    assert result["provenance"]["photo_inventory"]["excluded_position_count"] == 1


def test_builder_rejects_an_empty_photo_inventory_before_overwriting_a_page(tmp_path):
    build = runpy.run_path(str(ROOT / "dashboard/build_embedding_atlas.py"))["build"]
    source, output = tmp_path / "atlas.json", tmp_path / "atlas.html"
    source.write_text(json.dumps({"points": []}))
    output.write_text("last verified page")
    with pytest.raises(ValueError, match="at least one positioned photo"):
        build(source, output)
    assert output.read_text() == "last verified page"


def test_points_carry_the_family_and_genus_of_the_recorded_taxon_only():
    atlas, catalogue = fixture()
    catalogue["taxa"] = [
        {"id": "f", "name": "Fabaceae", "rank": "family", "parent": None},
        {"id": "g", "name": "Inga", "rank": "genus", "parent": "f"},
        {"id": "s", "name": "Inga alba", "rank": "species", "parent": "g"},
        {"id": "other", "name": "Moraceae", "rank": "family", "parent": None},
    ]
    by_key = {p["key"]: p for p in catalogue["photos"]}
    by_key["a.JPG"].update(recorded_taxon="s", predicted_taxon="other")
    by_key["b.JPG"]["recorded_taxon"] = "f"
    by_key["missing.JPG"]["recorded_taxon"] = "unknown"
    points = {p["key"]: p for p in JOIN(atlas, catalogue, SOURCE)["points"]}
    assert (points["a.JPG"]["family"], points["a.JPG"]["genus"]) == ("Fabaceae", "Inga")
    assert (points["b.JPG"]["family"], points["b.JPG"]["genus"]) == ("Fabaceae", None)
    assert (points["missing.JPG"]["family"], points["missing.JPG"]["genus"]) == (None, None)
