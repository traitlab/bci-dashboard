"""Build the catalogue-first photo explorer from a frozen local export."""

import argparse
import json
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_index import available_names
from page import scoped_photo_page


def build(source, output, scope_dir=None):
    data = json.loads(Path(source).read_text())
    if data.get("schema_version") != 1:
        raise ValueError("Explorer input requires schema_version 1")
    for field in ("photos", "taxa"):
        if not isinstance(data.get(field), list):
            raise TypeError("Explorer input requires a " + field + " list")
    for field, identity in (("photos", "key"), ("taxa", "id")):
        values = [row.get(identity) for row in data[field]]
        if any(not isinstance(value, str) or not value for value in values):
            raise ValueError("Explorer " + field + " require nonempty " + identity)
        if len(set(values)) != len(values):
            raise ValueError("Duplicate explorer " + identity)
    template = runpy.run_path(str(Path(__file__).with_name("explorer_assets.py")))["HTML"]
    site = runpy.run_path(str(Path(__file__).with_name("site_navigation.py")))
    current = "explorer.html"
    template = scoped_photo_page(
        template, scope_dir or str(Path(output).parent),
        available_names(str(Path(output).parent)) | {current})
    template = template.replace("__SITE_CSS__", site["CSS"]).replace(
        "__SITE_NAV__", site["navigation"](current)
    )
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(template.replace("__EXPLORER_DATA__", payload))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="build/explorer.json")
    parser.add_argument("--output", default="build/explorer.html")
    parser.add_argument("--scope-dir", help="Folder holding scope.csv for the byline (default: the output folder)")
    args = parser.parse_args()
    build(args.input, args.output, args.scope_dir)
