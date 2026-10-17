"""Contract tests for the offline comparison readiness gate."""

import copy
import hashlib
import json
import subprocess
import sys

import pytest
from conftest import REPO, load

audit = load(
    "_photo_match_readiness_under_test", REPO / "labelling" / "photo_match_readiness.py"
).audit


def receipt(root, name, contents):
    path = root / name
    path.write_bytes(contents)
    return {"path": name, "sha256": hashlib.sha256(contents).hexdigest()}


@pytest.fixture
def prepared(tmp_path):
    frames = []
    for index in range(2):
        frames.append(
            {
                "key": f"mission/frame-{index}.jpg",
                "tree_id": f"verified-tree-{index}",
                "prospective_query_selected": index == 0,
                "exposure_flags": [],
                "image": receipt(
                    tmp_path, f"image-{index}.jpg", f"original-{index}".encode()
                ),
                "crop": receipt(
                    tmp_path, f"crop-{index}.jpg", f"crop-{index}".encode()
                ),
                "models": {
                    name: {
                        "available": True,
                        "crop_box": [10, 5, 90, 75],
                        "source_size": [100, 80],
                    }
                    for name in ("plantnet", "plantclef")
                },
            }
        )
    for frame in frames:
        for model in frame["models"].values():
            model["input_crop_sha256"] = frame["crop"]["sha256"]
    rows = [
        {
            "query_key": frames[0]["key"],
            "candidate_key": frames[1]["key"],
            "query_crop_sha256": frames[0]["crop"]["sha256"],
            "candidate_crop_sha256": frames[1]["crop"]["sha256"],
            "relevant": True,
        }
    ]
    judgments = receipt(
        tmp_path,
        "judgments.json",
        json.dumps({"schema_version": 1, "judgments": rows}).encode(),
    )
    judgments.update(independent=True, complete=True)
    manifest = {
        "schema_version": 1,
        "frames": frames,
        "models": {
            name: {
                "checkpoint_identity": f"sha256:{'a' * 64}",
                "preprocessing_receipt": "frozen-recipe-v1, resize 256, center crop 224",
            }
            for name in ("plantnet", "plantclef")
        },
        "judgments": judgments,
        "protocol": {
            "approved": True,
            "review_pairs": [[frames[0]["key"], frames[1]["key"]]],
        },
    }
    return manifest, tmp_path


def codes(result):
    return {item["code"] for item in result["issues"]}


def test_complete_input_and_deterministic_common_universe(prepared):
    manifest, root = prepared
    before = copy.deepcopy(manifest)
    result = audit(manifest, root)
    assert result["ready"] is True
    assert result["common_candidate_keys"] == sorted(
        frame["key"] for frame in manifest["frames"]
    )
    assert result["exclusions"] == []
    assert manifest == before


@pytest.mark.parametrize(
    "manifest",
    [None, {}, {"schema_version": 1, "frames": []}, {"schema_version": True}],
)
def test_absent_or_empty_input_never_ready(tmp_path, manifest):
    result = audit(manifest, tmp_path)
    assert not result["ready"]
    assert "missing_frames" in codes(result)


def test_duplicate_and_missing_keys_are_explicit(prepared):
    manifest, root = prepared
    manifest["frames"].append(copy.deepcopy(manifest["frames"][0]))
    manifest["frames"].append({"models": {}})
    result = audit(manifest, root)
    assert {"duplicate_frame_key", "missing_frame_key"} <= codes(result)
    assert manifest["frames"][0]["key"] not in result["common_candidate_keys"]
    assert {row["reason"] for row in result["exclusions"]} == {
        "duplicate_frame_key",
        "missing_frame_key",
    }


def test_unequal_candidates_keep_exclusions_visible(prepared):
    manifest, root = prepared
    manifest["frames"][0]["models"]["plantnet"]["available"] = False
    result = audit(manifest, root)
    assert not result["ready"]
    assert "unequal_candidate_sets" in codes(result)
    assert result["exclusions"] == [
        {
            "key": manifest["frames"][0]["key"],
            "reason": "missing_model_vectors",
            "missing_models": ["plantnet"],
        }
    ]


