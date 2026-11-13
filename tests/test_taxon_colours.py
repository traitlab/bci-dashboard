"""Tree Colors cover every clade, stay deterministic, and shade an order apart from its clade."""

import csv
import re
import sys

from test_explorer_browser import ROOT

sys.path.insert(0, str(ROOT / "dashboard"))
from taxon_colours import tree_colours


def rows(name):
    with open(ROOT / "input" / name, newline="") as handle:
        return list(csv.DictReader(handle))


def test_every_clade_is_coloured_with_a_hex_value():
    colours = tree_colours()
    assert colours
    for row in rows("clade_common.csv"):
        assert row["clade"] in colours
    assert all(re.fullmatch(r"#[0-9a-f]{6}", value) for value in colours.values())


def test_no_other_bucket_and_output_is_deterministic():
    colours = tree_colours()
    assert not [name for name in colours if "other" in name.lower()]
    assert colours == tree_colours()


def test_an_order_differs_from_its_clade():
    colours = tree_colours()
    pairs = [(r["order"], r["clade"]) for r in rows("order_clade.csv") if r["order"] in colours and r["clade"] in colours]
    assert pairs
    assert all(colours[order] != colours[clade] for order, clade in pairs)
