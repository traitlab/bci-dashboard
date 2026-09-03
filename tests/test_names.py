"""Name reconciliation, the join every published number depends on.

A box label that does not compare equal to a GT species name is not a visible
failure: it degrades into a diagnostic saying the crop is filled by some other
species. So the cases here are the ones the box CSV actually contains, not
invented ones.

    .venv/bin/pytest tests/test_names.py
"""

import csv
import re

import pytest


@pytest.mark.parametrize("label,expected", [
    # The common shape: a 6-char code followed by a 4-char one.
    ("Hura crepitans-HURACR-HURC", "hura crepitans"),
    # '-ANAE' is 4 characters, below what normalize() alone recognises.
    ("Anacardium excelsum-ANACEX-ANAE", "anacardium excelsum"),
    ("Luehea seemannii-LUEHSE-LUE1", "luehea seemannii"),
    ("Quararibea asterolepis-QUARAS", "quararibea asterolepis"),
    ("Alseis", "alseis"),
    # The reason codes are matched on upper case: lowering first would make
    # '-cati' indistinguishable from a collection code.
    ("Macfadyena unguis-cati-MACFUN-MACU", "macfadyena unguis-cati"),
    ("", ""),
    (None, ""),
])
def test_strip_collection_codes(core, label, expected):
    assert core.strip_collection_codes(label) == expected


def test_every_label_in_the_box_csv_resolves(core, box_csv):
    """After stripping, the only hyphen left in the corpus is a real epithet.

    A leftover hyphen cannot be told from a lowered collection code by shape
    alone, so the legitimate cases are pinned by name. A new one appearing means
    either a new epithet or a code shape the stripper misses, and both are worth
    a look before the numbers ship.
    """
    with box_csv.open(newline="", encoding="utf-8") as fh:
        labels = {r["lb_label"] for r in csv.DictReader(fh)}
    hyphenated_epithets = {"macfadyena unguis-cati"}
    left = sorted(
        s for s in (core.strip_collection_codes(x) for x in labels)
        if "-" in s and s not in hyphenated_epithets
    )
    assert left == [], f"{len(left)} labels still carry a code"


@pytest.fixture(scope="module")
def frames(crop_overlap, box_csv):
    """Every frame the gate built, with the name the crop is dominated by."""
    built, _ = crop_overlap.build()
    return built


class TestCropDominantIsComparable:
    """The gate's dominant name has to be in the same vocabulary as the GT label.

    It is not enough for the stripper to be correct: crop_overlap has to call it
    instead of normalize(), because normalize() lowers the string and a lowered
    collection code cannot be stripped afterwards. That regression is silent in
    the names themselves, and it moves every gated number: `coverage_split`
    rejects a frame whose crop dominant does not equal the label, so a dominant
    that no longer compares would reject about 99% of frames instead of 10%.
    """

    def test_dominant_names_carry_no_collection_code(self, frames):
        # A code that survived lowering shows up as a trailing hyphen group of
        # letters and digits that is not a real epithet.
        suspect = sorted({
            f["dominant"] for f in frames.values()
            if f["dominant"] and re.search(r"-[a-z]*\d", f["dominant"])
        })
        assert suspect == []

    def test_dominant_names_mostly_exist_in_the_gt_vocabulary(
            self, core, frames, gt_csv):
        """A name that no GT record uses is either a real disagreement about what
        fills the crop or a broken join. Real disagreement cannot reach half."""
        with gt_csv.open(newline="", encoding="utf-8") as fh:
            gt = {
                core.normalize(r["wcvp_canonical_name"])
                for r in csv.DictReader(fh)
                if (r["wcvp_canonical_name"] or "").strip()
            }
        dom = [f["dominant"] for f in frames.values() if f["dominant"]]
        unknown = sum(1 for d in dom if d not in gt)
        assert unknown / len(dom) < 0.5, \
            f"{unknown}/{len(dom)} dominant names unknown to the GT set"


@pytest.mark.parametrize("raw,expected", [
    ("Öcotea  Leptobotra", "ocotea leptobotra"),
    ("Hura_crepitans", "hura crepitans"),
    ("Inga edulis var. grandiflora", "inga edulis"),
])
def test_normalize(core, raw, expected):
    assert core.normalize(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Ocotea leptobotra (Ruiz & Pav.) Mez", "Ocotea leptobotra"),
    ("Ocotea", None),
    ("", None),
    (None, None),
])
def test_canonical_binomial(core, raw, expected):
    assert core.canonical_binomial(raw) == expected


@pytest.mark.parametrize("name,expected", [
    ("hura crepitans", True),
    ("hura", False),
])
def test_is_species_level(core, name, expected):
    assert core.is_species_level(name) is expected