@pytest.mark.parametrize(
    "box,size,expected",
    [
        (None, None, "unknown_crop_geometry"),
        ([0, 0, 101, 80], [100, 80], "invalid_crop_geometry"),
        ([1, 1, 1, 2], [100, 80], "invalid_crop_geometry"),
        ([False, 0, 3, 3], [100, 80], "unknown_crop_geometry"),
        ([0, 0, 3, 3], [100, 80], "different_model_inputs"),
    ],
)
def test_geometry_must_be_known_bounded_and_identical(prepared, box, size, expected):
    manifest, root = prepared
    manifest["frames"][0]["models"]["plantclef"].update(crop_box=box, source_size=size)
    result = audit(manifest, root)
    assert not result["ready"]
    assert expected in codes(result)


@pytest.mark.parametrize("field", ["checkpoint_identity", "preprocessing_receipt"])
@pytest.mark.parametrize(
    "value", [None, "", "unknown", "tile2x2 max", "API 7.5, weights not supplied"]
)
def test_exact_historical_provenance_required(prepared, field, value):
    manifest, root = prepared
    manifest["models"]["plantclef"][field] = value
    assert f"missing_{field}" in codes(audit(manifest, root))


def test_independent_complete_approved_judgments_required(prepared):
    manifest, root = prepared
    manifest["judgments"].update(independent=False, complete=False)
    manifest["protocol"]["approved"] = False
    result = audit(manifest, root)
    assert {
        "missing_independent_judgments",
        "incomplete_judgments",
        "unapproved_protocol",
    } <= codes(result)


@pytest.mark.parametrize("asset_name", ["image", "crop"])
def test_missing_and_tampered_image_bytes(prepared, asset_name):
    manifest, root = prepared
    path = root / manifest["frames"][0][asset_name]["path"]
    path.write_bytes(b"tampered")
    assert "asset_hash_mismatch" in codes(audit(manifest, root))
    path.unlink()
    assert "missing_asset_bytes" in codes(audit(manifest, root))


def test_missing_tree_identity_is_not_replaced_with_proximity(prepared):
    manifest, root = prepared
    manifest["frames"][0]["tree_id"] = None
    assert "unknown_tree_identity" in codes(audit(manifest, root))


@pytest.mark.parametrize("path", ["../outside.jpg", "/etc/passwd", "bad\x00path"])
def test_asset_path_must_stay_inside_package(prepared, path):
    manifest, root = prepared
    manifest["frames"][0]["image"]["path"] = path
    assert "unsafe_asset_path" in codes(audit(manifest, root))


def test_symlink_escape_rejected(prepared, tmp_path):
    manifest, root = prepared
    (root / "escape").symlink_to(root.parent)
    manifest["frames"][0]["image"]["path"] = "escape/private.jpg"
    assert "unsafe_asset_path" in codes(audit(manifest, root))


@pytest.mark.parametrize(
    "change,expected",
    [
        ("crop", "judgment_crop_mismatch"),
        ("label", "missing_judgment_label"),
        ("frame", "unknown_judgment_frame"),
        ("self", "invalid_judgment_pair"),
        ("duplicate", "invalid_judgment_pair"),
        ("empty", "empty_judgments"),
    ],
)
def test_judgments_bind_frozen_crops_and_valid_pairs(prepared, change, expected):
    manifest, root = prepared
    data = json.loads((root / "judgments.json").read_text())
    row = data["judgments"][0]
    if change == "crop":
        row["query_crop_sha256"] = "0" * 64
    elif change == "label":
        row["relevant"] = "true"
    elif change == "frame":
        row["query_key"] = "absent.jpg"
    elif change == "self":
        row["candidate_key"] = row["query_key"]
    elif change == "duplicate":
        data["judgments"].append(copy.deepcopy(row))
    else:
        data["judgments"] = []
    manifest["judgments"].update(
        receipt(root, "judgments.json", json.dumps(data).encode())
    )
    assert expected in codes(audit(manifest, root))


def test_judgment_tampering_and_invalid_json(prepared):
    manifest, root = prepared
    (root / "judgments.json").write_text("changed")
    assert "asset_hash_mismatch" in codes(audit(manifest, root))
    manifest["judgments"].update(receipt(root, "judgments.json", b"not JSON"))
    assert "invalid_judgments" in codes(audit(manifest, root))


