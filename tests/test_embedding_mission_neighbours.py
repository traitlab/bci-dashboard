"""Mission-restricted retrieval uses the full measured representation pool."""

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MISSING = object()


def export_pool(tmp_path, vectors, missions, neighbours=12):
    np = pytest.importorskip("numpy")
    spec = importlib.util.spec_from_file_location(
        "export_embedding_atlas", ROOT / "labelling/export_embedding_atlas.py"
    )
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    rows = []
    for i, mission in enumerate(missions):
        rows.append(
            {
                "global_key": str(i),
                "media_attributes": {"gpsPoint": "9.1,-79.8"},
                "metadata": {} if mission is MISSING else {"mission": mission},
                "row_data": "https://example.org/frame.jpg",
            }
        )
    inventory = tmp_path / "dataset_rows_combined.jsonl"
    inventory.write_text("\n".join(map(json.dumps, rows)))
    source = tmp_path / "vectors.json"
    source.write_text(json.dumps({str(i): vector for i, vector in enumerate(vectors)}))
    payload = exporter.export(
        tmp_path,
        neighbours=neighbours,
        crownfirst_embeddings=source,
        encoder_label="test-encoder",
    )
    assert payload["provenance"]["sources"] == [
        {"file": source.name, "sha256": exporter.sha(source)},
        {"file": inventory.name, "sha256": exporter.sha(inventory)},
    ]
    # This is the default ranking algorithm before mission-restricted retrieval.
    x = np.asarray(vectors, dtype=np.float64)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    for i, point in enumerate(payload["points"]):
        scores = x[i : i + 1] @ x.T
        scores[0, i] = -np.inf
        near = np.argsort(-scores[0], kind="stable")[: min(neighbours, len(x) - 1)]
        assert point["neighbours"] == [
            [int(j), round(float(scores[0, j]), 5)] for j in near
        ]
    return payload


def test_filters_full_pool_before_ranking_beyond_stored_neighbours(tmp_path):
    vectors = [[1.0, 0, 0]] + [[1.0, i / 1000, 0] for i in range(1, 14)]
    vectors.append([0.6, 0.8, 0])
    result = export_pool(tmp_path, vectors, ["flight-a"] * 14 + ["flight-b"])
    query = result["points"][0]
    assert len(query["neighbours"]) == 12
    assert 14 not in [index for index, _ in query["neighbours"]]
    assert query["other_mission_neighbours"] == [[14, 0.6]]


def test_eligible_ties_keep_pool_order_and_requested_limit(tmp_path):
    result = export_pool(
        tmp_path,
        [[1.0, 0, 0], [0, 1.0, 0], [1.0, 0, 0], [0, 1.0, 0], [0, 1.0, 0]],
        ["flight-a", "flight-b", "flight-a", "flight-c", "flight-d"],
        neighbours=2,
    )
    assert result["points"][0]["other_mission_neighbours"] == [[1, 0.0], [3, 0.0]]


@pytest.mark.parametrize("mission", [MISSING, None, "", " \t\n", 12, {}, ["flight-a"]])
def test_unknown_query_unavailable_and_unknown_candidates_excluded(tmp_path, mission):
    result = export_pool(
        tmp_path, [[1.0, 0, 0], [1.0, 0, 0]], [mission, "flight-b"]
    )
    unknown, known = result["points"]
    assert unknown["mission"] == ("" if mission is MISSING else mission)
    assert unknown["other_mission_neighbours"] is None
    assert known["other_mission_neighbours"] == []
    # Unknown missions remain available in unrestricted similarity retrieval.
    assert known["neighbours"] == [[0, 1.0]]


def test_matching_trims_only_whitespace_and_preserves_recorded_missions(tmp_path):
    missions = [" flight-a\t", "flight-a", "flight-b", " Flight-a "]
    result = export_pool(tmp_path, [[1.0, 0, 0]] * 4, missions)
    assert [point["mission"] for point in result["points"]] == missions
    assert result["points"][0]["other_mission_neighbours"] == [[2, 1.0], [3, 1.0]]
    meaning = result["provenance"]["other_mission_neighbours"]
    assert "other known mission IDs" in meaning
    assert "do not imply distinct trees or independent biological evidence" in meaning


def test_same_mission_only_has_no_eligible_neighbours(tmp_path):
    result = export_pool(
        tmp_path, [[1.0, 0, 0], [0, 1.0, 0]], ["flight-a", " flight-a "]
    )
    assert all(point["other_mission_neighbours"] == [] for point in result["points"])


def test_mission_changes_leave_default_representations_identical(tmp_path):
    vectors = [[1.0, 0, 0], [0.8, 0.6, 0], [0, 0, 1.0], [1.0, 0, 0]]
    before = export_pool(tmp_path, vectors, [MISSING] * 4)
    after = export_pool(tmp_path, vectors, ["a", "b", "b", "c"])
    for old, new in zip(before["points"], after["points"]):
        assert {
            k: v
            for k, v in old.items()
            if k not in {"mission", "other_mission_neighbours"}
        } == {
            k: v
            for k, v in new.items()
            if k not in {"mission", "other_mission_neighbours"}
        }
