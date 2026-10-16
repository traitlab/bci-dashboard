"""Build the self-contained spatial representation explorer, using stdlib only."""

import argparse
import hashlib
import json
import re
import runpy
from pathlib import Path

ANNOTATION_URL = re.compile(
    r"https://app\.labelbox\.com/projects/[A-Za-z0-9]+/data-rows/[A-Za-z0-9]+"
)


def inventory_digest(data):
    sources = data.get("provenance", {}).get("sources", [])
    inventory = [s for s in sources if s.get("file") == "dataset_rows_combined.jsonl"]
    if len(inventory) != 1 or not re.fullmatch(
        r"[a-f0-9]{64}", str(inventory[0].get("sha256", ""))
    ):
        raise ValueError("Annotation join requires one hashed inventory source")
    return inventory[0]["sha256"]


def attach_annotation_links(atlas, source):
    """Attach recorded Labelbox links without altering representation evidence."""
    source = Path(source)
    raw = source.read_bytes()
    catalogue = json.loads(raw)
    digest = inventory_digest(atlas)
    if inventory_digest(catalogue) != digest:
        raise ValueError("Annotation catalogue inventory source hash mismatch")
    links = {}
    for photo in catalogue["photos"]:
        key = photo.get("key")
        if not isinstance(key, str) or not key.strip() or key in links:
            raise ValueError("Annotation catalogue requires unique, nonempty frame keys")
        url = photo.get("annotation_url")
        if url is not None and (
            not isinstance(url, str) or not ANNOTATION_URL.fullmatch(url)
        ):
            raise ValueError("Invalid source Labelbox annotation URL for: " + key)
        links[key] = url
    keys = set()
    for photo in atlas["points"]:
        key = photo.get("key")
        if not isinstance(key, str) or not key.strip() or key in keys:
            raise ValueError("Annotation join requires unique, nonempty atlas frame keys")
        if key not in links:
            raise ValueError("Atlas frame absent from annotation catalogue: " + key)
        keys.add(key)
    for photo in atlas["points"]:
        photo["annotation_url"] = links[photo["key"]]
    atlas["provenance"]["annotation_links"] = {
        "source": {"file": source.name, "sha256": hashlib.sha256(raw).hexdigest()},
        "inventory_sha256": digest,
        "matched_count": sum(links[key] is not None for key in keys),
        "pool_size": len(keys),
        "method": "Exact frame-key join against the same recorded inventory",
        "meaning": "Recorded Labelbox data-row links; access may require a project login",
    }


def validate_comparison(atlas, comparison):
    """Require comparison inputs to identify this exact representation and labels."""
    atlas_sources = atlas.get("provenance", {}).get("sources", [])
    embeddings = [s for s in atlas_sources if s["file"].endswith((".npz", ".json"))]
    if not embeddings:
        raise ValueError("Atlas embedding source provenance is missing")
    comparison_sources = {}
    for source in comparison.get("sources", []):
        name, digest = source["file"], source["sha256"]
        if name in comparison_sources and comparison_sources[name] != digest:
            raise ValueError("Conflicting comparison source hashes: " + name)
        comparison_sources[name] = digest
    required = embeddings + [s for s in atlas_sources if s["file"].endswith(".csv")]
    for source in required:
        name = source["file"]
        if name not in comparison_sources:
            raise ValueError("Comparison is missing atlas input source: " + name)
        if comparison_sources[name] != source["sha256"]:
            raise ValueError("Comparison source hash mismatch: " + name)
    available = atlas.get("provenance", {}).get("labels", {}).get("available")
    if available is not None and available != comparison.get("labels_available"):
        raise ValueError("Comparison and atlas label availability differ")


def build(source, output, comparison=None, catalogue=None):
    data = json.loads(Path(source).read_text())
    if comparison:
        result = json.loads(Path(comparison).read_text())
        validate_comparison(data, result)
        data["comparison"] = result
    if catalogue is not None:
        attach_annotation_links(data, catalogue)
    template = runpy.run_path(
        str(Path(__file__).with_name("embedding_atlas_assets.py"))
    )["HTML"]
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace(
        "<", "\\u003c"
    )
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(template.replace("__ATLAS_DATA__", payload))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="build/embedding-atlas.json")
    parser.add_argument("--output", default="build/embedding-atlas.html")
    parser.add_argument("--comparison")
    parser.add_argument("--catalogue", help="Photo catalogue with source Labelbox links")
    args = parser.parse_args()
    build(args.input, args.output, args.comparison, args.catalogue)
