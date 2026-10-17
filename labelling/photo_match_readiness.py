"""Offline, fail-closed audit of frozen photo-match comparison inputs.

Schema 1 accepts two models, plantnet and plantclef. Frame crop boxes are
[left, top, right, bottom] source-pixel rectangles; source_size is [width, height].
Judgments are JSON {schema_version: 1, judgments: [...]} or CSV rows containing
query_key, candidate_key, query_crop_sha256, candidate_crop_sha256 and relevant.
JSON relevance must be boolean; CSV relevance must be 'true' or 'false'.
Judgment independence/completeness and protocol approval are explicit attestations,
not facts inferred by this tool. The audit neither scores nor retrieves images.
Available model records require input_crop_sha256 equal to the frozen crop hash.
Frames mark prospective_query_selected and explicit exposure_flags; selected queries
must be unexposed. protocol.review_pairs freezes exact [query_key, candidate_key]
assignments. This gate covers the different-tree endpoint and rejects same-tree
pairs. Receipt authenticity, crop pixels and biological independence require a
separate provenance review; this structural audit cannot establish them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

MODELS = ("plantnet", "plantclef")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def audit(manifest: object, root: str | Path) -> dict[str, Any]:
    """Return an auditable verdict without modifying inputs or using the network."""
    root = Path(root).resolve()
    issues: list[dict[str, str]] = []
    exclusions: list[dict[str, Any]] = []
    frames: dict[str, dict[str, Any]] = {}
    candidates: dict[str, set[str]] = {model: set() for model in MODELS}
    common: list[str] = []
    judgment_count = 0
    selected: set[str] = set()
    seen: set[tuple[str, str]] = set()

    def issue(code: str, location: str, detail: str) -> None:
        issues.append({"code": code, "location": location, "detail": detail})

    def asset(value: object, location: str) -> Path | None:
        if not isinstance(value, dict):
            issue("missing_asset", location, "Expected a path and SHA-256 receipt")
            return None
        relative, digest = value.get("path"), value.get("sha256")
        if not isinstance(relative, str) or not relative.strip():
            issue("missing_asset_path", location, "Asset path is absent")
            return None
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            issue("missing_asset_hash", location, "Expected lowercase SHA-256")
            return None
        try:
            path = (root / relative).resolve()
        except (OSError, ValueError, RuntimeError):
            issue("unsafe_asset_path", location, "Asset path cannot be resolved")
            return None
        if Path(relative).is_absolute() or not path.is_relative_to(root):
            issue("unsafe_asset_path", location, "Asset must resolve within root")
            return None
        try:
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(block)
            if hasher.hexdigest() != digest:
                issue("asset_hash_mismatch", location, "Bytes do not match receipt")
                return None
            if path.stat().st_size == 0:
                issue("empty_asset", location, "Asset contains no bytes")
                return None
        except (OSError, ValueError) as exc:
            issue("missing_asset_bytes", location, f"Cannot read asset: {exc}")
            return None
        return path

    def geometry(value: object, location: str) -> tuple[object, object] | None:
        if not isinstance(value, dict):
            issue("unknown_crop_geometry", location, "Missing model frame record")
            return None
        box, size = value.get("crop_box"), value.get("source_size")
        if not (
            isinstance(box, list)
            and len(box) == 4
            and isinstance(size, list)
            and len(size) == 2
            and all(type(n) is int for n in box + size)
        ):
            issue(
                "unknown_crop_geometry",
                location,
                "Expected integer crop_box and source_size",
            )
            return None
        left, top, right, bottom = box
        width, height = size
        if not (
            width > 0
            and height > 0
            and 0 <= left < right <= width
            and 0 <= top < bottom <= height
        ):
            issue(
                "invalid_crop_geometry",
                location,
                "Crop lies outside positive source dimensions",
            )
            return None
        return box, size

    if not isinstance(manifest, dict):
        issue("invalid_manifest", "manifest", "Expected a JSON object")
        manifest = {}
    if (
        type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 1
    ):
        issue("unsupported_schema", "schema_version", "Expected schema_version 1")
    model_records = manifest.get("models")
    for model in MODELS:
        record = model_records.get(model) if isinstance(model_records, dict) else None
        if not isinstance(record, dict):
            record = {}
        for field in ("checkpoint_identity", "preprocessing_receipt"):
            value = record.get(field)
            # Opaque exact run receipts are permitted, but placeholders are not identities.
            if (
                not isinstance(value, str)
                or value.strip().lower() in {"", "none", "null", "tile2x2 max"}
                or any(
                    token in value.lower()
                    for token in (
                        "unknown",
                        "unavailable",
                        "missing",
                        "not supplied",
                        "not recorded",
                        "unverified",
                    )
                )
            ):
                issue(
                    f"missing_{field}",
                    f"models.{model}.{field}",
                    "Exact historical model provenance is required",
                )
    frame_records = manifest.get("frames")
    if not isinstance(frame_records, list) or not frame_records:
        issue("missing_frames", "frames", "Expected a nonempty frame list")
        frame_records = []
    duplicate_keys: set[str] = set()
    for index, frame in enumerate(frame_records):
        location = f"frames[{index}]"
        if not isinstance(frame, dict):
            issue("invalid_frame", location, "Expected frame object")
            continue
        key = frame.get("key")
        if not isinstance(key, str) or not key.strip() or key != key.strip():
            issue(
                "missing_frame_key", location, "Expected nonempty exact frame identity"
            )
            exclusions.append(
                {"key": None, "reason": "missing_frame_key", "row": index}
            )
            continue
        if key in frames:
            issue("duplicate_frame_key", location, key)
            duplicate_keys.add(key)
            continue
        frames[key] = frame
        asset(frame.get("image"), f"{location}.image")
        asset(frame.get("crop"), f"{location}.crop")
        tree_id = frame.get("tree_id")
        if not isinstance(tree_id, str) or not tree_id.strip():
            issue(
                "unknown_tree_identity",
                location,
                "Verified physical-tree identity is required",
            )
        if frame.get("prospective_query_selected") is True:
            selected.add(key)
            if frame.get("exposure_flags") != []:
                issue(
                    "exposed_query",
                    location,
                    "Selected query needs explicit empty exposure_flags",
                )
        per_model = frame.get("models")
        if not isinstance(per_model, dict):
            per_model = {}
        geometries = []
        for model in MODELS:
            record = per_model.get(model)
            if (
                not isinstance(record, dict)
                or type(record.get("available")) is not bool
            ):
                issue(
                    "unknown_model_availability",
                    f"{location}.models.{model}",
                    "Availability must be explicitly true or false",
                )
                continue
            if record["available"]:
                candidates[model].add(key)
                digest = record.get("input_crop_sha256")
                crop = frame.get("crop")
                expected = crop.get("sha256") if isinstance(crop, dict) else None
                if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                    issue(
                        "missing_embedding_input_receipt",
                        f"{location}.models.{model}",
                        "Exact historical input crop hash required",
                    )
                elif digest != expected:
                    issue(
                        "different_model_input_bytes",
                        f"{location}.models.{model}",
                        "Embedding input differs from frozen crop",
                    )
                crop_geometry = geometry(record, f"{location}.models.{model}")
                if crop_geometry is not None:
                    geometries.append(crop_geometry)
        if len(geometries) == 2 and geometries[0] != geometries[1]:
            issue(
                "different_model_inputs",
                location,
                "Models do not use identical source size and crop rectangle",
            )
    common = sorted(set.intersection(*candidates.values()) - duplicate_keys)
    for key in sorted(frames):
        missing = [model for model in MODELS if key not in candidates[model]]
        if missing:
            exclusions.append(
                {
                    "key": key,
                    "reason": "missing_model_vectors",
                    "missing_models": missing,
                }
            )
        if key in duplicate_keys:
            exclusions.append(
                {"key": key, "reason": "duplicate_frame_key", "missing_models": []}
            )
    if candidates[MODELS[0]] != candidates[MODELS[1]]:
        issue(
            "unequal_candidate_sets",
            "frames",
            "Raw candidate sets differ; inspect explicit exclusions before approving a common universe",
        )
    if not common:
        issue("empty_common_candidates", "frames", "No unambiguous common candidates")
    if not selected:
        issue(
            "missing_prospective_queries",
            "frames",
            "Select at least one unexposed prospective query",
        )
    if selected - set(common):
        issue(
            "invalid_selected_query",
            "frames",
            "Selected queries must belong to the common universe",
        )
    protocol = manifest.get("protocol")
    if not isinstance(protocol, dict) or protocol.get("approved") is not True:
        issue(
            "unapproved_protocol",
            "protocol",
            "Frozen comparison protocol needs explicit approval",
        )
    review_pairs = protocol.get("review_pairs") if isinstance(protocol, dict) else None
    expected_pairs: set[tuple[str, str]] = set()
    if not isinstance(review_pairs, list) or not review_pairs:
        issue(
            "missing_review_assignment",
            "protocol.review_pairs",
            "Freeze a nonempty exact review assignment",
        )
        review_pairs = []
    for index, pair in enumerate(review_pairs):
        location = f"protocol.review_pairs[{index}]"
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not all(isinstance(key, str) for key in pair)
        ):
            issue(
                "invalid_review_pair", location, "Expected [query_key, candidate_key]"
            )
            continue
        query, candidate = pair
        assignment = query, candidate
        if (
            assignment in expected_pairs
            or query == candidate
            or query not in selected
            or candidate not in common
        ):
            issue(
                "invalid_review_pair",
                location,
                "Duplicate, self, unselected or unknown pair",
            )
        elif frames[query].get("tree_id") == frames[candidate].get("tree_id"):
            issue(
                "same_tree_pair",
                location,
                "Different-tree endpoint excludes repeat views",
            )
        expected_pairs.add(assignment)
    if selected - {query for query, _ in expected_pairs}:
        issue(
            "unassigned_selected_query",
            "protocol.review_pairs",
            "Every selected query needs review pairs",
        )
    judgments = manifest.get("judgments")
    if not isinstance(judgments, dict):
        judgments = {}
    if judgments.get("independent") is not True:
        issue(
            "missing_independent_judgments",
            "judgments",
            "Crop-level judgments must be independent of model outputs and whole-frame labels",
        )
    if judgments.get("complete") is not True:
        issue(
            "incomplete_judgments",
            "judgments",
            "The frozen review assignment is not complete",
        )
    judgment_path = asset(judgments, "judgments")
    if judgment_path is not None:
        try:
            rows: Any
            if judgment_path.suffix.lower() == ".csv":
                with judgment_path.open(newline="", encoding="utf-8") as stream:
                    rows = list(csv.DictReader(stream))
                csv_rows = True
            else:
                data = json.loads(judgment_path.read_text(encoding="utf-8"))
                if (
                    not isinstance(data, dict)
                    or type(data.get("schema_version")) is not int
                    or data.get("schema_version") != 1
                ):
                    raise ValueError("Expected judgment schema_version 1")
                rows = data.get("judgments")
                csv_rows = False
            if not isinstance(rows, list) or not rows:
                issue("empty_judgments", "judgments", "No completed crop judgments")
                rows = []
            for index, row in enumerate(rows):
                location = f"judgments[{index}]"
                if not isinstance(row, dict):
                    issue("invalid_judgment", location, "Expected judgment object")
                    continue
                query, candidate = row.get("query_key"), row.get("candidate_key")
                if (
                    not isinstance(query, str)
                    or not isinstance(candidate, str)
                    or query not in common
                    or candidate not in common
                ):
                    issue(
                        "unknown_judgment_frame",
                        location,
                        "Both frames must belong to the common universe",
                    )
                    continue
                pair = query, candidate
                if pair in seen or query == candidate:
                    issue("invalid_judgment_pair", location, "Duplicate or self pair")
                seen.add(pair)
                if query not in selected:
                    issue(
                        "unselected_judgment_query",
                        location,
                        "Judgment query was not prospectively selected",
                    )
                if frames[query].get("tree_id") == frames[candidate].get("tree_id"):
                    issue(
                        "same_tree_pair",
                        location,
                        "Different-tree endpoint excludes repeat views",
                    )
                for role, key in (("query", query), ("candidate", candidate)):
                    crop = frames[key].get("crop")
                    digest = crop.get("sha256") if isinstance(crop, dict) else None
                    actual = row.get(f"{role}_crop_sha256")
                    if (
                        not isinstance(actual, str)
                        or not SHA256.fullmatch(actual)
                        or actual != digest
                    ):
                        issue(
                            "judgment_crop_mismatch",
                            location,
                            f"{role} judgment is not bound to the frozen crop",
                        )
                relevant = row.get("relevant")
                if (csv_rows and relevant not in ("true", "false")) or (
                    not csv_rows and type(relevant) is not bool
                ):
                    issue(
                        "missing_judgment_label",
                        location,
                        "Expected explicit boolean relevance",
                    )
                judgment_count += 1
        except (OSError, UnicodeError, ValueError, csv.Error) as exc:
            issue("invalid_judgments", "judgments", str(exc))
    if seen != expected_pairs:
        issue(
            "judgment_assignment_mismatch",
            "judgments",
            "Judgments must cover exactly the frozen review pairs",
        )
    return {
        "schema_version": 1,
        "ready": not issues,
        "issues": issues,
        "common_candidate_keys": common,
        "exclusions": exclusions,
        "counts": {
            "frames": len(frames),
            "common_candidates": len(common),
            "judgments": judgment_count,
            "selected_queries": len(selected),
            **{f"{model}_candidates": len(keys) for model, keys in candidates.items()},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = audit(manifest, args.root)
    except (OSError, UnicodeError, ValueError) as exc:
        result = {
            "schema_version": 1,
            "ready": False,
            "issues": [
                {"code": "invalid_manifest", "location": "manifest", "detail": str(exc)}
            ],
        }
    # Never overwrite a supplied input, including symlink aliases of input assets.
    output = args.output.resolve()
    protected = {args.manifest.resolve()}
    if isinstance(locals().get("manifest"), dict):
        records = [manifest.get("judgments")]
        for frame in (
            manifest.get("frames", [])
            if isinstance(manifest.get("frames"), list)
            else []
        ):
            if isinstance(frame, dict):
                records.extend((frame.get("image"), frame.get("crop")))
        for record in records:
            if isinstance(record, dict) and isinstance(record.get("path"), str):
                try:
                    protected.add((args.root / record["path"]).resolve())
                except (OSError, ValueError, RuntimeError):
                    pass  # The audit already reports this invalid input path.
    if output in protected or any(
        output.exists() and path.exists() and output.samefile(path)
        for path in protected
    ):
        parser.error("--output must not overwrite any input")
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
