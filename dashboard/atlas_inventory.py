"""Join recorded atlas evidence to one positioned photo catalogue, offline."""

from __future__ import annotations

import copy
import math
import re
from typing import Any

ANNOTATION_URL = re.compile(
    r"https://app\.labelbox\.com/projects/[A-Za-z0-9]+/data-rows/[A-Za-z0-9]+"
)


def inventory_digest(data: dict[str, Any]) -> str:
    """Identify the exact recorded inventory, independently of catalogue ordering."""
    sources = data.get("provenance", {}).get("sources", [])
    inventory = [
        source
        for source in sources
        if source.get("file") == "dataset_rows_combined.jsonl"
    ]
    if len(inventory) != 1 or not re.fullmatch(
        r"[a-f0-9]{64}", str(inventory[0].get("sha256", ""))
    ):
        raise ValueError("Annotation join requires one hashed inventory source")
    return inventory[0]["sha256"]


def _by_key(rows: list[dict[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError(
                f"{name} requires photo objects with unique, nonempty frame keys"
            )
        key = row.get("key")
        if not isinstance(key, str) or not key.strip() or key in result:
            raise ValueError(f"{name} requires unique, nonempty frame keys")
        result[key] = row
    return result


def _positioned(photo: dict[str, Any]) -> bool:
    for coordinate, limit in (("lat", 90), ("lon", 180)):
        value = photo.get(coordinate)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not math.isfinite(value) or not -limit <= value <= limit:
            return False
    return True


def recorded_lineage(photo: dict[str, Any], taxa: dict[str, dict[str, Any]]):
    """Family and genus of the photo's recorded taxon, never of a predicted one."""
    found: dict[str, str] = {}
    taxon = taxa.get(photo.get("recorded_taxon"))
    while taxon and taxon["rank"] not in found:
        found[taxon["rank"]] = taxon["name"]
        taxon = taxa.get(taxon["parent"])
    return found.get("family"), found.get("genus")


def join_photo_inventory(
    atlas: dict[str, Any], catalogue: dict[str, Any], source: dict[str, str]
) -> dict[str, Any]:
    """Keep model evidence intact while allowing every positioned photo selection.

    Neighbour indices refer to the original atlas order. Remapping changes only
    indices, never candidate identity, order, or recorded similarity scores.
    """
    digest = inventory_digest(atlas)
    if inventory_digest(catalogue) != digest:
        raise ValueError("Annotation catalogue inventory source hash mismatch")
    if not isinstance(atlas.get("points"), list) or not isinstance(
        catalogue.get("photos"), list
    ):
        raise TypeError(
            "Photo inventory requires atlas points and catalogue photos lists"
        )
    old_points = atlas["points"]
    existing = _by_key(old_points, "Atlas")
    photos = _by_key(catalogue["photos"], "Annotation catalogue")
    for key in existing:
        if key not in photos:
            raise ValueError("Atlas frame absent from annotation catalogue: " + key)
    for key, photo in photos.items():
        url = photo.get("annotation_url")
        if url is not None and (
            not isinstance(url, str) or not ANNOTATION_URL.fullmatch(url)
        ):
            raise ValueError("Invalid source Labelbox annotation URL for: " + key)
    positioned = [photo for photo in catalogue["photos"] if _positioned(photo)]
    taxa = {taxon["id"]: taxon for taxon in catalogue.get("taxa", [])}
    new_indices = {photo["key"]: index for index, photo in enumerate(positioned)}
    for key, point in existing.items():
        if point.get("model_available", True) is not False and key not in new_indices:
            raise ValueError(
                "Recorded atlas model photo lacks a valid catalogue position: " + key
            )

    def remap(neighbours: Any) -> Any:
        if neighbours is None:
            return None
        if not isinstance(neighbours, list):
            raise TypeError("Recorded atlas neighbours must be a list or null")
        result = []
        for pair in neighbours:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(
                    "Recorded atlas neighbour must contain index and score"
                )
            index, score = pair
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or not 0 <= index < len(old_points)
            ):
                raise ValueError(
                    "Recorded atlas neighbour index is outside its model pool"
                )
            key = old_points[index]["key"]
            if key not in new_indices:
                raise ValueError(
                    "Recorded atlas neighbour lacks a valid catalogue position: " + key
                )
            if existing[key].get("model_available", True) is False:
                raise ValueError(
                    "Recorded atlas neighbour has no model evidence: " + key
                )
            result.append([new_indices[key], score])
        return result

    points = []
    for photo in positioned:
        old = existing.get(photo["key"])
        if old is not None and old.get("model_available", True) is not False:
            point = copy.deepcopy(old)
            point["model_available"] = True
            point["neighbours"] = remap(old.get("neighbours", []))
            if "other_mission_neighbours" in old:
                point["other_mission_neighbours"] = remap(
                    old["other_mission_neighbours"]
                )
            point["annotation_url"] = photo.get("annotation_url")
        else:
            point = {
                field: photo.get(field)
                for field in (
                    "key",
                    "label",
                    "mission",
                    "lat",
                    "lon",
                    "annotation_url",
                )
            }
            point.update(
                group="Labelled" if photo.get("label") else "Unlabelled",
                model_available=False,
                neighbours=[],
                other_mission_neighbours=None,
            )
        point["family"], point["genus"] = recorded_lineage(photo, taxa)
        points.append(point)
    result = copy.deepcopy(atlas)
    result["points"] = points
    result["provenance"]["photo_inventory"] = {
        "source": source,
        "inventory_sha256": digest,
        "catalogue_count": len(photos),
        "positioned_count": len(points),
        "excluded_position_count": len(photos) - len(points),
        "model_count": sum(point["model_available"] for point in points),
        "method": "Exact frame-key join; recorded model neighbours retain their order and scores",
    }
    result["provenance"]["annotation_links"] = {
        "source": source,
        "inventory_sha256": digest,
        "matched_count": sum(
            point.get("annotation_url") is not None for point in points
        ),
        "pool_size": len(points),
        "method": "Exact frame-key join against the same recorded inventory",
        "meaning": "Recorded Labelbox data-row links; access may require a project login",
    }
    return result
