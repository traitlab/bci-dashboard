import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("build_crown_map", Path(__file__).parents[1] / "dashboard" / "build_crown_map.py")
build_crown_map = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_crown_map)


def test_the_crown_map_holds_the_taxon_tree_but_no_crowns(tmp_path):
    out = tmp_path / "crown-map.html"
    build_crown_map.build(out)
    page = out.read_text()
    assert "__" not in page.replace("__proto__", "")
    assert "Fabaceae" in page and 'aria-current="page"' in page
    for private in ("object-arbutus", "Signature", "label_name", "top1_correct"):
        assert private not in page


def test_every_family_in_the_tree_has_a_colour():
    colours = build_crown_map.tree_colours()
    tree = build_crown_map.taxon_tree()
    assert tree and all(family in colours for _, orders in tree for _, families in orders for family in families)
