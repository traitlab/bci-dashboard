"""Build the catalogue-first photo explorer from a frozen local export."""

import argparse
import json
import runpy
from pathlib import Path


def build(source, output):
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
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(template.replace("__EXPLORER_DATA__", payload))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="build/explorer.json")
    parser.add_argument("--output", default="build/explorer.html")
    args = parser.parse_args()
    build(args.input, args.output)