def test_csv_judgments_and_cli_exit_codes(prepared):
    manifest, root = prepared
    data = json.loads((root / "judgments.json").read_text())["judgments"][0]
    contents = (
        ",".join(data)
        + "\n"
        + ",".join(
            str(value).lower() if type(value) is bool else value
            for value in data.values()
        )
        + "\n"
    )
    manifest["judgments"].update(receipt(root, "judgments.csv", contents.encode()))
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest))
    command = [
        sys.executable,
        "-m",
        "labelling.photo_match_readiness",
        str(path),
        "--root",
        str(root),
        "--output",
        str(root / "result.json"),
    ]
    assert subprocess.run(command, capture_output=True, check=False).returncode == 0
    manifest["models"]["plantclef"]["checkpoint_identity"] = None
    path.write_text(json.dumps(manifest))
    assert subprocess.run(command, capture_output=True, check=False).returncode == 2
    assert json.loads((root / "result.json").read_text())["ready"] is False
    before = path.read_bytes()
    command[-1] = str(path)
    assert subprocess.run(command, capture_output=True, check=False).returncode == 2
    assert path.read_bytes() == before


def test_cli_malformed_asset_is_not_a_crash(prepared):
    manifest, root = prepared
    manifest["frames"][0]["image"]["path"] = "invalid\x00path"
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest))
    output = root / "readiness.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "labelling.photo_match_readiness",
            str(path),
            "--root",
            str(root),
            "--output",
            str(output),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "unsafe_asset_path" in codes(json.loads(output.read_text()))
    assert b"Traceback" not in result.stderr


@pytest.mark.parametrize(
    "digest,expected",
    [
        (None, "missing_embedding_input_receipt"),
        ("0" * 64, "different_model_input_bytes"),
    ],
)
def test_embedding_material_receipt_is_required(prepared, digest, expected):
    manifest, root = prepared
    manifest["frames"][0]["models"]["plantclef"]["input_crop_sha256"] = digest
    assert expected in codes(audit(manifest, root))


@pytest.mark.parametrize("flags", [None, ["closed-control"], ["already-seen"]])
def test_selected_query_must_have_explicit_empty_exposure(prepared, flags):
    manifest, root = prepared
    manifest["frames"][0]["exposure_flags"] = flags
    assert "exposed_query" in codes(audit(manifest, root))


def test_query_selection_is_required_and_judgments_cannot_select_queries(prepared):
    manifest, root = prepared
    manifest["frames"][0]["prospective_query_selected"] = False
    assert {
        "missing_prospective_queries",
        "unselected_judgment_query",
        "invalid_review_pair",
    } <= codes(audit(manifest, root))


def test_different_tree_endpoint_rejects_same_tree_pairs(prepared):
    manifest, root = prepared
    manifest["frames"][1]["tree_id"] = manifest["frames"][0]["tree_id"]
    assert "same_tree_pair" in codes(audit(manifest, root))


@pytest.mark.parametrize(
    "pairs,expected",
    [
        (None, "missing_review_assignment"),
        ([], "missing_review_assignment"),
        ([["mission/frame-0.jpg", "absent"]], "invalid_review_pair"),
        ([["mission/frame-0.jpg", "mission/frame-0.jpg"]], "invalid_review_pair"),
        (
            [
                ["mission/frame-0.jpg", "mission/frame-1.jpg"],
                ["mission/frame-0.jpg", "mission/frame-1.jpg"],
            ],
            "invalid_review_pair",
        ),
    ],
)
def test_review_assignment_must_be_explicit_nonempty_and_valid(
    prepared, pairs, expected
):
    manifest, root = prepared
    manifest["protocol"]["review_pairs"] = pairs
    assert expected in codes(audit(manifest, root))


def test_judgment_completion_is_exact_assignment_coverage(prepared):
    manifest, root = prepared
    manifest["frames"][1]["prospective_query_selected"] = True
    manifest["protocol"]["review_pairs"].append(
        [manifest["frames"][1]["key"], manifest["frames"][0]["key"]]
    )
    assert "judgment_assignment_mismatch" in codes(audit(manifest, root))
