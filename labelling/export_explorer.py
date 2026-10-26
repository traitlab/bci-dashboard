"""Build an offline photo catalogue independently of representation coverage.

Rebuild docs/explorer.html byte for byte (OUT is any scratch dir, DATA the data root):

    python labelling/export_explorer.py --data-root DATA --plantnet-atlas embedding-atlas.json --output OUT/cat.json
    mkdir OUT/site && cp docs/* OUT/site/
    python dashboard/build_explorer.py --input OUT/cat.json --output OUT/site/explorer.html
    python -m dashboard.refresh_site_ui --site OUT/site --out OUT/out   # OUT/out/explorer.html

The refresh step adds the full nav (data-photo-pages), so build_explorer output alone differs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from atlas_taxonomy import (
    PROJECT,
    Taxonomy,
    canonical_frame,
    decode_json,
    digest,
    load_predictions,
    read_json,
    text,
    unique_frames,
)

ANNOTATION = re.compile(
    r"https://app\.labelbox\.com/projects/[A-Za-z0-9]+/data-rows/[A-Za-z0-9]+"
)


def source(path, sources):
    path = Path(path)
    if path.exists():
        sources.append({"file": path.name, "sha256": digest(path)})
        value = read_json(path)
        if not isinstance(value, dict):
            raise TypeError(f"JSON source must be an object: {path}")
        return value
    return None


def labels_from(path, sources):
    if not path.exists():
        return {}
    sources.append({"file": path.name, "sha256": digest(path)})
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"global_key", "wcvp_canonical_name"} <= set(reader.fieldnames or []):
            raise ValueError("Labels require global_key and wcvp_canonical_name")
        return unique_frames(
            (
                (row["global_key"], text(row["wcvp_canonical_name"], "recorded label"))
                for row in reader
            ),
            "recorded labels",
        )


def representations(atlas):
    if atlas is None:
        return {}, None
    if not isinstance(atlas, dict) or not isinstance(atlas.get("points"), list):
        raise TypeError("Representation atlas must contain points")
    points = atlas["points"]
    unique_frames(((p["key"], p) for p in points), "representation atlas")
    records = []
    for point in points:
        neighbours = []
        for pair in point.get("neighbours", []):
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or type(pair[0]) is not int
                or not 0 <= pair[0] < len(points)
                or type(pair[1]) not in (int, float)
                or not math.isfinite(pair[1])
                or not -1 <= pair[1] <= 1
            ):
                raise ValueError("Invalid representation neighbour")
            neighbours.append({"key": points[pair[0]]["key"], "score": pair[1]})
        record = {
            "version": text(point.get("version"), "representation version"),
            "neighbours": neighbours,
        }
        for field in ("crop", "source_width", "source_height"):
            value = point.get(field)
            if value is not None and (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"Invalid representation {field}")
            record[field] = value
        records.append((point["key"], record))
    return unique_frames(records, "representation atlas"), atlas.get("provenance", {})


def position(row):
    attributes = row.get("media_attributes")
    if attributes is not None and not isinstance(attributes, dict):
        raise TypeError("Inventory media_attributes must be an object")
    point = (attributes or {}).get("gpsPoint")
    if point is None:
        return None, None
    if not isinstance(point, str):
        raise TypeError("Inventory gpsPoint must be a string or null")
    try:
        lat, lon = map(float, point.split(","))
    except ValueError as error:
        raise ValueError("Invalid inventory gpsPoint") from error
    if (
        not math.isfinite(lat)
        or not math.isfinite(lon)
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
    ):
        raise ValueError("Invalid inventory gpsPoint")
    return lat, lon


def export_catalogue(data_root, plantnet_atlas=None):
    root = Path(data_root)
    sources = []
    inventory = root / "dataset_rows_combined.jsonl"
    sources.append({"file": inventory.name, "sha256": digest(inventory)})
    rows = []
    for line in inventory.read_text().splitlines():
        if line.strip():
            row = decode_json(line, inventory)
            if not isinstance(row, dict):
                raise ValueError("Inventory row must be an object")
            rows.append(row)
    inventory_keys = unique_frames(
        ((r.get("global_key"), r["global_key"]) for r in rows), "inventory"
    )
    labels = labels_from(root / "gt_dominant_taxon.csv", sources)
    checklist = source(root / f"checklist_{PROJECT}.json", sources)
    keys = source(root / "gbif_keys.json", sources)
    wcvp = source(root / "wcvp_cache.json", sources)
    taxonomy = Taxonomy(checklist, keys, wcvp)
    predictions, prediction_provenance = load_predictions(
        root / "predictions/cache", taxonomy
    )
    atlas = (
        source(plantnet_atlas, sources)
        if isinstance(plantnet_atlas, (str, Path))
        else plantnet_atlas
    )
    if plantnet_atlas is not None and atlas is None:
        raise ValueError("Provided representation atlas does not exist")
    representation, representation_provenance = representations(atlas)
    for alias, record in representation.items():
        if alias not in inventory_keys:
            raise ValueError("Representation frame is absent from inventory: " + alias)
        for neighbour in record["neighbours"]:
            neighbour["key"] = inventory_keys[canonical_frame(neighbour["key"])]
    photos, references = [], []
    for row in rows:
        key = row["global_key"]
        alias = canonical_frame(key)
        label = labels.get(alias)
        recorded, status = taxonomy.recorded(label)
        prediction = predictions.get(
            alias,
            {
                "status": "missing",
                "name": None,
                "taxon": None,
                "score": None,
                "version": None,
                "project": None,
                "project_source": None,
                "tied": False,
                "original_name": None,
            },
        )
        metadata = row.get("metadata")
        metadata = {} if metadata is None else metadata
        if not isinstance(metadata, dict):
            raise TypeError("Inventory metadata must be an object")
        annotation = text(metadata.get("original_labelbox_url"), "annotation URL")
        if annotation and not ANNOTATION.fullmatch(annotation):
            annotation = None
        lat, lon = position(row)
        photos.append(
            {
                "key": key,
                "mission": text(metadata.get("mission"), "mission"),
                "lat": lat,
                "lon": lon,
                "label": label,
                "recorded_taxon": recorded,
                "recorded_status": status,
                "prediction": prediction,
                "representation": representation.get(alias),
                "annotation_url": annotation,
            }
        )
        references.extend((recorded, prediction["taxon"]))
    coverage = {
        "photos": len(photos),
        "recorded": dict(Counter(p["recorded_status"] for p in photos)),
        "predictions": dict(Counter(p["prediction"]["status"] for p in photos)),
        "representation": sum(p["representation"] is not None for p in photos),
        "annotation_links": sum(p["annotation_url"] is not None for p in photos),
        "prediction_ties": sum(p["prediction"]["tied"] for p in photos),
    }
    return {
        "schema_version": 1,
        "photos": photos,
        "taxa": taxonomy.used(references),
        "provenance": {
            "sources": sources,
            "predictions": prediction_provenance,
            "representation": representation_provenance,
            "taxonomy": {
                "project": PROJECT,
                "available": checklist is not None,
                "local_ids": "Family/genus IDs are local facet keys, not global taxon identifiers.",
                "prediction_basis": "Top returned Pl@ntNet candidate, not a confirmed label.",
                "recorded_basis": "Original recorded frame labels, not every visible crown.",
            },
        },
        "coverage": coverage,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(
            os.environ.get(
                "BCI_DASHBOARD_DATA", Path(__file__).resolve().parents[1] / "data"
            )
        ),
    )
    parser.add_argument("--plantnet-atlas", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("build/explorer-catalogue.json")
    )
    args = parser.parse_args()
    catalogue = export_catalogue(args.data_root, args.plantnet_atlas)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            catalogue, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
    )


if __name__ == "__main__":
    main()
