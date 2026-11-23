"""Build the crown map page. It embeds only the taxon tree and its colours; crowns load from #data=<link>."""

import argparse
import csv
import json
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from taxon_colours import INPUT, tree_colours


def taxon_tree():
    """[[clade, [[order, [family, ...]], ...]], ...] in the clade file's order."""
    def rows(name):
        with open(INPUT / name, newline="") as handle:
            return list(csv.DictReader(handle))
    families = {}
    for row in rows("family_order.csv"):
        families.setdefault(row["order"], []).append(row["family"])
    orders = {}
    for row in rows("order_clade.csv"):
        orders.setdefault(row["clade"], []).append(row["order"])
    return [[clade, [[order, sorted(families.get(order, []))] for order in sorted(orders.get(clade, []))]]
            for clade in (row["clade"] for row in rows("clade_common.csv"))]


def build(output):
    template = runpy.run_path(str(Path(__file__).with_name("crown_map_assets.py")))["HTML"]
    site = runpy.run_path(str(Path(__file__).with_name("site_navigation.py")))
    page = (template.replace("__FAVICON__", site["FAVICON"]).replace("__SITE_CSS__", site["CSS"])
            .replace("__SITE_NAV__", site["navigation"]("crown-map.html"))
            .replace("__COLOURS__", json.dumps(tree_colours(), separators=(",", ":")))
            .replace("__TREE__", json.dumps(taxon_tree(), separators=(",", ":"))))
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs/crown-map.html")
    build(parser.parse_args().output)
